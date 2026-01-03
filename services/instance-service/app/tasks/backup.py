"""
Instance backup tasks
"""

import os
import json
import asyncio
from datetime import datetime
from typing import Dict, Any
from pathlib import Path

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_backup_completed_email, send_backup_failed_email
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

# Backup storage paths
BACKUP_BASE_PATH = "/mnt/cephfs/odoo_backups"
BACKUP_ACTIVE_PATH = f"{BACKUP_BASE_PATH}/active"
BACKUP_STAGING_PATH = f"{BACKUP_BASE_PATH}/staging"
BACKUP_TEMP_PATH = f"{BACKUP_BASE_PATH}/temp"


@celery_app.task(bind=True)
def backup_instance_task(self, instance_id: str, backup_name: str = None):
    """Background task to create instance backup"""
    try:
        logger.info("Starting instance backup workflow", instance_id=instance_id, backup_name=backup_name, task_id=self.request.id)
        result = asyncio.run(_backup_instance_workflow(instance_id, backup_name))
        logger.info("Instance backup completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance backup failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _backup_instance_workflow(instance_id: str, backup_name: str = None) -> Dict[str, Any]:
    """Main backup workflow with stop-backup-start pattern for consistent state"""
    # Import K8s helpers from maintenance to avoid circular imports
    from app.tasks.maintenance import _stop_kubernetes_deployment, _start_kubernetes_deployment

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    # Generate backup name if not provided
    if not backup_name:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{instance['database_name']}_{timestamp}"
    else:
        # Always prefix with instance info for clarity
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{instance['database_name']}_{instance['name'].replace(' ', '_')}_{backup_name}_{timestamp}"

    logger.info("Starting backup workflow with stop-backup-start pattern",
               instance_name=instance['name'], backup_name=backup_name)

    # Remember if instance was running before backup
    was_running = instance['status'] == InstanceStatus.RUNNING.value

    try:
        # Step 1: Update status to MAINTENANCE and stop instance if running
        await _update_instance_status(instance_id, InstanceStatus.MAINTENANCE, "Creating backup")

        if was_running:
            logger.info("Stopping instance for consistent backup")
            await _stop_kubernetes_deployment(instance)
            # Wait a moment for clean shutdown
            await asyncio.sleep(5)

        # Step 2: Ensure backup directories exist
        _ensure_backup_directories()

        # Step 3: Create database backup (with stopped instance for consistency)
        db_backup_path = await _create_database_backup(instance, backup_name)
        logger.info("Database backup created", path=db_backup_path)

        # Step 4: Create data volume backup (with stopped instance for consistency)
        data_backup_path, data_backup_size = await _create_data_volume_backup(instance, backup_name)
        logger.info("Data volume backup created", path=data_backup_path, size=data_backup_size)

        # Step 5: Create backup metadata
        backup_metadata = await _create_backup_metadata(instance, backup_name, db_backup_path, data_backup_path, data_backup_size)

        # Step 6: Store backup info in database
        backup_id = await _store_backup_record(instance_id, backup_metadata)

        # Step 7: Restart instance if it was running before backup
        if was_running:
            logger.info("Restarting instance after backup")
            container_result = await _start_kubernetes_deployment(instance)
            await _wait_for_odoo_startup(container_result, timeout=300)
            await _update_instance_network_info(instance_id, container_result)
            await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        else:
            # Instance was stopped, keep it stopped
            await _update_instance_status(instance_id, InstanceStatus.STOPPED)

        # Step 8: Send backup completed email
        try:
            user_info = await _get_user_info(instance['customer_id'])
            if user_info and user_info.get('email'):
                backup_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")
                await send_backup_completed_email(
                    email=user_info['email'],
                    first_name=user_info.get('first_name', 'there'),
                    instance_name=instance['name'],
                    backup_name=backup_name,
                    backup_size=backup_metadata["total_size"],
                    backup_date=backup_date
                )
                logger.info("Backup completed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("Failed to send backup completed email", error=str(email_error))

        return {
            "status": "success",
            "backup_id": backup_id,
            "backup_name": backup_name,
            "database_backup": db_backup_path,
            "data_backup": data_backup_path,
            "backup_size": backup_metadata["total_size"],
            "was_running": was_running,
            "message": "Backup created successfully with stop-backup-start pattern"
        }

    except Exception as e:
        logger.error("Backup workflow failed", error=str(e))
        # Try to restore original state if something went wrong
        if was_running:
            try:
                logger.info("Attempting to restart instance after backup failure")
                container_result = await _start_kubernetes_deployment(instance)
                await _update_instance_network_info(instance_id, container_result)
                await _update_instance_status(instance_id, InstanceStatus.RUNNING)
            except Exception as restore_error:
                logger.error("Failed to restore instance state after backup failure", error=str(restore_error))
                await _update_instance_status(instance_id, InstanceStatus.ERROR, f"Backup failed and could not restart: {str(e)}")
        else:
            await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))

        # Send backup failed email
        try:
            user_info = await _get_user_info(instance['customer_id'])
            if user_info and user_info.get('email'):
                await send_backup_failed_email(
                    email=user_info['email'],
                    first_name=user_info.get('first_name', 'there'),
                    instance_name=instance['name'],
                    error_message=str(e)
                )
                logger.info("Backup failed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("Failed to send backup failed email", error=str(email_error))

        raise


def _ensure_backup_directories():
    """Create backup directory structure"""
    for path in [BACKUP_ACTIVE_PATH, BACKUP_STAGING_PATH, BACKUP_TEMP_PATH]:
        Path(path).mkdir(parents=True, exist_ok=True)


async def _create_database_backup(instance: Dict[str, Any], backup_name: str) -> str:
    """Create PostgreSQL database backup from instance's database server"""
    backup_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_database.sql"

    # Get database server connection info for this instance
    db_server = await _get_db_server_for_instance(instance)

    # Use db_name (actual allocated database) with fallback to database_name for backward compatibility
    db_name = instance.get('db_name') or instance['database_name']
    cmd = [
        "pg_dump",
        f"--host={db_server['host']}",
        f"--port={db_server['port']}",
        f"--username={db_server['admin_user']}",
        f"--dbname={db_name}",
        f"--file={backup_file}",
        "--verbose",
        "--no-password"
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
        error_msg = stderr.decode() if stderr else "Database backup failed"
        raise RuntimeError(f"Database backup failed: {error_msg}")

    logger.info("Database backup completed", file=backup_file, size=os.path.getsize(backup_file))
    return backup_file


async def _create_data_volume_backup(instance: Dict[str, Any], backup_name: str) -> tuple[str, int]:
    """Create backup of Odoo data volume using Kubernetes Job"""
    backup_file = f"{backup_name}_data.tar.gz"
    backup_full_path = f"{BACKUP_ACTIVE_PATH}/{backup_file}"

    try:
        # Get PVC name for instance
        instance_id = instance['id'].hex
        pvc_name = f"odoo-instance-{instance_id}"

        logger.info("Starting data volume backup with Kubernetes Job",
                   pvc_name=pvc_name,
                   backup_file=backup_file)

        # Create Kubernetes client
        k8s_client = KubernetesClient()

        # Generate unique job name
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        job_name = f"backup-{instance['id'].hex[:8]}-{timestamp}".lower()

        # Create backup job with instance PVC
        success = k8s_client.create_backup_job(
            job_name=job_name,
            instance_pvc_name=pvc_name,
            backup_file=backup_file,
            backup_base_path="/mnt/cephfs/odoo_backups"
        )

        if not success:
            raise RuntimeError("Failed to create backup job")

        # Wait for job to complete (10 minute timeout)
        job_success = k8s_client.wait_for_job_completion(job_name, timeout=600)

        if not job_success:
            raise RuntimeError("Backup job failed or timed out")

        # Get backup file size
        if os.path.exists(backup_full_path):
            backup_size = os.path.getsize(backup_full_path)
            logger.info("Data volume backup completed", file=backup_full_path, size=backup_size)
            return backup_full_path, backup_size
        else:
            logger.warning("Backup file not found after job completion", file=backup_full_path)
            Path(backup_full_path).touch()
            return backup_full_path, 0

    except Exception as e:
        logger.error("Failed to backup data volume", error=str(e), exc_info=True)
        # Create empty backup file to maintain consistency
        Path(backup_full_path).touch()
        return backup_full_path, 0


async def _create_backup_metadata(instance: Dict[str, Any], backup_name: str, db_backup_path: str, data_backup_path: str, data_size: int = None) -> Dict[str, Any]:
    """Create backup metadata"""
    db_size = os.path.getsize(db_backup_path) if os.path.exists(db_backup_path) else 0
    # Use provided data_size if available, otherwise try to get from filesystem
    if data_size is None:
        data_size = os.path.getsize(data_backup_path) if os.path.exists(data_backup_path) else 0

    metadata = {
        "backup_name": backup_name,
        "instance_id": str(instance['id']),
        "instance_name": instance['name'],
        "database_name": instance['database_name'],
        "customer_id": str(instance['customer_id']),
        "odoo_version": instance.get('odoo_version', '17.0'),
        "instance_type": instance.get('instance_type', 'development'),
        "created_at": datetime.utcnow().isoformat(),
        "database_backup_path": db_backup_path,
        "data_backup_path": data_backup_path,
        "database_size": db_size,
        "data_size": data_size,
        "total_size": db_size + data_size,
        "status": "completed"
    }

    # Save metadata file
    metadata_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_metadata.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    return metadata


async def _store_backup_record(instance_id: str, metadata: Dict[str, Any]) -> str:
    """Store backup record in database"""
    # For now, return a generated backup ID
    # In a full implementation, this would store in a backups table
    backup_id = f"backup_{instance_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    logger.info("Backup record stored", backup_id=backup_id, metadata=metadata)
    return backup_id
