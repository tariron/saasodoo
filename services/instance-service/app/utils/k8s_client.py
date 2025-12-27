"""
Native Kubernetes client for Odoo instance management
No Docker API mimicry - uses Kubernetes API directly
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


class KubernetesClient:
    """Native Kubernetes client for managing Odoo instances"""

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

    def create_odoo_instance(
        self,
        instance_name: str,
        instance_id: str,
        image: str,
        env_vars: Dict[str, str],
        cpu_limit: str = "1",
        memory_limit: str = "2Gi",
        pvc_name: str = None,
        ingress_host: str = None,
        labels: Dict[str, str] = None
    ) -> Dict[str, str]:
        """
        Create Kubernetes resources for an Odoo instance

        Args:
            instance_name: Name for the deployment (e.g., 'odoo-customer-abc123')
            instance_id: Full instance ID
            image: Docker image (e.g., 'bitnamilegacy/odoo:17')
            env_vars: Environment variables dict
            cpu_limit: CPU limit (e.g., "2")
            memory_limit: Memory limit (e.g., "4Gi")
            pvc_name: Name of PVC for persistent storage
            ingress_host: Hostname for ingress (e.g., 'customer.example.com')
            labels: Additional labels

        Returns:
            Dict with deployment_uid, service_name, service_dns
        """
        try:
            self._ensure_connection()

            # Extract short hex ID from instance_id for monitoring compatibility
            instance_hex = instance_id[:8] if len(instance_id) > 8 else instance_id

            # Prepare labels
            resource_labels = {
                "app": "odoo",
                "instance": instance_name,
                "instance-id": instance_hex,  # Short hex for monitoring queries
                "saasodoo.io/instance-id": instance_id,  # Full UUID for reference
                "saasodoo.io/type": "odoo-instance"
            }
            if labels:
                # Only add valid K8s labels (alphanumeric + -._)
                for k, v in labels.items():
                    if k.startswith('saasodoo.'):
                        resource_labels[k] = v

            # Environment variables
            env_list = [client.V1EnvVar(name=k, value=str(v)) for k, v in env_vars.items()]

            # Volume mounts
            volume_mounts = []
            volumes = []
            if pvc_name:
                volume_mounts.append(client.V1VolumeMount(
                    name="odoo-data",
                    mount_path="/bitnami/odoo"  # Bitnami Odoo persistent volume (addons, conf, data)
                ))
                volumes.append(client.V1Volume(
                    name="odoo-data",
                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                        claim_name=pvc_name
                    )
                ))

            # Resource requirements
            resources = client.V1ResourceRequirements(
                limits={
                    "cpu": f"{int(float(cpu_limit) * 1000)}m",
                    "memory": memory_limit
                },
                requests={
                    "cpu": f"{int(float(cpu_limit) * 500)}m",
                    "memory": memory_limit  # Request same as limit for guaranteed QoS
                }
            )

            # Container spec
            container = client.V1Container(
                name="odoo",
                image=image,
                env=env_list,
                resources=resources,
                volume_mounts=volume_mounts,
                ports=[client.V1ContainerPort(container_port=8069, name="http")],
                # NO security context - let Bitnami handle user management (runs as root, switches to odoo user)
                readiness_probe=client.V1Probe(
                    http_get=client.V1HTTPGetAction(
                        path="/",
                        port=8069
                    ),
                    initial_delay_seconds=30,
                    period_seconds=10,
                    timeout_seconds=5,
                    failure_threshold=3
                ),
                liveness_probe=client.V1Probe(
                    http_get=client.V1HTTPGetAction(
                        path="/",
                        port=8069
                    ),
                    initial_delay_seconds=60,
                    period_seconds=30,
                    timeout_seconds=10,
                    failure_threshold=5
                )
            )

            # Pod template
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=resource_labels),
                spec=client.V1PodSpec(
                    containers=[container],
                    volumes=volumes
                    # NO pod security context - let Bitnami handle permissions
                )
            )

            # Deployment
            deployment = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(
                    name=instance_name,
                    labels=resource_labels
                ),
                spec=client.V1DeploymentSpec(
                    replicas=1,
                    selector=client.V1LabelSelector(
                        match_labels={"app": "odoo", "instance": instance_name}
                    ),
                    template=pod_template
                )
            )

            # Create Deployment
            created_deployment = self.apps_v1.create_namespaced_deployment(
                namespace=self.namespace,
                body=deployment
            )

            # Service name
            service_name = f"{instance_name}-service"

            # Create Service
            service = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(
                    name=service_name,
                    labels=resource_labels
                ),
                spec=client.V1ServiceSpec(
                    selector={"app": "odoo", "instance": instance_name},
                    ports=[client.V1ServicePort(
                        name="http",
                        port=8069,
                        target_port=8069
                    )],
                    type="ClusterIP"
                )
            )

            self.core_v1.create_namespaced_service(
                namespace=self.namespace,
                body=service
            )

            # Service DNS (this is what we'll use for health checks)
            service_dns = f"{service_name}.{self.namespace}.svc.cluster.local"

            # Create Ingress if host specified
            if ingress_host:
                ingress = client.V1Ingress(
                    api_version="networking.k8s.io/v1",
                    kind="Ingress",
                    metadata=client.V1ObjectMeta(
                        name=instance_name,
                        labels=resource_labels,
                        annotations={"kubernetes.io/ingress.class": "traefik"}
                    ),
                    spec=client.V1IngressSpec(
                        rules=[client.V1IngressRule(
                            host=ingress_host,
                            http=client.V1HTTPIngressRuleValue(
                                paths=[client.V1HTTPIngressPath(
                                    path="/",
                                    path_type="Prefix",
                                    backend=client.V1IngressBackend(
                                        service=client.V1IngressServiceBackend(
                                            name=service_name,
                                            port=client.V1ServiceBackendPort(number=8069)
                                        )
                                    )
                                )]
                            )
                        )]
                    )
                )

                self.networking_v1.create_namespaced_ingress(
                    namespace=self.namespace,
                    body=ingress
                )

                logger.info("Created Deployment, Service, and Ingress",
                           deployment=instance_name,
                           service=service_name,
                           ingress_host=ingress_host)
            else:
                logger.info("Created Deployment and Service",
                           deployment=instance_name,
                           service=service_name)

            return {
                "deployment_uid": created_deployment.metadata.uid,
                "deployment_name": instance_name,
                "service_name": service_name,
                "service_dns": service_dns,
                "ingress_host": ingress_host
            }

        except Exception as e:
            logger.error("Failed to create Odoo instance",
                        instance_name=instance_name, error=str(e))
            raise

    def wait_for_deployment_ready(
        self,
        deployment_name: str,
        timeout: int = 180,
        check_interval: int = 5
    ) -> bool:
        """
        Wait for Deployment to be ready

        Args:
            deployment_name: Name of deployment
            timeout: Timeout in seconds
            check_interval: Check interval in seconds

        Returns:
            True if ready, False if timeout
        """
        try:
            self._ensure_connection()
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    deployment = self.apps_v1.read_namespaced_deployment(
                        deployment_name, self.namespace
                    )

                    # Check if ready
                    if (deployment.status.ready_replicas and
                        deployment.status.ready_replicas == deployment.spec.replicas):
                        logger.info("Deployment is ready", name=deployment_name)
                        return True

                    logger.debug("Waiting for Deployment to be ready",
                               name=deployment_name,
                               ready=deployment.status.ready_replicas or 0,
                               desired=deployment.spec.replicas)

                except ApiException:
                    pass

                time.sleep(check_interval)

            logger.warning("Deployment did not become ready within timeout",
                         name=deployment_name, timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error waiting for Deployment",
                       name=deployment_name, error=str(e))
            return False

    def scale_deployment(self, deployment_name: str, replicas: int) -> bool:
        """
        Scale deployment to specified replicas

        Args:
            deployment_name: Name of deployment
            replicas: Number of replicas (0 to stop, 1 to start)

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            # Patch deployment scale
            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={'spec': {'replicas': replicas}}
            )

            action = "stopped" if replicas == 0 else "started"
            logger.info(f"Deployment {action}",
                       name=deployment_name,
                       replicas=replicas)
            return True

        except Exception as e:
            logger.error("Failed to scale deployment",
                       name=deployment_name,
                       replicas=replicas,
                       error=str(e))
            return False

    def delete_instance(self, instance_name: str) -> bool:
        """
        Delete all resources for an instance

        Args:
            instance_name: Name of the instance

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            service_name = f"{instance_name}-service"

            # Delete Deployment
            try:
                self.apps_v1.delete_namespaced_deployment(
                    instance_name,
                    self.namespace,
                    body=client.V1DeleteOptions(propagation_policy='Foreground')
                )
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete Service
            try:
                self.core_v1.delete_namespaced_service(service_name, self.namespace)
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete Ingress
            try:
                self.networking_v1.delete_namespaced_ingress(instance_name, self.namespace)
            except ApiException as e:
                if e.status != 404:
                    raise

            logger.info("Instance resources deleted", name=instance_name)
            return True

        except Exception as e:
            logger.error("Failed to delete instance",
                       name=instance_name, error=str(e))
            return False

    def get_pod_status(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """
        Get pod status for an instance

        Args:
            instance_name: Name of the instance

        Returns:
            Dict with pod status info or None
        """
        try:
            self._ensure_connection()

            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=odoo,instance={instance_name}"
            )

            if not pods.items:
                return None

            pod = pods.items[0]  # Get first pod

            return {
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "pod_ip": pod.status.pod_ip,
                "started_at": pod.status.start_time.isoformat() if pod.status.start_time else None,
                "ready": all(c.ready for c in pod.status.container_statuses) if pod.status.container_statuses else False
            }

        except Exception as e:
            logger.error("Failed to get pod status",
                       instance_name=instance_name, error=str(e))
            return None

    def get_pod_logs(self, instance_name: str, tail_lines: int = 100) -> Optional[str]:
        """
        Get logs from pod

        Args:
            instance_name: Name of the instance
            tail_lines: Number of lines to return

        Returns:
            Log string or None
        """
        try:
            self._ensure_connection()

            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=odoo,instance={instance_name}"
            )

            if not pods.items:
                return None

            pod_name = pods.items[0].metadata.name

            logs = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace,
                tail_lines=tail_lines
            )

            return logs

        except Exception as e:
            logger.error("Failed to get pod logs",
                       instance_name=instance_name, error=str(e))
            return None

    def update_deployment_image(self, deployment_name: str, new_image: str) -> bool:
        """
        Update deployment container image

        Args:
            deployment_name: Name of deployment
            new_image: New container image (e.g., 'bitnamilegacy/odoo:18')

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            # Patch deployment with new image
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body={
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{
                                    'name': 'odoo',
                                    'image': new_image
                                }]
                            }
                        }
                    }
                }
            )

            logger.info("Deployment image updated",
                       name=deployment_name,
                       image=new_image)
            return True

        except Exception as e:
            logger.error("Failed to update deployment image",
                       name=deployment_name,
                       image=new_image,
                       error=str(e))
            return False

    def update_deployment_env(self, deployment_name: str, env_vars: Dict[str, str]) -> bool:
        """
        Update deployment environment variables

        Args:
            deployment_name: Name of deployment
            env_vars: Environment variables dict to update/add

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()

            # Convert env vars to Kubernetes format
            env_list = [{'name': k, 'value': str(v)} for k, v in env_vars.items()]

            # Patch deployment with new env vars
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body={
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{
                                    'name': 'odoo',
                                    'env': env_list
                                }]
                            }
                        }
                    }
                }
            )

            logger.info("Deployment environment updated",
                       name=deployment_name,
                       env_count=len(env_vars))
            return True

        except Exception as e:
            logger.error("Failed to update deployment environment",
                       name=deployment_name,
                       error=str(e))
            return False

    def create_backup_job(
        self,
        job_name: str,
        instance_pvc_name: str,
        backup_file: str,
        backup_base_path: str = "/mnt/cephfs/odoo_backups"
    ) -> bool:
        """
        Create Kubernetes Job to backup instance PVC data using tar

        Args:
            job_name: Name for the job (e.g., 'backup-fffff-20250125')
            instance_pvc_name: Name of the instance PVC to backup
            backup_file: Backup filename (e.g., 'backup_name_data.tar.gz')
            backup_base_path: Base path for backups

        Returns:
            True if job created successfully
        """
        try:
            self._ensure_connection()

            batch_v1 = client.BatchV1Api()

            # Job specification
            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    labels={"app": "backup", "job-type": "backup"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,  # Auto-cleanup after 5 minutes
                    backoff_limit=2,  # Retry twice on failure
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "backup"}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[client.V1Container(
                                name="backup",
                                image="alpine:latest",
                                command=[
                                    "tar",
                                    "-czf",
                                    f"/backup/active/{backup_file}",
                                    "-C",
                                    "/data",
                                    "."
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="source-data",
                                        mount_path="/data",
                                        read_only=True
                                    ),
                                    client.V1VolumeMount(
                                        name="backup-storage",
                                        mount_path="/backup"
                                    )
                                ]
                            )],
                            volumes=[
                                client.V1Volume(
                                    name="source-data",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name=instance_pvc_name
                                    )
                                ),
                                client.V1Volume(
                                    name="backup-storage",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name="odoo-backups-pvc"
                                    )
                                )
                            ]
                        )
                    )
                )
            )

            batch_v1.create_namespaced_job(namespace=self.namespace, body=job)

            logger.info("Backup job created",
                       job_name=job_name,
                       pvc_name=instance_pvc_name,
                       backup_file=backup_file)
            return True

        except Exception as e:
            logger.error("Failed to create backup job",
                       job_name=job_name,
                       error=str(e))
            return False

    def create_restore_job(
        self,
        job_name: str,
        instance_pvc_name: str,
        backup_file: str,
        backup_base_path: str = "/mnt/cephfs/odoo_backups"
    ) -> bool:
        """
        Create Kubernetes Job to restore data from backup to instance PVC

        Args:
            job_name: Name for the job (e.g., 'restore-fffff-20250125')
            instance_pvc_name: Name of the instance PVC to restore to
            backup_file: Backup filename (e.g., 'backup_name_data.tar.gz')
            backup_base_path: Base path for backups

        Returns:
            True if job created successfully
        """
        try:
            self._ensure_connection()

            batch_v1 = client.BatchV1Api()

            # Job specification
            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    labels={"app": "restore", "job-type": "restore"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,  # Auto-cleanup after 5 minutes
                    backoff_limit=2,  # Retry twice on failure
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "restore"}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[client.V1Container(
                                name="restore",
                                image="alpine:latest",
                                command=[
                                    "tar",
                                    "-xzf",
                                    f"/backup/active/{backup_file}",
                                    "-C",
                                    "/data"
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="dest-data",
                                        mount_path="/data"
                                    ),
                                    client.V1VolumeMount(
                                        name="backup-storage",
                                        mount_path="/backup",
                                        read_only=True
                                    )
                                ]
                            )],
                            volumes=[
                                client.V1Volume(
                                    name="dest-data",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name=instance_pvc_name
                                    )
                                ),
                                client.V1Volume(
                                    name="backup-storage",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name="odoo-backups-pvc"
                                    )
                                )
                            ]
                        )
                    )
                )
            )

            batch_v1.create_namespaced_job(namespace=self.namespace, body=job)

            logger.info("Restore job created",
                       job_name=job_name,
                       backup_file=backup_file,
                       pvc_name=instance_pvc_name)
            return True

        except Exception as e:
            logger.error("Failed to create restore job",
                       job_name=job_name,
                       error=str(e))
            return False

    def wait_for_job_completion(
        self,
        job_name: str,
        timeout: int = 600,
        check_interval: int = 5
    ) -> bool:
        """
        Wait for Kubernetes Job to complete

        Args:
            job_name: Name of the job
            timeout: Timeout in seconds (default 10 minutes)
            check_interval: Check interval in seconds

        Returns:
            True if job succeeded, False if failed or timeout
        """
        try:
            self._ensure_connection()
            batch_v1 = client.BatchV1Api()

            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    job = batch_v1.read_namespaced_job(job_name, self.namespace)

                    # Check if job succeeded
                    if job.status.succeeded and job.status.succeeded > 0:
                        logger.info("Job completed successfully", name=job_name)
                        return True

                    # Check if job failed
                    if job.status.failed and job.status.failed > 0:
                        logger.error("Job failed", name=job_name, failed_count=job.status.failed)
                        return False

                    logger.debug("Waiting for job to complete",
                               name=job_name,
                               active=job.status.active or 0)

                except ApiException as e:
                    if e.status == 404:
                        logger.warning("Job not found", name=job_name)
                        return False

                time.sleep(check_interval)

            logger.warning("Job did not complete within timeout",
                         name=job_name, timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error waiting for job",
                       name=job_name, error=str(e))
            return False

    def exec_in_pod(
        self,
        pod_name: str,
        command: List[str],
        container: str = "odoo"
    ) -> tuple[bool, str]:
        """
        Execute command in a running pod

        Args:
            pod_name: Name of the pod
            command: Command to execute as list
            container: Container name (default: 'odoo')

        Returns:
            Tuple of (success: bool, output: str)
        """
        try:
            self._ensure_connection()

            from kubernetes.stream import stream

            # Execute command in pod
            resp = stream(
                self.core_v1.connect_get_namespaced_pod_exec,
                pod_name,
                self.namespace,
                command=command,
                container=container,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )

            logger.info("Command executed in pod",
                       pod=pod_name,
                       command=' '.join(command))

            return True, resp

        except Exception as e:
            error_msg = str(e)
            logger.error("Failed to exec in pod",
                       pod=pod_name,
                       command=' '.join(command),
                       error=error_msg)
            return False, error_msg

    def get_pod_name_for_deployment(self, deployment_name: str) -> Optional[str]:
        """
        Get pod name for a deployment

        Args:
            deployment_name: Name of the deployment

        Returns:
            Pod name or None if not found
        """
        try:
            self._ensure_connection()

            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=odoo,instance={deployment_name}"
            )

            if not pods.items:
                logger.warning("No pods found for deployment", deployment=deployment_name)
                return None

            # Return first running pod
            for pod in pods.items:
                if pod.status.phase == "Running":
                    return pod.metadata.name

            # If no running pods, return first pod
            return pods.items[0].metadata.name

        except Exception as e:
            logger.error("Failed to get pod name",
                       deployment=deployment_name,
                       error=str(e))
            return None

    def create_instance_pvc(self, pvc_name: str, storage_size: str) -> bool:
        """
        Create PVC for Odoo instance

        Args:
            pvc_name: Name of the PVC (e.g., 'odoo-instance-{uuid}')
            storage_size: Storage size in Kubernetes format (e.g., '10Gi', '25Gi')

        Returns:
            True if successful

        Raises:
            Exception if PVC creation fails
        """
        try:
            self._ensure_connection()

            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(
                    name=pvc_name,
                    namespace=self.namespace,
                    labels={
                        "app": "odoo-instance",
                        "managed-by": "saasodoo"
                    },
                    annotations={
                        "saasodoo.io/created-at": datetime.utcnow().isoformat()
                    }
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],  # RWO for single instance
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

            logger.info("Created instance PVC", pvc_name=pvc_name, size=storage_size)
            return True

        except Exception as e:
            logger.error("Failed to create PVC",
                       pvc_name=pvc_name,
                       size=storage_size,
                       error=str(e))
            raise

    def wait_for_pvc_bound(self, pvc_name: str, timeout: int = 60) -> bool:
        """
        Wait for PVC to be Bound to a PV

        Args:
            pvc_name: Name of the PVC to wait for
            timeout: Maximum time to wait in seconds (default: 60)

        Returns:
            True if PVC becomes Bound within timeout

        Raises:
            Exception if PVC doesn't become Bound within timeout
        """
        try:
            self._ensure_connection()

            start_time = time.time()
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise Exception(f"PVC {pvc_name} did not become Bound within {timeout}s timeout")

                try:
                    pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                        name=pvc_name,
                        namespace=self.namespace
                    )

                    if pvc.status.phase == "Bound":
                        logger.info("PVC is Bound",
                                   pvc_name=pvc_name,
                                   elapsed=f"{elapsed:.1f}s")
                        return True

                    logger.debug("Waiting for PVC to be Bound",
                               pvc_name=pvc_name,
                               status=pvc.status.phase,
                               elapsed=f"{elapsed:.1f}s")

                except ApiException as e:
                    if e.status == 404:
                        logger.warning("PVC not found yet", pvc_name=pvc_name)
                    else:
                        raise

                time.sleep(2)  # Check every 2 seconds

        except Exception as e:
            logger.error("Failed waiting for PVC to bind",
                       pvc_name=pvc_name,
                       error=str(e))
            raise

    def delete_pvc(self, pvc_name: str) -> bool:
        """
        Delete instance PVC

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

    def resize_pvc(self, pvc_name: str, new_size: str) -> bool:
        """
        Resize PVC (expansion only - Kubernetes does not support shrinking)

        Args:
            pvc_name: Name of the PVC
            new_size: New size in Kubernetes format (e.g., '20Gi')

        Returns:
            True if successful

        Raises:
            ValueError if new size is smaller than current size
        """
        try:
            self._ensure_connection()

            # Get current PVC
            pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self.namespace
            )

            current_size = pvc.spec.resources.requests["storage"]

            # Update size
            pvc.spec.resources.requests["storage"] = new_size

            self.core_v1.patch_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self.namespace,
                body=pvc
            )

            logger.info("Resized PVC",
                       pvc_name=pvc_name,
                       old_size=current_size,
                       new_size=new_size)
            return True

        except Exception as e:
            logger.error("Failed to resize PVC",
                       pvc_name=pvc_name,
                       new_size=new_size,
                       error=str(e))
            return False

    def read_file_from_pvc(
        self,
        pvc_name: str,
        file_path: str,
        timeout: int = 120
    ) -> Optional[str]:
        """
        Read a file from a PVC using a temporary Kubernetes Job

        Args:
            pvc_name: Name of the PVC to read from
            file_path: Path to file inside PVC (e.g., '/conf/odoo.conf')
            timeout: Job completion timeout in seconds

        Returns:
            File contents as string, or None if failed
        """
        self._ensure_connection()

        # Generate unique job name
        timestamp = int(time.time())
        job_name = f"read-file-{timestamp}"

        try:
            logger.info("Creating Job to read file from PVC",
                       pvc_name=pvc_name,
                       file_path=file_path,
                       job_name=job_name)

            # Create Job that mounts PVC and cats the file
            batch_v1 = client.BatchV1Api()

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    namespace=self.namespace,
                    labels={
                        "app": "file-reader",
                        "managed-by": "saasodoo-instance-service"
                    }
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,  # Auto-cleanup after 5 minutes
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(
                            labels={
                                "app": "file-reader",
                                "job-name": job_name
                            }
                        ),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[
                                client.V1Container(
                                    name="reader",
                                    image="busybox:latest",
                                    command=["cat", file_path],
                                    volume_mounts=[
                                        client.V1VolumeMount(
                                            name="data",
                                            mount_path="/"
                                        )
                                    ]
                                )
                            ],
                            volumes=[
                                client.V1Volume(
                                    name="data",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name=pvc_name
                                    )
                                )
                            ]
                        )
                    )
                )
            )

            batch_v1.create_namespaced_job(namespace=self.namespace, body=job)

            # Wait for Job completion and get pod logs
            pod_name = self._wait_for_job_pod(job_name, timeout)
            if not pod_name:
                logger.error("Job pod not found", job_name=job_name)
                return None

            # Get logs (file contents)
            file_contents = self.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self.namespace
            )

            logger.info("Successfully read file from PVC",
                       pvc_name=pvc_name,
                       file_path=file_path,
                       content_length=len(file_contents))

            return file_contents

        except Exception as e:
            logger.error("Failed to read file from PVC",
                       pvc_name=pvc_name,
                       file_path=file_path,
                       error=str(e),
                       exc_info=True)
            return None

    def write_file_to_pvc(
        self,
        pvc_name: str,
        file_path: str,
        content: str,
        timeout: int = 120
    ) -> bool:
        """
        Write a file to a PVC using a temporary Kubernetes Job

        Args:
            pvc_name: Name of the PVC to write to
            file_path: Path to file inside PVC (e.g., '/conf/odoo.conf')
            content: File content to write
            timeout: Job completion timeout in seconds

        Returns:
            True if successful, False otherwise
        """
        self._ensure_connection()

        # Generate unique names
        timestamp = int(time.time())
        job_name = f"write-file-{timestamp}"
        configmap_name = f"file-content-{timestamp}"

        try:
            logger.info("Creating Job to write file to PVC",
                       pvc_name=pvc_name,
                       file_path=file_path,
                       job_name=job_name,
                       content_length=len(content))

            # Create ConfigMap with file content
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=self.namespace,
                    labels={
                        "app": "file-writer",
                        "managed-by": "saasodoo-instance-service"
                    }
                ),
                data={"content": content}
            )

            self.core_v1.create_namespaced_config_map(
                namespace=self.namespace,
                body=configmap
            )

            # Create Job that copies ConfigMap to PVC
            batch_v1 = client.BatchV1Api()

            # Ensure parent directory exists and then write file
            command = [
                "sh", "-c",
                f"mkdir -p $(dirname {file_path}) && cp /tmp/content {file_path}"
            ]

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    namespace=self.namespace,
                    labels={
                        "app": "file-writer",
                        "managed-by": "saasodoo-instance-service"
                    }
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(
                            labels={
                                "app": "file-writer",
                                "job-name": job_name
                            }
                        ),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[
                                client.V1Container(
                                    name="writer",
                                    image="busybox:latest",
                                    command=command,
                                    volume_mounts=[
                                        client.V1VolumeMount(
                                            name="data",
                                            mount_path="/"
                                        ),
                                        client.V1VolumeMount(
                                            name="content",
                                            mount_path="/tmp"
                                        )
                                    ]
                                )
                            ],
                            volumes=[
                                client.V1Volume(
                                    name="data",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name=pvc_name
                                    )
                                ),
                                client.V1Volume(
                                    name="content",
                                    config_map=client.V1ConfigMapVolumeSource(
                                        name=configmap_name
                                    )
                                )
                            ]
                        )
                    )
                )
            )

            batch_v1.create_namespaced_job(namespace=self.namespace, body=job)

            # Wait for Job completion
            success = self._wait_for_job_completion(job_name, timeout)

            # Cleanup ConfigMap
            try:
                self.core_v1.delete_namespaced_config_map(
                    name=configmap_name,
                    namespace=self.namespace
                )
            except Exception as e:
                logger.warning("Failed to cleanup ConfigMap",
                             configmap_name=configmap_name,
                             error=str(e))

            if success:
                logger.info("Successfully wrote file to PVC",
                           pvc_name=pvc_name,
                           file_path=file_path)
            else:
                logger.error("Failed to write file to PVC",
                           pvc_name=pvc_name,
                           file_path=file_path)

            return success

        except Exception as e:
            logger.error("Failed to write file to PVC",
                       pvc_name=pvc_name,
                       file_path=file_path,
                       error=str(e),
                       exc_info=True)

            # Cleanup ConfigMap on error
            try:
                self.core_v1.delete_namespaced_config_map(
                    name=configmap_name,
                    namespace=self.namespace
                )
            except:
                pass

            return False

    def _wait_for_job_pod(self, job_name: str, timeout: int = 120) -> Optional[str]:
        """
        Wait for a Job's pod to be created and return its name

        Args:
            job_name: Name of the Job
            timeout: Maximum wait time in seconds

        Returns:
            Pod name if found, None otherwise
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                pods = self.core_v1.list_namespaced_pod(
                    namespace=self.namespace,
                    label_selector=f"job-name={job_name}"
                )

                if pods.items:
                    pod_name = pods.items[0].metadata.name
                    logger.debug("Found Job pod", job_name=job_name, pod_name=pod_name)

                    # Wait for pod to complete
                    while time.time() - start_time < timeout:
                        pod = self.core_v1.read_namespaced_pod(
                            name=pod_name,
                            namespace=self.namespace
                        )

                        if pod.status.phase in ["Succeeded", "Failed"]:
                            if pod.status.phase == "Succeeded":
                                return pod_name
                            else:
                                logger.error("Job pod failed", pod_name=pod_name)
                                return None

                        time.sleep(2)

            except Exception as e:
                logger.debug("Waiting for Job pod", job_name=job_name, error=str(e))

            time.sleep(2)

        logger.error("Timeout waiting for Job pod", job_name=job_name, timeout=timeout)
        return None

    def _wait_for_job_completion(self, job_name: str, timeout: int = 120) -> bool:
        """
        Wait for a Job to complete

        Args:
            job_name: Name of the Job
            timeout: Maximum wait time in seconds

        Returns:
            True if Job succeeded, False otherwise
        """
        start_time = time.time()
        batch_v1 = client.BatchV1Api()

        while time.time() - start_time < timeout:
            try:
                job = batch_v1.read_namespaced_job(
                    name=job_name,
                    namespace=self.namespace
                )

                if job.status.succeeded:
                    logger.debug("Job completed successfully", job_name=job_name)
                    return True
                elif job.status.failed:
                    logger.error("Job failed", job_name=job_name)
                    return False

            except Exception as e:
                logger.debug("Waiting for Job completion", job_name=job_name, error=str(e))

            time.sleep(2)

        logger.error("Timeout waiting for Job completion", job_name=job_name, timeout=timeout)
        return False
