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
from app.utils.notification_client import get_notification_client
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


@celery_app.task(bind=True)
def unpause_instance_task(self, instance_id: str):
    """Background task to unpause instance"""
    try:
        logger.info("Starting instance unpause workflow", instance_id=instance_id, task_id=self.request.id)
        result = asyncio.run(_unpause_instance_workflow(instance_id))
        logger.info("Instance unpause completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance unpause failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _start_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main start workflow with Docker operations"""
    
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    logger.info("Starting start workflow", instance_name=instance['name'])
    
    # Get user information for email notifications
    user_info = await _get_user_info(instance['customer_id'])
    logger.info("User info for start workflow", customer_id=instance['customer_id'], user_info=user_info)
    
    try:
        # Step 1: Update status to STARTING
        await _update_instance_status(instance_id, InstanceStatus.STARTING)
        
        # Step 2: Start Docker container
        container_result = await _start_docker_container(instance)
        logger.info("Container started", container_id=container_result['container_id'])
        
        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=300) #120 seconds
        logger.info("Odoo startup confirmed after start")
        
        # Step 4: Update instance with current network info
        await _update_instance_network_info(instance_id, container_result)
        
        # Step 5: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        # Step 6: Send instance started email
        logger.info("Attempting to send instance started email", user_info=user_info)
        if user_info:
            try:
                logger.info("Getting notification client")
                client = get_notification_client()
                logger.info("Sending template email", email=user_info['email'], template_name="instance_started")
                await client.send_template_email(
                    to_emails=[user_info['email']],
                    template_name="instance_started",
                    template_variables={
                        "first_name": user_info['first_name'],
                        "instance_name": instance['name'],
                        "instance_url": container_result['external_url']
                    },
                    tags=["instance", "lifecycle", "started"]
                )
                logger.info("Instance started email sent successfully", email=user_info['email'])
            except Exception as e:
                logger.error("Failed to send instance started email", error=str(e), exc_info=True)
        else:
            logger.warning("No user info available, skipping email notification")
        
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
    
    # Get user information for email notifications
    user_info = await _get_user_info(instance['customer_id'])
    logger.info("User info for stop workflow", customer_id=instance['customer_id'], user_info=user_info)
    
    try:
        # Step 1: Update status to STOPPING
        await _update_instance_status(instance_id, InstanceStatus.STOPPING)
        
        # Step 2: Stop Docker container gracefully
        await _stop_docker_container(instance)
        logger.info("Container stopped successfully")
        
        # Step 3: Mark as STOPPED
        await _update_instance_status(instance_id, InstanceStatus.STOPPED)
        
        # Step 4: Send instance stopped email
        logger.info("Attempting to send instance stopped email", user_info=user_info)
        if user_info:
            try:
                logger.info("Getting notification client")
                client = get_notification_client()
                logger.info("Sending template email", email=user_info['email'], template_name="instance_stopped")
                await client.send_template_email(
                    to_emails=[user_info['email']],
                    template_name="instance_stopped",
                    template_variables={
                        "first_name": user_info['first_name'],
                        "instance_name": instance['name'],
                        "reason": "Instance stopped by user request"
                    },
                    tags=["instance", "lifecycle", "stopped"]
                )
                logger.info("Instance stopped email sent successfully", email=user_info['email'])
            except Exception as e:
                logger.error("Failed to send instance stopped email", error=str(e), exc_info=True)
        else:
            logger.warning("No user info available, skipping email notification")
        
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
        await _wait_for_odoo_startup(container_result, timeout=300) #120 seconds
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


async def _unpause_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main unpause workflow with Docker operations"""
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    logger.info("Starting unpause workflow", instance_name=instance['name'])
    try:
        # Step 1: Unpause Docker container
        await _unpause_docker_container(instance)
        logger.info("Container unpaused successfully")
        
        # Step 2: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "message": "Instance unpaused successfully"
        }
    except Exception as e:
        logger.error("Unpause workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _restart_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Restart Docker service (force update)"""
    client = docker.from_env()

    service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        service = client.services.get(service_name)

        logger.info("Restarting service (force update)", service_name=service_name)
        service.force_update()

        # Wait for new task to be running
        for _ in range(30):  # 60 second timeout
            await asyncio.sleep(2)
            service.reload()
            tasks = service.tasks(filters={'desired-state': 'running'})

            # Find most recent running task
            running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
            if running_tasks:
                newest_task = sorted(running_tasks, key=lambda t: t['CreatedAt'], reverse=True)[0]

                # Extract network IP from task
                internal_ip = None
                network_attachments = newest_task.get('NetworksAttachments', [])
                if network_attachments and network_attachments[0].get('Addresses'):
                    internal_ip = network_attachments[0]['Addresses'][0].split('/')[0]

                if not internal_ip:
                    internal_ip = 'localhost'

                return {
                    'service_id': service.id,
                    'service_name': service_name,
                    'internal_ip': internal_ip,
                    'internal_url': f'http://{internal_ip}:8069',
                    'external_url': f'http://{instance["database_name"]}.saasodoo.local'
                }

        raise RuntimeError("Service failed to restart within timeout")

    except docker.errors.NotFound:
        raise ValueError(f"Service {service_name} not found. Instance may need reprovisioning.")
    except Exception as e:
        logger.error("Failed to restart service", service_name=service_name, error=str(e))
        raise


async def _start_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start existing Docker service (scale to 1)"""
    client = docker.from_env()

    service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        # Try to get existing service
        service = client.services.get(service_name)

        logger.info("Starting service (scaling to 1)", service_name=service_name)

        # Scale to 1 replica
        service.update(mode={'Replicated': {'Replicas': 1}})

        # Wait for task to be running
        for _ in range(30):  # 60 second timeout
            await asyncio.sleep(2)
            service.reload()
            tasks = service.tasks(filters={'desired-state': 'running'})

            running_task = next((t for t in tasks if t['Status']['State'] == 'running'), None)
            if running_task:
                # Extract network IP from task
                internal_ip = None
                network_attachments = running_task.get('NetworksAttachments', [])
                if network_attachments and network_attachments[0].get('Addresses'):
                    internal_ip = network_attachments[0]['Addresses'][0].split('/')[0]

                if not internal_ip:
                    internal_ip = 'localhost'

                return {
                    'service_id': service.id,
                    'service_name': service_name,
                    'internal_ip': internal_ip,
                    'internal_url': f'http://{internal_ip}:8069',
                    'external_url': f'http://{instance["database_name"]}.saasodoo.local'
                }

        raise RuntimeError("Service failed to start within timeout")

    except docker.errors.NotFound:
        # Service doesn't exist - this can happen after termination/reactivation
        # Fall back to provisioning a new service
        logger.info("Service not found, falling back to provisioning", service_name=service_name)
        from app.tasks.provisioning import _deploy_odoo_container, _create_odoo_database

        # Create database if it doesn't exist
        try:
            db_info = await _create_odoo_database(instance)
            logger.info("Database created/verified", database=instance['database_name'])
        except Exception as db_e:
            logger.warning("Database creation failed, assuming it exists", error=str(db_e))
            db_info = {
                'db_host': os.getenv('POSTGRES_HOST', 'postgres'),
                'db_port': 5432,
                'db_name': instance['database_name'],
                'db_user': instance['database_name'],
                'db_password': instance.get('database_password', 'odoo_pass')
            }

        # Deploy new service
        service_result = await _deploy_odoo_container(instance, db_info)
        logger.info("New service deployed after missing service", service_id=service_result['service_id'])
        return service_result
    except Exception as e:
        logger.error("Failed to start service", service_name=service_name, error=str(e))
        raise


async def _stop_docker_container(instance: Dict[str, Any]):
    """Stop Docker service gracefully (scale to 0)"""
    client = docker.from_env()

    service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        service = client.services.get(service_name)

        logger.info("Stopping service (scaling to 0)", service_name=service_name)

        # Scale to 0 replicas
        service.update(mode={'Replicated': {'Replicas': 0}})

        logger.info("Service stopped successfully", service_name=service_name)

    except docker.errors.NotFound:
        logger.warning("Service not found during stop", service_name=service_name)
    except Exception as e:
        logger.error("Failed to stop service", service_name=service_name, error=str(e))
        raise


async def _unpause_docker_container(instance: Dict[str, Any]):
    """Unpause Docker service (Swarm doesn't support pause, so we map to start)"""
    logger.info("Swarm doesn't support pause/unpause - mapping unpause to start")
    return await _start_docker_container(instance)


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


async def _get_user_info(customer_id: str) -> Dict[str, Any]:
    """Get user information from user-service for email notifications"""
    try:
        import httpx
        
        # Use the user-service API to get customer details
        user_service_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')
        
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{user_service_url}/users/internal/{customer_id}")
            
            if response.status_code == 200:
                user_data = response.json()
                return {
                    'email': user_data.get('email', ''),
                    'first_name': user_data.get('first_name', 'there')
                }
            else:
                logger.warning("Failed to get user info from user-service", 
                              customer_id=customer_id, status_code=response.status_code)
                return None
                
    except Exception as e:
        logger.error("Error getting user info", customer_id=customer_id, error=str(e))
        return None