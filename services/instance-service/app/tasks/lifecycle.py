"""
Instance lifecycle management tasks (start, stop, restart)
"""

import os
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import get_notification_client
from app.utils.kubernetes import KubernetesClient
from app.tasks.helpers import (
    get_instance_from_db as _get_instance_from_db,
    update_instance_status as _update_instance_status,
    wait_for_odoo_startup as _wait_for_odoo_startup,
    update_instance_network_info as _update_instance_network_info,
    get_user_info as _get_user_info,
)
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
        
        # Step 2: Start Docker service
        container_result = await _start_docker_container(instance)
        logger.info("Service started", service_id=container_result.get('service_id'))
        
        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=300)  # 300 seconds (5 minutes)
        logger.info("Odoo startup confirmed after start")

        # Step 4: Update instance with current network info
        await _update_instance_network_info(instance_id, container_result)

        # Step 5: Update status to RUNNING (health check passed)
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        logger.info("Instance status updated to RUNNING after health check")

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
            "service_id": container_result.get('service_id'),
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

        # Step 3: Send instance stopped email (reconciliation will set STOPPED status)
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
        
        # Step 2: Restart Docker service
        container_result = await _restart_docker_container(instance)
        logger.info("Service restarted", service_id=container_result.get('service_id'))
        
        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=300)  # 300 seconds (5 minutes)
        logger.info("Odoo startup confirmed after restart")

        # Step 4: Update instance with current network info
        await _update_instance_network_info(instance_id, container_result)

        # Step 5: Update status to RUNNING (health check passed)
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)
        logger.info("Instance status updated to RUNNING after health check")

        return {
            "status": "success",
            "service_id": container_result.get('service_id'),
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

        # Docker events monitoring will handle transition to RUNNING status

        return {
            "status": "success",
            "message": "Instance unpaused successfully"
        }
    except Exception as e:
        logger.error("Unpause workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _restart_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Restart Kubernetes deployment (delete pods, let deployment recreate them)"""
    client = KubernetesClient()

    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
    service_name = f"{deployment_name}-service"

    try:
        logger.info("Restarting deployment (deleting pod)", deployment_name=deployment_name)

        # Get current pod name
        pod_status = client.get_pod_status(deployment_name)
        if not pod_status:
            raise ValueError(f"No pod found for deployment {deployment_name}")

        pod_name = pod_status['name']

        # Delete the pod - Kubernetes will automatically recreate it via the deployment
        try:
            client.core_v1.delete_namespaced_pod(
                name=pod_name,
                namespace=client.namespace
            )
            logger.info("Pod deleted, waiting for recreation", pod_name=pod_name)
        except Exception as delete_error:
            logger.warning("Failed to delete pod, trying deployment restart", error=str(delete_error))
            # Fallback: Use kubectl-style rollout restart by patching deployment annotations
            import time
            client.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=client.namespace,
                body={
                    'spec': {
                        'template': {
                            'metadata': {
                                'annotations': {
                                    'kubectl.kubernetes.io/restartedAt': datetime.utcnow().isoformat()
                                }
                            }
                        }
                    }
                }
            )

        # Wait for new pod to be running
        deployment_ready = client.wait_for_deployment_ready(
            deployment_name=deployment_name,
            timeout=180
        )

        if not deployment_ready:
            raise RuntimeError("Deployment failed to become ready after restart")

        # Use Service DNS for internal URL
        namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')
        service_dns = f"{service_name}.{namespace}.svc.cluster.local"

        # Get new pod status
        new_pod_status = client.get_pod_status(deployment_name)
        service_id = new_pod_status['name'] if new_pod_status else deployment_name

        return {
            'service_id': service_id,
            'service_name': deployment_name,
            'service_dns': service_dns,
            'internal_url': f'http://{service_dns}:8069',
            'external_url': f'http://{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}'
        }

    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            raise ValueError(f"Deployment {deployment_name} not found. Instance may need reprovisioning.")
        else:
            logger.error("Failed to restart deployment", deployment_name=deployment_name, error=str(e))
            raise


async def _start_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    """Start existing Kubernetes deployment (scale to 1)"""
    client = KubernetesClient()

    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
    service_name = f"{deployment_name}-service"

    try:
        # Scale deployment to 1 replica
        logger.info("Starting deployment (scaling to 1)", deployment_name=deployment_name)

        success = client.scale_deployment(deployment_name, replicas=1)
        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name}")

        # Wait for deployment to be ready
        deployment_ready = client.wait_for_deployment_ready(
            deployment_name=deployment_name,
            timeout=180
        )

        if not deployment_ready:
            raise RuntimeError("Deployment failed to become ready within timeout")

        # Use Service DNS for internal URL
        namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')
        service_dns = f"{service_name}.{namespace}.svc.cluster.local"

        # Get pod status to retrieve deployment UID
        pod_status = client.get_pod_status(deployment_name)
        service_id = pod_status['name'] if pod_status else deployment_name

        return {
            'service_id': service_id,
            'service_name': deployment_name,
            'service_dns': service_dns,
            'internal_url': f'http://{service_dns}:8069',
            'external_url': f'http://{instance["database_name"]}.{os.getenv("BASE_DOMAIN", "saasodoo.local")}'
        }

    except Exception as e:
        # Check if deployment doesn't exist
        if "not found" in str(e).lower() or "404" in str(e):
            # Deployment doesn't exist - this can happen after termination/reactivation
            # Fall back to provisioning a new deployment
            logger.info("Deployment not found, falling back to provisioning", deployment_name=deployment_name)
            from app.tasks.provisioning import _deploy_odoo_container, _create_odoo_database

            # Create database if it doesn't exist
            try:
                db_info = await _create_odoo_database(instance)
                logger.info("Database created/verified", database=instance['database_name'])
            except Exception as db_e:
                logger.warning("Database creation failed, assuming it exists", error=str(db_e))
                db_info = {
                    'db_host': os.getenv('POSTGRES_HOST', 'postgres'),
                    'db_port': int(os.getenv('POSTGRES_PORT', '5432')),
                    'db_name': instance['database_name'],
                    'db_user': instance['database_name'],
                    'db_password': instance.get('database_password', 'odoo_pass')
                }

            # Deploy new deployment
            service_result = await _deploy_odoo_container(instance, db_info)
            logger.info("New deployment created after missing deployment", service_id=service_result['service_id'])
            return service_result
        else:
            logger.error("Failed to start deployment", deployment_name=deployment_name, error=str(e))
            raise


async def _stop_docker_container(instance: Dict[str, Any]):
    """Stop Kubernetes deployment gracefully (scale to 0) and wait for verification"""
    client = KubernetesClient()

    deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    try:
        logger.info("Stopping deployment (scaling to 0)", deployment_name=deployment_name)

        # Scale to 0 replicas
        success = client.scale_deployment(deployment_name, replicas=0)
        if not success:
            raise RuntimeError(f"Failed to scale deployment {deployment_name} to 0")

        # Wait for pods to terminate (check deployment scale)
        for attempt in range(30):  # 60 second timeout
            await asyncio.sleep(2)

            # Check pod status - should be None when scaled to 0
            pod_status = client.get_pod_status(deployment_name)
            if pod_status is None:
                logger.info("All pods stopped successfully", deployment_name=deployment_name)
                return

            logger.debug(
                "Waiting for pods to stop",
                deployment_name=deployment_name,
                attempt=attempt + 1,
                pod_status=pod_status
            )

        # If we get here, timeout occurred
        raise RuntimeError(f"Deployment failed to scale down within timeout (60s)")

    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            logger.warning("Deployment not found during stop", deployment_name=deployment_name)
        else:
            logger.error("Failed to stop deployment", deployment_name=deployment_name, error=str(e))
            raise


async def _unpause_docker_container(instance: Dict[str, Any]):
    """Unpause Kubernetes deployment (Kubernetes doesn't support pause, so we map to start)"""
    logger.info("Kubernetes doesn't support pause/unpause - mapping unpause to start")
    return await _start_docker_container(instance)