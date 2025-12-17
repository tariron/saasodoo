"""
Database migration tasks for instance upgrades (shared → dedicated)
"""

import os
import asyncio
import asyncpg
import docker
import httpx
import configparser
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from celery import current_task
from app.celery_config import celery_app
from app.models.instance import InstanceStatus
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, max_retries=0)
def migrate_database_task(self, instance_id: str):
    """
    Background task to migrate database from shared to dedicated

    Args:
        instance_id: UUID of the instance to migrate
    """
    try:
        logger.info("Starting database migration",
                   instance_id=instance_id,
                   task_id=self.request.id)

        # Run async migration workflow
        result = asyncio.run(_migrate_workflow(instance_id))

        logger.info("Database migration completed", instance_id=instance_id, result=result)
        return result

    except Exception as e:
        logger.error("Database migration failed", instance_id=instance_id, error=str(e))

        # Update instance status to ERROR
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, f"Migration failed: {str(e)}"))

        # Re-raise for Celery to mark task as failed
        raise


async def _migrate_workflow(instance_id: str) -> Dict[str, Any]:
    """
    Main migration workflow: shared → dedicated database

    Steps:
    1. Stop instance
    2. Backup database
    3. Provision dedicated server
    4. Update instance record with new DB connection
    5. Restore backup to dedicated server
    6. Update Docker service environment (edit odoo.conf)
    7. Restart instance
    """
    from app.tasks.maintenance import (
        _get_instance_from_db,
        _stop_docker_service,
        _backup_instance_workflow,
        _restore_database_backup,
        _get_backup_record,
        _wait_for_odoo_startup,
        _update_instance_status
    )

    logger.info("Migration workflow started", instance_id=instance_id)

    # Get instance details
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    original_status = instance['status']
    logger.info("Instance retrieved",
               instance_name=instance['name'],
               current_db_type=instance.get('db_type', 'shared'),
               original_status=original_status)

    try:
        # Step 1: Update status to maintenance mode
        await _update_instance_status(instance_id, InstanceStatus.MAINTENANCE, "Database migration in progress")

        # Step 2: Stop instance if it's running
        if original_status in ['running', 'starting']:
            logger.info("Stopping instance for migration", instance_id=instance_id)
            await _stop_docker_service(instance)
        else:
            logger.info("Instance not running, skipping stop", instance_id=instance_id, status=original_status)

        # Step 3: Create backup
        logger.info("Creating pre-migration backup", instance_id=instance_id)
        backup_result = await _backup_instance_workflow(instance_id, "pre_migration")
        backup_id = backup_result['backup_id']
        logger.info("Pre-migration backup created", backup_id=backup_id)

        # Step 4: Provision dedicated database server
        logger.info("Provisioning dedicated database server", instance_id=instance_id)
        dedicated = await _provision_dedicated_via_api(instance_id)
        logger.info("Dedicated server provisioned",
                   db_server_id=dedicated['db_server_id'],
                   db_host=dedicated['db_host'])

        # Step 5: Update instance record with new database connection
        logger.info("Updating instance database connection", instance_id=instance_id)
        await _update_db_connection(instance_id, dedicated)

        # Step 6: Restore backup to dedicated server
        logger.info("Restoring backup to dedicated server", instance_id=instance_id, backup_id=backup_id)
        backup_info = await _get_backup_record(backup_id)
        instance = await _get_instance_from_db(instance_id)  # Reload with new db info
        await _restore_database_backup(instance, backup_info)
        logger.info("Backup restored to dedicated server", instance_id=instance_id)

        # Step 7: Update Docker service environment (edit odoo.conf)
        logger.info("Updating service configuration", instance_id=instance_id)
        await _update_service_environment(instance, dedicated)

        # Step 8: Restart instance
        logger.info("Starting instance with new database connection", instance_id=instance_id)
        container_info = await _start_docker_service_after_migration(instance)

        # Step 9: Wait for Odoo to start
        logger.info("Waiting for Odoo startup", instance_id=instance_id)
        await _wait_for_odoo_startup(container_info, timeout=300)

        # Step 10: Mark as running
        await _update_instance_status(instance_id, InstanceStatus.RUNNING, None)

        logger.info("Database migration completed successfully", instance_id=instance_id)

        return {
            "status": "success",
            "message": "Database migration completed successfully",
            "instance_id": instance_id,
            "backup_id": backup_id,
            "db_server_id": dedicated['db_server_id'],
            "db_host": dedicated['db_host'],
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error("Migration workflow failed", instance_id=instance_id, error=str(e))

        # Try to restore to original status
        try:
            await _update_instance_status(instance_id, InstanceStatus.ERROR, f"Migration failed: {str(e)}")
        except:
            pass

        raise


# Helper functions

async def _provision_dedicated_via_api(instance_id: str) -> Dict[str, Any]:
    """
    Call database-service to provision dedicated server

    Returns:
        Dict with: db_server_id, db_host, db_port, db_user, db_password
    """
    database_service_url = os.getenv('DATABASE_SERVICE_URL', 'http://database-service:8005')

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{database_service_url}/api/database/provision-dedicated",
            json={"instance_id": instance_id}
        )

        if response.status_code != 200:
            error_detail = response.text
            raise Exception(f"Failed to provision dedicated server: {response.status_code} - {error_detail}")

        data = response.json()
        logger.info("Dedicated server provisioned via API",
                   instance_id=instance_id,
                   db_server_id=data.get('db_server_id'))

        return data


async def _update_db_connection(instance_id: str, dedicated: Dict[str, Any]):
    """
    Update instance record with new database connection details
    """
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )

    try:
        await conn.execute("""
            UPDATE instances
            SET db_server_id = $1, db_host = $2, db_port = $3,
                db_user = $4, db_type = 'dedicated', updated_at = $5
            WHERE id = $6
        """,
            dedicated['db_server_id'],
            dedicated['db_host'],
            dedicated['db_port'],
            dedicated['db_user'],
            datetime.utcnow(),
            UUID(instance_id)
        )

        logger.info("Instance database connection updated",
                   instance_id=instance_id,
                   db_host=dedicated['db_host'],
                   db_type='dedicated')

    finally:
        await conn.close()


async def _update_service_environment(instance: Dict[str, Any], dedicated: Dict[str, Any]):
    """
    Update Docker service environment variables and odoo.conf

    CRITICAL: Environment variables DO NOT override odoo.conf when ODOO_SKIP_BOOTSTRAP=yes.
    Bitnami Odoo ONLY reads odoo.conf after bootstrap phase.
    We must manually edit odoo.conf AND update env vars for consistency.

    Test Results (2025-12-17):
    - Scenario 1: Env vars only → FAILED (ignored by Bitnami)
    - Scenario 2: Delete odoo.conf → FAILED (container crashes)
    - Scenario 3: Manual edit odoo.conf + env vars → SUCCESS ✓
    """
    client = docker.from_env()
    service_name = instance.get('service_name')

    if not service_name:
        # Fallback to constructing service name
        service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    # Step 1: Update odoo.conf file (REQUIRED - this is what Odoo actually uses)
    cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
    odoo_conf_path = f"{cephfs_path}/conf/odoo.conf"

    logger.info("Updating odoo.conf with new database connection",
                odoo_conf_path=odoo_conf_path,
                new_db_host=dedicated['db_host'])

    # Read existing config to preserve all settings
    config = configparser.ConfigParser()
    config.read(odoo_conf_path)

    # Ensure [options] section exists
    if 'options' not in config:
        config['options'] = {}

    # Update ONLY database connection fields
    config['options']['db_host'] = dedicated['db_host']
    config['options']['db_user'] = dedicated['db_user']
    config['options']['db_password'] = dedicated['db_password']
    # Note: db_name stays the same (we're moving the same database)

    # Write back complete config
    with open(odoo_conf_path, 'w') as f:
        config.write(f)

    logger.info("odoo.conf updated successfully")

    # Step 2: Update Docker service environment variables (for consistency & documentation)
    # These won't override odoo.conf, but keeps env vars in sync
    try:
        service = client.services.get(service_name)

        # Get current environment
        current_spec = service.attrs['Spec']
        current_env = current_spec.get('TaskTemplate', {}).get('ContainerSpec', {}).get('Env', [])

        # Filter out old database connection vars
        new_env = [e for e in current_env if not any(e.startswith(prefix) for prefix in [
            'ODOO_DATABASE_HOST=',
            'ODOO_DATABASE_USER=',
            'ODOO_DATABASE_PASSWORD='
        ])]

        # Add new database connection vars
        new_env.extend([
            f'ODOO_DATABASE_HOST={dedicated["db_host"]}',
            f'ODOO_DATABASE_USER={dedicated["db_user"]}',
            f'ODOO_DATABASE_PASSWORD={dedicated["db_password"]}'
        ])

        # Update service with new environment
        service.update(
            env=new_env,
            force_update=True  # Force restart to pick up new odoo.conf
        )

        logger.info("Service environment variables updated and restart triggered",
                   service_name=service_name)

    except docker.errors.NotFound:
        logger.warning("Service not found for environment update",
                      service_name=service_name)
        # Continue anyway - odoo.conf is updated which is what matters
    except Exception as e:
        logger.error("Failed to update service environment",
                    service_name=service_name,
                    error=str(e))
        # Don't fail the migration - odoo.conf is updated which is critical


async def _start_docker_service_after_migration(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start Docker service after migration (reuses logic from lifecycle)
    """
    from app.tasks.lifecycle import _start_docker_service

    container_info = await _start_docker_service(instance)
    logger.info("Service started after migration", instance_id=str(instance['id']))

    return container_info
