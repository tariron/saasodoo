"""
Kubernetes Deployment operations for Odoo instances
"""

import time
from typing import Dict, Any, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class DeploymentOperationsMixin:
    """Mixin for Kubernetes Deployment operations"""

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
                "instance-id": instance_hex,
                "saasodoo.io/instance-id": instance_id,
                "saasodoo.io/type": "odoo-instance"
            }
            if labels:
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
                    mount_path="/bitnami/odoo"
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
                    "memory": memory_limit
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
                readiness_probe=client.V1Probe(
                    http_get=client.V1HTTPGetAction(path="/", port=8069),
                    initial_delay_seconds=30,
                    period_seconds=10,
                    timeout_seconds=5,
                    failure_threshold=3
                ),
                liveness_probe=client.V1Probe(
                    http_get=client.V1HTTPGetAction(path="/", port=8069),
                    initial_delay_seconds=60,
                    period_seconds=30,
                    timeout_seconds=10,
                    failure_threshold=5
                )
            )

            # Pod template
            pod_template = client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=resource_labels),
                spec=client.V1PodSpec(containers=[container], volumes=volumes)
            )

            # Deployment
            deployment = client.V1Deployment(
                api_version="apps/v1",
                kind="Deployment",
                metadata=client.V1ObjectMeta(name=instance_name, labels=resource_labels),
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
                namespace=self.namespace, body=deployment
            )

            # Service name
            service_name = f"{instance_name}-service"

            # Create Service
            service = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(name=service_name, labels=resource_labels),
                spec=client.V1ServiceSpec(
                    selector={"app": "odoo", "instance": instance_name},
                    ports=[client.V1ServicePort(name="http", port=8069, target_port=8069)],
                    type="ClusterIP"
                )
            )

            self.core_v1.create_namespaced_service(namespace=self.namespace, body=service)

            # Service DNS
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

                self.networking_v1.create_namespaced_ingress(namespace=self.namespace, body=ingress)

                logger.info("Created Deployment, Service, and Ingress",
                           deployment=instance_name, service=service_name, ingress_host=ingress_host)
            else:
                logger.info("Created Deployment and Service",
                           deployment=instance_name, service=service_name)

            return {
                "deployment_uid": created_deployment.metadata.uid,
                "deployment_name": instance_name,
                "service_name": service_name,
                "service_dns": service_dns,
                "ingress_host": ingress_host
            }

        except Exception as e:
            logger.error("Failed to create Odoo instance", instance_name=instance_name, error=str(e))
            raise

    def wait_for_deployment_ready(
        self,
        deployment_name: str,
        timeout: int = 180,
        check_interval: int = 5
    ) -> bool:
        """Wait for Deployment to be ready"""
        try:
            self._ensure_connection()
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    deployment = self.apps_v1.read_namespaced_deployment(
                        deployment_name, self.namespace
                    )

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
            logger.error("Error waiting for Deployment", name=deployment_name, error=str(e))
            return False

    def scale_deployment(self, deployment_name: str, replicas: int) -> bool:
        """Scale deployment to specified replicas"""
        try:
            self._ensure_connection()

            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={'spec': {'replicas': replicas}}
            )

            action = "stopped" if replicas == 0 else "started"
            logger.info(f"Deployment {action}", name=deployment_name, replicas=replicas)
            return True

        except Exception as e:
            logger.error("Failed to scale deployment",
                       name=deployment_name, replicas=replicas, error=str(e))
            return False

    def delete_instance(self, instance_name: str) -> bool:
        """Delete all resources for an instance"""
        try:
            self._ensure_connection()

            service_name = f"{instance_name}-service"

            # Delete Deployment
            try:
                self.apps_v1.delete_namespaced_deployment(
                    instance_name, self.namespace,
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
            logger.error("Failed to delete instance", name=instance_name, error=str(e))
            return False

    def get_pod_status(self, instance_name: str) -> Optional[Dict[str, Any]]:
        """Get pod status for an instance"""
        try:
            self._ensure_connection()

            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=odoo,instance={instance_name}"
            )

            if not pods.items:
                return None

            pod = pods.items[0]

            return {
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "pod_ip": pod.status.pod_ip,
                "started_at": pod.status.start_time.isoformat() if pod.status.start_time else None,
                "ready": all(c.ready for c in pod.status.container_statuses) if pod.status.container_statuses else False
            }

        except Exception as e:
            logger.error("Failed to get pod status", instance_name=instance_name, error=str(e))
            return None

    def get_pod_logs(self, instance_name: str, tail_lines: int = 100) -> Optional[str]:
        """Get logs from pod"""
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
                name=pod_name, namespace=self.namespace, tail_lines=tail_lines
            )

            return logs

        except Exception as e:
            logger.error("Failed to get pod logs", instance_name=instance_name, error=str(e))
            return None

    def update_deployment_image(self, deployment_name: str, new_image: str) -> bool:
        """Update deployment container image"""
        try:
            self._ensure_connection()

            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body={
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'odoo', 'image': new_image}]
                            }
                        }
                    }
                }
            )

            logger.info("Deployment image updated", name=deployment_name, image=new_image)
            return True

        except Exception as e:
            logger.error("Failed to update deployment image",
                       name=deployment_name, image=new_image, error=str(e))
            return False

    def update_deployment_env(self, deployment_name: str, env_vars: Dict[str, str]) -> bool:
        """Update deployment environment variables"""
        try:
            self._ensure_connection()

            env_list = [{'name': k, 'value': str(v)} for k, v in env_vars.items()]

            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body={
                    'spec': {
                        'template': {
                            'spec': {
                                'containers': [{'name': 'odoo', 'env': env_list}]
                            }
                        }
                    }
                }
            )

            logger.info("Deployment environment updated", name=deployment_name, env_count=len(env_vars))
            return True

        except Exception as e:
            logger.error("Failed to update deployment environment",
                       name=deployment_name, error=str(e))
            return False
