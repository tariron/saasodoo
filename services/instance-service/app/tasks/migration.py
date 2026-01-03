"""
Database migration tasks for instance upgrades (shared → dedicated)
"""

import os
import asyncio
import asyncpg
import httpx
import configparser
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

# Import shared helpers from centralized module
from app.tasks.helpers import (
    get_instance_from_db as _get_instance_from_db,
    update_instance_status as _update_instance_status,
    wait_for_odoo_startup as _wait_for_odoo_startup,
)
# Import maintenance-specific functions
from app.tasks.maintenance import (
    _stop_kubernetes_deployment,
    _start_kubernetes_deployment,
    _backup_instance_workflow,
    _restore_database_backup,
    _get_backup_record,
)
from app.utils.kubernetes import KubernetesClient

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
    6. Update Kubernetes deployment environment (edit odoo.conf)
    7. Restart instance
    """
 
    logger.info("Migration workflow started", instance_id=instance_id)

    # Get instance details
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    original_status = instance['status']
    
    # Get customer ID and set plan tier for provisioning
    customer_id = str(instance['customer_id'])
    target_plan_tier = "premium" 

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
            await _stop_kubernetes_deployment(instance)
        else:
            logger.info("Instance not running, skipping stop", instance_id=instance_id, status=original_status)

        # Step 3: Create backup
        logger.info("Creating pre-migration backup", instance_id=instance_id)
        backup_result = await _backup_instance_workflow(instance_id, "pre_migration")
        backup_id = backup_result['backup_id']
        logger.info("Pre-migration backup created", backup_id=backup_id)

        # Step 4: Provision dedicated database server
        logger.info("Provisioning dedicated database server", instance_id=instance_id)
        # Pass required arguments to fix 422 error
        dedicated = await _provision_dedicated_via_api(instance_id, customer_id, target_plan_tier)
        logger.info("Dedicated server provisioned",
                   db_server_id=dedicated['db_server_id'],
                   db_host=dedicated['db_host'])

        # Step 5: Update instance record with new database connection
        logger.info("Updating instance database connection", instance_id=instance_id)
        await _update_db_connection(instance_id, dedicated)

        # Step 6: Restore backup to dedicated server
        logger.info("Restoring backup to dedicated server", instance_id=instance_id, backup_id=backup_id)
        
        # FIX: Construct info from memory (backup_result) instead of reading from disk
        # This prevents the 'NoneType' error if the file isn't immediately visible
        backup_info = {
            'backup_id': backup_id,
            'backup_name': backup_result.get('backup_name'),
            'database_backup_path': backup_result.get('database_backup'),
            'data_backup_path': backup_result.get('data_backup')
        }

        # Reload instance to get the NEW db_host/db_type we just updated in Step 5
        instance = await _get_instance_from_db(instance_id)

        # Step 6a: Create PostgreSQL user on dedicated server with existing credentials
        # Get db_server info to access admin credentials
        from app.tasks.maintenance import _get_db_server_for_instance
        db_server = await _get_db_server_for_instance(instance)

        logger.info("Creating database user on dedicated server", instance_id=instance_id)
        await _create_db_user_on_dedicated_server(instance, db_server)

        await _restore_database_backup(instance, backup_info)

        # Step 7: Update Kubernetes deployment environment (edit odoo.conf)
        logger.info("Updating deployment configuration", instance_id=instance_id)
        await _update_service_environment(instance, dedicated)

        # Step 8: Restart instance
        logger.info("Starting instance with new database connection", instance_id=instance_id)
        container_info = await _start_kubernetes_deployment_after_migration(instance)

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

# TODO: Move this to database-service as a proper endpoint
# This function should be replaced with a database-service endpoint like:
# POST /api/database/create-user
# Request: { "db_server_id": "...", "db_user": "...", "db_password": "..." }
# This is a temporary workaround - proper architecture is to have database-service
# handle all PostgreSQL user management, not instance-service doing it directly.
async def _create_db_user_on_dedicated_server(instance: Dict[str, Any], db_server: Dict[str, Any]):
    """
    Create PostgreSQL user on dedicated server from existing credentials

    TEMPORARY: This should be moved to database-service.
    When we provision a dedicated server, database-service should also create
    the database user using credentials provided in the request.
    """
    # Read existing credentials from odoo.conf in PVC using Kubernetes Job
    from app.utils.kubernetes import KubernetesClient

    pvc_name = f"odoo-instance-{instance['id'].hex}"
    k8s_client = KubernetesClient()

    logger.info("Reading odoo.conf from PVC", pvc_name=pvc_name)
    odoo_conf_content = k8s_client.read_file_from_pvc(
        pvc_name=pvc_name,
        file_path="/conf/odoo.conf"
    )

    if not odoo_conf_content:
        raise Exception(f"Failed to read odoo.conf from PVC {pvc_name}")

    config = configparser.ConfigParser()
    config.read_string(odoo_conf_content)

    db_user = config['options']['db_user']
    db_password = config['options']['db_password']

    logger.info("Creating PostgreSQL user on dedicated server",
                db_user=db_user,
                db_host=db_server['host'])

    # Connect using admin credentials from db_server record
    conn = await asyncpg.connect(
        host=db_server['host'],
        port=int(db_server['port']),
        database='postgres',
        user=db_server['admin_user'],
        password=db_server['admin_password']
    )

    try:
        await conn.execute(f"CREATE USER {db_user} WITH PASSWORD '{db_password}'")
        logger.info("PostgreSQL user created successfully",
                   db_user=db_user,
                   db_host=db_server['host'])
    except asyncpg.exceptions.DuplicateObjectError:
        logger.info("PostgreSQL user already exists (skipping)",
                   db_user=db_user)
    finally:
        await conn.close()


async def _provision_dedicated_via_api(instance_id: str, customer_id: str, plan_tier: str) -> Dict[str, Any]:
    """
    Call database-service to provision dedicated server
    """
    database_service_url = os.getenv('DATABASE_SERVICE_URL', 'http://database-service:8005')

    # Construct the correct payload required by database-service
    payload = {
        "instance_id": instance_id,
        "customer_id": customer_id,
        "plan_tier": plan_tier
    }

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(
            f"{database_service_url}/api/database/provision-dedicated",
            json=payload
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
            SET db_server_id = $1, db_host = $2,
                db_type = 'dedicated', updated_at = $3
            WHERE id = $4
        """,
            dedicated['db_server_id'],
            dedicated['db_host'],
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
    Update Kubernetes deployment environment variables and odoo.conf

    CRITICAL: Environment variables DO NOT override odoo.conf when ODOO_SKIP_BOOTSTRAP=yes.
    Bitnami Odoo ONLY reads odoo.conf after bootstrap phase.
    We must manually edit odoo.conf AND update env vars for consistency.

    Test Results (2025-12-17):
    - Scenario 1: Env vars only → FAILED (ignored by Bitnami)
    - Scenario 2: Delete odoo.conf → FAILED (container crashes)
    - Scenario 3: Manual edit odoo.conf + env vars → SUCCESS ✓
    """
    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    # Step 1: Update odoo.conf file in PVC using Kubernetes Job
    # (REQUIRED - this is what Odoo actually uses)
    from app.utils.kubernetes import KubernetesClient
    from io import StringIO

    pvc_name = f"odoo-instance-{instance['id'].hex}"
    k8s_client = KubernetesClient()

    logger.info("Reading odoo.conf from PVC to update database connection",
                pvc_name=pvc_name,
                new_db_host=dedicated['db_host'])

    # Read existing config to preserve all settings
    odoo_conf_content = k8s_client.read_file_from_pvc(
        pvc_name=pvc_name,
        file_path="/conf/odoo.conf"
    )

    if not odoo_conf_content:
        raise Exception(f"Failed to read odoo.conf from PVC {pvc_name}")

    config = configparser.ConfigParser()
    config.read_string(odoo_conf_content)

    # Ensure [options] section exists
    if 'options' not in config:
        config['options'] = {}

    # Update ONLY the database host (credentials remain the same)
    config['options']['db_host'] = dedicated['db_host']
    # Note: db_user, db_password, and db_name all stay the same (we're just moving the database)

    # Write back complete config to PVC
    output = StringIO()
    config.write(output)
    new_conf_content = output.getvalue()

    success = k8s_client.write_file_to_pvc(
        pvc_name=pvc_name,
        file_path="/conf/odoo.conf",
        content=new_conf_content
    )

    if not success:
        raise Exception(f"Failed to write updated odoo.conf to PVC {pvc_name}")

    logger.info("odoo.conf updated successfully in PVC", pvc_name=pvc_name)

    # Step 2: Update Kubernetes deployment environment variables (for consistency & documentation)
    # These won't override odoo.conf, but keeps env vars in sync
    try:
        k8s_client = KubernetesClient()

        # Update deployment environment with new database host
        new_env = {
            'ODOO_DATABASE_HOST': dedicated['db_host']
        }

        success = k8s_client.update_deployment_env(deployment_name, new_env)

        if success:
            logger.info("Deployment environment variables updated",
                       deployment_name=deployment_name,
                       new_db_host=dedicated['db_host'])
        else:
            logger.warning("Failed to update deployment environment",
                          deployment_name=deployment_name)
            # Continue anyway - odoo.conf is updated which is what matters

    except Exception as e:
        logger.error("Failed to update deployment environment",
                    deployment_name=deployment_name,
                    error=str(e))
        # Don't fail the migration - odoo.conf is updated which is critical


async def _start_kubernetes_deployment_after_migration(instance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start Kubernetes deployment after migration (reuses logic from maintenance)
    """
    deployment_info = await _start_kubernetes_deployment(instance)
    logger.info("Deployment started after migration", instance_id=str(instance['id']))

    return deployment_info
