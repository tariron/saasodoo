"""
Instance lifecycle management tasks (start, stop, restart)
"""

import os
import asyncio
import asyncpg
import docker
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True)
def start_instance_task(self, instance_id: str):
    """Background task to start instance"""
    try:
        logger.info("Starting instance start workflow", instance_id=instance_id, task_id=self.request.id)
        result = asyncio.run(_start_instance_workflow(instance_id))
        logger.info("Instance start completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance start failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


@celery_app.task(bind=True)
def stop_instance_task(self, instance_id: str):
    """Background task to stop instance"""
    try:
        logger.info("Starting instance stop workflow", instance_id=instance_id, task_id=self.request.id)
        result = asyncio.run(_stop_instance_workflow(instance_id))
        logger.info("Instance stop completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance stop failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


@celery_app.task(bind=True)
def restart_instance_task(self, instance_id: str):
    """Background task to restart instance"""
    try:
        logger.info("Starting instance restart workflow", instance_id=instance_id, task_id=self.request.id)
        result = asyncio.run(_restart_instance_workflow(instance_id))
        logger.info("Instance restart completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance restart failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _start_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main start workflow with Docker operations"""
    
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    logger.info("Starting start workflow", instance_name=instance['name'])
    
    try:
        # Step 1: Update status to STARTING
        await _update_instance_status(instance_id, InstanceStatus.STARTING)
        
        # Step 2: Start Docker container
        container_result = await _start_docker_container(instance)
        logger.info("Container started", container_id=container_result['container_id'])
        
        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=120)
        logger.info("Odoo startup confirmed after start")
        
        # Step 4: Update instance with current network info
        await _update_instance_network_info(instance_id, container_result)
        
        # Step 5: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "container_id": container_result['container_id'],
            "external_url": container_result['external_url'],
            "message": "Instance started successfully"
        }
        
    except Exception as e:
        logger.error("Start workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _stop_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main stop workflow with Docker operations"""
    
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    logger.info("Starting stop workflow", instance_name=instance['name'])
    
    try:
        # Step 1: Update status to STOPPING
        await _update_instance_status(instance_id, InstanceStatus.STOPPING)
        
        # Step 2: Stop Docker container gracefully
        await _stop_docker_container(instance)
        logger.info("Container stopped successfully")
        
        # Step 3: Mark as STOPPED
        await _update_instance_status(instance_id, InstanceStatus.STOPPED)
        
        return {
            "status": "success",
            "message": "Instance stopped successfully"
        }
        
    except Exception as e:
        logger.error("Stop workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _restart_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main restart workflow with Docker operations"""
    
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    logger.info("Starting restart workflow", instance_name=instance['name'])
    
    try:
        # Step 1: Update status to RESTARTING
        await _update_instance_status(instance_id, InstanceStatus.RESTARTING)
        
        # Step 2: Restart Docker container
        container_result = await _restart_docker_container(instance)
        logger.info("Container restarted", container_id=container_result['container_id'])
        
        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=120)
        logger.info("Odoo startup confirmed after restart")
        
        # Step 4: Update instance with current network info
        await _update_instance_network_info(instance_id, container_result)
        
        # Step 5: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "container_id": container_result['container_id'],
            "external_url": container_result['external_url'],
            "message": "Instance restarted successfully"
        }
        
    except Exception as e:
        logger.error("Restart workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _restart_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Restart Docker container"""
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    try:
        container = client.containers.get(container_name)
        
        logger.info("Restarting container", container_name=container_name)
        container.restart(timeout=30)
        
        # Wait for container to be running after restart
        for _ in range(35):
            container.reload()
            if container.status == 'running':
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("Container failed to restart within timeout")
        
        # Get updated network info
        internal_ip = _get_container_ip(container)
        
        return {
            'container_id': container.id,
            'container_name': container_name,
            'internal_ip': internal_ip,
            'internal_url': f'http://{internal_ip}:8069',
            'external_url': f'http://{instance["database_name"]}.odoo.saasodoo.local'
        }
        
    except docker.errors.NotFound:
        raise ValueError(f"Container {container_name} not found. Instance may need reprovisioning.")
    except Exception as e:
        logger.error("Failed to restart container", container_name=container_name, error=str(e))
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
            'external_url': f'http://{instance["database_name"]}.odoo.saasodoo.local'
        }
        
    except docker.errors.NotFound:
        # Container doesn't exist - this shouldn't happen for existing instances
        raise ValueError(f"Container {container_name} not found. Instance may need reprovisioning.")
    except Exception as e:
        logger.error("Failed to start container", container_name=container_name, error=str(e))
        raise


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


# ===== DATABASE UTILITIES (duplicated from provisioning.py for now) =====

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
            import json
            
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


async def _wait_for_odoo_startup(container_info: Dict[str, Any], timeout: int = 120):
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