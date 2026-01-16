"""
Kubernetes client wrapper for PostgreSQL pool management
Handles creation and management of PostgreSQL via CNPG (CloudNativePG) operator
"""

import os
import time
import base64
import structlog
from typing import Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = structlog.get_logger(__name__)

# CNPG CRD configuration
CNPG_API_GROUP = "postgresql.cnpg.io"
CNPG_API_VERSION = "v1"
CNPG_CLUSTER_PLURAL = "clusters"
CNPG_POOLER_PLURAL = "poolers"


class PostgreSQLKubernetesClient:
    """Kubernetes client for managing PostgreSQL database pools via CNPG"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize PostgreSQL Kubernetes client

        Args:
            max_retries: Maximum number of connection retry attempts
            retry_delay: Base delay between retries (with exponential backoff)
        """
        self.core_v1 = None
        self.apps_v1 = None
        self.custom_api = None  # For CNPG CRDs
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
                    self.custom_api = client.CustomObjectsApi()

                    # Test connection (list pods in our namespace)
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

    def _parse_memory(self, memory_str: str) -> int:
        """
        Parse memory string to bytes

        Args:
            memory_str: Memory string like "4G", "2048M", "1024K"

        Returns:
            Memory in bytes
        """
        memory_str = memory_str.upper().strip()
        multipliers = {
            'K': 1024,
            'M': 1024 ** 2,
            'G': 1024 ** 3,
            'T': 1024 ** 4
        }

        for suffix, multiplier in multipliers.items():
            if memory_str.endswith(suffix):
                try:
                    value = float(memory_str[:-1])
                    return int(value * multiplier)
                except ValueError:
                    raise ValueError(f"Invalid memory format: {memory_str}")

        try:
            return int(memory_str)
        except ValueError:
            raise ValueError(f"Invalid memory format: {memory_str}")

    def _calculate_shared_buffers(self, memory_bytes: int) -> str:
        """Calculate PostgreSQL shared_buffers as 25% of total memory"""
        shared_buffers_bytes = int(memory_bytes * 0.25)
        shared_buffers_mb = shared_buffers_bytes // (1024 ** 2)
        return f"{shared_buffers_mb}MB"

    def _calculate_effective_cache_size(self, memory_bytes: int) -> str:
        """Calculate PostgreSQL effective_cache_size as 75% of total memory"""
        cache_size_bytes = int(memory_bytes * 0.75)
        cache_size_mb = cache_size_bytes // (1024 ** 2)
        return f"{cache_size_mb}MB"

    def _calculate_max_connections(self, max_instances: int) -> int:
        """Calculate PostgreSQL max_connections based on expected instances"""
        base_connections_per_instance = 20
        admin_buffer = 10
        return (max_instances * base_connections_per_instance) + admin_buffer

    def create_postgres_pool_service(
        self,
        pool_name: str,
        postgres_password: str,
        pvc_name: str,
        cpu_limit: str = "2",
        memory_limit: str = "4G",
        max_instances: int = 50,
        postgres_version: str = "18",
        postgres_image: str = "postgres:18-alpine",
        network: str = "saasodoo-network"
    ) -> Dict[str, str]:
        """
        Create a PostgreSQL pool StatefulSet in Kubernetes (idempotent)

        If StatefulSet/Service already exist, returns their info.
        Only creates resources that don't exist.

        Args:
            pool_name: Name of the pool
            postgres_password: Admin password for PostgreSQL
            pvc_name: Name of PVC for data persistence
            cpu_limit: CPU limit (e.g., "2" for 2 cores)
            memory_limit: Memory limit (e.g., "4G")
            max_instances: Maximum number of databases this pool will host
            postgres_version: PostgreSQL version
            postgres_image: Full Docker image tag
            network: (Ignored in K8s - using Services)

        Returns:
            Dictionary with service_id (StatefulSet UID) and service_name
        """
        try:
            self._ensure_connection()

            # Check if StatefulSet already exists
            existing_statefulset = None
            try:
                existing_statefulset = self.apps_v1.read_namespaced_stateful_set(
                    name=pool_name,
                    namespace=self.namespace
                )
                logger.info("StatefulSet already exists",
                           pool_name=pool_name,
                           uid=existing_statefulset.metadata.uid,
                           ready_replicas=existing_statefulset.status.ready_replicas)
            except ApiException as e:
                if e.status != 404:
                    raise
                # StatefulSet doesn't exist, will create below

            # Check if Service already exists
            existing_service = None
            try:
                existing_service = self.core_v1.read_namespaced_service(
                    name=pool_name,
                    namespace=self.namespace
                )
                logger.info("Service already exists", pool_name=pool_name)
            except ApiException as e:
                if e.status != 404:
                    raise
                # Service doesn't exist, will create below

            # If both exist, return existing info
            if existing_statefulset and existing_service:
                logger.info("Both StatefulSet and Service already exist, skipping creation",
                           pool_name=pool_name)
                # Note: service_id is the StatefulSet name (not UID) because
                # wait_for_service_ready() uses it to look up by name
                return {
                    "service_id": pool_name,
                    "service_name": pool_name
                }

            # Parse memory limit
            memory_bytes = self._parse_memory(memory_limit)

            # Calculate PostgreSQL tuning parameters
            max_connections = self._calculate_max_connections(max_instances)
            shared_buffers = self._calculate_shared_buffers(memory_bytes)
            effective_cache_size = self._calculate_effective_cache_size(memory_bytes)

            logger.info("Creating PostgreSQL pool StatefulSet",
                       pool_name=pool_name,
                       pvc_name=pvc_name,
                       cpu_limit=cpu_limit,
                       memory_limit=memory_limit,
                       max_connections=max_connections)

            # Environment variables for PostgreSQL
            env_vars = [
                client.V1EnvVar(name="POSTGRES_PASSWORD", value=postgres_password),
                client.V1EnvVar(name="POSTGRES_USER", value="postgres"),
                client.V1EnvVar(name="POSTGRES_DB", value="postgres"),
                client.V1EnvVar(name="PGDATA", value="/var/lib/postgresql/data/pgdata"),
                # Performance tuning
                client.V1EnvVar(name="POSTGRES_MAX_CONNECTIONS", value=str(max_connections)),
                client.V1EnvVar(name="POSTGRES_SHARED_BUFFERS", value=shared_buffers),
                client.V1EnvVar(name="POSTGRES_EFFECTIVE_CACHE_SIZE", value=effective_cache_size),
                client.V1EnvVar(name="POSTGRES_WORK_MEM", value="16MB"),
                client.V1EnvVar(name="POSTGRES_MAINTENANCE_WORK_MEM", value="256MB"),
                client.V1EnvVar(name="POSTGRES_WAL_BUFFERS", value="16MB"),
                client.V1EnvVar(name="POSTGRES_CHECKPOINT_COMPLETION_TARGET", value="0.9"),
                client.V1EnvVar(name="POSTGRES_RANDOM_PAGE_COST", value="1.1"),
            ]

            # Resource requirements
            cpu_limit_str = f"{int(float(cpu_limit) * 1000)}m"
            memory_limit_str = f"{int(memory_bytes / (1024 ** 2))}Mi"
            resources = client.V1ResourceRequirements(
                limits={
                    "cpu": cpu_limit_str,
                    "memory": memory_limit_str
                },
                requests={
                    "cpu": f"{int(float(cpu_limit) * 500)}m",
                    "memory": f"{int(memory_bytes / (1024 ** 2) * 0.5)}Mi"
                }
            )

            # Volume mounts
            volume_mounts = [
                client.V1VolumeMount(
                    name="postgres-data",
                    mount_path="/var/lib/postgresql/data"
                )
            ]

            # Volumes (PVC for persistent storage)
            volumes = [
                client.V1Volume(
                    name="postgres-data",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                )
            ]

            # Liveness probe
            liveness_probe = client.V1Probe(
                _exec=client.V1ExecAction(
                    command=["pg_isready", "-U", "postgres"]
                ),
                initial_delay_seconds=30,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=5
            )

            # Readiness probe
            readiness_probe = client.V1Probe(
                _exec=client.V1ExecAction(
                    command=["pg_isready", "-U", "postgres"]
                ),
                initial_delay_seconds=10,
                period_seconds=5,
                timeout_seconds=3,
                failure_threshold=3
            )

            # Container spec
            container = client.V1Container(
                name="postgres",
                image=postgres_image,
                env=env_vars,
                resources=resources,
                volume_mounts=volume_mounts,
                liveness_probe=liveness_probe,
                readiness_probe=readiness_probe,
                ports=[client.V1ContainerPort(container_port=5432, name="postgres")]
            )

            # Pod template
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={
                        "app": "postgres-pool",
                        "pool-name": pool_name,
                        "saasodoo.service.type": "database-pool"
                    }
                ),
                spec=client.V1PodSpec(
                    containers=[container],
                    volumes=volumes
                )
            )

            # StatefulSet spec
            statefulset_spec = client.V1StatefulSetSpec(
                service_name=pool_name,
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"app": "postgres-pool", "pool-name": pool_name}
                ),
                template=template
            )

            # StatefulSet
            statefulset = client.V1StatefulSet(
                api_version="apps/v1",
                kind="StatefulSet",
                metadata=client.V1ObjectMeta(
                    name=pool_name,
                    labels={
                        "saasodoo.service.type": "database-pool",
                        "saasodoo.pool.name": pool_name,
                        "saasodoo.pool.max_instances": str(max_instances),
                        "saasodoo.postgres.version": postgres_version
                    }
                ),
                spec=statefulset_spec
            )

            # Create StatefulSet if it doesn't exist
            if existing_statefulset:
                created = existing_statefulset
                logger.info("Using existing StatefulSet", pool_name=pool_name)
            else:
                created = self.apps_v1.create_namespaced_stateful_set(
                    namespace=self.namespace,
                    body=statefulset
                )
                logger.info("Created new StatefulSet", pool_name=pool_name)

            # Create Service if it doesn't exist
            if not existing_service:
                service = client.V1Service(
                    api_version="v1",
                    kind="Service",
                    metadata=client.V1ObjectMeta(name=pool_name),
                    spec=client.V1ServiceSpec(
                        selector={"app": "postgres-pool", "pool-name": pool_name},
                        ports=[client.V1ServicePort(port=5432, target_port=5432)],
                        cluster_ip="None"  # Headless service
                    )
                )

                self.core_v1.create_namespaced_service(
                    namespace=self.namespace,
                    body=service
                )
                logger.info("Created new Service", pool_name=pool_name)
            else:
                logger.info("Using existing Service", pool_name=pool_name)

            logger.info("PostgreSQL pool StatefulSet ready",
                       pool_name=pool_name,
                       statefulset_name=created.metadata.name)

            # Note: service_id is the StatefulSet name (not UID) because
            # wait_for_service_ready() uses it to look up the StatefulSet by name
            return {
                "service_id": pool_name,
                "service_name": pool_name
            }

        except Exception as e:
            logger.error("Failed to create PostgreSQL pool StatefulSet",
                        pool_name=pool_name, error=str(e))
            raise

    def wait_for_service_ready(
        self,
        service_id: str,
        timeout: int = 180,
        check_interval: int = 5
    ) -> bool:
        """Wait for StatefulSet to be ready"""
        try:
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    # Get StatefulSet by name (service_id is the name in K8s)
                    statefulset = self.apps_v1.read_namespaced_stateful_set(
                        service_id, self.namespace
                    )

                    # Check if ready
                    if statefulset.status.ready_replicas == statefulset.spec.replicas:
                        logger.info("StatefulSet is ready", name=service_id)
                        return True

                    logger.debug("Waiting for StatefulSet to be ready",
                               name=service_id,
                               ready=statefulset.status.ready_replicas,
                               desired=statefulset.spec.replicas)

                except ApiException:
                    pass

                time.sleep(check_interval)

            logger.warning("StatefulSet did not become ready within timeout",
                         name=service_id, timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error waiting for StatefulSet",
                       name=service_id, error=str(e))
            return False

    def remove_service(self, service_id: str) -> bool:
        """Remove StatefulSet and associated Service"""
        try:
            self._ensure_connection()

            # Delete StatefulSet
            self.apps_v1.delete_namespaced_stateful_set(
                service_id,
                self.namespace,
                body=client.V1DeleteOptions(
                    propagation_policy='Foreground'
                )
            )

            # Delete Service
            try:
                self.core_v1.delete_namespaced_service(service_id, self.namespace)
            except ApiException:
                pass  # Service might not exist

            logger.info("StatefulSet removed", name=service_id)
            return True

        except Exception as e:
            logger.error("Failed to remove StatefulSet",
                       name=service_id, error=str(e))
            return False

    def get_service_info(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get StatefulSet information"""
        try:
            self._ensure_connection()

            statefulset = self.apps_v1.read_namespaced_stateful_set(
                service_id, self.namespace
            )

            return {
                "service_id": statefulset.metadata.uid,
                "service_name": statefulset.metadata.name,
                "replicas": statefulset.spec.replicas,
                "ready_replicas": statefulset.status.ready_replicas or 0,
                "status": "running" if statefulset.status.ready_replicas == statefulset.spec.replicas else "starting",
                "created": statefulset.metadata.creation_timestamp.isoformat()
            }

        except ApiException as e:
            if e.status == 404:
                return None
            logger.error("Failed to get StatefulSet info",
                       name=service_id, error=str(e))
            return None

    def update_service_resources(
        self,
        service_id: str,
        cpu_limit: str,
        memory_limit: str
    ) -> bool:
        """Update StatefulSet resource limits"""
        try:
            self._ensure_connection()

            # Parse limits
            memory_bytes = self._parse_memory(memory_limit)
            cpu_limit_str = f"{int(float(cpu_limit) * 1000)}m"
            memory_limit_str = f"{int(memory_bytes / (1024 ** 2))}Mi"

            # Patch StatefulSet
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "postgres",
                                "resources": {
                                    "limits": {
                                        "cpu": cpu_limit_str,
                                        "memory": memory_limit_str
                                    },
                                    "requests": {
                                        "cpu": f"{int(float(cpu_limit) * 500)}m",
                                        "memory": f"{int(memory_bytes / (1024 ** 2) * 0.5)}Mi"
                                    }
                                }
                            }]
                        }
                    }
                }
            }

            self.apps_v1.patch_namespaced_stateful_set(
                service_id,
                self.namespace,
                patch
            )

            logger.info("Updated StatefulSet resources",
                       name=service_id,
                       cpu=cpu_limit_str,
                       memory=memory_limit_str)
            return True

        except Exception as e:
            logger.error("Failed to update StatefulSet resources",
                       name=service_id, error=str(e))
            return False

    def create_postgres_pvc(self, pvc_name: str, storage_size: str) -> bool:
        """
        Create PVC for PostgreSQL server (idempotent)

        If PVC already exists and is healthy (Bound or Pending), returns True.
        Only creates if PVC doesn't exist.

        Args:
            pvc_name: Name of the PVC (e.g., 'postgres-pool-1', 'postgres-dedicated-{uuid}')
            storage_size: Storage size in Kubernetes format (e.g., '50Gi', '100Gi')

        Returns:
            True if successful (either created or already exists)

        Raises:
            Exception if PVC creation fails or existing PVC is in failed state
        """
        try:
            self._ensure_connection()

            # Check if PVC already exists
            try:
                existing_pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                    name=pvc_name,
                    namespace=self.namespace
                )
                pvc_phase = existing_pvc.status.phase

                if pvc_phase in ('Bound', 'Pending'):
                    logger.info("PVC already exists and is healthy",
                               pvc_name=pvc_name,
                               phase=pvc_phase,
                               size=existing_pvc.spec.resources.requests.get('storage'))
                    return True
                elif pvc_phase == 'Lost':
                    raise Exception(f"PVC {pvc_name} exists but is in Lost state - manual intervention required")
                else:
                    logger.warning("PVC exists in unexpected state",
                                 pvc_name=pvc_name,
                                 phase=pvc_phase)
                    # Continue and let it be - might recover
                    return True

            except ApiException as e:
                if e.status != 404:
                    raise
                # PVC doesn't exist, proceed to create

            from datetime import datetime

            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(
                    name=pvc_name,
                    namespace=self.namespace,
                    labels={
                        "app": "postgres-server",
                        "managed-by": "saasodoo-database-service"
                    },
                    annotations={
                        "saasodoo.io/created-at": datetime.utcnow().isoformat()
                    }
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],  # RWO for single PostgreSQL server
                    storage_class_name="rook-cephfs",
                    resources=client.V1ResourceRequirements(
                        requests={"storage": storage_size}
                    )
                )
            )

            self.core_v1.create_namespaced_persistent_volume_claim(
                namespace=self.namespace,
                body=pvc
            )

            logger.info("Created PostgreSQL PVC", pvc_name=pvc_name, size=storage_size)
            return True

        except Exception as e:
            logger.error("Failed to create PVC",
                       pvc_name=pvc_name,
                       size=storage_size,
                       error=str(e))
            raise

    def delete_pvc(self, pvc_name: str) -> bool:
        """
        Delete PostgreSQL PVC

        Args:
            pvc_name: Name of the PVC to delete

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            self.core_v1.delete_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(propagation_policy='Foreground')
            )

            logger.info("Deleted PVC", pvc_name=pvc_name)
            return True

        except ApiException as e:
            if e.status == 404:
                logger.warning("PVC not found (already deleted)", pvc_name=pvc_name)
                return True
            logger.error("Failed to delete PVC", pvc_name=pvc_name, error=str(e))
            return False

        except Exception as e:
            logger.error("Failed to delete PVC", pvc_name=pvc_name, error=str(e))
            return False

    # ==================== CNPG Methods ====================

    def create_cnpg_cluster(
        self,
        cluster_name: str,
        storage_size: str = "50Gi",
        cpu_limit: str = "2",
        memory_limit: str = "4G",
        max_instances: int = 50,
        instances: int = 1,
        storage_class: str = "rook-cephfs"
    ) -> Dict[str, str]:
        """
        Create a CNPG PostgreSQL Cluster (idempotent)

        CNPG automatically:
        - Creates PVC for storage
        - Generates admin password in Secret: {cluster_name}-superuser
        - Creates Services: {cluster_name}-rw, {cluster_name}-r, {cluster_name}-ro

        Args:
            cluster_name: Name of the cluster (e.g., 'postgres-pool-1')
            storage_size: Storage size (e.g., '50Gi')
            cpu_limit: CPU limit (e.g., '2')
            memory_limit: Memory limit (e.g., '4G')
            max_instances: Max databases for connection tuning
            instances: Number of PostgreSQL replicas (1 for shared, 1+ for HA)
            storage_class: Kubernetes StorageClass to use

        Returns:
            Dictionary with cluster_name and status
        """
        try:
            self._ensure_connection()

            # Check if cluster already exists
            try:
                existing = self.custom_api.get_namespaced_custom_object(
                    group=CNPG_API_GROUP,
                    version=CNPG_API_VERSION,
                    namespace=self.namespace,
                    plural=CNPG_CLUSTER_PLURAL,
                    name=cluster_name
                )
                logger.info("CNPG Cluster already exists",
                           cluster_name=cluster_name,
                           status=existing.get('status', {}).get('phase', 'unknown'))
                return {
                    "cluster_name": cluster_name,
                    "status": "exists"
                }
            except ApiException as e:
                if e.status != 404:
                    raise
                # Cluster doesn't exist, create it

            # Parse memory for PostgreSQL tuning
            memory_bytes = self._parse_memory(memory_limit)
            max_connections = self._calculate_max_connections(max_instances)
            shared_buffers_mb = int(memory_bytes * 0.25 / (1024 ** 2))
            effective_cache_mb = int(memory_bytes * 0.75 / (1024 ** 2))

            # Convert limits to K8s format
            memory_limit_mi = f"{int(memory_bytes / (1024 ** 2))}Mi"
            memory_request_mi = f"{int(memory_bytes * 0.5 / (1024 ** 2))}Mi"
            cpu_limit_m = f"{int(float(cpu_limit) * 1000)}m"
            cpu_request_m = f"{int(float(cpu_limit) * 500)}m"

            logger.info("Creating CNPG Cluster",
                       cluster_name=cluster_name,
                       storage_size=storage_size,
                       instances=instances,
                       max_connections=max_connections)

            # CNPG Cluster manifest
            cluster_manifest = {
                "apiVersion": f"{CNPG_API_GROUP}/{CNPG_API_VERSION}",
                "kind": "Cluster",
                "metadata": {
                    "name": cluster_name,
                    "namespace": self.namespace,
                    "labels": {
                        "saasodoo.service.type": "database-pool",
                        "saasodoo.pool.name": cluster_name,
                        "saasodoo.pool.max_instances": str(max_instances)
                    }
                },
                "spec": {
                    "instances": instances,
                    # Enable superuser access - creates {cluster}-superuser secret
                    "enableSuperuserAccess": True,
                    "postgresql": {
                        "parameters": {
                            "max_connections": str(max_connections),
                            "shared_buffers": f"{shared_buffers_mb}MB",
                            "effective_cache_size": f"{effective_cache_mb}MB",
                            "work_mem": "16MB",
                            "maintenance_work_mem": "256MB",
                            "wal_buffers": "16MB",
                            "checkpoint_completion_target": "0.9",
                            "random_page_cost": "1.1"
                        }
                    },
                    "storage": {
                        "size": storage_size,
                        "storageClass": storage_class
                    },
                    "resources": {
                        "requests": {
                            "memory": memory_request_mi,
                            "cpu": cpu_request_m
                        },
                        "limits": {
                            "memory": memory_limit_mi,
                            "cpu": cpu_limit_m
                        }
                    }
                }
            }

            # Create the cluster
            self.custom_api.create_namespaced_custom_object(
                group=CNPG_API_GROUP,
                version=CNPG_API_VERSION,
                namespace=self.namespace,
                plural=CNPG_CLUSTER_PLURAL,
                body=cluster_manifest
            )

            logger.info("CNPG Cluster created", cluster_name=cluster_name)
            return {
                "cluster_name": cluster_name,
                "status": "created"
            }

        except Exception as e:
            logger.error("Failed to create CNPG Cluster",
                        cluster_name=cluster_name, error=str(e))
            raise

    def create_cnpg_pooler(
        self,
        cluster_name: str,
        pooler_instances: int = 2,
        pool_mode: str = "transaction",
        max_client_conn: int = 1000,
        default_pool_size: int = 20
    ) -> Dict[str, str]:
        """
        Create a CNPG Pooler (PgBouncer) for a cluster (idempotent)

        Args:
            cluster_name: Name of the CNPG cluster to attach to
            pooler_instances: Number of PgBouncer replicas
            pool_mode: PgBouncer pool mode (transaction recommended for Odoo)
            max_client_conn: Maximum client connections
            default_pool_size: Default pool size per database

        Returns:
            Dictionary with pooler_name and status
        """
        try:
            self._ensure_connection()

            pooler_name = f"{cluster_name}-pooler"

            # Check if pooler already exists
            try:
                existing = self.custom_api.get_namespaced_custom_object(
                    group=CNPG_API_GROUP,
                    version=CNPG_API_VERSION,
                    namespace=self.namespace,
                    plural=CNPG_POOLER_PLURAL,
                    name=pooler_name
                )
                logger.info("CNPG Pooler already exists", pooler_name=pooler_name)
                return {
                    "pooler_name": pooler_name,
                    "status": "exists"
                }
            except ApiException as e:
                if e.status != 404:
                    raise
                # Pooler doesn't exist, create it

            logger.info("Creating CNPG Pooler",
                       pooler_name=pooler_name,
                       cluster_name=cluster_name,
                       instances=pooler_instances)

            # CNPG Pooler manifest
            pooler_manifest = {
                "apiVersion": f"{CNPG_API_GROUP}/{CNPG_API_VERSION}",
                "kind": "Pooler",
                "metadata": {
                    "name": pooler_name,
                    "namespace": self.namespace
                },
                "spec": {
                    "cluster": {
                        "name": cluster_name
                    },
                    "instances": pooler_instances,
                    "type": "rw",
                    "pgbouncer": {
                        "poolMode": pool_mode,
                        "parameters": {
                            "max_client_conn": str(max_client_conn),
                            "default_pool_size": str(default_pool_size)
                        }
                    },
                    "template": {
                        "spec": {
                            "containers": [{
                                "name": "pgbouncer",
                                "resources": {
                                    "requests": {
                                        "cpu": "25m",
                                        "memory": "48Mi"
                                    },
                                    "limits": {
                                        "cpu": "100m",
                                        "memory": "96Mi"
                                    }
                                }
                            }]
                        }
                    }
                }
            }

            # Create the pooler
            self.custom_api.create_namespaced_custom_object(
                group=CNPG_API_GROUP,
                version=CNPG_API_VERSION,
                namespace=self.namespace,
                plural=CNPG_POOLER_PLURAL,
                body=pooler_manifest
            )

            logger.info("CNPG Pooler created", pooler_name=pooler_name)
            return {
                "pooler_name": pooler_name,
                "status": "created"
            }

        except Exception as e:
            logger.error("Failed to create CNPG Pooler",
                        cluster_name=cluster_name, error=str(e))
            raise

    def wait_for_cnpg_cluster_ready(
        self,
        cluster_name: str,
        timeout: int = 300,
        check_interval: int = 10
    ) -> bool:
        """
        Wait for CNPG Cluster to be ready

        Args:
            cluster_name: Name of the cluster
            timeout: Maximum wait time in seconds
            check_interval: Time between checks in seconds

        Returns:
            True if cluster is ready, False if timeout
        """
        try:
            self._ensure_connection()
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    cluster = self.custom_api.get_namespaced_custom_object(
                        group=CNPG_API_GROUP,
                        version=CNPG_API_VERSION,
                        namespace=self.namespace,
                        plural=CNPG_CLUSTER_PLURAL,
                        name=cluster_name
                    )

                    status = cluster.get('status', {})
                    phase = status.get('phase', 'unknown')
                    ready_instances = status.get('readyInstances', 0)
                    desired_instances = cluster.get('spec', {}).get('instances', 1)

                    logger.debug("Waiting for CNPG Cluster",
                               cluster_name=cluster_name,
                               phase=phase,
                               ready=ready_instances,
                               desired=desired_instances)

                    # Check if cluster is ready
                    if phase == "Cluster in healthy state" and ready_instances >= desired_instances:
                        logger.info("CNPG Cluster is ready",
                                   cluster_name=cluster_name,
                                   phase=phase)
                        return True

                except ApiException as e:
                    if e.status == 404:
                        logger.warning("CNPG Cluster not found", cluster_name=cluster_name)
                    else:
                        logger.warning("Error checking cluster status",
                                     cluster_name=cluster_name, error=str(e))

                time.sleep(check_interval)

            logger.warning("CNPG Cluster did not become ready within timeout",
                         cluster_name=cluster_name, timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error waiting for CNPG Cluster",
                       cluster_name=cluster_name, error=str(e))
            return False

    def get_secret_value(self, secret_name: str, key: str) -> Optional[str]:
        """
        Read a value from a Kubernetes Secret

        Args:
            secret_name: Name of the secret (e.g., 'postgres-pool-1-superuser')
            key: Key within the secret (e.g., 'password', 'username')

        Returns:
            Decoded secret value, or None if not found
        """
        try:
            self._ensure_connection()

            secret = self.core_v1.read_namespaced_secret(
                name=secret_name,
                namespace=self.namespace
            )

            if secret.data and key in secret.data:
                # Secret values are base64 encoded
                encoded_value = secret.data[key]
                decoded_value = base64.b64decode(encoded_value).decode('utf-8')
                logger.debug("Read secret value", secret_name=secret_name, key=key)
                return decoded_value
            else:
                logger.warning("Key not found in secret",
                             secret_name=secret_name, key=key)
                return None

        except ApiException as e:
            if e.status == 404:
                logger.warning("Secret not found", secret_name=secret_name)
                return None
            logger.error("Failed to read secret",
                       secret_name=secret_name, error=str(e))
            return None

        except Exception as e:
            logger.error("Error reading secret",
                       secret_name=secret_name, error=str(e))
            return None

    def delete_cnpg_cluster(self, cluster_name: str) -> bool:
        """
        Delete a CNPG Cluster and its associated Pooler

        Args:
            cluster_name: Name of the cluster to delete

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            # Delete pooler first (if exists)
            pooler_name = f"{cluster_name}-pooler"
            try:
                self.custom_api.delete_namespaced_custom_object(
                    group=CNPG_API_GROUP,
                    version=CNPG_API_VERSION,
                    namespace=self.namespace,
                    plural=CNPG_POOLER_PLURAL,
                    name=pooler_name
                )
                logger.info("Deleted CNPG Pooler", pooler_name=pooler_name)
            except ApiException as e:
                if e.status != 404:
                    logger.warning("Failed to delete pooler",
                                 pooler_name=pooler_name, error=str(e))

            # Delete cluster
            self.custom_api.delete_namespaced_custom_object(
                group=CNPG_API_GROUP,
                version=CNPG_API_VERSION,
                namespace=self.namespace,
                plural=CNPG_CLUSTER_PLURAL,
                name=cluster_name
            )

            logger.info("Deleted CNPG Cluster", cluster_name=cluster_name)
            return True

        except ApiException as e:
            if e.status == 404:
                logger.warning("CNPG Cluster not found (already deleted)",
                             cluster_name=cluster_name)
                return True
            logger.error("Failed to delete CNPG Cluster",
                       cluster_name=cluster_name, error=str(e))
            return False

        except Exception as e:
            logger.error("Error deleting CNPG Cluster",
                       cluster_name=cluster_name, error=str(e))
            return False

    def get_cnpg_cluster_status(self, cluster_name: str) -> Optional[Dict[str, Any]]:
        """
        Get status of a CNPG Cluster

        Args:
            cluster_name: Name of the cluster

        Returns:
            Status dict or None if not found
        """
        try:
            self._ensure_connection()

            cluster = self.custom_api.get_namespaced_custom_object(
                group=CNPG_API_GROUP,
                version=CNPG_API_VERSION,
                namespace=self.namespace,
                plural=CNPG_CLUSTER_PLURAL,
                name=cluster_name
            )

            status = cluster.get('status', {})
            return {
                "cluster_name": cluster_name,
                "phase": status.get('phase', 'unknown'),
                "ready_instances": status.get('readyInstances', 0),
                "instances": cluster.get('spec', {}).get('instances', 1),
                "current_primary": status.get('currentPrimary', ''),
                "conditions": status.get('conditions', [])
            }

        except ApiException as e:
            if e.status == 404:
                return None
            logger.error("Failed to get cluster status",
                       cluster_name=cluster_name, error=str(e))
            return None
