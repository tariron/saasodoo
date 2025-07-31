"""
Instance provisioning background tasks
"""

import os
import asyncio
import asyncpg
import docker
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from celery import current_task
from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_instance_provisioning_started_email, send_instance_ready_email, send_instance_provisioning_failed_email
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str):
    """
    Background task to provision a new Odoo instance
    """
    try:
        logger.info("Starting instance provisioning", instance_id=instance_id, task_id=self.request.id)
        
        # Use sync version for Celery compatibility
        result = asyncio.run(_provision_instance_workflow(instance_id))
        
        logger.info("Instance provisioning completed", instance_id=instance_id, result=result)
        return result
        
    except Exception as e:
        logger.error("Instance provisioning failed", instance_id=instance_id, error=str(e))
        
        # Update instance status to ERROR
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        
        # Re-raise for Celery to mark task as failed
        raise


async def _provision_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main provisioning workflow"""
    
    # Step 1: Get instance details
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    
    logger.info("Provisioning workflow started", instance_name=instance['name'])
    
    # Get user information for email notifications
    user_info = await _get_user_info(instance['customer_id'])
    
    try:
        # Step 2: Send provisioning started email
        if user_info:
            try:
                await send_instance_provisioning_started_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    estimated_time="10-15 minutes"
                )
                logger.info("Provisioning started email sent", email=user_info['email'])
            except Exception as e:
                logger.warning("Failed to send provisioning started email", error=str(e))
        
        # Step 3: Update status to STARTING
        await _update_instance_status(instance_id, InstanceStatus.STARTING)
        
        # Step 4: Create dedicated Odoo database
        db_info = await _create_odoo_database(instance)
        logger.info("Database created", database=instance['database_name'])
        
        # Step 5: Deploy Bitnami Odoo container
        container_info = await _deploy_odoo_container(instance, db_info)
        logger.info("Container deployed", container_id=container_info['container_id'])
        
        # Step 6: Wait for Odoo to start up
        await _wait_for_odoo_startup(container_info, timeout=300)  # 5 minutes
        logger.info("Odoo startup confirmed")
        
        # Step 7: Update instance with connection details
        await _update_instance_network_info(instance_id, container_info)
        
        # Step 8: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        # Step 9: Send instance ready email
        if user_info:
            try:
                await send_instance_ready_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    instance_url=container_info['external_url'],
                    admin_email=instance['admin_email']
                )
                logger.info("Instance ready email sent", email=user_info['email'])
            except Exception as e:
                logger.warning("Failed to send instance ready email", error=str(e))
        
        return {
            "status": "success",
            "container_id": container_info['container_id'],
            "external_url": container_info['external_url'],
            "message": "Instance provisioned successfully"
        }
        
    except Exception as e:
        # Cleanup on failure
        logger.error("Provisioning failed, starting cleanup", error=str(e))
        
        # Send provisioning failed email
        if user_info:
            try:
                await send_instance_provisioning_failed_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    error_reason=str(e)[:200],  # Truncate long error messages
                    support_url=f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
                )
                logger.info("Provisioning failed email sent", email=user_info['email'])
            except Exception as email_error:
                logger.warning("Failed to send provisioning failed email", error=str(email_error))
        
        await _cleanup_failed_provisioning(instance_id, instance)
        raise


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
            
            # Deserialize JSON fields (same logic as InstanceDatabase.get_instance)
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


async def _create_odoo_database(instance: Dict[str, Any]) -> Dict[str, str]:
    """Create dedicated PostgreSQL database for Odoo instance"""
    
    # Connect to PostgreSQL as admin
    admin_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database='postgres',  # Connect to default DB
        user=os.getenv('POSTGRES_USER', 'saasodoo'),
        password=os.getenv('POSTGRES_PASSWORD', 'saasodoo123')
    )
    
    try:
        database_name = instance['database_name']
        db_user = f"odoo_{database_name}"
        db_password = f"odoo_pass_{instance['id'].hex[:8]}"
        
        # Create database user first
        await admin_conn.execute(f'CREATE USER "{db_user}" WITH PASSWORD \'{db_password}\'')
        logger.info("Database user created", user=db_user)
        
        # Create database with owner
        await admin_conn.execute(f'CREATE DATABASE "{database_name}" OWNER "{db_user}"')
        logger.info("Database created", database=database_name)
        
        # Grant additional privileges
        await admin_conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{database_name}" TO "{db_user}"')
        
        return {
            "db_name": database_name,
            "db_user": db_user,
            "db_password": db_password,
            "db_host": os.getenv('POSTGRES_HOST', 'postgres'),
            "db_port": "5432"
        }
        
    finally:
        await admin_conn.close()


async def _deploy_odoo_container(instance: Dict[str, Any], db_info: Dict[str, str]) -> Dict[str, Any]:
    """Deploy Bitnami Odoo container"""
    
    # Use auto-detection for socket connection
    client = docker.from_env()
    
    container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
    
    # Container configuration
    environment = {
        'ODOO_DATABASE_HOST': db_info['db_host'],
        'ODOO_DATABASE_PORT_NUMBER': db_info['db_port'],
        'ODOO_DATABASE_NAME': db_info['db_name'],
        'ODOO_DATABASE_USER': db_info['db_user'],
        'ODOO_DATABASE_PASSWORD': db_info['db_password'],
        'ODOO_EMAIL': instance['admin_email'],
        'ODOO_PASSWORD': instance['admin_password'],  # Use provided password or generate
        'ODOO_LOAD_DEMO_DATA': 'yes' if instance['demo_data'] else 'no',
    }
    
    # Add custom environment variables
    if instance.get('environment_vars'):
        environment.update(instance['environment_vars'])
    
    # Resource limits
    mem_limit = instance['memory_limit']
    cpu_limit = instance['cpu_limit']
    
    try:
        # Pull Bitnami Odoo image
        logger.info("Pulling Bitnami Odoo image")
        client.images.pull('bitnami/odoo:17')  # Use version from instance.odoo_version
        
        # Create persistent volume for Odoo data
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
        
        # Create and start container with persistent volume
        container = client.containers.run(
            'bitnami/odoo:17',
            name=container_name,
            environment=environment,
            mem_limit=mem_limit,
            cpu_count=int(cpu_limit),
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            volumes={
                volume_name: {'bind': '/bitnami/odoo', 'mode': 'rw'}
            },
            labels={
                'saasodoo.instance.id': str(instance['id']),
                'saasodoo.instance.name': instance['name'],
                'saasodoo.customer.id': str(instance['customer_id']),
                # Traefik labels for automatic routing
                'traefik.enable': 'true',
                f'traefik.http.routers.{container_name}.rule': f'Host(`{instance["database_name"]}.saasodoo.local`)',
                f'traefik.http.routers.{container_name}.service': container_name,
                f'traefik.http.services.{container_name}.loadbalancer.server.port': '8069',
            }
        )
        
        # Connect to network after creation
        try:
            network = client.networks.get('saasodoo-network')
            network.connect(container)
            logger.info("Container connected to network", container_name=container_name, network='saasodoo-network')
        except docker.errors.NotFound:
            logger.warning("Network saasodoo-network not found, skipping network connection")
        
        logger.info("Container created and started", container_id=container.id, name=container_name)
        
        # Get container network info
        container.reload()
        internal_ip = None
        if 'saasodoo-network' in container.attrs['NetworkSettings']['Networks']:
            network_info = container.attrs['NetworkSettings']['Networks']['saasodoo-network']
            internal_ip = network_info['IPAddress']
        else:
            # Fallback to first available network
            networks = container.attrs['NetworkSettings']['Networks']
            if networks:
                first_network = next(iter(networks.values()))
                internal_ip = first_network['IPAddress']
        
        if not internal_ip:
            internal_ip = 'localhost'  # Fallback
        
        return {
            'container_id': container.id,
            'container_name': container_name,
            'internal_ip': internal_ip,
            'internal_url': f'http://{internal_ip}:8069',
            'external_url': f'http://{instance.get("subdomain") or instance["database_name"]}.saasodoo.local',
            'admin_password': environment['ODOO_PASSWORD']
        }
        
    except Exception as e:
        logger.error("Container deployment failed", error=str(e))
        raise


async def _wait_for_odoo_startup(container_info: Dict[str, Any], timeout: int = 300):
    """Wait for Odoo to start up and be accessible"""
    import httpx
    import asyncio
    
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


async def _cleanup_failed_provisioning(instance_id: str, instance: Dict[str, Any]):
    """Clean up resources after failed provisioning"""
    logger.info("Starting cleanup", instance_id=instance_id)
    
    try:
        # Remove Docker container if created
        client = docker.from_env()
        container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"
        
        try:
            container = client.containers.get(container_name)
            container.stop(timeout=10)
            container.remove()
            logger.info("Container cleaned up", container_name=container_name)
        except docker.errors.NotFound:
            pass  # Container doesn't exist
        
        # Remove Docker volume if created
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
        try:
            volume = client.volumes.get(volume_name)
            volume.remove()
            logger.info("Volume cleaned up", volume_name=volume_name)
        except docker.errors.NotFound:
            pass  # Volume doesn't exist
        
        # Remove database if created
        admin_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=5432,
            database='postgres',
            user=os.getenv('POSTGRES_USER', 'saasodoo'),
            password=os.getenv('POSTGRES_PASSWORD', 'saasodoo123')
        )
        
        try:
            database_name = instance['database_name']
            db_user = f"odoo_{database_name}"
            
            # Terminate connections and drop database
            await admin_conn.execute(f"""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = '{database_name}'
                AND pid <> pg_backend_pid()
            """)
            
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
            await admin_conn.execute(f'DROP USER IF EXISTS "{db_user}"')
            logger.info("Database cleaned up", database=database_name)
            
        finally:
            await admin_conn.close()
            
    except Exception as e:
        logger.error("Cleanup failed", error=str(e))


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