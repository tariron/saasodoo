"""
Docker client wrapper for PostgreSQL pool management
Handles creation and management of PostgreSQL Docker Swarm services
"""

import os
import docker
import time
import structlog
from typing import Dict, Any, Optional, List
from docker.types import ServiceMode, Resources, RestartPolicy, Mount, UpdateConfig

logger = structlog.get_logger(__name__)


class PostgreSQLDockerClient:
    """Docker client for managing PostgreSQL database pool services in Docker Swarm"""

    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize PostgreSQL Docker client

        Args:
            max_retries: Maximum number of connection retry attempts
            retry_delay: Base delay between retries (with exponential backoff)
        """
        self.client = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_connection_check = 0
        self._connection_check_interval = 30  # seconds

    def _ensure_connection(self):
        """Ensure Docker client is connected with retry logic"""
        current_time = time.time()

        # Check if we need to verify connection
        if (self.client is None or
                current_time - self._last_connection_check > self._connection_check_interval):

            for attempt in range(self.max_retries):
                try:
                    if self.client is None:
                        self.client = docker.from_env()

                    # Test connection
                    self.client.ping()
                    self._last_connection_check = current_time

                    if attempt > 0:
                        logger.info("Docker client reconnected successfully", attempt=attempt + 1)

                    return

                except Exception as e:
                    if attempt == self.max_retries - 1:
                        logger.error("Failed to connect to Docker after all retries",
                                   error=str(e),
                                   attempts=self.max_retries)
                        raise
                    else:
                        logger.warning("Docker connection failed, retrying",
                                     error=str(e),
                                     attempt=attempt + 1,
                                     max_retries=self.max_retries)
                        time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff

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

        # No suffix, assume bytes
        try:
            return int(memory_str)
        except ValueError:
            raise ValueError(f"Invalid memory format: {memory_str}")

    def _calculate_shared_buffers(self, memory_bytes: int) -> str:
        """
        Calculate PostgreSQL shared_buffers as 25% of total memory

        Args:
            memory_bytes: Total memory in bytes

        Returns:
            Formatted shared_buffers value (e.g., "1024MB")
        """
        shared_buffers_bytes = int(memory_bytes * 0.25)
        shared_buffers_mb = shared_buffers_bytes // (1024 ** 2)
        return f"{shared_buffers_mb}MB"

    def _calculate_effective_cache_size(self, memory_bytes: int) -> str:
        """
        Calculate PostgreSQL effective_cache_size as 75% of total memory

        Args:
            memory_bytes: Total memory in bytes

        Returns:
            Formatted effective_cache_size value (e.g., "3072MB")
        """
        cache_size_bytes = int(memory_bytes * 0.75)
        cache_size_mb = cache_size_bytes // (1024 ** 2)
        return f"{cache_size_mb}MB"

    def _calculate_max_connections(self, max_instances: int) -> int:
        """
        Calculate PostgreSQL max_connections based on expected instances

        Args:
            max_instances: Maximum number of Odoo instances this pool will host

        Returns:
            Calculated max_connections value
        """
        # Each Odoo instance typically needs ~10-20 connections
        # Add buffer for admin connections
        base_connections_per_instance = 20
        admin_buffer = 10
        return (max_instances * base_connections_per_instance) + admin_buffer

    def create_postgres_pool_service(
        self,
        pool_name: str,
        postgres_password: str,
        storage_path: str,
        cpu_limit: str = "2",
        memory_limit: str = "4G",
        max_instances: int = 50,
        postgres_version: str = "18",
        postgres_image: str = "postgres:18-alpine",
        network: str = "saasodoo-network"
    ) -> Dict[str, str]:
        """
        Create a PostgreSQL pool service in Docker Swarm

        Args:
            pool_name: Name of the pool (e.g., "postgres-pool-1")
            postgres_password: Admin password for PostgreSQL
            storage_path: CephFS path for data persistence
            cpu_limit: CPU limit (e.g., "2" for 2 cores)
            memory_limit: Memory limit (e.g., "4G")
            max_instances: Maximum number of databases this pool will host
            postgres_version: PostgreSQL version
            postgres_image: Full Docker image tag
            network: Docker network to attach to

        Returns:
            Dictionary with service_id and service_name

        Raises:
            docker.errors.APIError: If service creation fails
        """
        try:
            self._ensure_connection()

            # Parse memory limit
            memory_bytes = self._parse_memory(memory_limit)
            memory_bytes_reservation = int(memory_bytes * 0.5)  # Reserve 50%

            # Calculate PostgreSQL tuning parameters
            max_connections = self._calculate_max_connections(max_instances)
            shared_buffers = self._calculate_shared_buffers(memory_bytes)
            effective_cache_size = self._calculate_effective_cache_size(memory_bytes)

            logger.info("Creating PostgreSQL pool service",
                       pool_name=pool_name,
                       storage_path=storage_path,
                       cpu_limit=cpu_limit,
                       memory_limit=memory_limit,
                       max_connections=max_connections)

            # Environment variables for PostgreSQL
            environment = [
                f"POSTGRES_PASSWORD={postgres_password}",
                "POSTGRES_USER=postgres",
                "POSTGRES_DB=postgres",
                f"PGDATA=/var/lib/postgresql/data/pgdata",
                # Performance tuning
                f"POSTGRES_MAX_CONNECTIONS={max_connections}",
                f"POSTGRES_SHARED_BUFFERS={shared_buffers}",
                f"POSTGRES_EFFECTIVE_CACHE_SIZE={effective_cache_size}",
                # Additional tuning
                "POSTGRES_WORK_MEM=16MB",
                "POSTGRES_MAINTENANCE_WORK_MEM=256MB",
                "POSTGRES_WAL_BUFFERS=16MB",
                "POSTGRES_CHECKPOINT_COMPLETION_TARGET=0.9",
                "POSTGRES_RANDOM_PAGE_COST=1.1",
            ]

            # Resources configuration
            resources = Resources(
                cpu_limit=int(float(cpu_limit) * 1e9),  # Convert to nanocores
                mem_limit=memory_bytes,
                cpu_reservation=int(float(cpu_limit) * 0.5 * 1e9),  # Reserve 50%
                mem_reservation=memory_bytes_reservation
            )

            # Mount configuration for CephFS
            mounts = [
                Mount(
                    target="/var/lib/postgresql/data",
                    source=storage_path,
                    type="bind",
                    read_only=False
                )
            ]

            # Placement constraints - only run on database nodes
            placement_constraints = ["node.labels.role==database"]

            # Health check using pg_isready
            healthcheck = {
                "test": ["CMD-SHELL", "pg_isready -U postgres || exit 1"],
                "interval": 10 * 1000000000,  # 10 seconds in nanoseconds
                "timeout": 5 * 1000000000,     # 5 seconds
                "retries": 5,
                "start_period": 30 * 1000000000  # 30 seconds
            }

            # Restart policy
            restart_policy = RestartPolicy(
                condition="any",
                delay=5 * 1000000000,  # 5 seconds in nanoseconds
                max_attempts=3
            )

            # Update configuration
            update_config = UpdateConfig(
                parallelism=1,
                delay=10 * 1000000000,  # 10 seconds
                failure_action="rollback"
            )

            # Labels for identification
            labels = {
                "saasodoo.service.type": "database-pool",
                "saasodoo.pool.name": pool_name,
                "saasodoo.pool.max_instances": str(max_instances),
                "saasodoo.postgres.version": postgres_version
            }

            # Create the service
            service = self.client.services.create(
                image=postgres_image,
                name=pool_name,
                env=environment,
                resources=resources,
                mounts=mounts,
                networks=[network],
                mode=ServiceMode('replicated', replicas=1),
                restart_policy=restart_policy,
                update_config=update_config,
                labels=labels,
                healthcheck=healthcheck,
                constraints=placement_constraints
            )

            logger.info("PostgreSQL pool service created successfully",
                       pool_name=pool_name,
                       service_id=service.id)

            return {
                "service_id": service.id,
                "service_name": pool_name
            }

        except Exception as e:
            logger.error("Failed to create PostgreSQL pool service",
                        pool_name=pool_name,
                        error=str(e))
            raise

    def wait_for_service_ready(
        self,
        service_id: str,
        timeout: int = 180,
        check_interval: int = 10
    ) -> bool:
        """
        Wait for PostgreSQL service to become healthy

        Args:
            service_id: Docker service ID or name
            timeout: Maximum wait time in seconds
            check_interval: Seconds between health checks

        Returns:
            True if service is healthy, False if timeout or failed
        """
        try:
            self._ensure_connection()
            service = self.client.services.get(service_id)

            logger.info("Waiting for PostgreSQL service to become ready",
                       service_id=service_id,
                       timeout=timeout)

            start_time = time.time()
            last_log_time = start_time

            while time.time() - start_time < timeout:
                service.reload()
                tasks = service.tasks(filters={'desired-state': 'running'})

                # Check for running tasks
                running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
                failed_tasks = [t for t in tasks if t['Status']['State'] == 'failed']

                # Log progress every 30 seconds
                if time.time() - last_log_time > 30:
                    logger.info("Waiting for service readiness",
                               service_id=service_id,
                               running_tasks=len(running_tasks),
                               failed_tasks=len(failed_tasks),
                               elapsed=int(time.time() - start_time))
                    last_log_time = time.time()

                # Check for failures
                if failed_tasks and not running_tasks:
                    logger.error("Service tasks failed",
                                service_id=service_id,
                                failed_tasks=len(failed_tasks))
                    return False

                # Check if we have a healthy running task
                if running_tasks:
                    task = running_tasks[0]

                    # Check if task has been running for at least 10 seconds (stability check)
                    created_at = task.get('CreatedAt')
                    if created_at:
                        from datetime import datetime
                        try:
                            create_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            uptime = (datetime.now(create_time.tzinfo) - create_time).total_seconds()

                            if uptime > 10:
                                logger.info("PostgreSQL service is healthy",
                                           service_id=service_id,
                                           uptime=uptime)
                                return True
                        except Exception:
                            pass

                time.sleep(check_interval)

            logger.error("Service failed to become ready within timeout",
                        service_id=service_id,
                        timeout=timeout)
            return False

        except Exception as e:
            logger.error("Error while waiting for service readiness",
                        service_id=service_id,
                        error=str(e))
            return False

    def remove_service(self, service_id: str) -> bool:
        """
        Remove a Docker Swarm service

        Args:
            service_id: Service ID or name to remove

        Returns:
            True if removed successfully, False otherwise
        """
        try:
            self._ensure_connection()

            try:
                service = self.client.services.get(service_id)
                service.remove()
                logger.info("Service removed successfully", service_id=service_id)
                return True
            except docker.errors.NotFound:
                logger.warning("Service not found for removal", service_id=service_id)
                return True  # Already gone, consider success

        except Exception as e:
            logger.error("Failed to remove service", service_id=service_id, error=str(e))
            return False

    def get_service_info(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed service information

        Args:
            service_id: Service ID or name

        Returns:
            Dictionary with service details or None if not found
        """
        try:
            self._ensure_connection()

            try:
                service = self.client.services.get(service_id)
                service.reload()
                tasks = service.tasks()

                running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
                failed_tasks = [t for t in tasks if t['Status']['State'] == 'failed']

                return {
                    "service_id": service.id,
                    "name": service.name,
                    "created_at": service.attrs.get('CreatedAt'),
                    "updated_at": service.attrs.get('UpdatedAt'),
                    "replicas": len(running_tasks),
                    "desired_replicas": service.attrs['Spec']['Mode'].get('Replicated', {}).get('Replicas', 0),
                    "running_tasks": len(running_tasks),
                    "failed_tasks": len(failed_tasks),
                    "labels": service.attrs.get('Spec', {}).get('Labels', {}),
                    "tasks": tasks
                }
            except docker.errors.NotFound:
                logger.debug("Service not found", service_id=service_id)
                return None

        except Exception as e:
            logger.error("Failed to get service info", service_id=service_id, error=str(e))
            return None

    def update_service_resources(
        self,
        service_id: str,
        cpu_limit: Optional[str] = None,
        memory_limit: Optional[str] = None
    ) -> bool:
        """
        Update service resource limits without downtime

        Args:
            service_id: Service ID or name
            cpu_limit: New CPU limit (e.g., "4" for 4 cores), optional
            memory_limit: New memory limit (e.g., "8G"), optional

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_connection()
            service = self.client.services.get(service_id)

            # Get current spec
            spec = service.attrs['Spec']
            task_template = spec['TaskTemplate']
            current_resources = task_template.get('Resources', {})

            # Update resources
            limits = current_resources.get('Limits', {})
            reservations = current_resources.get('Reservations', {})

            if cpu_limit:
                cpu_nano = int(float(cpu_limit) * 1e9)
                limits['NanoCPUs'] = cpu_nano
                reservations['NanoCPUs'] = int(cpu_nano * 0.5)

            if memory_limit:
                memory_bytes = self._parse_memory(memory_limit)
                limits['MemoryBytes'] = memory_bytes
                reservations['MemoryBytes'] = int(memory_bytes * 0.5)

            # Apply update
            service.update(
                task_template=task_template
            )

            logger.info("Service resources updated successfully",
                       service_id=service_id,
                       cpu_limit=cpu_limit,
                       memory_limit=memory_limit)
            return True

        except Exception as e:
            logger.error("Failed to update service resources",
                        service_id=service_id,
                        error=str(e))
            return False


# Global singleton instance
_docker_client = None


def get_docker_client() -> PostgreSQLDockerClient:
    """
    Get singleton instance of PostgreSQL Docker client

    Returns:
        PostgreSQLDockerClient instance
    """
    global _docker_client
    if _docker_client is None:
        _docker_client = PostgreSQLDockerClient()
    return _docker_client

# Alias for compatibility with provisioning tasks
DockerClientWrapper = PostgreSQLDockerClient
