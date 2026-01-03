"""
Instance maintenance tasks (backup, restore, update)

This module provides backward-compatible imports for maintenance tasks.
The actual implementations have been split into focused modules:
- backup.py: Backup operations
- restore.py: Restore operations
- upgrade.py: Version upgrade operations

This module also contains shared Kubernetes helper functions used by
backup, restore, and upgrade workflows.
"""

import os
import asyncio
from typing import Dict, Any

from app.utils.kubernetes import KubernetesClient
import structlog

logger = structlog.get_logger(__name__)

# ===== RE-EXPORTS FOR BACKWARD COMPATIBILITY =====
# These imports ensure existing code that imports from maintenance.py continues to work

from app.tasks.backup import (
    backup_instance_task,
    _backup_instance_workflow,
    _ensure_backup_directories,
    _create_database_backup,
    _create_data_volume_backup,
    _create_backup_metadata,
    _store_backup_record,
    BACKUP_BASE_PATH,
    BACKUP_ACTIVE_PATH,
    BACKUP_STAGING_PATH,
    BACKUP_TEMP_PATH,
)

from app.tasks.restore import (
    restore_instance_task,
    _restore_instance_workflow,
    _get_backup_record,
    _restore_database_backup,
    _restore_data_volume_backup,
    _recreate_database,
    _restore_database_permissions,
    _reset_odoo_database_state,
)

from app.tasks.upgrade import (
    update_instance_task,
    _update_instance_workflow,
    _is_valid_version_upgrade,
    _update_instance_version,
    _deploy_updated_service,
    _run_database_migration,
)


# ===== SHARED KUBERNETES HELPER FUNCTIONS =====
# These functions are used by backup.py, restore.py, and upgrade.py
# They remain here to avoid circular imports

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

        # Wait for deployment to be ready (300s timeout for Odoo startup after backup)
        ready = k8s_client.wait_for_deployment_ready(deployment_name, timeout=300)

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
