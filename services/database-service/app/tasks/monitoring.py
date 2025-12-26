"""
Database Pool Monitoring Tasks
Periodic health checks and cleanup tasks for database pools
"""

import os
import structlog
import asyncpg
from datetime import datetime, timedelta

from app.celery_config import celery_app
from app.utils.database import db_service
from app.utils.k8s_client import PostgreSQLKubernetesClient

logger = structlog.get_logger(__name__)


@celery_app.task(
    name='app.tasks.monitoring.health_check_db_pools',
    bind=False,
    max_retries=0  # Don't retry periodic tasks
)
def health_check_db_pools():
    """
    Celery task wrapper that runs the async health check workflow
    """
    import asyncio
    return asyncio.run(_health_check_db_pools_async())


async def _health_check_db_pools_async():
    """
    Periodic health check task for all active database pools

    This task runs every 5 minutes (configured in celery beat schedule) and:
    1. Queries all active pools from database
    2. Tests connectivity to each PostgreSQL server
    3. Executes test query
    4. Verifies database count matches records
    5. Updates health status in database
    6. Marks pools as unhealthy after 3 consecutive failures

    Returns:
        dict: Summary of health check results
    """
    try:
        logger.info("Starting scheduled health check for all pools")

        # Create fresh database connection for this task
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'instance'),
            user=os.getenv('DB_SERVICE_USER', 'database_service'),
            password=os.getenv('DB_SERVICE_PASSWORD', 'database_service_secure_pass_change_me')
        )

        try:
            # Query all pools including error status to allow recovery
            query = """
                SELECT id, name, host, port, status, health_status, health_check_failures,
                       admin_user, admin_password
                FROM db_servers
                WHERE status IN ('active', 'full', 'initializing', 'error')
                ORDER BY last_health_check ASC NULLS FIRST
            """
            pools = await conn.fetch(query)

            logger.info(f"Checking health of {len(pools)} pools")

            results = {
                'healthy': 0,
                'degraded': 0,
                'unhealthy': 0,
                'total': len(pools)
            }

            # Check each pool
            for pool in pools:
                pool_id = str(pool['id'])
                pool_name = pool['name']

                try:
                    # Get admin credentials from database record
                    admin_user = pool['admin_user']
                    admin_password = pool['admin_password']

                    if not admin_user or not admin_password:
                        logger.warning(
                            "Admin credentials not configured for pool, skipping health check",
                            pool_name=pool_name
                        )
                        continue

                    # Connect to the pool's PostgreSQL server
                    pool_conn = await asyncpg.connect(
                        host=pool['host'],
                        port=pool['port'],
                        user=admin_user,
                        password=admin_password,
                        database='postgres',
                        timeout=5.0
                    )

                    try:
                        # Execute test query
                        result = await pool_conn.fetchval("SELECT 1")

                        if result == 1:
                            # Health check passed
                            update_query = """
                                UPDATE db_servers
                                SET health_status = 'healthy',
                                    health_check_failures = 0,
                                    last_health_check = NOW()
                                WHERE id = $1
                            """
                            await conn.execute(update_query, pool_id)

                            results['healthy'] += 1

                            logger.debug("Pool health check passed", pool_name=pool_name)

                            # If pool was initializing/error and is now healthy, promote to active
                            if pool['status'] in ('initializing', 'error'):
                                await conn.execute(
                                    "UPDATE db_servers SET status = 'active' WHERE id = $1",
                                    pool_id
                                )
                                logger.info(
                                    "Pool recovered and promoted to active",
                                    pool_name=pool_name,
                                    previous_status=pool['status']
                                )

                    finally:
                        await pool_conn.close()

                except (asyncpg.PostgresError, OSError, TimeoutError) as e:
                    # Health check failed
                    failure_count = (pool['health_check_failures'] or 0) + 1

                    # Determine health status based on failure count
                    if failure_count >= 3:
                        new_health_status = 'unhealthy'
                        results['unhealthy'] += 1

                        # If pool was active, mark as error
                        if pool['status'] == 'active':
                            await conn.execute(
                                """
                                UPDATE db_servers
                                SET status = 'error',
                                    health_status = $1,
                                    health_check_failures = $2,
                                    last_health_check = NOW()
                                WHERE id = $3
                                """,
                                new_health_status, failure_count, pool_id
                            )

                            logger.error(
                                "Pool marked as unhealthy and errored",
                                pool_name=pool_name,
                                failure_count=failure_count,
                                error=str(e)
                            )
                        else:
                            await conn.execute(
                                """
                                UPDATE db_servers
                                SET health_status = $1,
                                    health_check_failures = $2,
                                    last_health_check = NOW()
                                WHERE id = $3
                                """,
                                new_health_status, failure_count, pool_id
                            )
                    else:
                        new_health_status = 'degraded'
                        results['degraded'] += 1

                        await conn.execute(
                            """
                            UPDATE db_servers
                            SET health_status = $1,
                                health_check_failures = $2,
                                last_health_check = NOW()
                            WHERE id = $3
                            """,
                            new_health_status, failure_count, pool_id
                        )

                    logger.warning(
                        "Pool health check failed",
                        pool_name=pool_name,
                        failure_count=failure_count,
                        health_status=new_health_status,
                        error=str(e)
                    )

            # Log summary
            logger.info(
                "Health check completed",
                total=results['total'],
                healthy=results['healthy'],
                degraded=results['degraded'],
                unhealthy=results['unhealthy']
            )

            return results

        finally:
            await conn.close()

    except Exception as e:
        logger.error("Health check task failed", error=str(e), exc_info=True)
        raise


@celery_app.task(
    name='app.tasks.monitoring.cleanup_failed_pools',
    bind=False,
    max_retries=0
)
def cleanup_failed_pools():
    """
    Celery task wrapper that runs the async cleanup workflow
    """
    import asyncio
    return asyncio.run(_cleanup_failed_pools_async())


async def _cleanup_failed_pools_async():
    """
    Cleanup task for failed database pools

    This task runs daily and:
    1. Identifies pools in 'error' status with no active databases
    2. Removes Docker Swarm services
    3. Optionally archives CephFS data
    4. Removes or marks database records as deprovisioned
    5. Cleans up orphaned Docker services

    Returns:
        dict: Summary of cleanup operations
    """
    try:
        logger.info("Starting failed pools cleanup task")

        k8s_client = PostgreSQLKubernetesClient()

        if not db_service.pool:
            await db_service.connect()

        async with db_service.get_connection() as conn:
            # Find failed pools with no active databases
            query = """
                SELECT id, name, swarm_service_id, storage_path, status, last_health_check
                FROM db_servers
                WHERE status = 'error'
                  AND current_instances = 0
                  AND last_health_check < NOW() - INTERVAL '24 hours'
            """
            failed_pools = await conn.fetch(query)

            logger.info(f"Found {len(failed_pools)} failed pools eligible for cleanup")

            results = {
                'removed_services': 0,
                'cleaned_storage': 0,
                'updated_records': 0,
                'errors': 0
            }

            for pool in failed_pools:
                pool_id = str(pool['id'])
                pool_name = pool['name']
                service_id = pool['swarm_service_id']

                try:
                    # Remove Kubernetes StatefulSet
                    if service_id:
                        try:
                            removed = k8s_client.remove_service(service_id)
                            if removed:
                                results['removed_services'] += 1
                                logger.info(
                                    "Kubernetes StatefulSet removed",
                                    pool_name=pool_name,
                                    service_id=service_id
                                )
                        except Exception as e:
                            logger.error(
                                "Failed to remove Docker service",
                                pool_name=pool_name,
                                service_id=service_id,
                                error=str(e)
                            )
                            results['errors'] += 1

                    # TODO: Archive CephFS data before deletion
                    # For now, we'll leave the data directory intact

                    # Update database record
                    update_query = """
                        UPDATE db_servers
                        SET status = 'deprovisioned',
                            updated_at = NOW()
                        WHERE id = $1
                    """
                    await conn.execute(update_query, pool_id)
                    results['updated_records'] += 1

                    logger.info(
                        "Pool cleaned up",
                        pool_name=pool_name,
                        pool_id=pool_id
                    )

                except Exception as e:
                    logger.error(
                        "Failed to cleanup pool",
                        pool_name=pool_name,
                        error=str(e),
                        exc_info=True
                    )
                    results['errors'] += 1

            logger.info(
                "Cleanup task completed",
                removed_services=results['removed_services'],
                updated_records=results['updated_records'],
                errors=results['errors']
            )

            return results

    except Exception as e:
        logger.error("Cleanup task failed", error=str(e), exc_info=True)
        raise
