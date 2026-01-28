"""
Instance provisioning background tasks
"""

import os
import asyncio
import asyncpg
import subprocess
import shutil
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from celery import current_task
from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import send_instance_provisioning_started_email, send_instance_ready_email, send_instance_provisioning_failed_email
from app.utils.password_generator import generate_secure_password
from app.tasks.helpers import (
    get_instance_from_db as _get_instance_from_db,
    update_instance_status as _update_instance_status,
    wait_for_odoo_startup as _wait_for_odoo_startup,
    update_instance_network_info as _update_instance_network_info,
    get_user_info as _get_user_info,
    get_db_connection_params,
)
import structlog

logger = structlog.get_logger(__name__)


# Removed _parse_size_to_bytes and _create_cephfs_directory_with_quota
# These functions are deprecated - quota enforcement now handled by Kubernetes PVC limits


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


async def _update_instance_database_info(instance_id: str, db_server_id: str, db_host: str, db_port: int, db_name: str, db_user: str):
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
            SET db_server_id = $1, db_host = $2, db_port = $3, db_name = $4, db_user = $5, updated_at = $6
            WHERE id = $7
        """, UUID(db_server_id), db_host, db_port, db_name, db_user, datetime.utcnow(), UUID(instance_id))

        logger.info("Instance database info updated",
                   instance_id=instance_id,
                   db_server_id=db_server_id,
                   db_host=db_host,
                   db_port=db_port,
                   db_user=db_user)
    finally:
        await conn.close()


async def _deploy_odoo_container(instance: Dict[str, Any], db_info: Dict[str, str]) -> Dict[str, Any]:
    """Deploy Bitnami Odoo container"""

    # Use Kubernetes client
    from app.utils.kubernetes import KubernetesClient
    client = KubernetesClient()

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
        # Kubernetes automatically pulls images
        odoo_version = instance.get('odoo_version', '17')
        logger.info("Kubernetes will pull image automatically", version=odoo_version)

        # Get storage limit from instance and convert to Kubernetes format
        storage_limit = instance.get('storage_limit', '10G')
        k8s_storage_size = storage_limit + 'i' if storage_limit.endswith('G') else storage_limit + 'i'
        pvc_name = f"odoo-instance-{instance['id'].hex}"

        # Create PVC for instance storage
        logger.info("Creating instance PVC", pvc_name=pvc_name, size=k8s_storage_size)
        client.create_instance_pvc(pvc_name, k8s_storage_size)
        logger.info("Created instance PVC",
                   pvc_name=pvc_name,
                   storage_limit=k8s_storage_size)

        # Wait for PVC to be Bound before creating deployment
        logger.info("Waiting for PVC to bind", pvc_name=pvc_name)
        client.wait_for_pvc_bound(pvc_name, timeout=60)
        logger.info("PVC is bound and ready", pvc_name=pvc_name)

        # Prepare labels
        labels = {
            'saasodoo.instance.id': str(instance['id']),
            'saasodoo.instance.name': instance['name'],
            'saasodoo.customer.id': str(instance['customer_id']),
        }

        # Prepare ingress hostname
        ingress_host = f"{instance['database_name']}.{os.getenv('BASE_DOMAIN', 'saasodoo.local')}"

        # Create Kubernetes resources using native API
        logger.info("Creating Kubernetes resources",
                   instance_name=service_name,
                   image=f'bitnamilegacy/odoo:{odoo_version}')

        result = client.create_odoo_instance(
            instance_name=service_name,
            instance_id=str(instance['id']),
            image=f'bitnamilegacy/odoo:{odoo_version}',
            env_vars=environment,
            cpu_limit=str(cpu_limit),
            memory_limit=mem_limit,
            pvc_name=pvc_name,
            ingress_host=ingress_host,
            labels=labels
        )

        logger.info("Kubernetes resources created",
                   deployment_uid=result['deployment_uid'],
                   service_name=result['service_name'],
                   service_dns=result['service_dns'])

        # Wait for deployment to be ready
        logger.info("Waiting for deployment to be ready", deployment=service_name)
        deployment_ready = client.wait_for_deployment_ready(
            deployment_name=service_name,
            timeout=300  # 5 minutes for image pull + pod startup
        )

        if not deployment_ready:
            raise Exception(f"Deployment {service_name} did not become ready within timeout")

        logger.info("Deployment is ready", deployment=service_name)

        # Use Service DNS for health checks (more reliable than pod IP)
        service_dns = result['service_dns']
        internal_url = f"http://{service_dns}:8069"

        return {
            'service_id': result['deployment_uid'],
            'service_name': service_name,
            'service_dns': service_dns,
            'internal_url': internal_url,
            'external_url': f'http://{ingress_host}',
            'admin_password': generated_password  # Return generated password for email
        }
        
    except Exception as e:
        logger.error("Container deployment failed", error=str(e))
        raise


async def _cleanup_failed_provisioning(instance_id: str, instance: Dict[str, Any]):
    """Clean up resources after failed provisioning"""
    logger.info("Starting cleanup", instance_id=instance_id)
    
    try:
        # Remove Kubernetes resources if created
        from app.utils.kubernetes import KubernetesClient
        client = KubernetesClient()
        service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

        try:
            deleted = client.delete_instance(service_name)
            if deleted:
                logger.info("Kubernetes resources cleaned up", instance_name=service_name)
        except Exception as e:
            logger.warning("Failed to delete Kubernetes resources",
                         instance_name=service_name, error=str(e))

        # Clean up PVC if created
        pvc_name = f"odoo-instance-{instance['id'].hex}"
        try:
            client.delete_pvc(pvc_name)
            logger.info("Instance PVC cleaned up", pvc_name=pvc_name)
        except Exception as e:
            logger.warning("Failed to clean up PVC", pvc_name=pvc_name, error=str(e))

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


@celery_app.task(
    bind=True,
    name="instance.wait_for_database_and_provision",
    queue="instance_provisioning",
    max_retries=10,  # 10 attempts × 60 seconds = 10 minutes
    default_retry_delay=60  # Wait 60 seconds between retries
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
                'db_server_id': db_allocation.get('db_server_id'),
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
                db_server_id=db_info['db_server_id'],
                db_host=db_info['db_host'],
                db_port=db_info['db_port'],
                db_name=db_info['db_name'],
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

            # Retry after configured delay (60 seconds)
            raise self.retry()

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