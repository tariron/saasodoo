"""
Instance maintenance tasks (backup, restore, update)
"""

import os
import json
import asyncio
import asyncpg
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pathlib import Path

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_backup_completed_email, send_backup_failed_email, send_restore_completed_email, send_restore_failed_email
from app.utils.k8s_client import KubernetesClient
import structlog

logger = structlog.get_logger(__name__)

# Backup storage paths
# Using direct CephFS mount for Docker Desktop WSL compatibility
# In production with native Docker, this can be changed back to /var/lib/odoo/backups
BACKUP_BASE_PATH = "/mnt/cephfs/odoo_backups"
BACKUP_ACTIVE_PATH = f"{BACKUP_BASE_PATH}/active"
BACKUP_STAGING_PATH = f"{BACKUP_BASE_PATH}/staging"


def _parse_size_to_bytes(size_str: str) -> int:
    """
    Convert size string like '10G' or '512M' to bytes

    Args:
        size_str: Size string with unit (e.g., '10G', '512M')

    Returns:
        Size in bytes
    """
    size_str = size_str.upper().strip()

    # Extract numeric value and unit
    value = int(size_str[:-1])
    unit = size_str[-1]

    # Define multipliers
    multipliers = {
        'M': 1024 ** 2,  # Megabytes
        'G': 1024 ** 3,  # Gigabytes
        'T': 1024 ** 4   # Terabytes
    }

    return value * multipliers.get(unit, 1)
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


@celery_app.task(bind=True)
def update_instance_task(self, instance_id: str, target_version: str):
    """Background task to update instance Odoo version"""
    try:
        logger.info("Starting instance update workflow", instance_id=instance_id, target_version=target_version, task_id=self.request.id)
        result = asyncio.run(_update_instance_workflow(instance_id, target_version))
        logger.info("Instance update completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance update failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _backup_instance_workflow(instance_id: str, backup_name: str = None) -> Dict[str, Any]:
    """Main backup workflow with stop-backup-start pattern for consistent state"""
    
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
                logger.info("✅ Backup completed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("❌ Failed to send backup completed email", error=str(email_error))
        
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
                logger.info("✅ Backup failed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("❌ Failed to send backup failed email", error=str(email_error))
        
        raise


async def _restore_instance_workflow(instance_id: str, backup_id: str) -> Dict[str, Any]:
    """Main restore workflow with Docker volume operations"""
    
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
                logger.info("✅ Restore completed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("❌ Failed to send restore completed email", error=str(email_error))
        
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
                logger.info("✅ Restore failed email sent", email=user_info['email'])
        except Exception as email_error:
            logger.error("❌ Failed to send restore failed email", error=str(email_error))
        
        raise


async def _update_instance_workflow(instance_id: str, target_version: str) -> Dict[str, Any]:
    """Main update workflow with Odoo version upgrade"""
    
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    current_version = instance.get('odoo_version', '17.0')
    
    logger.info("Starting update workflow", 
               instance_name=instance['name'], 
               current_version=current_version, 
               target_version=target_version)
    
    try:
        # Step 1: Validate version upgrade path
        if not _is_valid_version_upgrade(current_version, target_version):
            raise ValueError(f"Invalid upgrade path from {current_version} to {target_version}")
        
        # Step 2: Create automatic backup before update
        backup_name = f"pre_update_{current_version}_to_{target_version}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        backup_result = await _backup_instance_workflow(instance_id, backup_name)
        logger.info("Pre-update backup created", backup_id=backup_result['backup_id'])
        
        # Step 3: Update status to UPDATING
        await _update_instance_status(instance_id, InstanceStatus.MAINTENANCE, f"Updating to {target_version}")
        
        # Step 4: Stop current deployment
        await _stop_kubernetes_deployment(instance)
        logger.info("Instance stopped for update")
        
        # Step 5: Update instance record with new version
        await _update_instance_version(instance_id, target_version)
        
        # Step 6: Deploy new service with updated version
        updated_instance = await _get_instance_from_db(instance_id)
        container_result = await _deploy_updated_service(updated_instance)
        logger.info("Updated service deployed", service_id=container_result.get('service_id'))
        
        # Step 7: Run database migration if needed
        await _run_database_migration(updated_instance, current_version, target_version)
        logger.info("Database migration completed")
        
        # Step 8: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=180)  # Longer timeout for updates
        
        # Step 9: Update network info and mark as running
        await _update_instance_network_info(instance_id, container_result)
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "previous_version": current_version,
            "current_version": target_version,
            "backup_id": backup_result['backup_id'],
            "container_id": container_result['container_id'],
            "message": f"Instance updated from {current_version} to {target_version}"
        }
        
    except Exception as e:
        logger.error("Update workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


# ===== BACKUP OPERATIONS =====

def _ensure_backup_directories():
    """Create backup directory structure"""
    for path in [BACKUP_ACTIVE_PATH, BACKUP_STAGING_PATH, BACKUP_TEMP_PATH]:
        Path(path).mkdir(parents=True, exist_ok=True)


async def _create_database_backup(instance: Dict[str, Any], backup_name: str) -> str:
    """Create PostgreSQL database backup from instance's database server"""
    backup_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_database.sql"

    # Get database server connection info for this instance
    db_server = await _get_db_server_for_instance(instance)

    # Use pg_dump to create database backup from correct pool
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
        # Get CephFS path for instance data
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
        cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

        # Check if CephFS path exists
        if not os.path.exists(cephfs_path):
            logger.warning("CephFS path not found, skipping data volume backup", path=cephfs_path)
            Path(backup_full_path).touch()
            return backup_full_path, 0

        logger.info("Starting data volume backup with Kubernetes Job",
                   volume_name=volume_name,
                   cephfs_path=cephfs_path,
                   backup_file=backup_file)

        # Create Kubernetes client
        k8s_client = KubernetesClient()

        # Generate unique job name
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        job_name = f"backup-{instance['id'].hex[:8]}-{timestamp}".lower()

        # Create backup job
        success = k8s_client.create_backup_job(
            job_name=job_name,
            source_path=cephfs_path,
            backup_file=backup_file,
            backup_base_path=BACKUP_BASE_PATH
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


# ===== RESTORE OPERATIONS =====

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

    volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
    cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

    try:
        # Get storage limit from instance for CephFS quota
        storage_limit = instance.get('storage_limit', '10G')

        # Import helper function from provisioning
        from app.tasks.provisioning import _create_cephfs_directory_with_quota

        # Create CephFS directory with quota for restore (or clear existing)
        _create_cephfs_directory_with_quota(cephfs_path, storage_limit)
        logger.info("Created CephFS directory with quota for restore",
                   path=cephfs_path,
                   storage_limit=storage_limit)

        # Create Kubernetes client
        k8s_client = KubernetesClient()

        # Generate unique job name
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        job_name = f"restore-{instance['id'].hex[:8]}-{timestamp}".lower()

        # Create restore job
        success = k8s_client.create_restore_job(
            job_name=job_name,
            backup_file=backup_filename,
            dest_path=cephfs_path,
            backup_base_path=BACKUP_BASE_PATH
        )

        if not success:
            raise RuntimeError("Failed to create restore job")

        # Wait for job to complete (10 minute timeout)
        job_success = k8s_client.wait_for_job_completion(job_name, timeout=600)

        if not job_success:
            raise RuntimeError("Restore job failed or timed out")

        logger.info("Data volume restored from backup",
                   volume=volume_name,
                   backup_file=backup_filename)

    except Exception as e:
        logger.error("Failed to restore data volume", error=str(e), exc_info=True)
        raise


# ===== UPDATE OPERATIONS =====

def _is_valid_version_upgrade(current: str, target: str) -> bool:
    """Validate if version upgrade path is supported"""
    # Simple version validation - can be enhanced later
    supported_versions = ['16.0', '17.0', '18.0']
    
    if target not in supported_versions:
        return False
    
    # Allow same version (for reinstall/repair)
    if current == target:
        return True
    
    # Allow upgrade to newer versions
    current_major = float(current)
    target_major = float(target)
    
    return target_major >= current_major


async def _update_instance_version(instance_id: str, target_version: str):
    """Update instance version in database"""
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
            SET odoo_version = $1, updated_at = $2
            WHERE id = $3
        """, target_version, datetime.utcnow(), UUID(instance_id))
        
        logger.info("Instance version updated", instance_id=instance_id, version=target_version)
    finally:
        await conn.close()


async def _deploy_updated_service(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Deploy service with updated Odoo version"""
    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
    odoo_version = instance.get('odoo_version', '17.0')
    new_image = f"bitnamilegacy/odoo:{odoo_version}"

    try:
        k8s_client = KubernetesClient()

        logger.info("Updating deployment image", deployment_name=deployment_name, image=new_image)

        # Update deployment with new image
        success = k8s_client.update_deployment_image(deployment_name, new_image)

        if not success:
            raise RuntimeError(f"Failed to update deployment image to {new_image}")

        # Scale to 1 replica (in case it was scaled down)
        success = k8s_client.scale_deployment(deployment_name, replicas=1)

        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name} to 1")

        # Wait for deployment to be ready with new image
        ready = k8s_client.wait_for_deployment_ready(deployment_name, timeout=180)

        if not ready:
            raise RuntimeError("Deployment failed to become ready after update")

        # Get pod status
        pod_status = k8s_client.get_pod_status(deployment_name)

        # Service DNS
        service_name = f"{deployment_name}-service"
        service_dns = f"{service_name}.{k8s_client.namespace}.svc.cluster.local"

        logger.info("Deployment updated successfully", deployment_name=deployment_name, image=new_image)

        return {
            'service_id': deployment_name,
            'service_name': service_name,
            'container_id': pod_status.get('name') if pod_status else None,
            'internal_url': f'http://{service_dns}:8069',
            'external_url': f'http://{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}'
        }

    except Exception as e:
        logger.error("Failed to deploy updated service", deployment_name=deployment_name, error=str(e))
        raise


async def _run_database_migration(instance: Dict[str, Any], from_version: str, to_version: str):
    """Run Odoo database migration using Kubernetes exec"""
    if from_version == to_version:
        logger.info("Same version, skipping migration")
        return

    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        k8s_client = KubernetesClient()

        # Get pod name for deployment
        pod_name = k8s_client.get_pod_name_for_deployment(deployment_name)

        if not pod_name:
            raise RuntimeError(f"No running pod found for deployment {deployment_name}")

        logger.info("Running database migration", pod=pod_name, from_version=from_version, to_version=to_version)

        # Run Odoo with --update=all to migrate database
        migration_command = [
            "odoo",
            f"--database={instance['database_name']}",
            "--update=all",
            "--stop-after-init",
            "--log-level=info"
        ]

        success, output = k8s_client.exec_in_pod(pod_name, migration_command)

        if not success:
            raise RuntimeError(f"Database migration failed: {output}")

        logger.info("Database migration completed successfully", output=output)

    except Exception as e:
        logger.error("Database migration failed", error=str(e), exc_info=True)
        raise


# ===== DATABASE UTILITIES (duplicated from lifecycle.py for now) =====

async def _get_db_server_for_instance(instance: Dict[str, Any]) -> Dict[str, str]:
    """Get database server connection info for instance

    Args:
        instance: Instance dictionary with db_server_id and/or db_host

    Returns:
        Dict with host, port, admin_user, admin_password
    """
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )

    try:
        # Prefer db_server_id if available
        if instance.get('db_server_id'):
            row = await conn.fetchrow("""
                SELECT host, port, admin_user, admin_password
                FROM db_servers
                WHERE id = $1
            """, instance['db_server_id'])

            if row:
                logger.info("Retrieved database server info by db_server_id",
                           instance_id=str(instance['id']),
                           db_server=row['host'])

                return {
                    'host': row['host'],
                    'port': str(row['port']),
                    'admin_user': row['admin_user'],
                    'admin_password': row['admin_password']
                }

        # Fallback: Query by db_host (for old instances without db_server_id)
        if instance.get('db_host'):
            logger.info("Querying database server by db_host (fallback for old instance)",
                       instance_id=str(instance['id']),
                       db_host=instance['db_host'])

            row = await conn.fetchrow("""
                SELECT host, port, admin_user, admin_password
                FROM db_servers
                WHERE host = $1
            """, instance['db_host'])

            if row:
                logger.info("Retrieved database server info by db_host",
                           instance_id=str(instance['id']),
                           db_server=row['host'])

                return {
                    'host': row['host'],
                    'port': str(row['port']),
                    'admin_user': row['admin_user'],
                    'admin_password': row['admin_password']
                }

        # Last resort: Use environment variables (legacy fallback)
        logger.warning("Using legacy environment variables for database connection",
                      instance_id=str(instance['id']),
                      reason="No db_server_id or db_host found in db_servers")

        return {
            'host': os.getenv('ODOO_POSTGRES_HOST', 'postgres'),
            'port': os.getenv('ODOO_POSTGRES_PORT', '5432'),
            'admin_user': os.getenv('ODOO_POSTGRES_ADMIN_USER', 'odoo_admin'),
            'admin_password': os.getenv('ODOO_POSTGRES_ADMIN_PASSWORD', 'changeme')
        }

    finally:
        await conn.close()


async def _get_instance_from_db(instance_id: str) -> Dict[str, Any]:
    """Get instance details from database"""
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )
    
    try:
        row = await conn.fetchrow("SELECT * FROM instances WHERE id = $1", UUID(instance_id))
        if row:
            instance_data = dict(row)
            
            # Deserialize JSON fields
            if instance_data.get('custom_addons'):
                instance_data['custom_addons'] = json.loads(instance_data['custom_addons'])
            else:
                instance_data['custom_addons'] = []
                
            if instance_data.get('disabled_modules'):
                instance_data['disabled_modules'] = json.loads(instance_data['disabled_modules'])
            else:
                instance_data['disabled_modules'] = []
                
            if instance_data.get('environment_vars'):
                instance_data['environment_vars'] = json.loads(instance_data['environment_vars'])
            else:
                instance_data['environment_vars'] = {}
                
            if instance_data.get('metadata'):
                instance_data['metadata'] = json.loads(instance_data['metadata'])
            else:
                instance_data['metadata'] = {}
            
            return instance_data
        return None
    finally:
        await conn.close()


async def _update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    """Update instance status in database"""
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
            SET status = $1, error_message = $2, updated_at = $3
            WHERE id = $4
        """, status.value, error_message, datetime.utcnow(), UUID(instance_id))
        
        logger.info("Instance status updated", instance_id=instance_id, status=status.value)
    finally:
        await conn.close()


async def _store_backup_record(instance_id: str, metadata: Dict[str, Any]) -> str:
    """Store backup record in database"""
    # For now, return a generated backup ID
    # In a full implementation, this would store in a backups table
    backup_id = f"backup_{instance_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    logger.info("Backup record stored", backup_id=backup_id, metadata=metadata)
    return backup_id


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
            # Try modern Odoo structure first
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
            # Fallback: just disable all cron jobs temporarily to prevent conflicts
            try:
                await conn.execute("UPDATE ir_cron SET active = false WHERE cron_name LIKE '%module%'")
            except Exception:
                logger.debug("Cron cleanup failed, skipping")
        
        # Reset session information that might conflict (if table exists)
        try:
            await conn.execute("DELETE FROM ir_sessions WHERE session_id IS NOT NULL")
        except Exception:
            # Table might not exist in all Odoo versions
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


# Kubernetes-based maintenance helper functions
async def _stop_kubernetes_deployment(instance: Dict[str, Any]):
    """Stop Kubernetes deployment gracefully (scale to 0)"""
    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        logger.info("Stopping deployment (scaling to 0)", deployment_name=deployment_name)

        k8s_client = KubernetesClient()

        # Scale to 0 replicas
        success = k8s_client.scale_deployment(deployment_name, replicas=0)

        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name} to 0")

        # Wait for pods to terminate (60 second timeout)
        for _ in range(30):
            await asyncio.sleep(2)
            pod_status = k8s_client.get_pod_status(deployment_name)

            if not pod_status:
                logger.info("Deployment stopped successfully", deployment_name=deployment_name)
                return

        logger.warning("Deployment did not stop within timeout", deployment_name=deployment_name)

    except Exception as e:
        logger.error("Failed to stop deployment", deployment_name=deployment_name, error=str(e))
        raise


async def _start_kubernetes_deployment(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start existing Kubernetes deployment (scale to 1)"""
    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        logger.info("Starting deployment (scaling to 1)", deployment_name=deployment_name)

        k8s_client = KubernetesClient()

        # Scale to 1 replica
        success = k8s_client.scale_deployment(deployment_name, replicas=1)

        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name} to 1")

        # Wait for deployment to be ready
        ready = k8s_client.wait_for_deployment_ready(deployment_name, timeout=120)

        if not ready:
            raise RuntimeError("Deployment failed to become ready within timeout")

        # Get pod status for network info
        pod_status = k8s_client.get_pod_status(deployment_name)

        if not pod_status:
            logger.warning("Could not get pod status, using service DNS")
            pod_ip = None
        else:
            pod_ip = pod_status.get('pod_ip')

        # Service DNS (this is what we use for health checks)
        service_name = f"{deployment_name}-service"
        service_dns = f"{service_name}.{k8s_client.namespace}.svc.cluster.local"

        logger.info("Deployment started successfully", deployment_name=deployment_name)

        return {
            'service_id': deployment_name,  # Using deployment name as service_id
            'service_name': service_name,
            'pod_ip': pod_ip,
            'internal_url': f'http://{service_dns}:8069',
            'external_url': f'http://{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}'
        }

    except Exception as e:
        logger.error("Failed to start deployment", deployment_name=deployment_name, error=str(e))
        raise


async def _start_kubernetes_deployment_for_restore(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start Kubernetes deployment with restore-optimized environment variables"""
    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        logger.info("Starting deployment with restore optimization", deployment_name=deployment_name)

        k8s_client = KubernetesClient()

        # Environment optimized for restored instance
        restore_env = {
            'ODOO_SKIP_BOOTSTRAP': 'yes',  # Skip database initialization
            'ODOO_SKIP_MODULES_UPDATE': 'yes',  # Skip module updates on startup
            'BITNAMI_DEBUG': 'true',  # Enable debug logging
        }

        # Update deployment environment variables
        success = k8s_client.update_deployment_env(deployment_name, restore_env)

        if not success:
            logger.warning("Failed to update environment variables, continuing anyway")

        # Scale to 1 replica
        success = k8s_client.scale_deployment(deployment_name, replicas=1)

        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name} to 1")

        # Wait for deployment to be ready
        ready = k8s_client.wait_for_deployment_ready(deployment_name, timeout=180)

        if not ready:
            raise RuntimeError("Deployment failed to become ready within timeout")

        # Get pod status for network info
        pod_status = k8s_client.get_pod_status(deployment_name)

        if not pod_status:
            logger.warning("Could not get pod status, using service DNS")
            pod_ip = None
        else:
            pod_ip = pod_status.get('pod_ip')

        # Service DNS
        service_name = f"{deployment_name}-service"
        service_dns = f"{service_name}.{k8s_client.namespace}.svc.cluster.local"

        logger.info("Deployment started successfully after restore", deployment_name=deployment_name)

        return {
            'service_id': deployment_name,
            'service_name': service_name,
            'pod_ip': pod_ip,
            'internal_url': f'http://{service_dns}:8069',
            'external_url': f'http://{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}'
        }

    except Exception as e:
        logger.error("Failed to start deployment for restore", deployment_name=deployment_name, error=str(e))
        raise


async def _wait_for_odoo_startup(container_info: Dict[str, Any], timeout: int = 300):
    """Wait for Odoo to start up and be accessible"""
    import httpx
    
    url = container_info['internal_url']
    start_time = datetime.utcnow()
    
    logger.info("Waiting for Odoo startup", url=url, timeout=timeout)
    
    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(url, timeout=10)
                if response.status_code in [200, 303, 302]:  # Odoo redirects are normal
                    logger.info("Odoo is accessible")
                    return True
            except Exception:
                pass  # Continue waiting
            
            await asyncio.sleep(10)  # Check every 10 seconds
    
    raise TimeoutError(f"Odoo did not start within {timeout} seconds")


async def _update_instance_network_info(instance_id: str, container_info: Dict[str, Any]):
    """Update instance with network and container information"""
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
            SET service_id = $1, service_name = $2,
                internal_url = $3, external_url = $4, updated_at = $5
            WHERE id = $6
        """,
            container_info.get('service_id'),
            container_info.get('service_name'),
            container_info['internal_url'],
            container_info['external_url'],
            datetime.utcnow(),
            UUID(instance_id)
        )
        
        logger.info("Instance network info updated", instance_id=instance_id)
    finally:
        await conn.close()


async def _get_user_info(customer_id: str) -> Dict[str, Any]:
    """Get user information from user-service for email notifications"""
    try:
        # Use the user-service API to get customer details
        user_service_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{user_service_url}/users/internal/{customer_id}")
            
            if response.status_code == 200:
                user_data = response.json()
                return {
                    'email': user_data.get('email', ''),
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', '')
                }
            else:
                logger.warning("Failed to get user info from user-service", 
                              customer_id=customer_id, status_code=response.status_code)
                return None
                
    except Exception as e:
        logger.error("Error getting user info", customer_id=customer_id, error=str(e))
        return None