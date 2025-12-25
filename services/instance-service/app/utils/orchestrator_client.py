"""
Orchestrator client factory
Returns appropriate client based on ORCHESTRATOR environment variable
"""

import os
from typing import Union

# Global orchestrator client instance
_orchestrator_client = None


def get_orchestrator_client() -> Union['DockerClientWrapper', 'KubernetesClientWrapper']:
    """
    Get the appropriate orchestrator client based on environment

    Returns:
        DockerClientWrapper for Docker/Swarm
        KubernetesClientWrapper for Kubernetes
    """
    global _orchestrator_client

    if _orchestrator_client is None:
        orchestrator = os.getenv('ORCHESTRATOR', 'docker').lower()

        if orchestrator == 'kubernetes':
            from .k8s_client import KubernetesClientWrapper
            _orchestrator_client = KubernetesClientWrapper()
        else:
            from .docker_client import DockerClientWrapper
            _orchestrator_client = DockerClientWrapper()

    return _orchestrator_client


# Alias for backward compatibility
def get_docker_client():
    """Backward compatibility alias - returns orchestrator client"""
    return get_orchestrator_client()
