"""
Kubernetes PVC (Persistent Volume Claim) operations
"""

import time
from typing import Optional
from datetime import datetime
from kubernetes import client
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class VolumeOperationsMixin:
    """Mixin for Kubernetes PVC operations"""

    def create_instance_pvc(self, pvc_name: str, storage_size: str) -> bool:
        """Create PVC for Odoo instance"""
        try:
            self._ensure_connection()

            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(
                    name=pvc_name,
                    namespace=self.namespace,
                    labels={"app": "odoo-instance", "managed-by": "saasodoo"},
                    annotations={"saasodoo.io/created-at": datetime.utcnow().isoformat()}
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    storage_class_name="rook-cephfs",
                    resources=client.V1ResourceRequirements(requests={"storage": storage_size})
                )
            )

            self.core_v1.create_namespaced_persistent_volume_claim(namespace=self.namespace, body=pvc)

            logger.info("Created instance PVC", pvc_name=pvc_name, size=storage_size)
            return True

        except Exception as e:
            logger.error("Failed to create PVC", pvc_name=pvc_name, size=storage_size, error=str(e))
            raise

    def wait_for_pvc_bound(self, pvc_name: str, timeout: int = 60) -> bool:
        """Wait for PVC to be Bound to a PV"""
        try:
            self._ensure_connection()

            start_time = time.time()
            while True:
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    raise Exception(f"PVC {pvc_name} did not become Bound within {timeout}s timeout")

                try:
                    pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                        name=pvc_name, namespace=self.namespace
                    )

                    if pvc.status.phase == "Bound":
                        logger.info("PVC is Bound", pvc_name=pvc_name, elapsed=f"{elapsed:.1f}s")
                        return True

                    logger.debug("Waiting for PVC to be Bound",
                               pvc_name=pvc_name, status=pvc.status.phase, elapsed=f"{elapsed:.1f}s")

                except ApiException as e:
                    if e.status == 404:
                        logger.warning("PVC not found yet", pvc_name=pvc_name)
                    else:
                        raise

                time.sleep(2)

        except Exception as e:
            logger.error("Failed waiting for PVC to bind", pvc_name=pvc_name, error=str(e))
            raise

    def delete_pvc(self, pvc_name: str) -> bool:
        """Delete instance PVC"""
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
        """Resize PVC (expansion only)"""
        try:
            self._ensure_connection()

            pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                name=pvc_name, namespace=self.namespace
            )

            current_size = pvc.spec.resources.requests["storage"]
            pvc.spec.resources.requests["storage"] = new_size

            self.core_v1.patch_namespaced_persistent_volume_claim(
                name=pvc_name, namespace=self.namespace, body=pvc
            )

            logger.info("Resized PVC", pvc_name=pvc_name, old_size=current_size, new_size=new_size)
            return True

        except Exception as e:
            logger.error("Failed to resize PVC", pvc_name=pvc_name, new_size=new_size, error=str(e))
            return False

    def read_file_from_pvc(
        self,
        pvc_name: str,
        file_path: str,
        timeout: int = 120
    ) -> Optional[str]:
        """Read a file from a PVC using a temporary Kubernetes Job"""
        self._ensure_connection()

        timestamp = int(time.time())
        job_name = f"read-file-{timestamp}"

        try:
            logger.info("Creating Job to read file from PVC",
                       pvc_name=pvc_name, file_path=file_path, job_name=job_name)

            batch_v1 = client.BatchV1Api()

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    namespace=self.namespace,
                    labels={"app": "file-reader", "managed-by": "saasodoo-instance-service"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "file-reader", "job-name": job_name}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[
                                client.V1Container(
                                    name="reader",
                                    image="busybox:latest",
                                    command=["cat", file_path],
                                    volume_mounts=[client.V1VolumeMount(name="data", mount_path="/")]
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

            pod_name = self._wait_for_job_pod(job_name, timeout)
            if not pod_name:
                logger.error("Job pod not found", job_name=job_name)
                return None

            file_contents = self.core_v1.read_namespaced_pod_log(name=pod_name, namespace=self.namespace)

            logger.info("Successfully read file from PVC",
                       pvc_name=pvc_name, file_path=file_path, content_length=len(file_contents))

            return file_contents

        except Exception as e:
            logger.error("Failed to read file from PVC",
                       pvc_name=pvc_name, file_path=file_path, error=str(e), exc_info=True)
            return None

    def write_file_to_pvc(
        self,
        pvc_name: str,
        file_path: str,
        content: str,
        timeout: int = 120
    ) -> bool:
        """Write a file to a PVC using a temporary Kubernetes Job"""
        self._ensure_connection()

        timestamp = int(time.time())
        job_name = f"write-file-{timestamp}"
        configmap_name = f"file-content-{timestamp}"

        try:
            logger.info("Creating Job to write file to PVC",
                       pvc_name=pvc_name, file_path=file_path, job_name=job_name, content_length=len(content))

            # Create ConfigMap with file content
            configmap = client.V1ConfigMap(
                metadata=client.V1ObjectMeta(
                    name=configmap_name,
                    namespace=self.namespace,
                    labels={"app": "file-writer", "managed-by": "saasodoo-instance-service"}
                ),
                data={"content": content}
            )

            self.core_v1.create_namespaced_config_map(namespace=self.namespace, body=configmap)

            # Create Job
            batch_v1 = client.BatchV1Api()

            command = ["sh", "-c", f"mkdir -p $(dirname {file_path}) && cp /tmp/content {file_path}"]

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    namespace=self.namespace,
                    labels={"app": "file-writer", "managed-by": "saasodoo-instance-service"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "file-writer", "job-name": job_name}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[
                                client.V1Container(
                                    name="writer",
                                    image="busybox:latest",
                                    command=command,
                                    volume_mounts=[
                                        client.V1VolumeMount(name="data", mount_path="/"),
                                        client.V1VolumeMount(name="content", mount_path="/tmp")
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
                                    config_map=client.V1ConfigMapVolumeSource(name=configmap_name)
                                )
                            ]
                        )
                    )
                )
            )

            batch_v1.create_namespaced_job(namespace=self.namespace, body=job)

            success = self._wait_for_job_completion_internal(job_name, timeout)

            # Cleanup ConfigMap
            try:
                self.core_v1.delete_namespaced_config_map(name=configmap_name, namespace=self.namespace)
            except Exception as e:
                logger.warning("Failed to cleanup ConfigMap", configmap_name=configmap_name, error=str(e))

            if success:
                logger.info("Successfully wrote file to PVC", pvc_name=pvc_name, file_path=file_path)
            else:
                logger.error("Failed to write file to PVC", pvc_name=pvc_name, file_path=file_path)

            return success

        except Exception as e:
            logger.error("Failed to write file to PVC",
                       pvc_name=pvc_name, file_path=file_path, error=str(e), exc_info=True)

            try:
                self.core_v1.delete_namespaced_config_map(name=configmap_name, namespace=self.namespace)
            except:
                pass

            return False

    def _wait_for_job_pod(self, job_name: str, timeout: int = 120) -> Optional[str]:
        """Wait for a Job's pod to be created and return its name"""
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

                    while time.time() - start_time < timeout:
                        pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=self.namespace)

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

    def _wait_for_job_completion_internal(self, job_name: str, timeout: int = 120) -> bool:
        """Wait for a Job to complete (internal helper)"""
        start_time = time.time()
        batch_v1 = client.BatchV1Api()

        while time.time() - start_time < timeout:
            try:
                job = batch_v1.read_namespaced_job(name=job_name, namespace=self.namespace)

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
