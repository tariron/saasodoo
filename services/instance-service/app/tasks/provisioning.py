"""
Instance provisioning background tasks
"""

import os
import asyncio
import asyncpg
import docker
import subprocess
import shutil
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from celery import current_task
from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.database import OdooInstanceDatabaseManager
from app.utils.notification_client import send_instance_provisioning_started_email, send_instance_ready_email, send_instance_provisioning_failed_email
from app.utils.password_generator import generate_secure_password
import structlog

logger = structlog.get_logger(__name__)


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


def _create_cephfs_directory_with_quota(path: str, size_limit: str):
    """
    Create CephFS directory and set quota

    Args:
        path: Full path to directory on CephFS mount
        size_limit: Size limit string (e.g., '10G', '512M')
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(path, exist_ok=True)
        logger.info("Created CephFS directory", path=path)

        # Parse size to bytes
        quota_bytes = _parse_size_to_bytes(size_limit)

        # Set CephFS quota using setfattr
        cmd = [
            'setfattr',
            '-n', 'ceph.quota.max_bytes',
            '-v', str(quota_bytes),
            path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        logger.info("Set CephFS quota", path=path, size_limit=size_limit, quota_bytes=quota_bytes)

    except subprocess.CalledProcessError as e:
        logger.error("Failed to set CephFS quota", path=path, error=str(e), stderr=e.stderr)
        raise RuntimeError(f"Failed to set CephFS quota: {e.stderr}")
    except Exception as e:
        logger.error("Failed to create CephFS directory with quota", path=path, error=str(e))
        raise


@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    """
    Background task to provision a new Odoo instance

    Args:
        instance_id: UUID of the instance to provision
        db_info: Dictionary containing database credentials from database-service (required)
                 Keys: db_host, db_port, db_name, db_user, db_password
    """
    try:
        if not db_info:
            raise ValueError("db_info is required - database must be allocated before provisioning")

        logger.info("Starting instance provisioning",
                   instance_id=instance_id,
                   task_id=self.request.id,
                   db_host=db_info.get('db_host'),
                   db_name=db_info.get('db_name'))

        # Use sync version for Celery compatibility
        result = asyncio.run(_provision_instance_workflow(instance_id, db_info))

        logger.info("Instance provisioning completed", instance_id=instance_id, result=result)
        return result

    except Exception as e:
        logger.error("Instance provisioning failed", instance_id=instance_id, error=str(e))

        # Update instance status to ERROR
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))

        # Re-raise for Celery to mark task as failed
        raise


async def _provision_instance_workflow(instance_id: str, db_info: Dict[str, str]) -> Dict[str, Any]:
    """
    Main provisioning workflow

    Args:
        instance_id: UUID of the instance to provision
        db_info: Database credentials from database-service (required).
                 Keys: db_host, db_port, db_name, db_user, db_password
    """

    # Validate db_info is provided
    if not db_info:
        raise ValueError("db_info is required - database must be allocated by database-service before provisioning")

    # Step 1: Get instance details
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    logger.info("Provisioning workflow started",
               instance_name=instance['name'],
               db_host=db_info['db_host'],
               db_name=db_info['db_name'])

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

        # Step 4: Use database credentials from database-service
        logger.info("Using database credentials from database-service",
                   db_host=db_info['db_host'],
                   db_name=db_info['db_name'])

        # Step 5: Deploy Bitnami Odoo service
        container_info = await _deploy_odoo_container(instance, db_info)
        logger.info("Service deployed", service_id=container_info['service_id'])

        # Step 6: Wait for Odoo to start up
        await _wait_for_odoo_startup(container_info, timeout=300)  # 5 minutes
        logger.info("Odoo startup confirmed")

        # Step 7: Update instance with connection details
        await _update_instance_network_info(instance_id, container_info, db_info)

        # Step 8: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)

        # Step 9: Send instance ready email with password
        if user_info:
            try:
                await send_instance_ready_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    instance_url=container_info['external_url'],
                    admin_email=instance['admin_email'],
                    admin_password=container_info['admin_password']  # Include generated password
                )
                logger.info("Instance ready email sent with password", email=user_info['email'])
            except Exception as e:
                logger.warning("Failed to send instance ready email", error=str(e))

        return {
            "status": "success",
            "service_id": container_info['service_id'],
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
        port=int(os.getenv('POSTGRES_PORT', '5432')),
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


async def _update_instance_database_info(instance_id: str, db_host: str, db_port: int, db_user: str):
    """Update instance with database connection info (non-sensitive data only)"""
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
            SET db_host = $1, db_port = $2, db_user = $3, updated_at = $4
            WHERE id = $5
        """, db_host, db_port, db_user, datetime.utcnow(), UUID(instance_id))

        logger.info("Instance database info updated",
                   instance_id=instance_id,
                   db_host=db_host,
                   db_port=db_port,
                   db_user=db_user)
    finally:
        await conn.close()


async def _deploy_odoo_container(instance: Dict[str, Any], db_info: Dict[str, str]) -> Dict[str, Any]:
    """Deploy Bitnami Odoo container"""
    
    # Use auto-detection for socket connection
    client = docker.from_env()

    # Service naming for Swarm (changed from container_name)
    service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    # Generate secure random password for this instance
    generated_password = generate_secure_password()
    logger.info("Generated secure password for instance", instance_id=str(instance['id']))

    # Container configuration
    environment = {
        'ODOO_DATABASE_HOST': db_info['db_host'],
        'ODOO_DATABASE_PORT_NUMBER': str(db_info['db_port']),
        'ODOO_DATABASE_NAME': db_info['db_name'],
        'ODOO_DATABASE_USER': db_info['db_user'],
        'ODOO_DATABASE_PASSWORD': db_info['db_password'],
        'ODOO_EMAIL': instance['admin_email'],
        'ODOO_PASSWORD': generated_password,  # Use generated password
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
        odoo_version = instance.get('odoo_version', '17')
        logger.info("Pulling Bitnami Odoo image", version=odoo_version)
        client.images.pull(f'bitnamilegacy/odoo:{odoo_version}')

        # Get storage limit from instance
        storage_limit = instance.get('storage_limit', '10G')
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"

        # Create CephFS directory with quota for direct bind mount
        cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
        _create_cephfs_directory_with_quota(cephfs_path, storage_limit)
        logger.info("Created CephFS directory with quota",
                   volume_name=volume_name,
                   storage_limit=storage_limit,
                   path=cephfs_path)

        # Create Swarm service with persistent volume
        import asyncio

        # Create resources specification
        # Convert memory limit from string like "2G" to bytes
        mem_limit_bytes = _parse_size_to_bytes(mem_limit) if isinstance(mem_limit, str) else mem_limit
        resources = docker.types.Resources(
            cpu_limit=int(cpu_limit * 1_000_000_000),  # Convert to nanocpus
            mem_limit=mem_limit_bytes
        )

        # Create mount for CephFS directory (direct bind mount)
        mount = docker.types.Mount(
            target='/bitnami/odoo',
            source=cephfs_path,
            type='bind'
        )

        # Create service
        service = client.services.create(
            image=f'bitnamilegacy/odoo:{odoo_version}',
            name=service_name,
            env=environment,  # Note: env is dict for services, not list
            resources=resources,
            mode=docker.types.ServiceMode('replicated', replicas=1),
            mounts=[mount],
            networks=['saasodoo-network'],
            labels={
                'saasodoo.instance.id': str(instance['id']),
                'saasodoo.instance.name': instance['name'],
                'saasodoo.customer.id': str(instance['customer_id']),
                # Traefik labels for automatic routing
                'traefik.enable': 'true',
                f'traefik.http.routers.{service_name}.rule': f'Host(`{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}`)',
                f'traefik.http.routers.{service_name}.service': service_name,
                f'traefik.http.services.{service_name}.loadbalancer.server.port': '8069',
            },
            restart_policy=docker.types.RestartPolicy(condition='any')
        )

        logger.info("Service created", service_id=service.id, service_name=service_name)

        # Wait for task to start
        await asyncio.sleep(5)  # Give Swarm time to schedule

        # Get running task information
        service.reload()
        tasks = service.tasks()

        running_task = next((t for t in tasks if t['Status']['State'] == 'running'), None)

        # If no running task yet, wait a bit more
        if not running_task:
            max_wait = 120  # 2 minutes for image pull + container startup
            waited = 5
            while waited < max_wait and not running_task:
                await asyncio.sleep(5)
                waited += 5
                service.reload()
                tasks = service.tasks()
                running_task = next((t for t in tasks if t['Status']['State'] == 'running'), None)

        if not running_task:
            raise Exception(f"Service {service_name} failed to start a running task within {max_wait} seconds")

        # Extract task information
        internal_ip = None
        network_attachments = running_task.get('NetworksAttachments', [])
        if network_attachments and network_attachments[0].get('Addresses'):
            internal_ip = network_attachments[0]['Addresses'][0].split('/')[0]

        if not internal_ip:
            internal_ip = 'localhost'  # Fallback

        return {
            'service_id': service.id,
            'service_name': service_name,
            'internal_ip': internal_ip,
            'internal_url': f'http://{internal_ip}:8069',
            'external_url': f'http://{instance.get("subdomain") or instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}',
            'admin_password': generated_password  # Return generated password for email
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


async def _update_instance_network_info(instance_id: str, container_info: Dict[str, Any], db_info: Dict[str, str]):
    """Update instance with network, container, and database information"""
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
                internal_url = $3, external_url = $4,
                db_host = $5, db_port = $6, updated_at = $7
            WHERE id = $8
        """,
            container_info['service_id'],
            container_info['service_name'],
            container_info['internal_url'],
            container_info['external_url'],
            db_info['db_host'],
            int(db_info['db_port']),
            datetime.utcnow(),
            UUID(instance_id)
        )

        logger.info("Instance network and database info updated",
                   instance_id=instance_id,
                   db_host=db_info['db_host'],
                   db_port=db_info['db_port'])
    finally:
        await conn.close()


async def _cleanup_failed_provisioning(instance_id: str, instance: Dict[str, Any]):
    """Clean up resources after failed provisioning"""
    logger.info("Starting cleanup", instance_id=instance_id)
    
    try:
        # Remove Docker service if created
        client = docker.from_env()
        service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

        try:
            service = client.services.get(service_name)
            service.remove()
            logger.info("Service cleaned up", service_name=service_name)
        except docker.errors.NotFound:
            pass  # Service doesn't exist

        # Clean up CephFS directory if created
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
        cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
        try:
            if os.path.exists(cephfs_path):
                shutil.rmtree(cephfs_path)
                logger.info("CephFS directory cleaned up", path=cephfs_path)
        except Exception as e:
            logger.warning("Failed to clean up CephFS directory", path=cephfs_path, error=str(e))

        # In the future, this should call a deallocation endpoint on the database-service.
        # For now, we will log that a deallocation is required.
        # The database-service owns database lifecycle management.
        database_name = instance['database_name']
        logger.info("Deallocation of database required",
                   database=database_name,
                   instance_id=instance_id,
                   message="Database cleanup should be handled by database-service deallocation endpoint")
            
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


@celery_app.task(
    bind=True,
    name="instance.wait_for_database_and_provision",
    queue="instance_provisioning",
    max_retries=30,  # 30 attempts × 10 seconds = 5 minutes
    default_retry_delay=10  # Wait 10 seconds between retries
)
def wait_for_database_and_provision(
    self,
    instance_id: str,
    customer_id: str,
    db_type: str
):
    """
    Poll database-service until database is allocated, then proceed with provisioning.

    This task is queued when database allocation returns status='provisioning'.
    It polls every 10 seconds for up to 5 minutes.

    Args:
        instance_id: UUID of the instance waiting for database
        customer_id: UUID of the customer
        db_type: Database type ('shared' or 'dedicated')
    """
    import httpx

    logger.info(
        "waiting_for_database_allocation",
        instance_id=instance_id,
        db_type=db_type,
        attempt=self.request.retries + 1,
    )

    try:
        # Get database service URL
        database_service_url = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8005")

        # Map db_type to database-service parameters
        require_dedicated = (db_type == "dedicated")

        # Try to allocate database using httpx (sync version)
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{database_service_url}/api/database/allocate",
                json={
                    "instance_id": instance_id,
                    "customer_id": customer_id,
                    "plan_tier": "starter",
                    "require_dedicated": require_dedicated
                }
            )
            response.raise_for_status()
            db_allocation = response.json()

        if db_allocation.get("status") == "allocated":
            # Database is now allocated!
            # Extract credentials into db_info dictionary
            db_info = {
                'db_host': db_allocation.get('db_host'),
                'db_port': db_allocation.get('db_port'),
                'db_name': db_allocation.get('db_name'),
                'db_user': db_allocation.get('db_user'),
                'db_password': db_allocation.get('db_password')  # Sensitive - only in memory
            }

            logger.info(
                "database_allocated",
                instance_id=instance_id,
                db_host=db_info['db_host'],
                db_name=db_info['db_name'],
                db_user=db_info['db_user']
            )

            # Persist non-sensitive database info to instances table
            asyncio.run(_update_instance_database_info(
                instance_id=instance_id,
                db_host=db_info['db_host'],
                db_port=db_info['db_port'],
                db_user=db_info['db_user']
            ))

            # Hand off to provision_instance_task with db_info (including password)
            provision_instance_task.delay(instance_id, db_info)

            logger.info(
                "provisioning_task_queued",
                instance_id=instance_id,
                message="Database allocated, provisioning task queued with credentials"
            )

            return {
                "status": "success",
                "message": "Database allocated, provisioning started",
                "db_host": db_info['db_host'],
                "db_name": db_info['db_name']
            }

        else:
            # Still provisioning, retry
            logger.info(
                "database_still_provisioning",
                instance_id=instance_id,
                attempt=self.request.retries + 1,
                max_retries=self.max_retries,
            )

            if self.request.retries >= self.max_retries:
                # Timeout after 5 minutes
                logger.error(
                    "database_allocation_timeout",
                    instance_id=instance_id,
                    timeout_minutes=5,
                )

                # Update instance to error status
                asyncio.run(_update_instance_status(
                    instance_id,
                    InstanceStatus.ERROR,
                    'Database allocation timeout after 5 minutes'
                ))

                raise Exception("Database allocation timeout after 5 minutes")

            # Retry after 10 seconds
            raise self.retry(countdown=10)

    except httpx.HTTPStatusError as e:
        logger.error(
            "database_allocation_http_error",
            instance_id=instance_id,
            status_code=e.response.status_code,
            response_text=e.response.text,
        )

        # Update instance to error status
        asyncio.run(_update_instance_status(
            instance_id,
            InstanceStatus.ERROR,
            f"Database allocation failed: {e.response.text}"
        ))

        raise

    except Exception as e:
        logger.error(
            "wait_for_database_task_failed",
            instance_id=instance_id,
            error=str(e),
        )
        raise