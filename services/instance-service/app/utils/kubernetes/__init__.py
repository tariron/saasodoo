"""
Kubernetes client package for managing Odoo instances

This package provides Kubernetes API operations for:
- Odoo instance deployments and services
- Persistent volume management (PVCs)
- Backup/restore jobs
- Pod operations (logs, exec, status)

The package is organized into modules by concern:
- base.py: KubernetesClientBase with connection management
- deployments.py: DeploymentOperationsMixin for deployment/service operations
- jobs.py: JobOperationsMixin for backup/restore job operations
- volumes.py: VolumeOperationsMixin for PVC operations
- client.py: Composite KubernetesClient class
"""

from app.utils.kubernetes.client import KubernetesClient

__all__ = ['KubernetesClient']
