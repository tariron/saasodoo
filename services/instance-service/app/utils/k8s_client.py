"""
Kubernetes client wrapper for instance service
Provides same interface as DockerClientWrapper but uses Kubernetes API
"""

import os
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class KubernetesServiceManager:
    """Service manager for Kubernetes - provides Docker-compatible services API"""

    def __init__(self, k8s_client):
        self.k8s_client = k8s_client

    def create(self, image, name, env, resources, mode, mounts, networks, labels, restart_policy):
        """
        Create Kubernetes Deployment (mimics docker.services.create)

        Args:
            image: Docker image (e.g., 'bitnamilegacy/odoo:17')
            name: Deployment name
            env: Environment variables (dict)
            resources: Docker resources spec
            mode: Service mode (ignored in K8s)
            mounts: List of Docker mount specs
            networks: List of networks (ignored in K8s)
            labels: Labels dict
            restart_policy: Restart policy (ignored - K8s uses deployment spec)

        Returns:
            Object with .id property (deployment UID)
        """
        try:
            # Convert env dict to K8s env list
            env_list = [client.V1EnvVar(name=k, value=str(v)) for k, v in env.items()]

            # Convert mounts to K8s volumes
            volume_mounts = []
            volumes = []
            for i, mount in enumerate(mounts):
                vol_name = f"vol-{i}"
                volume_mounts.append(client.V1VolumeMount(
                    name=vol_name,
                    mount_path=mount['Target']
                ))
                volumes.append(client.V1Volume(
                    name=vol_name,
                    host_path=client.V1HostPathVolumeSource(
                        path=mount['Source'],
                        type="DirectoryOrCreate"
                    )
                ))

            # Convert resources to K8s format
            cpu_limit = resources['Limits']['NanoCPUs'] / 1e9  # Convert to cores
            mem_limit = resources['Limits']['MemoryBytes']

            k8s_resources = client.V1ResourceRequirements(
                limits={
                    "cpu": f"{int(cpu_limit * 1000)}m",
                    "memory": f"{int(mem_limit / (1024**2))}Mi"
                },
                requests={
                    "cpu": f"{int(cpu_limit * 500)}m",  # 50% of limit
                    "memory": f"{int(mem_limit / (1024**2) * 0.5)}Mi"
                }
            )

            # Create container spec
            container = client.V1Container(
                name="odoo",
                image=image,
                env=env_list,
                resources=k8s_resources,
                volume_mounts=volume_mounts,
                ports=[client.V1ContainerPort(container_port=8069, name="odoo")]
            )

            # Separate labels into K8s labels and extract routing info
            # K8s labels must be alphanumeric + '-', '_', '.'
            k8s_labels = {}
            ingress_host = None

            for key, value in labels.items():
                if key.startswith('traefik.http.routers.') and key.endswith('.rule'):
                    # Extract host from Traefik rule: Host(`subdomain.domain.com`)
                    import re
                    match = re.search(r'Host\(`([^`]+)`\)', value)
                    if match:
                        ingress_host = match.group(1)
                elif key.startswith('saasodoo.'):
                    # SaasOdoo labels - keep as labels
                    k8s_labels[key] = value

            # Add required selector labels
            k8s_labels['app'] = 'odoo'
            k8s_labels['instance'] = name

            # Create pod template with labels only (no annotations)
            template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=k8s_labels),
                spec=client.V1PodSpec(containers=[container], volumes=volumes)
            )

            # Create deployment spec - selector must match pod labels
            spec = client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": "odoo", "instance": name}),
                template=template
            )

            # Create deployment with labels
            deployment = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(name=name, labels=k8s_labels),
                spec=spec
            )

            created = self.k8s_client.apps_v1.create_namespaced_deployment(
                namespace=self.k8s_client.namespace,
                body=deployment
            )

            # Create Service for internal routing
            service_name = f"{name}-service"
            service_spec = client.V1ServiceSpec(
                selector={"app": "odoo", "instance": name},
                ports=[client.V1ServicePort(port=8069, target_port=8069)],
                type="ClusterIP"
            )

            service = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(name=service_name, labels=k8s_labels),
                spec=service_spec
            )

            self.k8s_client.core_v1.create_namespaced_service(
                namespace=self.k8s_client.namespace,
                body=service
            )

            # Create Ingress for subdomain routing
            if ingress_host:
                networking_v1 = client.NetworkingV1Api()

                ingress_rule = client.V1IngressRule(
                    host=ingress_host,
                    http=client.V1HTTPIngressRuleValue(
                        paths=[
                            client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=client.V1IngressBackend(
                                    service=client.V1IngressServiceBackend(
                                        name=service_name,
                                        port=client.V1ServiceBackendPort(number=8069)
                                    )
                                )
                            )
                        ]
                    )
                )

                ingress = client.V1Ingress(
                    api_version="networking.k8s.io/v1",
                    kind="Ingress",
                    metadata=client.V1ObjectMeta(
                        name=name,
                        labels=k8s_labels,
                        annotations={"kubernetes.io/ingress.class": "traefik"}
                    ),
                    spec=client.V1IngressSpec(rules=[ingress_rule])
                )

                networking_v1.create_namespaced_ingress(
                    namespace=self.k8s_client.namespace,
                    body=ingress
                )

                logger.info("Created Deployment, Service, and Ingress",
                           deployment=name,
                           service=service_name,
                           ingress_host=ingress_host,
                           uid=created.metadata.uid)
            else:
                logger.info("Created Deployment and Service (no Ingress - host not found)",
                           deployment=name, uid=created.metadata.uid)

            # Return object with .id property and methods to mimic docker service
            class ServiceResult:
                def __init__(self, uid, deployment_name, k8s_client):
                    self.id = uid
                    self.name = deployment_name
                    self._k8s_client = k8s_client
                    self._deployment = None

                def reload(self):
                    """Reload deployment state"""
                    self._deployment = self._k8s_client.apps_v1.read_namespaced_deployment(
                        self.name,
                        self._k8s_client.namespace
                    )

                def tasks(self):
                    """Get pods (mimics service tasks)"""
                    pods = self._k8s_client.core_v1.list_namespaced_pod(
                        namespace=self._k8s_client.namespace,
                        label_selector=f"app=odoo,instance={self.name}"
                    )

                    tasks = []
                    for pod in pods.items:
                        state = 'running' if pod.status.phase == 'Running' else pod.status.phase.lower()

                        # Include pod IP in NetworksAttachments to match Docker Swarm format
                        network_attachments = []
                        if pod.status.pod_ip:
                            network_attachments = [{
                                'Addresses': [f"{pod.status.pod_ip}/32"]
                            }]

                        tasks.append({
                            'ID': pod.metadata.uid,
                            'Status': {'State': state},
                            'DesiredState': 'running',
                            'NetworksAttachments': network_attachments
                        })

                    return tasks

            return ServiceResult(created.metadata.uid, name, self.k8s_client)

        except Exception as e:
            logger.error("Failed to create Deployment", name=name, error=str(e))
            raise

    def get(self, service_name):
        """
        Get Kubernetes Deployment (mimics docker.services.get)

        Args:
            service_name: Deployment name

        Returns:
            Deployment object with Docker-compatible interface
        """
        try:
            deployment = self.k8s_client.apps_v1.read_namespaced_deployment(
                service_name,
                self.k8s_client.namespace
            )

            # Return wrapper with Docker-compatible methods
            class DeploymentWrapper:
                def __init__(self, deployment, k8s_client):
                    self._deployment = deployment
                    self._k8s_client = k8s_client
                    self.id = deployment.metadata.uid
                    self.name = deployment.metadata.name

                def reload(self):
                    """Reload deployment state"""
                    self._deployment = self._k8s_client.apps_v1.read_namespaced_deployment(
                        self.name,
                        self._k8s_client.namespace
                    )

                def tasks(self):
                    """Get pods (mimics service tasks)"""
                    pods = self._k8s_client.core_v1.list_namespaced_pod(
                        namespace=self._k8s_client.namespace,
                        label_selector=f"app=odoo,instance={self.name}"
                    )

                    tasks = []
                    for pod in pods.items:
                        state = 'running' if pod.status.phase == 'Running' else pod.status.phase.lower()

                        # Include pod IP in NetworksAttachments to match Docker Swarm format
                        network_attachments = []
                        if pod.status.pod_ip:
                            network_attachments = [{
                                'Addresses': [f"{pod.status.pod_ip}/32"]
                            }]

                        tasks.append({
                            'ID': pod.metadata.uid,
                            'Status': {'State': state},
                            'DesiredState': 'running',
                            'NetworksAttachments': network_attachments
                        })

                    return tasks

            return DeploymentWrapper(deployment, self.k8s_client)

        except ApiException as e:
            if e.status == 404:
                raise Exception(f"Service {service_name} not found")
            raise


class KubernetesClientWrapper:
    """Kubernetes client with same interface as DockerClientWrapper"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_connection_check = 0
        self._connection_check_interval = 30  # seconds

        # Kubernetes clients
        self.core_v1 = None
        self.apps_v1 = None
        self.namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')

        # Naming patterns (same as Docker client)
        self.service_pattern = re.compile(r'^odoo-([^-]+)-([a-f0-9]{8})$')
        self.container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')

        # Service manager for Docker-compatible API
        self.services = KubernetesServiceManager(self)

        # Initialize connection
        self._ensure_connection()

    def _ensure_connection(self):
        """Ensure Kubernetes client is connected with retry logic"""
        current_time = time.time()

        if (self.core_v1 is None or
            current_time - self._last_connection_check > self._connection_check_interval):

            for attempt in range(self.max_retries):
                try:
                    # Load Kubernetes config (in-cluster or from kubeconfig)
                    try:
                        config.load_incluster_config()
                        logger.info("Loaded in-cluster Kubernetes config")
                    except config.ConfigException:
                        config.load_kube_config()
                        logger.info("Loaded kubeconfig")

                    # Initialize API clients
                    self.core_v1 = client.CoreV1Api()
                    self.apps_v1 = client.AppsV1Api()

                    # Test connection (list pods in our namespace)
                    self.core_v1.list_namespaced_pod(namespace=self.namespace, limit=1)
                    self._last_connection_check = current_time

                    if attempt > 0:
                        logger.info("Kubernetes client reconnected", attempt=attempt + 1)

                    return

                except Exception as e:
                    if attempt == self.max_retries - 1:
                        logger.error("Failed to connect to Kubernetes after all retries",
                                   error=str(e), attempts=self.max_retries)
                        raise
                    else:
                        logger.warning("Kubernetes connection failed, retrying",
                                     error=str(e), attempt=attempt + 1)
                        time.sleep(self.retry_delay * (2 ** attempt))

    # ========================================================================
    # CONTAINER/POD OPERATIONS (Maps to Deployment + Pod operations)
    # ========================================================================

    def get_container(self, container_name: str) -> Optional[Dict[str, Any]]:
        """
        Get pod by deployment name
        In K8s, we work with deployments, but return pod info for compatibility
        """
        try:
            self._ensure_connection()

            # List pods for this deployment
            label_selector = f"app=odoo,instance={container_name}"
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=label_selector
            )

            if not pods.items:
                logger.debug("No pods found for instance", instance=container_name)
                return None

            # Return first pod (deployments typically have 1 pod for instances)
            pod = pods.items[0]
            return {
                'pod': pod,
                'name': container_name,
                'pod_name': pod.metadata.name
            }

        except ApiException as e:
            if e.status == 404:
                logger.debug("Pod not found", instance=container_name)
                return None
            logger.error("Failed to get pod", instance=container_name, error=str(e))
            raise
        except Exception as e:
            logger.error("Failed to get pod", instance=container_name, error=str(e))
            raise

    def list_saasodoo_containers(self) -> List[Dict[str, Any]]:
        """List all SaaS Odoo pods with metadata"""
        try:
            self._ensure_connection()

            # List all pods with odoo label
            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector="app=odoo"
            )

            saasodoo_pods = []
            for pod in pods.items:
                instance_name = pod.metadata.labels.get('instance', '')
                if instance_name and self.is_saasodoo_container(instance_name):
                    metadata = self.extract_container_metadata(instance_name)
                    if metadata:
                        metadata.update({
                            'container_id': pod.metadata.uid,
                            'pod_name': pod.metadata.name,
                            'status': pod.status.phase.lower(),
                            'created': pod.metadata.creation_timestamp.isoformat(),
                            'labels': pod.metadata.labels or {}
                        })
                        saasodoo_pods.append(metadata)

            logger.debug("Found SaaS Odoo pods", count=len(saasodoo_pods))
            return saasodoo_pods

        except Exception as e:
            logger.error("Failed to list SaaS Odoo pods", error=str(e))
            raise

    def is_saasodoo_container(self, container_name: str) -> bool:
        """Check if name follows SaaS Odoo naming pattern"""
        return bool(self.service_pattern.match(container_name) or
                   self.container_pattern.match(container_name))

    def extract_container_metadata(self, container_name: str) -> Optional[Dict[str, str]]:
        """Extract metadata from SaaS Odoo container name"""
        match = self.service_pattern.match(container_name) or \
                self.container_pattern.match(container_name)
        if match:
            database_name, instance_id_hex = match.groups()
            return {
                'container_name': container_name,
                'database_name': database_name,
                'instance_id_hex': instance_id_hex
            }
        return None

    def get_container_status(self, container_name: str) -> Optional[str]:
        """Get pod status"""
        try:
            container = self.get_container(container_name)
            if container and 'pod' in container:
                pod = container['pod']
                # Map K8s pod phase to Docker-like status
                phase = pod.status.phase.lower()
                if phase == 'running':
                    # Check if all containers in pod are ready
                    if pod.status.container_statuses:
                        all_ready = all(cs.ready for cs in pod.status.container_statuses)
                        return 'running' if all_ready else 'starting'
                elif phase == 'pending':
                    return 'created'
                elif phase == 'succeeded':
                    return 'exited'
                elif phase == 'failed':
                    return 'dead'
                return phase
            return None
        except Exception as e:
            logger.error("Failed to get pod status", instance=container_name, error=str(e))
            return None

    def get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive pod information"""
        try:
            container = self.get_container(container_name)
            if not container or 'pod' not in container:
                return None

            pod = container['pod']

            # Get associated service
            service_name = f"{container_name}-service"
            try:
                service = self.core_v1.read_namespaced_service(service_name, self.namespace)
                port_info = {
                    'cluster_ip': service.spec.cluster_ip,
                    'ports': [
                        {
                            'port': port.port,
                            'target_port': port.target_port,
                            'protocol': port.protocol
                        } for port in service.spec.ports
                    ]
                }
            except:
                port_info = {}

            return {
                'container_id': pod.metadata.uid,
                'name': container_name,
                'pod_name': pod.metadata.name,
                'status': self.get_container_status(container_name),
                'state': {
                    'phase': pod.status.phase,
                    'reason': pod.status.reason,
                    'message': pod.status.message
                },
                'created': pod.metadata.creation_timestamp.isoformat(),
                'started_at': pod.status.start_time.isoformat() if pod.status.start_time else None,
                'network_info': {
                    'pod_ip': pod.status.pod_ip,
                    'host_ip': pod.status.host_ip
                },
                'port_bindings': port_info,
                'labels': pod.metadata.labels or {},
                'image': pod.spec.containers[0].image if pod.spec.containers else '',
                'node_name': pod.spec.node_name,
                'environment': [
                    {'name': env.name, 'value': env.value}
                    for env in (pod.spec.containers[0].env or [])
                    if pod.spec.containers
                ]
            }

        except Exception as e:
            logger.error("Failed to get pod info", instance=container_name, error=str(e))
            return None

    def start_container(self, container_name: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Start deployment (scale to 1 if stopped)
        """
        try:
            self._ensure_connection()
            deployment_name = container_name

            logger.info("Starting deployment", deployment=deployment_name)

            # Get current deployment
            deployment = self.apps_v1.read_namespaced_deployment(
                deployment_name, self.namespace
            )

            current_replicas = deployment.spec.replicas or 0

            if current_replicas > 0:
                logger.info("Deployment already running", deployment=deployment_name)
                return self._get_start_result(deployment_name)

            # Scale to 1
            deployment.spec.replicas = 1
            self.apps_v1.patch_namespaced_deployment(
                deployment_name,
                self.namespace,
                deployment
            )

            # Wait for pod to be running
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = self.get_container_status(container_name)
                if status == 'running':
                    logger.info("Deployment started successfully",
                              deployment=deployment_name)
                    return self._get_start_result(deployment_name)
                time.sleep(2)

            raise TimeoutError(f"Deployment {deployment_name} did not start within {timeout}s")

        except ApiException as e:
            logger.error("Failed to start deployment",
                       deployment=deployment_name, error=str(e))
            raise
        except Exception as e:
            logger.error("Failed to start deployment",
                       deployment=deployment_name, error=str(e))
            raise

    def stop_container(self, container_name: str, timeout: int = 30) -> bool:
        """
        Stop deployment (scale to 0)
        """
        try:
            self._ensure_connection()
            deployment_name = container_name

            logger.info("Stopping deployment", deployment=deployment_name)

            # Scale to 0
            deployment = self.apps_v1.read_namespaced_deployment(
                deployment_name, self.namespace
            )
            deployment.spec.replicas = 0
            self.apps_v1.patch_namespaced_deployment(
                deployment_name,
                self.namespace,
                deployment
            )

            # Wait for pods to terminate
            start_time = time.time()
            while time.time() - start_time < timeout:
                status = self.get_container_status(container_name)
                if status is None:
                    logger.info("Deployment stopped successfully",
                              deployment=deployment_name)
                    return True
                time.sleep(2)

            logger.warning("Deployment stop timeout", deployment=deployment_name)
            return False

        except Exception as e:
            logger.error("Failed to stop deployment",
                       deployment=deployment_name, error=str(e))
            return False

    def restart_container(self, container_name: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Restart deployment by deleting pod (triggers recreation)
        """
        try:
            self._ensure_connection()

            logger.info("Restarting deployment", deployment=container_name)

            # Get pod
            container = self.get_container(container_name)
            if not container or 'pod' not in container:
                raise ValueError(f"Pod for {container_name} not found")

            pod_name = container['pod_name']

            # Delete pod (deployment will recreate it)
            self.core_v1.delete_namespaced_pod(pod_name, self.namespace)

            # Wait for new pod to be running
            start_time = time.time()
            old_pod_uid = container['pod'].metadata.uid

            while time.time() - start_time < timeout:
                time.sleep(2)
                new_container = self.get_container(container_name)
                if new_container and 'pod' in new_container:
                    new_pod = new_container['pod']
                    # Check if it's a different pod (recreated)
                    if new_pod.metadata.uid != old_pod_uid:
                        status = self.get_container_status(container_name)
                        if status == 'running':
                            logger.info("Deployment restarted successfully",
                                      deployment=container_name)
                            return self._get_start_result(container_name)

            raise TimeoutError(f"Deployment {container_name} did not restart within {timeout}s")

        except Exception as e:
            logger.error("Failed to restart deployment",
                       deployment=container_name, error=str(e))
            raise

    def _get_start_result(self, deployment_name: str) -> Dict[str, Any]:
        """Get deployment start result info"""
        info = self.get_container_info(deployment_name)
        if not info:
            return {'status': 'unknown'}

        return {
            'status': 'started',
            'deployment': deployment_name,
            'pod_name': info.get('pod_name'),
            'pod_ip': info.get('network_info', {}).get('pod_ip'),
            'started_at': info.get('started_at'),
            'image': info.get('image')
        }

    def get_container_logs(self, container_name: str, tail: int = 100) -> Optional[str]:
        """Get pod logs"""
        try:
            self._ensure_connection()

            container = self.get_container(container_name)
            if not container or 'pod_name' not in container:
                return None

            pod_name = container['pod_name']
            logs = self.core_v1.read_namespaced_pod_log(
                pod_name,
                self.namespace,
                tail_lines=tail
            )

            return logs

        except Exception as e:
            logger.error("Failed to get pod logs",
                       instance=container_name, error=str(e))
            return None

    def container_health_check(self, container_name: str) -> Dict[str, Any]:
        """Check pod health"""
        try:
            container = self.get_container(container_name)
            if not container or 'pod' not in container:
                return {
                    'healthy': False,
                    'status': 'not_found',
                    'message': 'Pod not found'
                }

            pod = container['pod']
            status = self.get_container_status(container_name)

            # Check if pod is running and ready
            healthy = status == 'running'

            if pod.status.container_statuses:
                container_status = pod.status.container_statuses[0]
                ready = container_status.ready

                # Check restart count
                restart_count = container_status.restart_count

                return {
                    'healthy': healthy and ready,
                    'status': status,
                    'ready': ready,
                    'restart_count': restart_count,
                    'message': f"Pod {status}, ready={ready}, restarts={restart_count}"
                }

            return {
                'healthy': healthy,
                'status': status,
                'message': f"Pod {status}"
            }

        except Exception as e:
            logger.error("Health check failed",
                       instance=container_name, error=str(e))
            return {
                'healthy': False,
                'status': 'error',
                'message': str(e)
            }

    def update_container_resources(self, container_name: str,
                                   cpu_limit: float, memory_bytes: int) -> bool:
        """Update deployment resource limits"""
        try:
            self._ensure_connection()
            deployment_name = container_name

            # Convert CPU cores to millicores string
            cpu_limit_str = f"{int(cpu_limit * 1000)}m"
            # Convert bytes to Mi
            memory_limit_str = f"{int(memory_bytes / (1024 * 1024))}Mi"

            # Patch deployment
            patch = {
                'spec': {
                    'template': {
                        'spec': {
                            'containers': [{
                                'name': 'odoo',
                                'resources': {
                                    'limits': {
                                        'cpu': cpu_limit_str,
                                        'memory': memory_limit_str
                                    },
                                    'requests': {
                                        'cpu': f"{int(cpu_limit * 500)}m",  # 50% of limit
                                        'memory': f"{int(memory_bytes / (1024 * 1024) * 0.5)}Mi"
                                    }
                                }
                            }]
                        }
                    }
                }
            }

            self.apps_v1.patch_namespaced_deployment(
                deployment_name,
                self.namespace,
                patch
            )

            logger.info("Updated deployment resources",
                       deployment=deployment_name,
                       cpu=cpu_limit_str,
                       memory=memory_limit_str)
            return True

        except Exception as e:
            logger.error("Failed to update deployment resources",
                       deployment=deployment_name, error=str(e))
            return False

    # ========================================================================
    # SERVICE OPERATIONS (For backward compatibility, map to deployment ops)
    # ========================================================================

    def get_service(self, service_name: str):
        """Alias for get_container (backward compat with Swarm code)"""
        return self.get_container(service_name)

    def get_service_by_label(self, label_key: str, label_value: str):
        """Get deployment by label"""
        try:
            self._ensure_connection()

            deployments = self.apps_v1.list_namespaced_deployment(
                self.namespace,
                label_selector=f"{label_key}={label_value}"
            )

            if deployments.items:
                return deployments.items[0]
            return None

        except Exception as e:
            logger.error("Failed to get deployment by label",
                       label=f"{label_key}={label_value}", error=str(e))
            return None

    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get deployment status"""
        return self.get_container_info(service_name)

    def start_service(self, service_name: str, timeout: int = 60) -> Dict[str, Any]:
        """Start deployment"""
        return self.start_container(service_name, timeout)

    def stop_service(self, service_name: str, timeout: int = 30) -> bool:
        """Stop deployment"""
        return self.stop_container(service_name, timeout)

    def restart_service(self, service_name: str, timeout: int = 60) -> Dict[str, Any]:
        """Restart deployment"""
        return self.restart_container(service_name, timeout)

    def get_service_logs(self, service_name: str, tail: int = 100) -> Optional[str]:
        """Get deployment logs"""
        return self.get_container_logs(service_name, tail)

    def list_saasodoo_services(self) -> List[Dict[str, Any]]:
        """List all SaaS Odoo deployments"""
        return self.list_saasodoo_containers()

    def is_saasodoo_service(self, service_name: str) -> bool:
        """Check if follows SaaS Odoo naming"""
        return self.is_saasodoo_container(service_name)

    def extract_service_metadata(self, service_name: str) -> Optional[Dict[str, str]]:
        """Extract metadata from service name"""
        return self.extract_container_metadata(service_name)

    def service_health_check(self, service_name: str) -> Dict[str, Any]:
        """Check deployment health"""
        return self.container_health_check(service_name)

    def update_service_resources(self, service_name: str,
                                 cpu_limit: float, memory_bytes: int) -> bool:
        """Update deployment resources"""
        return self.update_container_resources(service_name, cpu_limit, memory_bytes)

    def cleanup_orphaned_containers(self) -> List[str]:
        """
        Cleanup orphaned pods
        In K8s, this is less needed as deployments manage pods automatically
        """
        logger.info("Cleanup orphaned pods - K8s deployments self-manage")
        return []
