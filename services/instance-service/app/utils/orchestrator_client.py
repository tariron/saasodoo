"""
Orchestrator client factory
Returns Kubernetes client for container orchestration
"""

import os

# Global orchestrator client instance
_orchestrator_client = None


def get_orchestrator_client():
    """
    Get the Kubernetes client for orchestration

    Returns:
        KubernetesClient instance
    """
    global _orchestrator_client

    if _orchestrator_client is None:
        from .k8s_client import KubernetesClient
        _orchestrator_client = KubernetesClient()

    return _orchestrator_client


# Backward compatibility alias
def get_docker_client():
    """Backward compatibility - returns Kubernetes client"""
    return get_orchestrator_client()
