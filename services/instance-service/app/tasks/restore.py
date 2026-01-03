"""
Instance restore tasks
"""

import os
import json
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any, Optional

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_restore_completed_email, send_restore_failed_email
from app.utils.kubernetes import KubernetesClient
from app.tasks.helpers import (
    get_instance_from_db as _get_instance_from_db,
    update_instance_status as _update_instance_status,
    wait_for_odoo_startup as _wait_for_odoo_startup,
    update_instance_network_info as _update_instance_network_info,
    get_user_info as _get_user_info,
    get_db_server_for_instance as _get_db_server_for_instance,
)
import structlog

logger = structlog.get_logger(__name__)

# Backup storage paths (same as backup.py)
BACKUP_BASE_PATH = "/mnt/cephfs/odoo_backups"
BACKUP_ACTIVE_PATH = f"{BACKUP_BASE_PATH}/active"


@celery_app.task(bind=True)
def restore_instance_task(self, instance_id: str, backup_id: str):
    """Background task to restore instance from backup"""
    try:
        logger.info("Starting instance restore workflow", instance_id=instance_id, backup_id=backup_id, task_id=self.request.id)
        result = asyncio.run(_restore_instance_workflow(instance_id, backup_id))
        logger.info("Instance restore completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance restore failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _restore_instance_workflow(instance_id: str, backup_id: str) -> Dict[str, Any]:
    """Main restore workflow with Docker volume operations"""
    # Import K8s helpers from maintenance to avoid circular imports
    from app.tasks.maintenance import _stop_kubernetes_deployment, _start_kubernetes_deployment_for_restore

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    backup_info = await _get_backup_record(backup_id)
    if not backup_info:
        raise ValueError(f"Backup {backup_id} not found")

    logger.info("Starting restore workflow", instance_name=instance['name'], backup_name=backup_info['backup_name'])

    try:
        # Step 1: Update status to RESTORING
        await _update_instance_status(instance_id, InstanceStatus.MAINTENANCE, "Restoring from backup")

        # Step 2: Stop instance if running
        was_running = instance['status'] == InstanceStatus.RUNNING.value
        if was_running:
            await _stop_kubernetes_deployment(instance)
            logger.info("Instance stopped for restore")

        # Step 3: Restore database from backup
        await _restore_database_backup(instance, backup_info)
        logger.info("Database restored from backup")

        # Get database server info for permission and state operations
        db_server = await _get_db_server_for_instance(instance)

        # Use actual allocated database name with fallback for backward compatibility
        db_name = instance.get('db_name') or instance['database_name']

        # Step 3.5: Restore database permissions
        await _restore_database_permissions(db_name, instance, db_server)
        logger.info("Database permissions restored")

        # Step 3.6: Reset Odoo database state to prevent startup conflicts
        await _reset_odoo_database_state(db_name, instance, db_server)
        logger.info("Odoo database state reset for clean startup")

        # Step 4: Restore data volume from backup
        await _restore_data_volume_backup(instance, backup_info)
        logger.info("Data volume restored from backup")

        # Step 5: Start deployment with restore-optimized configuration
        container_result = await _start_kubernetes_deployment_for_restore(instance)
        logger.info("Deployment started after restore")

        # Step 6: Wait for Odoo to start and update network info (always start after restore)
        await _wait_for_odoo_startup(container_result, timeout=300)
        await _update_instance_network_info(instance_id, container_result)
        logger.info("Instance started after restore")
        target_status = InstanceStatus.RUNNING

        # Step 7: Update status
        await _update_instance_status(instance_id, target_status)

        # Step 8: Send restore completed email
        try:
            user_info = await _get_user_info(instance['customer_id'])
            if user_info and user_info.get('email'):
                restore_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")
                instance_url = f"http://{instance['database_name']}.{os.getenv('BASE_DOMAIN', 'saasodoo.local')}"
                await send_restore_completed_email(
                    email=user_info['email'],
                    first_name=user_info.get('first_name', 'there'),
                    instance_name=instance['name'],
                    backup_name=backup_info['backup_name'],
                    restore_date=restore_date,
                    instance_url=instance_url
                )
                logger.info("Restore completed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("Failed to send restore completed email", error=str(email_error))

        return {
            "status": "success",
            "backup_id": backup_id,
            "backup_name": backup_info['backup_name'],
            "restored_at": datetime.utcnow().isoformat(),
            "message": "Instance restored successfully"
        }

    except Exception as e:
        logger.error("Restore workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))

        # Send restore failed email
        try:
            user_info = await _get_user_info(instance['customer_id'])
            if user_info and user_info.get('email'):
                await send_restore_failed_email(
                    email=user_info['email'],
                    first_name=user_info.get('first_name', 'there'),
                    instance_name=instance['name'],
                    backup_name=backup_info['backup_name'] if backup_info else 'Unknown',
                    error_message=str(e)
                )
                logger.info("Restore failed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("Failed to send restore failed email", error=str(email_error))

        raise


async def _get_backup_record(backup_id: str) -> Optional[Dict[str, Any]]:
    """Get backup record from metadata files"""
    metadata_file = f"{BACKUP_ACTIVE_PATH}/{backup_id}_metadata.json"

    try:
        if os.path.exists(metadata_file):
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            return {
                "backup_id": backup_id,
                "backup_name": metadata.get('backup_name', backup_id),
                "database_backup_path": f"{BACKUP_ACTIVE_PATH}/{backup_id}_database.sql",
                "data_backup_path": f"{BACKUP_ACTIVE_PATH}/{backup_id}_data.tar.gz",
                "metadata": metadata
            }
    except Exception as e:
        logger.error("Failed to read backup metadata", backup_id=backup_id, error=str(e))

    return None


async def _restore_database_backup(instance: Dict[str, Any], backup_info: Dict[str, Any]):
    """Restore PostgreSQL database from backup to instance's database server"""
    backup_file = backup_info['database_backup_path']

    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"Database backup file not found: {backup_file}")

    # Get database server connection info for this instance
    db_server = await _get_db_server_for_instance(instance)

    # Use db_name (actual allocated database) with fallback to database_name for backward compatibility
    db_name = instance.get('db_name') or instance['database_name']

    # Drop existing database and recreate on correct pool
    await _recreate_database(db_name, db_server)

    # Restore from backup to correct pool
    cmd = [
        "psql",
        f"--host={db_server['host']}",
        f"--port={db_server['port']}",
        f"--username={db_server['admin_user']}",
        f"--dbname={db_name}",
        f"--file={backup_file}",
        "--quiet"
    ]

    env = os.environ.copy()
    env['PGPASSWORD'] = db_server['admin_password']

    process = await asyncio.create_subprocess_exec(
        *cmd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode() if stderr else "Database restore failed"
        raise RuntimeError(f"Database restore failed: {error_msg}")


async def _restore_data_volume_backup(instance: Dict[str, Any], backup_info: Dict[str, Any]):
    """Restore Odoo data volume from backup using Kubernetes Job"""
    backup_file = backup_info['data_backup_path']
    backup_filename = os.path.basename(backup_file)

    # Check if backup file exists
    if not os.path.exists(backup_file):
        logger.warning("Data backup file not found, skipping data restore", file=backup_file)
        return

    instance_id = instance['id'].hex
    pvc_name = f"odoo-instance-{instance_id}"

    try:
        # PVC should already exist from provisioning
        logger.info("Restoring to instance PVC", pvc_name=pvc_name)

        # Create Kubernetes client
        k8s_client = KubernetesClient()

        # Generate unique job name
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        job_name = f"restore-{instance['id'].hex[:8]}-{timestamp}".lower()

        # Create restore job with instance PVC
        success = k8s_client.create_restore_job(
            job_name=job_name,
            instance_pvc_name=pvc_name,
            backup_file=backup_filename,
            backup_base_path="/mnt/cephfs/odoo_backups"
        )

        if not success:
            raise RuntimeError("Failed to create restore job")

        # Wait for job to complete (10 minute timeout)
        job_success = k8s_client.wait_for_job_completion(job_name, timeout=600)

        if not job_success:
            raise RuntimeError("Restore job failed or timed out")

        logger.info("Data volume restored from backup",
                   pvc_name=pvc_name,
                   backup_file=backup_filename)

    except Exception as e:
        logger.error("Failed to restore data volume", error=str(e), exc_info=True)
        raise


async def _recreate_database(database_name: str, db_server: Dict[str, str]):
    """Drop and recreate database with proper permissions on specified database server"""
    conn = await asyncpg.connect(
        host=db_server['host'],
        port=int(db_server['port']),
        database='postgres',  # Connect to postgres database to drop/create
        user=db_server['admin_user'],
        password=db_server['admin_password']
    )

    try:
        # Terminate existing connections
        await conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{database_name}'
              AND pid <> pg_backend_pid()
        """)

        # Drop and recreate database
        await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await conn.execute(f'CREATE DATABASE "{database_name}"')

        logger.info("Database recreated on pool",
                   database=database_name,
                   db_server=db_server['host'])
    finally:
        await conn.close()


async def _restore_database_permissions(database_name: str, instance: Dict[str, Any], db_server: Dict[str, str]):
    """Restore proper database permissions for instance user on specified database server"""
    # Use the actual db_user from instance (allocated by database-service)
    db_user = instance.get('db_user') or f"odoo_{instance['database_name']}"

    conn = await asyncpg.connect(
        host=db_server['host'],
        port=int(db_server['port']),
        database=database_name,
        user=db_server['admin_user'],
        password=db_server['admin_password']
    )

    try:
        # Grant all privileges on database to instance user
        await conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{database_name}" TO "{db_user}"')

        # Grant all privileges on all tables in public schema
        await conn.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{db_user}"')

        # Grant all privileges on all sequences in public schema
        await conn.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{db_user}"')

        # Fix public schema ownership (critical for restored databases)
        await conn.execute(f'ALTER SCHEMA public OWNER TO "{db_user}"')

        # Grant CREATE, USAGE on public schema (essential for Odoo)
        await conn.execute(f'GRANT CREATE, USAGE ON SCHEMA public TO "{db_user}"')

        # Make user owner of the database for maximum privileges
        await conn.execute(f'ALTER DATABASE "{database_name}" OWNER TO "{db_user}"')

        # Set default privileges for future tables
        await conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{db_user}"')
        await conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{db_user}"')

        logger.info("Database permissions restored", database=database_name, user=db_user)
    finally:
        await conn.close()


async def _reset_odoo_database_state(database_name: str, instance: Dict[str, Any], db_server: Dict[str, str]):
    """Reset Odoo database state to prevent startup conflicts after restore on specified database server"""
    conn = await asyncpg.connect(
        host=db_server['host'],
        port=int(db_server['port']),
        database=database_name,
        user=db_server['admin_user'],
        password=db_server['admin_password']
    )

    try:
        # Clear module update flags that can cause startup hangs
        await conn.execute("""
            UPDATE ir_module_module
            SET state = 'installed'
            WHERE state IN ('to upgrade', 'to install', 'to remove')
        """)

        # Clear any pending module operations
        await conn.execute("""
            DELETE FROM ir_module_module_dependency
            WHERE module_id IN (
                SELECT id FROM ir_module_module WHERE state = 'uninstalled'
            )
        """)

        # Reset registry rebuild flags
        await conn.execute("""
            UPDATE ir_config_parameter
            SET value = 'false'
            WHERE key IN ('base.module_upgrade', 'web.base.url.freeze')
        """)

        # Clear any stuck cron jobs related to module updates (if structure matches)
        try:
            await conn.execute("""
                UPDATE ir_cron
                SET active = false
                WHERE ir_actions_server_id IN (
                    SELECT id FROM ir_act_server
                    WHERE model_id IN (
                        SELECT id FROM ir_model WHERE model = 'ir.module.module'
                    )
                )
            """)
        except Exception:
            try:
                await conn.execute("UPDATE ir_cron SET active = false WHERE cron_name LIKE '%module%'")
            except Exception:
                logger.debug("Cron cleanup failed, skipping")

        # Reset session information that might conflict (if table exists)
        try:
            await conn.execute("DELETE FROM ir_sessions WHERE session_id IS NOT NULL")
        except Exception:
            logger.debug("ir_sessions table not found, skipping session cleanup")

        # Clear any attachment locks (if table exists)
        try:
            await conn.execute("""
                UPDATE ir_attachment
                SET write_uid = NULL, write_date = NOW()
                WHERE res_model = 'ir.module.module'
            """)
        except Exception:
            logger.debug("ir_attachment table access failed, skipping attachment cleanup")

        # Clear any pending database updates (if parameters exist)
        try:
            await conn.execute("""
                DELETE FROM ir_config_parameter
                WHERE key LIKE 'database.%'
                AND key IN ('database.is_neutralized', 'database.uuid')
            """)
        except Exception:
            logger.debug("Database parameter cleanup failed, skipping")

        logger.info("Odoo database state reset completed", database=database_name)

    except Exception as e:
        logger.error("Failed to reset Odoo database state", database=database_name, error=str(e))
        raise
    finally:
        await conn.close()
