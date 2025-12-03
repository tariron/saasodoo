# Kubernetes Code Refactoring Guide

**Target Audience**: Python developers (beginner to intermediate)
**Timeline**: Weeks 4-6 of migration
**Estimated Effort**: 10-14 weeks total development time

---

## Table of Contents

1. [Refactoring Overview](#refactoring-overview)
2. [Docker SDK to Kubernetes API Migration](#docker-sdk-to-kubernetes-api-migration)
3. [CephFS to Kubernetes CSI](#cephfs-to-kubernetes-csi)
4. [Environment Variable Updates](#environment-variable-updates)
5. [Database Connection Adaptations](#database-connection-adaptations)
6. [Service Discovery Changes](#service-discovery-changes)
7. [Testing Strategy for Refactored Code](#testing-strategy-for-refactored-code)
8. [Migration Checklist](#migration-checklist)

---

## Refactoring Overview

### Critical Files Requiring Changes

| Priority | File | Lines | Effort | Description |
|----------|------|-------|--------|-------------|
| **CRITICAL** | `services/instance-service/app/utils/docker_client.py` | 800 | 3 weeks | Complete rewrite to Kubernetes API |
| **CRITICAL** | `services/instance-service/app/tasks/monitoring.py` | 1,248 | 3-4 weeks | Docker events → K8s Watch API |
| **HIGH** | `services/instance-service/app/tasks/provisioning.py` | 580 | 2-3 weeks | CephFS + Docker service creation |
| **HIGH** | `services/instance-service/app/tasks/lifecycle.py` | 594 | 2 weeks | Lifecycle management refactoring |
| **MEDIUM** | `services/instance-service/Dockerfile` | 58 | 1 day | Remove Docker socket mount |
| **MEDIUM** | `services/instance-service/app/celery_config.py` | 76 | 2 days | Configuration review |

### Key Pattern Translations

| Docker Swarm Pattern | Kubernetes Equivalent |
|---------------------|----------------------|
| `docker.services.create()` | `apps_v1_api.create_namespaced_deployment()` |
| `service.scale(replicas=N)` | `apps_v1_api.patch_namespaced_deployment_scale()` |
| `service.force_update()` | `apps_v1_api.patch_namespaced_deployment()` (update image tag) |
| `docker.events()` stream | `watch.Watch().stream(v1.list_namespaced_pod)` |
| Service naming: `odoo-{db}-{id}` | Deployment + Service: `odoo-{db}-{id}` |
| CephFS bind mount | PersistentVolumeClaim + volumeMounts |
| Traefik labels on service | IngressRoute CRD |
| Docker network | Kubernetes Service (ClusterIP) |

---

## Docker SDK to Kubernetes API Migration

### Step 1: Install Kubernetes Python Client

Update `services/instance-service/requirements.txt`:

```diff
- docker==7.1.0
+ kubernetes==29.0.0
  asyncio==3.4.3
  httpx==0.24.1
```

### Step 2: Create New Kubernetes Client Wrapper

**File**: `services/instance-service/app/utils/k8s_client.py` (NEW FILE)

```python
"""
Kubernetes Client Wrapper for Odoo Instance Management
Replaces docker_client.py with Kubernetes API equivalents
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
import asyncio

logger = logging.getLogger(__name__)


class KubernetesClientWrapper:
    """Wrapper for Kubernetes API operations on Odoo instances"""

    def __init__(self):
        """Initialize Kubernetes client"""
        try:
            # Load in-cluster config when running in Kubernetes
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except config.ConfigException:
            # Fall back to kubeconfig for local development
            config.load_kube_config()
            logger.info("Loaded kubeconfig from local environment")

        # Initialize API clients
        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        self.networking_v1 = client.NetworkingV1Api()

        # Configuration from environment
        self.namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')
        self.image_name = os.getenv('ODOO_IMAGE', 'bitnami/odoo:17')
        self.storage_class = os.getenv('STORAGE_CLASS_NAME', 'cephfs-saasodoo')

        # Naming pattern for services (matches Docker Swarm pattern)
        self.service_pattern = re.compile(r'^odoo-([^-]+)-([a-f0-9]{8})$')

    async def create_odoo_instance(
        self,
        instance_id: str,
        database_name: str,
        cpu_limit: str = "1000m",
        memory_limit: str = "2Gi",
        storage_size: str = "10Gi",
        environment_vars: Optional[Dict[str, str]] = None,
        subdomain: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Create Kubernetes Deployment, Service, PVC, and Ingress for Odoo instance

        Args:
            instance_id: Unique instance identifier (8-char hex)
            database_name: Database name (customer_db format)
            cpu_limit: CPU limit (e.g., "1000m" = 1 CPU)
            memory_limit: Memory limit (e.g., "2Gi")
            storage_size: Storage size for PVC (e.g., "10Gi")
            environment_vars: Additional environment variables
            subdomain: Subdomain for ingress (e.g., "customer1")

        Returns:
            dict: Created resource details
        """
        deployment_name = f"odoo-{database_name}-{instance_id}"

        try:
            # 1. Create PersistentVolumeClaim
            pvc = await self._create_pvc(
                name=f"{deployment_name}-storage",
                storage_size=storage_size
            )

            # 2. Create Deployment
            deployment = await self._create_deployment(
                name=deployment_name,
                instance_id=instance_id,
                database_name=database_name,
                pvc_name=pvc.metadata.name,
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                environment_vars=environment_vars or {}
            )

            # 3. Create Service
            service = await self._create_service(
                name=deployment_name,
                deployment_name=deployment_name
            )

            # 4. Create IngressRoute (Traefik CRD)
            if subdomain:
                ingress = await self._create_ingress(
                    name=deployment_name,
                    service_name=deployment_name,
                    subdomain=subdomain
                )
            else:
                ingress = None

            logger.info(f"Successfully created Odoo instance: {deployment_name}")

            return {
                'deployment_name': deployment_name,
                'service_name': service.metadata.name,
                'pvc_name': pvc.metadata.name,
                'ingress_created': ingress is not None,
                'namespace': self.namespace,
                'status': 'creating'
            }

        except ApiException as e:
            logger.error(f"Failed to create Odoo instance {deployment_name}: {e}")
            # Cleanup on failure
            await self._cleanup_instance(deployment_name)
            raise

    async def _create_pvc(self, name: str, storage_size: str) -> client.V1PersistentVolumeClaim:
        """Create PersistentVolumeClaim for Odoo data"""
        pvc = client.V1PersistentVolumeClaim(
            api_version="v1",
            kind="PersistentVolumeClaim",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self.namespace,
                labels={
                    'app': 'odoo',
                    'managed-by': 'saasodoo'
                }
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteMany"],  # RWX for CephFS
                storage_class_name=self.storage_class,
                resources=client.V1ResourceRequirements(
                    requests={"storage": storage_size}
                )
            )
        )

        return self.core_v1.create_namespaced_persistent_volume_claim(
            namespace=self.namespace,
            body=pvc
        )

    async def _create_deployment(
        self,
        name: str,
        instance_id: str,
        database_name: str,
        pvc_name: str,
        cpu_limit: str,
        memory_limit: str,
        environment_vars: Dict[str, str]
    ) -> client.V1Deployment:
        """Create Kubernetes Deployment for Odoo instance"""

        # Build environment variables
        env_vars = [
            client.V1EnvVar(name="ODOO_DATABASE_HOST", value=os.getenv('ODOO_POSTGRES_HOST', 'postgres')),
            client.V1EnvVar(name="ODOO_DATABASE_PORT", value=os.getenv('ODOO_POSTGRES_PORT', '5432')),
            client.V1EnvVar(name="ODOO_DATABASE_NAME", value=database_name),
            client.V1EnvVar(
                name="ODOO_DATABASE_USER",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="odoo-db-credentials",
                        key="username"
                    )
                )
            ),
            client.V1EnvVar(
                name="ODOO_DATABASE_PASSWORD",
                value_from=client.V1EnvVarSource(
                    secret_key_ref=client.V1SecretKeySelector(
                        name="odoo-db-credentials",
                        key="password"
                    )
                )
            ),
        ]

        # Add custom environment variables
        for key, value in environment_vars.items():
            env_vars.append(client.V1EnvVar(name=key, value=value))

        # Define container
        container = client.V1Container(
            name="odoo",
            image=self.image_name,
            ports=[client.V1ContainerPort(container_port=8069, name="http")],
            env=env_vars,
            resources=client.V1ResourceRequirements(
                requests={"cpu": cpu_limit, "memory": memory_limit},
                limits={"cpu": cpu_limit, "memory": memory_limit}
            ),
            volume_mounts=[
                client.V1VolumeMount(
                    name="odoo-data",
                    mount_path="/bitnami/odoo"
                )
            ],
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/web/health", port=8069),
                initial_delay_seconds=120,
                period_seconds=30,
                timeout_seconds=5,
                failure_threshold=3
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/web/health", port=8069),
                initial_delay_seconds=30,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=3
            )
        )

        # Define pod template
        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    'app': 'odoo',
                    'instance-id': instance_id,
                    'database': database_name,
                    'managed-by': 'saasodoo'
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                volumes=[
                    client.V1Volume(
                        name="odoo-data",
                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=pvc_name
                        )
                    )
                ]
            )
        )

        # Define deployment
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self.namespace,
                labels={
                    'app': 'odoo',
                    'instance-id': instance_id,
                    'managed-by': 'saasodoo'
                }
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,  # Single replica for stateful Odoo instances
                selector=client.V1LabelSelector(
                    match_labels={
                        'app': 'odoo',
                        'instance-id': instance_id
                    }
                ),
                template=pod_template,
                strategy=client.V1DeploymentStrategy(
                    type="Recreate"  # Important: Avoid parallel pods for stateful app
                )
            )
        )

        return self.apps_v1.create_namespaced_deployment(
            namespace=self.namespace,
            body=deployment
        )

    async def _create_service(self, name: str, deployment_name: str) -> client.V1Service:
        """Create Kubernetes Service for Odoo deployment"""
        service = client.V1Service(
            api_version="v1",
            kind="Service",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=self.namespace,
                labels={'app': 'odoo', 'managed-by': 'saasodoo'}
            ),
            spec=client.V1ServiceSpec(
                type="ClusterIP",
                selector={'app': 'odoo', 'instance-id': deployment_name.split('-')[-1]},
                ports=[
                    client.V1ServicePort(
                        name="http",
                        port=8069,
                        target_port=8069,
                        protocol="TCP"
                    )
                ]
            )
        )

        return self.core_v1.create_namespaced_service(
            namespace=self.namespace,
            body=service
        )

    async def _create_ingress(
        self,
        name: str,
        service_name: str,
        subdomain: str
    ):
        """
        Create Traefik IngressRoute (CRD)

        Note: This requires Traefik CRD to be installed.
        For standard Ingress, use networking_v1.create_namespaced_ingress() instead.
        """
        # Traefik IngressRoute uses custom CRD - requires CustomObjectsApi
        from kubernetes.client import CustomObjectsApi
        custom_api = CustomObjectsApi()

        host = f"{subdomain}.{os.getenv('BASE_DOMAIN', 'saasodoo.com')}"

        ingress_route = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {
                "name": name,
                "namespace": self.namespace
            },
            "spec": {
                "entryPoints": ["web", "websecure"],
                "routes": [
                    {
                        "match": f"Host(`{host}`)",
                        "kind": "Rule",
                        "services": [
                            {
                                "name": service_name,
                                "port": 8069
                            }
                        ]
                    }
                ]
            }
        }

        return custom_api.create_namespaced_custom_object(
            group="traefik.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="ingressroutes",
            body=ingress_route
        )

    async def get_instance_status(self, deployment_name: str) -> Dict[str, any]:
        """
        Get status of an Odoo instance

        Returns:
            dict: Status information including pod state, ready replicas, etc.
        """
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace
            )

            # Get pod status
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"instance-id={deployment_name.split('-')[-1]}"
            )

            pod_status = "unknown"
            if pods.items:
                pod = pods.items[0]
                pod_status = pod.status.phase.lower()

            return {
                'deployment_name': deployment_name,
                'desired_replicas': deployment.spec.replicas,
                'ready_replicas': deployment.status.ready_replicas or 0,
                'available_replicas': deployment.status.available_replicas or 0,
                'pod_status': pod_status,
                'status': self._map_pod_status_to_instance_status(pod_status)
            }

        except ApiException as e:
            if e.status == 404:
                return {'deployment_name': deployment_name, 'status': 'not_found'}
            raise

    def _map_pod_status_to_instance_status(self, pod_status: str) -> str:
        """Map Kubernetes pod status to instance status"""
        mapping = {
            'pending': 'creating',
            'running': 'running',
            'succeeded': 'stopped',
            'failed': 'error',
            'unknown': 'error'
        }
        return mapping.get(pod_status, 'unknown')

    async def scale_instance(self, deployment_name: str, replicas: int) -> bool:
        """
        Scale instance (start=1, stop=0)

        Note: For Odoo instances, we typically use 0 (stopped) or 1 (running).
        Horizontal scaling is NOT recommended for stateful Odoo instances.
        """
        try:
            scale = client.V1Scale(
                metadata=client.V1ObjectMeta(name=deployment_name, namespace=self.namespace),
                spec=client.V1ScaleSpec(replicas=replicas)
            )

            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body=scale
            )

            logger.info(f"Scaled {deployment_name} to {replicas} replicas")
            return True

        except ApiException as e:
            logger.error(f"Failed to scale {deployment_name}: {e}")
            return False

    async def delete_instance(self, deployment_name: str) -> bool:
        """Delete all resources for an Odoo instance"""
        try:
            await self._cleanup_instance(deployment_name)
            logger.info(f"Successfully deleted instance: {deployment_name}")
            return True
        except ApiException as e:
            logger.error(f"Failed to delete instance {deployment_name}: {e}")
            return False

    async def _cleanup_instance(self, deployment_name: str):
        """Clean up all Kubernetes resources for an instance"""
        # Delete Deployment
        try:
            self.apps_v1.delete_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body=client.V1DeleteOptions(propagation_policy='Foreground')
            )
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Failed to delete deployment {deployment_name}: {e}")

        # Delete Service
        try:
            self.core_v1.delete_namespaced_service(
                name=deployment_name,
                namespace=self.namespace
            )
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Failed to delete service {deployment_name}: {e}")

        # Delete PVC (optional - set RETAIN_STORAGE=true to keep data)
        if not os.getenv('RETAIN_STORAGE', 'false').lower() == 'true':
            try:
                self.core_v1.delete_namespaced_persistent_volume_claim(
                    name=f"{deployment_name}-storage",
                    namespace=self.namespace
                )
            except ApiException as e:
                if e.status != 404:
                    logger.warning(f"Failed to delete PVC for {deployment_name}: {e}")

        # Delete IngressRoute (Traefik CRD)
        try:
            from kubernetes.client import CustomObjectsApi
            custom_api = CustomObjectsApi()
            custom_api.delete_namespaced_custom_object(
                group="traefik.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="ingressroutes",
                name=deployment_name
            )
        except ApiException as e:
            if e.status != 404:
                logger.warning(f"Failed to delete IngressRoute for {deployment_name}: {e}")

    async def list_instances(self) -> List[Dict[str, any]]:
        """List all managed Odoo instances"""
        try:
            deployments = self.apps_v1.list_namespaced_deployment(
                namespace=self.namespace,
                label_selector="managed-by=saasodoo,app=odoo"
            )

            instances = []
            for deployment in deployments.items:
                status = await self.get_instance_status(deployment.metadata.name)
                instances.append(status)

            return instances

        except ApiException as e:
            logger.error(f"Failed to list instances: {e}")
            return []

    async def watch_pod_events(self, callback_func):
        """
        Watch Kubernetes pod events in real-time

        This replaces Docker event monitoring.
        Call this in a background task/thread.

        Args:
            callback_func: Async function to call with event data
                          Signature: async def callback(event_type, pod_name, pod_status)
        """
        w = watch.Watch()

        try:
            async for event in w.stream(
                self.core_v1.list_namespaced_pod,
                namespace=self.namespace,
                label_selector="managed-by=saasodoo,app=odoo",
                timeout_seconds=0  # Infinite watch
            ):
                event_type = event['type']  # ADDED, MODIFIED, DELETED
                pod = event['object']
                pod_name = pod.metadata.name
                pod_status = pod.status.phase

                # Extract instance ID from pod name
                match = self.service_pattern.match(pod_name.rsplit('-', 2)[0])
                if match:
                    await callback_func(event_type, pod_name, pod_status, pod)

        except Exception as e:
            logger.error(f"Error in pod event watch: {e}")
            # Implement reconnection logic here if needed
            raise


# Singleton instance
_k8s_client = None

def get_k8s_client() -> KubernetesClientWrapper:
    """Get singleton Kubernetes client instance"""
    global _k8s_client
    if _k8s_client is None:
        _k8s_client = KubernetesClientWrapper()
    return _k8s_client
```

### Step 3: Update Provisioning Tasks

**File**: `services/instance-service/app/tasks/provisioning.py`

**Changes needed** (line-by-line annotations):

```python
# OLD (Lines 1-10): Docker imports
from app.utils.docker_client import DockerClientWrapper
import docker

# NEW: Kubernetes imports
from app.utils.k8s_client import get_k8s_client
from kubernetes.client.rest import ApiException
```

```python
# OLD (Lines 52-86): CephFS quota with subprocess
async def create_cephfs_volume_with_quota(volume_name: str, quota_gb: int) -> str:
    """Create CephFS volume with quota using setfattr"""
    cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
    os.makedirs(cephfs_path, exist_ok=True)

    quota_bytes = quota_gb * 1024 * 1024 * 1024
    cmd = ['setfattr', '-n', 'ceph.quota.max_bytes', '-v', str(quota_bytes), cephfs_path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)

    return cephfs_path

# NEW: Use Kubernetes PVC with quota
async def create_storage_for_instance(instance_id: str, quota_gb: int) -> str:
    """Create PVC for instance - quota managed by StorageClass"""
    # Quota is now handled by Kubernetes PVC spec
    # No direct filesystem manipulation needed
    storage_size = f"{quota_gb}Gi"
    return storage_size  # Return size string for PVC creation
```

```python
# OLD (Lines 200-400): Docker service creation
docker_client = DockerClientWrapper()
service = docker_client.client.services.create(
    image='bitnami/odoo:17',
    name=f'odoo-{database_name}-{instance_id_short}',
    networks=['saasodoo-network'],
    mounts=[docker.types.Mount(
        target='/bitnami/odoo',
        source=cephfs_path,
        type='bind'
    )],
    labels={
        'traefik.enable': 'true',
        'traefik.http.routers.xxx.rule': f'Host(`{subdomain}.saasodoo.local`)',
    }
)

# NEW: Kubernetes deployment creation
k8s_client = get_k8s_client()
result = await k8s_client.create_odoo_instance(
    instance_id=instance_id_short,
    database_name=database_name,
    cpu_limit="1000m",
    memory_limit="2Gi",
    storage_size=f"{quota_gb}Gi",
    environment_vars={
        'ODOO_DATABASE_HOST': os.getenv('ODOO_POSTGRES_HOST'),
        'ODOO_DATABASE_NAME': database_name,
    },
    subdomain=subdomain
)
```

### Step 4: Update Lifecycle Tasks

**File**: `services/instance-service/app/tasks/lifecycle.py`

```python
# OLD: Scale Docker Swarm service
async def stop_instance(instance_id: str):
    docker_client = DockerClientWrapper()
    service = docker_client.client.services.get(deployment_name)
    service.scale(0)  # Scale to 0 replicas

# NEW: Scale Kubernetes deployment
async def stop_instance(instance_id: str):
    k8s_client = get_k8s_client()
    deployment_name = f"odoo-{database_name}-{instance_id}"
    await k8s_client.scale_instance(deployment_name, replicas=0)
```

```python
# OLD: Start Docker service
async def start_instance(instance_id: str):
    docker_client = DockerClientWrapper()
    service = docker_client.client.services.get(deployment_name)
    service.scale(1)

# NEW: Start Kubernetes deployment
async def start_instance(instance_id: str):
    k8s_client = get_k8s_client()
    deployment_name = f"odoo-{database_name}-{instance_id}"
    await k8s_client.scale_instance(deployment_name, replicas=1)
```

```python
# OLD: Delete Docker service
async def terminate_instance(instance_id: str):
    docker_client = DockerClientWrapper()
    service = docker_client.client.services.get(deployment_name)
    service.remove()

    # Remove CephFS directory
    shutil.rmtree(cephfs_path)

# NEW: Delete Kubernetes resources
async def terminate_instance(instance_id: str):
    k8s_client = get_k8s_client()
    deployment_name = f"odoo-{database_name}-{instance_id}"
    await k8s_client.delete_instance(deployment_name)
    # PVC deletion handled by k8s_client based on RETAIN_STORAGE env var
```

### Step 5: Update Monitoring (Event Watching)

**File**: `services/instance-service/app/tasks/monitoring.py`

This requires a **COMPLETE REWRITE** (1,248 lines → ~400 lines estimated).

**Key changes:**

```python
# OLD (Lines 346-400): Docker event monitoring thread
def _monitor_events(self):
    """Monitor Docker Swarm events in blocking thread"""
    event_filters = {'type': 'service', 'label': 'managed-by=saasodoo'}

    for event in self.docker_client.events(decode=True, filters=event_filters):
        event_type = event.get('Action')
        if event_type == 'create':
            # Handle service creation
        elif event_type == 'remove':
            # Handle service removal

# NEW: Kubernetes pod watch with async/await
async def _monitor_pod_events(self):
    """Monitor Kubernetes pod events asynchronously"""
    k8s_client = get_k8s_client()

    async def event_callback(event_type, pod_name, pod_status, pod):
        """Handle pod events"""
        if event_type == 'ADDED':
            await self._handle_pod_created(pod)
        elif event_type == 'MODIFIED':
            await self._handle_pod_updated(pod)
        elif event_type == 'DELETED':
            await self._handle_pod_deleted(pod)

    # Start watching (this runs indefinitely)
    await k8s_client.watch_pod_events(event_callback)
```

**Status mapping changes:**

```python
# OLD: Docker task state → instance status
docker_state_mapping = {
    'new': 'creating',
    'running': 'running',
    'shutdown': 'stopped',
    'failed': 'error',
}

# NEW: Kubernetes pod phase → instance status
k8s_phase_mapping = {
    'Pending': 'creating',
    'Running': 'running',
    'Succeeded': 'stopped',
    'Failed': 'error',
    'Unknown': 'error',
}
```

---

## CephFS to Kubernetes CSI

### Changes Required

1. **Remove direct filesystem operations** (no more `setfattr`, `os.makedirs`)
2. **Use PersistentVolumeClaim** for storage
3. **Quota management** via StorageClass parameters

### Before (Docker Swarm):

```python
# File: provisioning.py Lines 52-86
cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{database_name}_{instance_id}"
os.makedirs(cephfs_path, exist_ok=True)

# Set quota
cmd = ['setfattr', '-n', 'ceph.quota.max_bytes', '-v', str(quota_bytes), cephfs_path]
subprocess.run(cmd, check=True)

# Mount in container
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=cephfs_path,
    type='bind'
)
```

### After (Kubernetes):

```python
# Quota is now in PVC spec
pvc = client.V1PersistentVolumeClaim(
    spec=client.V1PersistentVolumeClaimSpec(
        resources=client.V1ResourceRequirements(
            requests={"storage": "10Gi"}  # This IS the quota
        ),
        storage_class_name="cephfs-saasodoo"
    )
)

# Mount in pod spec
volume_mount = client.V1VolumeMount(
    name="odoo-data",
    mount_path="/bitnami/odoo"
)
```

**StorageClass configuration** (infrastructure/kubernetes/storage/cephfs-storageclass.yaml):

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cephfs-saasodoo
provisioner: rook-ceph.cephfs.csi.ceph.com
parameters:
  clusterID: rook-ceph
  fsName: cephfs
  pool: cephfs_data
  # Quotas are enforced via PVC requests.storage
reclaimPolicy: Retain  # Don't delete data when PVC is deleted
allowVolumeExpansion: true  # Allow quota increases
```

---

## Environment Variable Updates

### Service Discovery Changes

**Before (Docker Swarm):**
```python
POSTGRES_HOST=postgres  # Direct DNS name
USER_SERVICE_URL=http://user-service:8001
BILLING_SERVICE_URL=http://billing-service:8004
```

**After (Kubernetes):**
```python
POSTGRES_HOST=postgres.saasodoo.svc.cluster.local  # FQDN
USER_SERVICE_URL=http://user-service.saasodoo.svc.cluster.local:8001
BILLING_SERVICE_URL=http://billing-service.saasodoo.svc.cluster.local:8004
```

### ConfigMap for Environment Variables

**Create**: `infrastructure/kubernetes/instance-service/configmap.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: instance-service-config
  namespace: saasodoo
data:
  POSTGRES_HOST: "postgres.saasodoo.svc.cluster.local"
  POSTGRES_PORT: "5432"
  POSTGRES_DB: "instance"
  REDIS_HOST: "redis.saasodoo.svc.cluster.local"
  REDIS_PORT: "6379"
  RABBITMQ_HOST: "rabbitmq.saasodoo.svc.cluster.local"
  RABBITMQ_PORT: "5672"
  USER_SERVICE_URL: "http://user-service.saasodoo.svc.cluster.local:8001"
  BILLING_SERVICE_URL: "http://billing-service.saasodoo.svc.cluster.local:8004"
  BASE_DOMAIN: "saasodoo.com"
  KUBERNETES_NAMESPACE: "saasodoo"
  STORAGE_CLASS_NAME: "cephfs-saasodoo"
  ODOO_IMAGE: "bitnami/odoo:17"
```

### Sealed Secrets for Sensitive Data

```bash
# Create secret for database credentials
kubectl create secret generic odoo-db-credentials \
  --from-literal=username=odoo_admin \
  --from-literal=password=your-secure-password \
  --dry-run=client -o yaml | kubeseal -w sealed-odoo-db-credentials.yaml

# Apply sealed secret
kubectl apply -f sealed-odoo-db-credentials.yaml
```

---

## Database Connection Adaptations

### Connection Pool Review

**File**: `shared/utils/database.py`

**Current configuration** (Lines 30-32):
```python
self.pool_config = {
    'min_size': 1,
    'max_size': 10,
    'command_timeout': 30
}
```

**Recommended for Kubernetes** (supports more concurrent instances):
```python
self.pool_config = {
    'min_size': 5,
    'max_size': 50,  # Increase for Kubernetes scale
    'command_timeout': 30,
    'max_inactive_connection_lifetime': 300  # Close idle connections after 5 min
}
```

### Health Check Updates

Add Kubernetes-aware health checks:

```python
# File: services/instance-service/app/main.py

@app.get("/health/kubernetes")
async def kubernetes_health_check():
    """Kubernetes-specific health check"""
    checks = {}

    # Check Kubernetes API connectivity
    try:
        k8s_client = get_k8s_client()
        k8s_client.core_v1.list_namespace(limit=1)
        checks['kubernetes_api'] = 'healthy'
    except Exception as e:
        checks['kubernetes_api'] = f'unhealthy: {str(e)}'

    # Check database
    try:
        db = get_database_manager()
        await db.execute_query("SELECT 1")
        checks['database'] = 'healthy'
    except Exception as e:
        checks['database'] = f'unhealthy: {str(e)}'

    # Check Redis
    try:
        redis_client = get_redis_client()
        await redis_client.ping()
        checks['redis'] = 'healthy'
    except Exception as e:
        checks['redis'] = f'unhealthy: {str(e)}'

    all_healthy = all(v == 'healthy' for v in checks.values())
    status_code = 200 if all_healthy else 503

    return JSONResponse(
        status_code=status_code,
        content={'status': 'healthy' if all_healthy else 'degraded', 'checks': checks}
    )
```

---

## Service Discovery Changes

### Dockerfile Updates

**Remove Docker socket mount:**

```dockerfile
# OLD (services/instance-service/Dockerfile Line 13):
# VOLUME /var/run/docker.sock:/var/run/docker.sock:ro

# NEW: No Docker socket needed!
# Kubernetes API access via ServiceAccount
```

### RBAC for Kubernetes API Access

**Create**: `infrastructure/kubernetes/instance-service/rbac.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: instance-service
  namespace: saasodoo
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: instance-service-role
  namespace: saasodoo
rules:
- apiGroups: ["apps"]
  resources: ["deployments", "deployments/scale"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["services", "persistentvolumeclaims", "pods"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["traefik.io"]
  resources: ["ingressroutes"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: instance-service-rolebinding
  namespace: saasodoo
subjects:
- kind: ServiceAccount
  name: instance-service
  namespace: saasodoo
roleRef:
  kind: Role
  name: instance-service-role
  apiGroup: rbac.authorization.k8s.io
```

---

## Testing Strategy for Refactored Code

### Unit Tests with Mocked Kubernetes API

**Create**: `services/instance-service/tests/test_k8s_client.py`

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.utils.k8s_client import KubernetesClientWrapper

@pytest.fixture
def mock_k8s_apis():
    """Mock Kubernetes API clients"""
    with patch('app.utils.k8s_client.config.load_incluster_config'), \
         patch('app.utils.k8s_client.client.AppsV1Api') as apps_mock, \
         patch('app.utils.k8s_client.client.CoreV1Api') as core_mock:

        yield {
            'apps_v1': apps_mock.return_value,
            'core_v1': core_mock.return_value
        }

@pytest.mark.asyncio
async def test_create_odoo_instance(mock_k8s_apis):
    """Test Odoo instance creation"""
    k8s_client = KubernetesClientWrapper()

    # Mock PVC creation
    mock_pvc = Mock()
    mock_pvc.metadata.name = "test-pvc"
    mock_k8s_apis['core_v1'].create_namespaced_persistent_volume_claim.return_value = mock_pvc

    # Mock Deployment creation
    mock_deployment = Mock()
    mock_deployment.metadata.name = "odoo-testdb-abc12345"
    mock_k8s_apis['apps_v1'].create_namespaced_deployment.return_value = mock_deployment

    # Mock Service creation
    mock_service = Mock()
    mock_service.metadata.name = "odoo-testdb-abc12345"
    mock_k8s_apis['core_v1'].create_namespaced_service.return_value = mock_service

    # Call method
    result = await k8s_client.create_odoo_instance(
        instance_id="abc12345",
        database_name="testdb",
        storage_size="10Gi"
    )

    # Assertions
    assert result['deployment_name'] == "odoo-testdb-abc12345"
    assert result['status'] == 'creating'
    mock_k8s_apis['core_v1'].create_namespaced_persistent_volume_claim.assert_called_once()
    mock_k8s_apis['apps_v1'].create_namespaced_deployment.assert_called_once()
```

### Integration Tests

Run against a real Kubernetes cluster (kind/k3s for testing):

```bash
# Install kind for local testing
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind

# Create test cluster
kind create cluster --name saasodoo-test

# Run integration tests
pytest services/instance-service/tests/integration/ --cluster=kind-saasodoo-test
```

---

## Migration Checklist

### Week 4: Kubernetes Client Implementation

- [ ] Install `kubernetes` Python package
- [ ] Create `k8s_client.py` with all methods
- [ ] Write unit tests for `k8s_client.py` (20+ test cases)
- [ ] Create RBAC configuration (ServiceAccount, Role, RoleBinding)
- [ ] Test Kubernetes API connectivity in dev cluster

### Week 5: Provisioning Refactoring

- [ ] Refactor `provisioning.py` to use `k8s_client`
- [ ] Remove CephFS direct manipulation code
- [ ] Update PVC creation logic
- [ ] Update Celery tasks to call new methods
- [ ] Test instance creation end-to-end
- [ ] Verify PVC binding and storage quota

### Week 6: Lifecycle & Monitoring

- [ ] Refactor `lifecycle.py` (start, stop, delete)
- [ ] Rewrite `monitoring.py` event watching
- [ ] Replace Docker event stream with Kubernetes watch
- [ ] Update status mapping logic
- [ ] Test instance lifecycle operations
- [ ] Verify monitoring detects status changes

### Week 7: Environment & Configuration

- [ ] Create ConfigMap for environment variables
- [ ] Create Sealed Secrets for credentials
- [ ] Update all service URLs to Kubernetes DNS format
- [ ] Remove Docker socket mount from Dockerfile
- [ ] Update database connection pool configuration
- [ ] Test all microservice-to-microservice communication

### Week 8: Testing & Validation

- [ ] Run unit tests (target: 70% coverage)
- [ ] Run integration tests in test cluster
- [ ] Perform end-to-end instance provisioning test
- [ ] Load test: Create 10 instances simultaneously
- [ ] Verify all instances are healthy
- [ ] Test failure scenarios (pod crash, node failure)

### Week 9: Documentation & Handoff

- [ ] Document all API changes
- [ ] Update operations runbook
- [ ] Create troubleshooting guide for Kubernetes-specific issues
- [ ] Train team on new architecture
- [ ] Code review all refactored files

---

## Before/After Comparison Summary

| Aspect | Docker Swarm | Kubernetes |
|--------|--------------|------------|
| **Client Library** | `docker==7.1.0` | `kubernetes==29.0.0` |
| **Container Management** | Docker Service API | Deployment + Pod |
| **Networking** | Docker overlay network | Kubernetes Service (ClusterIP) |
| **Storage** | CephFS bind mount + setfattr | PVC with CSI driver |
| **Ingress** | Traefik labels on service | IngressRoute CRD |
| **Scaling** | `service.scale(N)` | `patch_deployment_scale(N)` |
| **Event Monitoring** | `docker.events()` stream | `watch.Watch().stream()` |
| **Service Discovery** | Direct DNS names | FQDN with .svc.cluster.local |
| **Configuration** | ENV vars in compose file | ConfigMap + Secrets |
| **Permissions** | Docker socket access (GID/root) | RBAC ServiceAccount |
| **Health Checks** | Docker HEALTHCHECK | Liveness + Readiness probes |

---

## Rollback Plan

If refactoring fails, you can revert to Docker Swarm:

1. **Git revert** all code changes
2. **Redeploy** Docker Swarm services
3. **Restore** database backup
4. **Switch DNS** back to Docker Swarm load balancer

Keep Docker Swarm running during Weeks 4-7 as fallback!

---

**Next Steps:**
- Proceed to TESTING_STRATEGY.md for comprehensive testing approach
- See DATABASE_MIGRATION.md for data migration procedures
- See OPERATIONS_RUNBOOK.md for day-to-day operations

---

**Document Version**: 1.0
**Last Updated**: 2025-12-02
**Maintainer**: SaaSOdoo Development Team
