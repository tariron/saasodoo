"""
Kubernetes client for Odoo instance management

This module provides the composite KubernetesClient class that combines
all Kubernetes operations through mixin inheritance.
"""

from app.utils.kubernetes.base import KubernetesClientBase
from app.utils.kubernetes.deployments import DeploymentOperationsMixin
from app.utils.kubernetes.jobs import JobOperationsMixin
from app.utils.kubernetes.volumes import VolumeOperationsMixin


class KubernetesClient(
    KubernetesClientBase,
    DeploymentOperationsMixin,
    JobOperationsMixin,
    VolumeOperationsMixin
):
    """
    Composite Kubernetes client for Odoo instance management.

    Combines all Kubernetes operations:
    - Base: Connection management with retry logic
    - Deployments: Create/scale/delete Odoo instances
    - Jobs: Backup/restore operations
    - Volumes: PVC management
    """
    pass
