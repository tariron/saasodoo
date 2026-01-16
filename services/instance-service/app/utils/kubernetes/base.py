"""
Base Kubernetes client with connection management
"""

import os
import time
import base64
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class KubernetesClientBase:
    """Base class with Kubernetes connection management"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize Kubernetes client

        Args:
            max_retries: Maximum number of connection retry attempts
            retry_delay: Base delay between retries (with exponential backoff)
        """
        self.core_v1 = None
        self.apps_v1 = None
        self.networking_v1 = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_connection_check = 0
        self._connection_check_interval = 30  # seconds
        self.namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')

        self._ensure_connection()

    def _ensure_connection(self):
        """Ensure Kubernetes client is connected with retry logic"""
        current_time = time.time()

        if (self.core_v1 is None or
                current_time - self._last_connection_check > self._connection_check_interval):

            for attempt in range(self.max_retries):
                try:
                    # Load Kubernetes config
                    try:
                        config.load_incluster_config()
                        logger.info("Loaded in-cluster Kubernetes config")
                    except config.ConfigException:
                        config.load_kube_config()
                        logger.info("Loaded kubeconfig")

                    self.core_v1 = client.CoreV1Api()
                    self.apps_v1 = client.AppsV1Api()
                    self.networking_v1 = client.NetworkingV1Api()

                    # Test connection
                    self.core_v1.list_namespaced_pod(namespace=self.namespace, limit=1)
                    self._last_connection_check = current_time

                    if attempt > 0:
                        logger.info("Kubernetes client reconnected", attempt=attempt + 1)

                    return

                except Exception as e:
                    if attempt == self.max_retries - 1:
                        logger.error("Failed to connect to Kubernetes",
                                   error=str(e), attempts=self.max_retries)
                        raise
                    else:
                        logger.warning("Kubernetes connection failed, retrying",
                                     error=str(e), attempt=attempt + 1)
                        time.sleep(self.retry_delay * (2 ** attempt))

    def get_secret_value(self, secret_name: str, key: str) -> str:
        """
        Read a value from a Kubernetes Secret.

        Args:
            secret_name: Name of the secret
            key: Key within the secret data

        Returns:
            Decoded secret value string

        Raises:
            Exception: If secret or key not found
        """
        self._ensure_connection()

        try:
            secret = self.core_v1.read_namespaced_secret(
                name=secret_name,
                namespace=self.namespace
            )

            if key not in secret.data:
                raise Exception(f"Key '{key}' not found in secret {secret_name}")

            decoded = base64.b64decode(secret.data[key]).decode('utf-8')
            logger.debug("Read secret value", secret_name=secret_name, key=key)
            return decoded

        except ApiException as e:
            if e.status == 404:
                logger.warning("Secret not found", secret_name=secret_name)
                raise Exception(f"Secret {secret_name} not found")
            raise
