"""
Instance upgrade/update tasks
"""

import os
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.kubernetes import KubernetesClient
from app.tasks.helpers import (
    get_instance_from_db as _get_instance_from_db,
    update_instance_status as _update_instance_status,
    wait_for_odoo_startup as _wait_for_odoo_startup,
    update_instance_network_info as _update_instance_network_info,
)
import structlog

logger = structlog.get_logger(__name__)


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


async def _update_instance_workflow(instance_id: str, target_version: str) -> Dict[str, Any]:
    """Main update workflow with Odoo version upgrade"""
    # Import K8s helpers and backup from maintenance to avoid circular imports
    from app.tasks.maintenance import _stop_kubernetes_deployment
    from app.tasks.backup import _backup_instance_workflow

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
