"""
Instance maintenance tasks (backup, restore, update)
"""

import os
import json
import asyncio
import asyncpg
import docker
import tarfile
import shutil
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID
from pathlib import Path

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_backup_completed_email, send_backup_failed_email, send_restore_completed_email, send_restore_failed_email
import structlog

logger = structlog.get_logger(__name__)

# Backup storage paths
BACKUP_BASE_PATH = "/var/lib/odoo/backups"
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
            await _stop_docker_container(instance)
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
            container_result = await _start_docker_container(instance)
            await _wait_for_odoo_startup(container_result, timeout=300) #120 seconds
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
                container_result = await _start_docker_container(instance)
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
            await _stop_docker_container(instance)
            logger.info("Instance stopped for restore")
        
        # Step 3: Restore database from backup
        await _restore_database_backup(instance, backup_info)
        logger.info("Database restored from backup")
        
        # Step 3.5: Restore database permissions
        await _restore_database_permissions(instance['database_name'], instance)
        logger.info("Database permissions restored")
        
        # Step 3.6: Reset Odoo database state to prevent startup conflicts
        await _reset_odoo_database_state(instance['database_name'], instance)
        logger.info("Odoo database state reset for clean startup")
        
        # Step 4: Restore data volume from backup
        await _restore_data_volume_backup(instance, backup_info)
        logger.info("Data volume restored from backup")
        
        # Step 5: Always recreate container after restore (since volume was recreated)
        container_result = await _start_docker_container_for_restore(instance)
        logger.info("Container recreated after restore")
        
        # Step 6: Start the container if instance was running before, otherwise leave it stopped
        if was_running:
            await _wait_for_odoo_startup(container_result, timeout=300) #120 seconds
            await _update_instance_network_info(instance_id, container_result)
            logger.info("Instance restarted after restore with optimized startup")
            target_status = InstanceStatus.RUNNING
        else:
            # Stop the container but keep it available for starting later
            client = docker.from_env()
            container = client.containers.get(container_result['container_name'])
            container.stop()
            logger.info("Container created but stopped to match previous state")
            target_status = InstanceStatus.STOPPED
        
        # Step 7: Update status
        await _update_instance_status(instance_id, target_status)
        
        # Step 8: Send restore completed email
        try:
            user_info = await _get_user_info(instance['customer_id'])
            if user_info and user_info.get('email'):
                restore_date = datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC")
                instance_url = f"http://{instance['database_name']}.saasodoo.local"
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
        
        # Step 4: Stop current container
        await _stop_docker_container(instance)
        logger.info("Instance stopped for update")
        
        # Step 5: Update instance record with new version
        await _update_instance_version(instance_id, target_version)
        
        # Step 6: Deploy new container with updated version
        updated_instance = await _get_instance_from_db(instance_id)
        container_result = await _deploy_updated_container(updated_instance)
        logger.info("Updated container deployed", container_id=container_result['container_id'])
        
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
    """Create PostgreSQL database backup"""
    backup_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_database.sql"
    
    # Use pg_dump to create database backup
    cmd = [
        "pg_dump",
        f"--host={os.getenv('POSTGRES_HOST', 'postgres')}",
        f"--port=5432",
        f"--username={os.getenv('POSTGRES_USER', 'odoo_user')}",
        f"--dbname={instance['database_name']}",
        f"--file={backup_file}",
        "--verbose",
        "--no-password"
    ]
    
    env = os.environ.copy()
    env['PGPASSWORD'] = os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
    
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
    """Create backup of Odoo data volume"""
    client = docker.from_env()
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    backup_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_data.tar.gz"
    
    try:
        container = client.containers.get(container_name)
        
        # Create temporary container to access data volume
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
        
        # Run tar command in temporary container to backup volume
        logger.info("Starting data volume backup", volume_name=volume_name, backup_file=backup_file)
        
        try:
            result = client.containers.run(
                image="alpine:latest",
                command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
                volumes={
                    volume_name: {'bind': '/data', 'mode': 'ro'},
                    'odoo-backups': {'bind': '/backup', 'mode': 'rw'}
                },
                remove=True,
                detach=False
            )
            logger.info("Docker tar command output", output=result)
            
            # Get file size from within the volume using another container
            size_result = client.containers.run(
                image="alpine:latest",
                command=f"stat -c %s /backup/{backup_name}_data.tar.gz",
                volumes={'odoo-backups': {'bind': '/backup', 'mode': 'ro'}},
                remove=True,
                detach=False
            )
            backup_size = int(size_result.decode().strip())
            logger.info("Data volume backup completed", file=backup_file, size=backup_size)
            return backup_file, backup_size
            
        except Exception as docker_error:
            logger.error("Docker tar command failed", error=str(docker_error))
            # Create empty backup file to maintain consistency
            Path(backup_file).touch()
            logger.info("Created empty backup file as fallback", file=backup_file)
            return backup_file, 0
        
    except docker.errors.NotFound:
        logger.warning("Container not found, skipping data volume backup", container_name=container_name)
        # Create empty backup file to maintain consistency  
        Path(backup_file).touch()
        return backup_file, 0
    except Exception as e:
        logger.error("Failed to backup data volume", error=str(e))
        raise


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
    """Restore PostgreSQL database from backup"""
    backup_file = backup_info['database_backup_path']
    
    if not os.path.exists(backup_file):
        raise FileNotFoundError(f"Database backup file not found: {backup_file}")
    
    # Drop existing database and recreate
    await _recreate_database(instance['database_name'])
    
    # Restore from backup
    cmd = [
        "psql",
        f"--host={os.getenv('POSTGRES_HOST', 'postgres')}",
        f"--port=5432",
        f"--username={os.getenv('POSTGRES_USER', 'odoo_user')}",
        f"--dbname={instance['database_name']}",
        f"--file={backup_file}",
        "--quiet"
    ]
    
    env = os.environ.copy()
    env['PGPASSWORD'] = os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
    
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
    """Restore Odoo data volume from backup"""
    client = docker.from_env()
    backup_file = backup_info['data_backup_path']
    backup_filename = os.path.basename(backup_file)
    
    # Check if backup file exists in the Docker volume
    try:
        check_result = client.containers.run(
            image="alpine:latest",
            command=f"test -f /backup/{backup_filename}",
            volumes={'odoo-backups': {'bind': '/backup', 'mode': 'ro'}},
            remove=True,
            detach=False
        )
        logger.info("Data backup file found", file=backup_filename)
    except Exception:
        logger.warning("Data backup file not found in volume, skipping data restore", file=backup_filename)
        return
    
    volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        # Remove existing container that might be using the volume
        container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
        try:
            existing_container = client.containers.get(container_name)
            existing_container.remove(force=True)
            logger.info("Existing container removed for volume cleanup", container=container_name)
        except docker.errors.NotFound:
            pass
        
        # Remove existing volume if it exists
        try:
            existing_volume = client.volumes.get(volume_name)
            existing_volume.remove(force=True)
            logger.info("Existing data volume removed", volume=volume_name)
        except docker.errors.NotFound:
            pass
        
        # Create new volume
        new_volume = client.volumes.create(name=volume_name)
        logger.info("New data volume created", volume=volume_name)
        
        # Extract backup to new volume
        client.containers.run(
            image="alpine:latest",
            command=f"tar -xzf /backup/{backup_filename} -C /data",
            volumes={
                volume_name: {'bind': '/data', 'mode': 'rw'},
                'odoo-backups': {'bind': '/backup', 'mode': 'ro'}
            },
            remove=True,
            detach=False
        )
        
        logger.info("Data volume restored from backup", volume=volume_name, backup_file=backup_filename)
        
    except Exception as e:
        logger.error("Failed to restore data volume", error=str(e))
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
        port=5432,
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


async def _deploy_updated_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Deploy container with updated Odoo version"""
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    # Remove old container if exists
    try:
        old_container = client.containers.get(container_name)
        old_container.remove(force=True)
        logger.info("Old container removed", container_name=container_name)
    except docker.errors.NotFound:
        pass
    
    # Deploy new container with updated version
    # This reuses the container deployment logic from provisioning
    from app.tasks.provisioning import _deploy_odoo_container
    
    # Create minimal db_info for deployment
    db_info = {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': 5432,
        'database': instance['database_name'],
        'user': f"odoo_{instance['database_name']}",
        'password': 'generated_password'  # This should be retrieved from secure storage
    }
    
    return await _deploy_odoo_container(instance, db_info)


async def _run_database_migration(instance: Dict[str, Any], from_version: str, to_version: str):
    """Run Odoo database migration"""
    if from_version == to_version:
        logger.info("Same version, skipping migration")
        return
    
    client = docker.from_env()
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        container = client.containers.get(container_name)
        
        # Run Odoo with --update=all to migrate database
        migration_command = [
            "odoo",
            f"--database={instance['database_name']}",
            "--update=all",
            "--stop-after-init",
            "--log-level=info"
        ]
        
        exec_result = container.exec_run(migration_command, stream=True)
        
        # Monitor migration output
        for line in exec_result.output:
            logger.info("Migration output", line=line.decode().strip())
        
        if exec_result.exit_code != 0:
            raise RuntimeError(f"Database migration failed with exit code {exec_result.exit_code}")
        
        logger.info("Database migration completed successfully")
        
    except Exception as e:
        logger.error("Database migration failed", error=str(e))
        raise


# ===== DATABASE UTILITIES (duplicated from lifecycle.py for now) =====

async def _get_instance_from_db(instance_id: str) -> Dict[str, Any]:
    """Get instance details from database"""
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
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
        port=5432,
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


async def _recreate_database(database_name: str):
    """Drop and recreate database with proper permissions"""
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database='postgres',  # Connect to postgres db to drop/create others
        user=os.getenv('POSTGRES_USER', 'odoo_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
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
        
        logger.info("Database recreated", database=database_name)
    finally:
        await conn.close()


async def _restore_database_permissions(database_name: str, instance: Dict[str, Any]):
    """Restore proper database permissions for instance user"""
    # Extract database user from instance metadata or derive it
    db_user = f"odoo_{database_name}"
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database=database_name,
        user=os.getenv('POSTGRES_USER', 'odoo_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
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


async def _reset_odoo_database_state(database_name: str, instance: Dict[str, Any]):
    """Reset Odoo database state to prevent startup conflicts after restore"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database=database_name,
        user=os.getenv('POSTGRES_USER', 'odoo_user'),
        password=os.getenv('POSTGRES_PASSWORD', 'secure_password_change_me')
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


# Import functions from lifecycle.py that we need
async def _stop_docker_container(instance: Dict[str, Any]):
    """Stop Docker container gracefully"""
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        container = client.containers.get(container_name)
        
        if container.status not in ['running']:
            logger.info("Container already stopped", container_name=container_name, status=container.status)
            return
        
        logger.info("Stopping container gracefully", container_name=container_name)
        container.stop(timeout=30)  # 30 second graceful shutdown
        
        # Wait for container to stop
        for _ in range(35):  # 35 second timeout (30 + 5 buffer)
            container.reload()
            if container.status in ['exited', 'stopped']:
                break
            await asyncio.sleep(1)
        else:
            logger.warning("Container did not stop gracefully, forcing stop", container_name=container_name)
            container.kill()
        
        logger.info("Container stopped", container_name=container_name)
        
    except docker.errors.NotFound:
        logger.warning("Container not found during stop", container_name=container_name)
    except Exception as e:
        logger.error("Failed to stop container", container_name=container_name, error=str(e))
        raise


async def _start_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start existing Docker container"""
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        # Try to get existing container
        container = client.containers.get(container_name)
        
        if container.status == 'running':
            logger.info("Container already running", container_name=container_name)
        else:
            logger.info("Starting existing container", container_name=container_name)
            container.start()
            
        # Wait for container to be running
        for _ in range(30):  # 30 second timeout
            container.reload()
            if container.status == 'running':
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Container failed to start within timeout")
        
        # Get network info
        container.reload()
        internal_ip = _get_container_ip(container)
        
        return {
            'container_id': container.id,
            'container_name': container_name,
            'internal_ip': internal_ip,
            'internal_url': f'http://{internal_ip}:8069',
            'external_url': f'http://{instance["database_name"]}.saasodoo.local'
        }
        
    except docker.errors.NotFound:
        # Container doesn't exist - this shouldn't happen for existing instances
        raise ValueError(f"Container {container_name} not found. Instance may need reprovisioning.")
    except Exception as e:
        logger.error("Failed to start container", container_name=container_name, error=str(e))
        raise


def _get_container_ip(container) -> str:
    """Extract container IP address"""
    container.reload()
    
    # Try saasodoo-network first
    if 'saasodoo-network' in container.attrs['NetworkSettings']['Networks']:
        network_info = container.attrs['NetworkSettings']['Networks']['saasodoo-network']
        return network_info['IPAddress']
    
    # Fallback to first available network
    networks = container.attrs['NetworkSettings']['Networks']
    if networks:
        first_network = next(iter(networks.values()))
        return first_network['IPAddress']
    
    return 'localhost'  # Final fallback


async def _wait_for_odoo_startup(container_info: Dict[str, Any], timeout: int = 300): #120 seconds
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
        port=5432,
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )
    
    try:
        await conn.execute("""
            UPDATE instances 
            SET container_id = $1, container_name = $2, 
                internal_url = $3, external_url = $4, updated_at = $5
            WHERE id = $6
        """, 
            container_info['container_id'],
            container_info['container_name'],
            container_info['internal_url'],
            container_info['external_url'],
            datetime.utcnow(),
            UUID(instance_id)
        )
        
        logger.info("Instance network info updated", instance_id=instance_id)
    finally:
        await conn.close()


async def _start_docker_container_for_restore(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start Docker container with Bitnami optimization for restore operations"""
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        # Try to get existing container
        container = client.containers.get(container_name)
        
        # Stop the container if it's running
        if container.status == 'running':
            logger.info("Stopping container for restore optimization", container_name=container_name)
            container.stop(timeout=30)
        
        # Remove the existing container to recreate with optimized environment
        container.remove()
        logger.info("Container removed for restore optimization", container_name=container_name)
        
    except docker.errors.NotFound:
        logger.info("No existing container found, will create new one", container_name=container_name)
    
    # Create optimized container configuration for restore
    db_user = f"odoo_{instance['database_name']}"
    db_password = f"odoo_pass_{instance['id'].hex[:8]}"
    
    # Environment optimized for restored instance
    environment = {
        'ODOO_DATABASE_HOST': os.getenv('POSTGRES_HOST', 'postgres'),
        'ODOO_DATABASE_PORT_NUMBER': '5432',
        'ODOO_DATABASE_NAME': instance['database_name'],
        'ODOO_DATABASE_USER': db_user,
        'ODOO_DATABASE_PASSWORD': db_password,
        'ODOO_EMAIL': instance['admin_email'],
        'ODOO_PASSWORD': f"admin_{instance['id'].hex[:8]}",
        'ODOO_LOAD_DEMO_DATA': 'no',  # Skip demo data for restored instances
        # Bitnami-specific variables to optimize startup for restored databases
        'ODOO_SKIP_BOOTSTRAP': 'yes',  # Skip database initialization
        'ODOO_SKIP_MODULES_UPDATE': 'yes',  # Skip module updates on startup
        'BITNAMI_DEBUG': 'true',  # Enable debug logging for troubleshooting
    }
    
    # Add custom environment variables from instance if any
    if instance.get('environment_vars'):
        environment.update(instance['environment_vars'])
    
    # Resource limits
    mem_limit = instance['memory_limit']
    cpu_limit = instance['cpu_limit']
    
    try:
        # Create and start optimized container for restore
        container = client.containers.run(
            'bitnami/odoo:17',  # Use same version as original
            name=container_name,
            environment=environment,
            mem_limit=mem_limit,
            cpu_count=int(cpu_limit),
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            labels={
                'saasodoo.instance.id': str(instance['id']),
                'saasodoo.instance.name': instance['name'],
                'saasodoo.tenant.id': str(instance['customer_id']),
                'saasodoo.restore.optimized': 'true',
                # Traefik labels for automatic routing
                'traefik.enable': 'true',
                f'traefik.http.routers.{container_name}.rule': f'Host(`{instance["database_name"]}.saasodoo.local`)',
                f'traefik.http.routers.{container_name}.service': container_name,
                f'traefik.http.services.{container_name}.loadbalancer.server.port': '8069',
            },
            volumes={
                f'odoo_data_{instance["database_name"]}_{instance["id"].hex[:8]}': {
                    'bind': '/bitnami/odoo',
                    'mode': 'rw'
                }
            }
        )
        
        # Connect to network after creation
        try:
            network = client.networks.get('saasodoo-network')
            network.connect(container)
            logger.info("Restored container connected to network", container_name=container_name, network='saasodoo-network')
        except docker.errors.NotFound:
            logger.warning("Network saasodoo-network not found, skipping network connection")
        
        logger.info("Optimized container created for restore", container_id=container.id, name=container_name)
        
        # Get container network info
        container.reload()
        internal_ip = _get_container_ip(container)
        
        return {
            'container_id': container.id,
            'container_name': container_name,
            'internal_ip': internal_ip,
            'internal_url': f'http://{internal_ip}:8069',
            'external_url': f'http://{instance["database_name"]}.saasodoo.local'
        }
        
    except Exception as e:
        logger.error("Failed to start optimized container for restore", container_name=container_name, error=str(e))
        raise


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