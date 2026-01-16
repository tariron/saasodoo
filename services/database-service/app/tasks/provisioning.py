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
    Provision a new shared PostgreSQL pool using CNPG

    This task:
    1. Creates CNPG Cluster (handles PVC automatically)
    2. Creates CNPG Pooler (PgBouncer)
    3. Waits for cluster health
    4. Reads admin password from K8s Secret
    5. Creates database record
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
        logger.info("Starting CNPG database pool provisioning", max_instances=max_instances)

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

            logger.info("Determined pool name", pool_name=pool_name, pool_number=pool_number)

            # Step 2: Check if db_servers record already exists (idempotent retry handling)
            existing_query = """
                SELECT id, status
                FROM db_servers
                WHERE name = $1
            """
            existing_row = await conn.fetchrow(existing_query, pool_name)

            if existing_row:
                db_server_id = str(existing_row['id'])
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
                # Step 3: Create database record
                # Host points to pooler service: {pool_name}-pooler-rw
                # Password stored in K8s Secret: {pool_name}-superuser
                insert_query = """
                    INSERT INTO db_servers (
                        name, host, port, server_type, max_instances, current_instances,
                        status, health_status, storage_path, postgres_version, postgres_image,
                        cpu_limit, memory_limit, allocation_strategy, priority,
                        provisioned_by, provisioned_at, admin_user
                    )
                    VALUES (
                        $1, $2, 5432, 'shared', $3, 0,
                        'provisioning', 'unknown', $4, '16', 'cnpg',
                        '2', '4G', 'auto', 10,
                        'provisioning_task', NOW(), 'postgres'
                    )
                    RETURNING id
                """
                # Host is the pooler service name for PgBouncer connection
                # CNPG Pooler creates service: {cluster}-pooler
                pooler_host = f"{pool_name}-pooler"
                row = await conn.fetchrow(
                    insert_query,
                    pool_name,  # name
                    pooler_host,  # host (pooler service)
                    max_instances,  # max_instances
                    pool_name,  # storage_path (CNPG manages PVC)
                )
                db_server_id = str(row['id'])
                logger.info("Created new db_server record", db_server_id=db_server_id, pool_name=pool_name)

            # Step 4: Create CNPG Cluster (idempotent - handles PVC automatically)
            storage_size = "50Gi"

            try:
                logger.info("Creating CNPG Cluster", pool_name=pool_name, size=storage_size)
                cluster_info = self.k8s_client.create_cnpg_cluster(
                    cluster_name=pool_name,
                    storage_size=storage_size,
                    cpu_limit="2",
                    memory_limit="4G",
                    max_instances=max_instances,
                    instances=1
                )
                logger.info("CNPG Cluster creation initiated", cluster_info=cluster_info)

                # Update status to initializing
                await conn.execute(
                    "UPDATE db_servers SET status = 'initializing', swarm_service_id = $1, swarm_service_name = $2 WHERE id = $3",
                    pool_name, pool_name, db_server_id
                )

            except Exception as e:
                logger.error("CNPG Cluster creation failed", pool_name=pool_name, error=str(e), exc_info=True)
                await conn.execute(
                    "UPDATE db_servers SET status = 'error', health_status = 'unhealthy' WHERE id = $1",
                    db_server_id
                )
                raise

            # Step 5: Wait for CNPG Cluster to be ready
            try:
                healthy = self.k8s_client.wait_for_cnpg_cluster_ready(
                    cluster_name=pool_name,
                    timeout=300,  # 5 minutes for CNPG
                    check_interval=10
                )

                if not healthy:
                    logger.error("CNPG Cluster health check failed", pool_name=pool_name)
                    await conn.execute(
                        "UPDATE db_servers SET status = 'error', health_status = 'unhealthy' WHERE id = $1",
                        db_server_id
                    )
                    raise Exception(f"CNPG Cluster {pool_name} failed health check after provisioning")

                logger.info("CNPG Cluster is healthy", pool_name=pool_name)

            except Exception as e:
                logger.error("CNPG Cluster health check wait failed", pool_name=pool_name, error=str(e))
                raise

            # Step 6: Create CNPG Pooler (PgBouncer)
            try:
                logger.info("Creating CNPG Pooler", pool_name=pool_name)
                pooler_info = self.k8s_client.create_cnpg_pooler(
                    cluster_name=pool_name,
                    pooler_instances=2,
                    pool_mode="transaction",
                    max_client_conn=1000,
                    default_pool_size=20
                )
                logger.info("CNPG Pooler created", pooler_info=pooler_info)

            except Exception as e:
                logger.error("CNPG Pooler creation failed", pool_name=pool_name, error=str(e))
                # Continue anyway - direct connection still works
                logger.warning("Continuing without pooler - direct connection available")

            # Step 7: Verify admin password exists in K8s Secret
            secret_name = f"{pool_name}-superuser"
            admin_password = self.k8s_client.get_secret_value(secret_name, "password")

            if not admin_password:
                logger.error("Failed to read admin password from secret", secret_name=secret_name)
                await conn.execute(
                    "UPDATE db_servers SET status = 'error' WHERE id = $1",
                    db_server_id
                )
                raise Exception(f"Failed to read admin password from secret {secret_name}")

            logger.info("Verified admin password exists in K8s Secret", secret_name=secret_name)

            # Step 8: Mark pool as active (password read from K8s Secret at runtime)
            activate_query = """
                UPDATE db_servers
                SET status = 'active',
                    health_status = 'healthy',
                    last_health_check = NOW()
                WHERE id = $1
            """
            await conn.execute(activate_query, db_server_id)

            logger.info(
                "CNPG Pool provisioned successfully",
                pool_name=pool_name,
                db_server_id=db_server_id
            )

            return db_server_id

        finally:
            await conn.close()

    except Reject:
        raise  # Don't retry permanent failures

    except Exception as e:
        logger.error(
            "CNPG Pool provisioning failed",
            pool_name=pool_name,
            db_server_id=db_server_id,
            error=str(e),
            exc_info=True,
            retry_count=self.request.retries
        )

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
    Provision a dedicated PostgreSQL server for premium customer using CNPG

    This task:
    1. Creates CNPG Cluster with 1 instance (handles PVC automatically)
    2. Optionally creates CNPG Pooler (PgBouncer)
    3. Waits for cluster health
    4. Reads admin password from K8s Secret
    5. Creates database record
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
            "Starting CNPG dedicated server provisioning",
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
            # Step 1: Generate server name (use instance_id for uniqueness)
            instance_short = instance_id[:8]
            server_name = f"postgres-dedicated-{instance_short}"

            logger.info("Determined server name", server_name=server_name, instance_id=instance_id)

            # Step 2: Check if db_servers record already exists (idempotent retry handling)
            existing_query = """
                SELECT id, status
                FROM db_servers
                WHERE name = $1
            """
            existing_row = await conn.fetchrow(existing_query, server_name)

            if existing_row:
                db_server_id = str(existing_row['id'])
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
                # Step 3: Create database record
                # For dedicated, use direct connection (no pooler by default)
                # Password stored in K8s Secret: {server_name}-superuser
                direct_host = f"{server_name}-rw"
                insert_query = """
                    INSERT INTO db_servers (
                        name, host, port, server_type, max_instances, current_instances,
                        status, health_status, storage_path, postgres_version, postgres_image,
                        cpu_limit, memory_limit, allocation_strategy,
                        dedicated_to_customer_id, dedicated_to_instance_id,
                        provisioned_by, provisioned_at, admin_user
                    )
                    VALUES (
                        $1, $2, 5432, 'dedicated', 1, 0,
                        'provisioning', 'unknown', $3, '16', 'cnpg',
                        '2', '4G', 'manual',
                        $4, $5,
                        'provisioning_task', NOW(), 'postgres'
                    )
                    RETURNING id
                """
                row = await conn.fetchrow(
                    insert_query,
                    server_name,
                    direct_host,  # Direct connection for dedicated
                    server_name,  # CNPG manages PVC
                    customer_id,
                    instance_id
                )
                db_server_id = str(row['id'])
                logger.info("Created new db_server record", db_server_id=db_server_id)

            # Step 4: Create CNPG Cluster (idempotent - handles PVC automatically)
            storage_size = "100Gi"  # Larger storage for dedicated

            try:
                logger.info("Creating CNPG Cluster for dedicated server", server_name=server_name, size=storage_size)
                cluster_info = self.k8s_client.create_cnpg_cluster(
                    cluster_name=server_name,
                    storage_size=storage_size,
                    cpu_limit="2",
                    memory_limit="4G",
                    max_instances=1,  # Dedicated = 1 database
                    instances=1
                )
                logger.info("CNPG Cluster creation initiated", cluster_info=cluster_info)

                # Update status to initializing
                await conn.execute(
                    "UPDATE db_servers SET status = 'initializing', swarm_service_id = $1, swarm_service_name = $2 WHERE id = $3",
                    server_name, server_name, db_server_id
                )

            except Exception as e:
                logger.error("CNPG Cluster creation failed", server_name=server_name, error=str(e), exc_info=True)
                await conn.execute(
                    "UPDATE db_servers SET status = 'error', health_status = 'unhealthy' WHERE id = $1",
                    db_server_id
                )
                raise

            # Step 5: Wait for CNPG Cluster to be ready
            healthy = self.k8s_client.wait_for_cnpg_cluster_ready(
                cluster_name=server_name,
                timeout=300,
                check_interval=10
            )

            if not healthy:
                logger.error("CNPG Cluster health check failed", server_name=server_name)
                await conn.execute(
                    "UPDATE db_servers SET status = 'error', health_status = 'unhealthy' WHERE id = $1",
                    db_server_id
                )
                raise Exception(f"CNPG Cluster {server_name} failed health check")

            logger.info("CNPG Cluster is healthy", server_name=server_name)

            # Step 6: Verify admin password exists in K8s Secret
            secret_name = f"{server_name}-superuser"
            admin_password = self.k8s_client.get_secret_value(secret_name, "password")

            if not admin_password:
                logger.error("Failed to read admin password from secret", secret_name=secret_name)
                await conn.execute(
                    "UPDATE db_servers SET status = 'error' WHERE id = $1",
                    db_server_id
                )
                raise Exception(f"Failed to read admin password from secret {secret_name}")

            logger.info("Verified admin password exists in K8s Secret", secret_name=secret_name)

            # Step 7: Mark server as active (password read from K8s Secret at runtime)
            activate_query = """
                UPDATE db_servers
                SET status = 'active',
                    health_status = 'healthy',
                    last_health_check = NOW()
                WHERE id = $1
                RETURNING *
            """
            server = await conn.fetchrow(activate_query, db_server_id)

            logger.info(
                "CNPG Dedicated server provisioned",
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

        finally:
            await conn.close()

    except Exception as e:
        logger.error(
            "CNPG Dedicated provisioning failed",
            server_name=server_name,
            error=str(e),
            exc_info=True
        )
        raise
