"""
Database Pool Provisioning Tasks
Async tasks for provisioning new PostgreSQL pools and dedicated servers
"""

import os
import asyncio
import secrets
import structlog
from pathlib import Path
from celery import Task
from celery.exceptions import Reject

from app.celery_config import celery_app
from app.utils.k8s_client import PostgreSQLKubernetesClient
from app.utils.database import db_service

logger = structlog.get_logger(__name__)


class ProvisioningTask(Task):
    """
    Base task class for provisioning operations
    Provides Kubernetes client initialization and error handling
    """

    def __init__(self):
        super().__init__()
        self._k8s_client = None

    @property
    def k8s_client(self):
        """Lazy initialization of Kubernetes client"""
        if self._k8s_client is None:
            self._k8s_client = PostgreSQLKubernetesClient()
        return self._k8s_client


@celery_app.task(
    bind=True,
    base=ProvisioningTask,
    name='app.tasks.provisioning.provision_database_pool',
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def provision_database_pool(self, max_instances: int = 50):
    """
    Celery task wrapper for pool provisioning
    Executes async workflow using asyncio.run()
    """
    try:
        logger.info("Pool provisioning task started", task_id=self.request.id, max_instances=max_instances)
        result = asyncio.run(_provision_database_pool_workflow(self, max_instances))
        logger.info("Pool provisioning task completed", task_id=self.request.id, result=result)
        return result
    except Exception as e:
        logger.error("Pool provisioning task failed", task_id=self.request.id, error=str(e), exc_info=True)
        raise


async def _provision_database_pool_workflow(self, max_instances: int = 50):
    """
    Provision a new shared PostgreSQL pool

    This task:
    1. Creates CephFS directory structure
    2. Generates admin credentials
    3. Creates database record
    4. Creates Docker Swarm service
    5. Waits for service health
    6. Activates pool for allocation

    Args:
        max_instances: Maximum number of databases this pool can host

    Returns:
        str: ID of newly provisioned pool

    Raises:
        Reject: For permanent failures that shouldn't be retried
    """
    import asyncpg

    pool_name = None
    db_server_id = None

    try:
        logger.info("Starting database pool provisioning", max_instances=max_instances)

        # Create new database connection for this task
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'instance'),
            user=os.getenv('DB_SERVICE_USER', 'database_service'),
            password=os.getenv('DB_SERVICE_PASSWORD', 'database_service_secure_pass_change_me')
        )

        try:
            # Step 1: Determine next pool number
            count_query = """
                SELECT COUNT(*) as count
                FROM db_servers
                WHERE server_type = 'shared'
            """
            result = await conn.fetchrow(count_query)
            pool_number = result['count'] + 1
            pool_name = f"postgres-pool-{pool_number}"
            pvc_name = f"postgres-pool-{pool_number}"

            logger.info("Determined pool name", pool_name=pool_name, pool_number=pool_number)

            # Step 2: Check if db_servers record already exists (idempotent retry handling)
            existing_query = """
                SELECT id, admin_password, status
                FROM db_servers
                WHERE name = $1
            """
            existing_row = await conn.fetchrow(existing_query, pool_name)

            if existing_row:
                # Record exists - this is a retry, reuse existing password
                db_server_id = str(existing_row['id'])
                admin_password = existing_row['admin_password']
                logger.info("Found existing db_server record (retry scenario)",
                           db_server_id=db_server_id,
                           pool_name=pool_name,
                           current_status=existing_row['status'])

                # Reset status to provisioning if it was error
                if existing_row['status'] == 'error':
                    await conn.execute(
                        "UPDATE db_servers SET status = 'provisioning' WHERE id = $1",
                        db_server_id
                    )
            else:
                # Step 3: Generate new credentials (only for first run)
                admin_password = secrets.token_urlsafe(32)

                # Step 4: Create database record
                insert_query = """
                    INSERT INTO db_servers (
                        name, host, port, server_type, max_instances, current_instances,
                        status, health_status, storage_path, postgres_version, postgres_image,
                        cpu_limit, memory_limit, allocation_strategy, priority,
                        provisioned_by, provisioned_at, admin_user, admin_password
                    )
                    VALUES (
                        $1, $2, 5432, 'shared', $3, 0,
                        'provisioning', 'unknown', $4, '16', 'postgres:16-alpine',
                        '2', '4G', 'auto', 10,
                        'provisioning_task', NOW(), 'postgres', $5
                    )
                    RETURNING id
                """
                row = await conn.fetchrow(
                    insert_query,
                    pool_name,  # name
                    pool_name,  # host (K8s service DNS)
                    max_instances,  # max_instances
                    pvc_name,  # storage_path (now stores PVC name)
                    admin_password  # admin_password
                )
                db_server_id = str(row['id'])
                logger.info("Created new db_server record", db_server_id=db_server_id, pool_name=pool_name)

            # Step 5: Create PVC (idempotent - checks if exists)
            storage_size = "50Gi"  # Default pool storage size

            try:
                logger.info("Ensuring PVC for PostgreSQL pool", pvc_name=pvc_name, size=storage_size)
                self.k8s_client.create_postgres_pvc(pvc_name, storage_size)
                logger.info("PVC ready", pvc_name=pvc_name)

            except Exception as e:
                logger.error("PVC creation failed", pvc_name=pvc_name, error=str(e))
                raise Reject(f"Failed to create PVC: {e}", requeue=False)

            # Step 6: Create Kubernetes StatefulSet (idempotent)
            try:
                service_info = self.k8s_client.create_postgres_pool_service(
                    pool_name=pool_name,
                    postgres_password=admin_password,
                    pvc_name=pvc_name,
                    cpu_limit="2",
                    memory_limit="4G",
                    max_instances=max_instances
                )

                service_id = service_info['service_id']
                service_name = service_info['service_name']

                logger.info(
                    "Docker service created",
                    service_id=service_id,
                    service_name=service_name
                )

                # Update database record with service details
                update_query = """
                    UPDATE db_servers
                    SET swarm_service_id = $1,
                        swarm_service_name = $2,
                        status = 'initializing'
                    WHERE id = $3
                """
                await conn.execute(update_query, service_id, service_name, db_server_id)

            except Exception as e:
                logger.error(
                    "Docker service creation failed",
                    pool_name=pool_name,
                    error=str(e),
                    exc_info=True
                )

                # Update status to error
                error_update = """
                    UPDATE db_servers
                    SET status = 'error', health_status = 'unhealthy'
                    WHERE id = $1
                """
                await conn.execute(error_update, db_server_id)

                raise  # Will retry

            # Step 6: Wait for service health
            try:
                healthy = self.k8s_client.wait_for_service_ready(
                    service_id=service_id,
                    timeout=180,  # 3 minutes
                    check_interval=10
                )

                if healthy:
                    # Mark as active
                    activate_query = """
                        UPDATE db_servers
                        SET status = 'active', health_status = 'healthy',
                            last_health_check = NOW()
                        WHERE id = $1
                    """
                    await conn.execute(activate_query, db_server_id)

                    logger.info(
                        "Pool provisioned successfully",
                        pool_name=pool_name,
                        db_server_id=db_server_id
                    )

                    return db_server_id

                else:
                    # Health check failed
                    logger.error(
                        "Pool health check failed",
                        pool_name=pool_name,
                        service_id=service_id
                    )

                    # Update status
                    error_update = """
                        UPDATE db_servers
                        SET status = 'error', health_status = 'unhealthy'
                        WHERE id = $1
                    """
                    await conn.execute(error_update, db_server_id)

                    raise Exception(f"Pool {pool_name} failed health check after provisioning")

            except Exception as e:
                logger.error(
                    "Health check wait failed",
                    pool_name=pool_name,
                    error=str(e)
                )
                raise  # Will retry

        finally:
            await conn.close()

    except Reject:
        raise  # Don't retry permanent failures

    except Exception as e:
        logger.error(
            "Pool provisioning failed",
            pool_name=pool_name,
            db_server_id=db_server_id,
            error=str(e),
            exc_info=True,
            retry_count=self.request.retries
        )

        # Check if we should retry
        if self.request.retries >= self.max_retries:
            logger.error(
                "Pool provisioning exhausted retries",
                pool_name=pool_name,
                max_retries=self.max_retries
            )

        raise


@celery_app.task(
    bind=True,
    base=ProvisioningTask,
    name='app.tasks.provisioning.provision_dedicated_server',
    max_retries=2,
    default_retry_delay=120,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def provision_dedicated_server(
    self,
    instance_id: str,
    customer_id: str,
    plan_tier: str
):
    """
    Celery task wrapper for dedicated server provisioning
    Executes async workflow using asyncio.run()
    """
    try:
        logger.info("Dedicated server provisioning task started", task_id=self.request.id, instance_id=instance_id)
        result = asyncio.run(_provision_dedicated_server_workflow(self, instance_id, customer_id, plan_tier))
        logger.info("Dedicated server provisioning completed", task_id=self.request.id, result=result)
        return result
    except Exception as e:
        logger.error("Dedicated server provisioning failed", task_id=self.request.id, error=str(e), exc_info=True)
        raise


async def _provision_dedicated_server_workflow(
    self,
    instance_id: str,
    customer_id: str,
    plan_tier: str
):
    """
    Provision a dedicated PostgreSQL server for premium customer

    This task:
    1. Creates dedicated CephFS directory
    2. Generates admin credentials
    3. Creates database record (max_instances=1, dedicated flags)
    4. Creates Docker Swarm service with higher resources
    5. Waits for service health
    6. Returns server details

    Args:
        instance_id: UUID of Odoo instance
        customer_id: UUID of customer
        plan_tier: Subscription plan tier

    Returns:
        dict: Dedicated server details
    """
    import asyncpg

    server_name = None
    db_server_id = None

    try:
        logger.info(
            "Starting dedicated server provisioning",
            instance_id=instance_id,
            customer_id=customer_id,
            plan_tier=plan_tier
        )

        # Create new database connection for this task
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'instance'),
            user=os.getenv('DB_SERVICE_USER', 'database_service'),
            password=os.getenv('DB_SERVICE_PASSWORD', 'database_service_secure_pass_change_me')
        )

        try:
            # Step 1: Generate server name (use instance_id for uniqueness, not customer_id)
            instance_short = instance_id[:8]
            server_name = f"postgres-dedicated-{instance_short}"
            pvc_name = f"postgres-dedicated-{instance_short}"

            logger.info("Determined server name", server_name=server_name, instance_id=instance_id)

            # Step 2: Check if db_servers record already exists (idempotent retry handling)
            existing_query = """
                SELECT id, admin_password, status
                FROM db_servers
                WHERE name = $1
            """
            existing_row = await conn.fetchrow(existing_query, server_name)

            if existing_row:
                # Record exists - this is a retry, reuse existing password
                db_server_id = str(existing_row['id'])
                admin_password = existing_row['admin_password']
                logger.info("Found existing db_server record (retry scenario)",
                           db_server_id=db_server_id,
                           server_name=server_name,
                           current_status=existing_row['status'])

                # Reset status to provisioning if it was error
                if existing_row['status'] == 'error':
                    await conn.execute(
                        "UPDATE db_servers SET status = 'provisioning' WHERE id = $1",
                        db_server_id
                    )
            else:
                # Step 3: Generate new credentials (only for first run)
                admin_password = secrets.token_urlsafe(32)

                # Step 4: Create database record
                insert_query = """
                    INSERT INTO db_servers (
                        name, host, port, server_type, max_instances, current_instances,
                        status, health_status, storage_path, postgres_version, postgres_image,
                        cpu_limit, memory_limit, allocation_strategy,
                        dedicated_to_customer_id, dedicated_to_instance_id,
                        provisioned_by, provisioned_at, admin_user, admin_password
                    )
                    VALUES (
                        $1, $2, 5432, 'dedicated', 1, 0,
                        'provisioning', 'unknown', $3, '16', 'postgres:16-alpine',
                        '2', '4G', 'manual',
                        $4, $5,
                        'provisioning_task', NOW(), 'postgres', $6
                    )
                    RETURNING id
                """
                row = await conn.fetchrow(
                    insert_query,
                    server_name, server_name, pvc_name,  # storage_path now stores PVC name
                    customer_id, instance_id, admin_password
                )
                db_server_id = str(row['id'])
                logger.info("Created new db_server record", db_server_id=db_server_id)

            # Step 5: Create PVC (idempotent - checks if exists)
            storage_size = "100Gi"  # Dedicated server storage size

            try:
                logger.info("Ensuring PVC for dedicated PostgreSQL server", pvc_name=pvc_name, size=storage_size)
                self.k8s_client.create_postgres_pvc(pvc_name, storage_size)
                logger.info("PVC ready", pvc_name=pvc_name)

            except Exception as e:
                logger.error("PVC creation failed", pvc_name=pvc_name, error=str(e))
                raise Reject(f"Failed to create PVC: {e}", requeue=False)

            # Step 6: Create Kubernetes StatefulSet for dedicated server (idempotent)
            try:
                service_info = self.k8s_client.create_postgres_pool_service(
                    pool_name=server_name,
                    postgres_password=admin_password,
                    pvc_name=pvc_name,
                    cpu_limit="2",  # Same as shared pools
                    memory_limit="4G",  # Same as shared pools
                    max_instances=1  # Only one database
                )

                service_id = service_info['service_id']

                # Update record
                update_query = """
                    UPDATE db_servers
                    SET swarm_service_id = $1,
                        swarm_service_name = $2,
                        status = 'initializing'
                    WHERE id = $3
                """
                await conn.execute(update_query, service_id, server_name, db_server_id)

                logger.info("Dedicated service created", service_id=service_id)

            except Exception as e:
                logger.error("Service creation failed", error=str(e), exc_info=True)

                # Mark as error
                await conn.execute(
                    "UPDATE db_servers SET status = 'error' WHERE id = $1",
                    db_server_id
                )

                raise

            # Step 6: Wait for health
            healthy = self.k8s_client.wait_for_service_ready(
                service_id=service_id,
                timeout=180
            )

            if healthy:
                activate_query = """
                    UPDATE db_servers
                    SET status = 'active', health_status = 'healthy',
                        last_health_check = NOW()
                    WHERE id = $1
                    RETURNING *
                """
                server = await conn.fetchrow(activate_query, db_server_id)

                logger.info(
                    "Dedicated server provisioned",
                    server_name=server_name,
                    instance_id=instance_id
                )

                return {
                    'id': str(server['id']),
                    'name': server['name'],
                    'host': server['host'],
                    'port': server['port'],
                    'status': server['status']
                }

            else:
                await conn.execute(
                    "UPDATE db_servers SET status = 'error' WHERE id = $1",
                    db_server_id
                )
                raise Exception(f"Dedicated server {server_name} failed health check")

        finally:
            await conn.close()

    except Exception as e:
        logger.error(
            "Dedicated provisioning failed",
            server_name=server_name,
            error=str(e),
            exc_info=True
        )
        raise
