"""
Kubernetes Job operations for backup/restore
"""

import time
from typing import Optional, List
from kubernetes import client
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class JobOperationsMixin:
    """Mixin for Kubernetes Job operations (backup/restore)"""

    def create_backup_job(
        self,
        job_name: str,
        instance_pvc_name: str,
        backup_file: str,
        backup_base_path: str = "/mnt/cephfs/odoo_backups"
    ) -> bool:
        """Create Kubernetes Job to backup instance PVC data using tar"""
        try:
            self._ensure_connection()

            batch_v1 = client.BatchV1Api()

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    labels={"app": "backup", "job-type": "backup"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "backup"}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[client.V1Container(
                                name="backup",
                                image="alpine:latest",
                                command=["tar", "-czf", f"/backup/active/{backup_file}", "-C", "/data", "."],
                                volume_mounts=[
                                    client.V1VolumeMount(name="source-data", mount_path="/data", read_only=True),
                                    client.V1VolumeMount(name="backup-storage", mount_path="/backup")
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

            logger.info("Backup job created", job_name=job_name, pvc_name=instance_pvc_name, backup_file=backup_file)
            return True

        except Exception as e:
            logger.error("Failed to create backup job", job_name=job_name, error=str(e))
            return False

    def create_restore_job(
        self,
        job_name: str,
        instance_pvc_name: str,
        backup_file: str,
        backup_base_path: str = "/mnt/cephfs/odoo_backups"
    ) -> bool:
        """Create Kubernetes Job to restore data from backup to instance PVC"""
        try:
            self._ensure_connection()

            batch_v1 = client.BatchV1Api()

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    name=job_name,
                    labels={"app": "restore", "job-type": "restore"}
                ),
                spec=client.V1JobSpec(
                    ttl_seconds_after_finished=300,
                    backoff_limit=2,
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(labels={"app": "restore"}),
                        spec=client.V1PodSpec(
                            restart_policy="Never",
                            containers=[client.V1Container(
                                name="restore",
                                image="alpine:latest",
                                command=["tar", "-xzf", f"/backup/active/{backup_file}", "-C", "/data"],
                                volume_mounts=[
                                    client.V1VolumeMount(name="dest-data", mount_path="/data"),
                                    client.V1VolumeMount(name="backup-storage", mount_path="/backup", read_only=True)
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

            logger.info("Restore job created", job_name=job_name, backup_file=backup_file, pvc_name=instance_pvc_name)
            return True

        except Exception as e:
            logger.error("Failed to create restore job", job_name=job_name, error=str(e))
            return False

    def wait_for_job_completion(
        self,
        job_name: str,
        timeout: int = 600,
        check_interval: int = 5
    ) -> bool:
        """Wait for Kubernetes Job to complete"""
        try:
            self._ensure_connection()
            batch_v1 = client.BatchV1Api()

            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    job = batch_v1.read_namespaced_job(job_name, self.namespace)

                    if job.status.succeeded and job.status.succeeded > 0:
                        logger.info("Job completed successfully", name=job_name)
                        return True

                    if job.status.failed and job.status.failed > 0:
                        logger.error("Job failed", name=job_name, failed_count=job.status.failed)
                        return False

                    logger.debug("Waiting for job to complete", name=job_name, active=job.status.active or 0)

                except ApiException as e:
                    if e.status == 404:
                        logger.warning("Job not found", name=job_name)
                        return False

                time.sleep(check_interval)

            logger.warning("Job did not complete within timeout", name=job_name, timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error waiting for job", name=job_name, error=str(e))
            return False

    def exec_in_pod(
        self,
        pod_name: str,
        command: List[str],
        container: str = "odoo"
    ) -> tuple:
        """Execute command in a running pod"""
        try:
            self._ensure_connection()

            from kubernetes.stream import stream

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

            logger.info("Command executed in pod", pod=pod_name, command=' '.join(command))

            return True, resp

        except Exception as e:
            error_msg = str(e)
            logger.error("Failed to exec in pod", pod=pod_name, command=' '.join(command), error=error_msg)
            return False, error_msg

    def get_pod_name_for_deployment(self, deployment_name: str) -> Optional[str]:
        """Get pod name for a deployment"""
        try:
            self._ensure_connection()

            pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=odoo,instance={deployment_name}"
            )

            if not pods.items:
                logger.warning("No pods found for deployment", deployment=deployment_name)
                return None

            for pod in pods.items:
                if pod.status.phase == "Running":
                    return pod.metadata.name

            return pods.items[0].metadata.name

        except Exception as e:
            logger.error("Failed to get pod name", deployment=deployment_name, error=str(e))
            return None
