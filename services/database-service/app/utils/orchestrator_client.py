"""
Orchestrator client factory for database service
Returns appropriate client based on ORCHESTRATOR environment variable
"""

import os
from typing import Union

# Global orchestrator client instance
_orchestrator_client = None


def get_orchestrator_client() -> Union['PostgreSQLDockerClient', 'PostgreSQLKubernetesClient']:
    """
    Get the appropriate orchestrator client based on environment

    Returns:
        PostgreSQLDockerClient for Docker/Swarm
        PostgreSQLKubernetesClient for Kubernetes
    """
    global _orchestrator_client

    if _orchestrator_client is None:
        orchestrator = os.getenv('ORCHESTRATOR', 'docker').lower()

        if orchestrator == 'kubernetes':
            from .k8s_client import PostgreSQLKubernetesClient
            _orchestrator_client = PostgreSQLKubernetesClient()
        else:
            from .docker_client import PostgreSQLDockerClient
            _orchestrator_client = PostgreSQLDockerClient()

    return _orchestrator_client


# Alias for backward compatibility
def get_docker_client():
    """Backward compatibility alias - returns orchestrator client"""
    return get_orchestrator_client()
