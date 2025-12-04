"""
Admin API Endpoints for Database Service
Provides monitoring, management, and administrative operations for database pools
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import structlog
from asyncpg import Connection
from datetime import datetime

from app.utils.database import get_db_connection

logger = structlog.get_logger(__name__)

router = APIRouter()


class PoolInfo(BaseModel):
    """Database pool information schema"""
    id: str
    name: str
    server_type: str
    status: str
    health_status: str
    current_instances: int
    max_instances: int
    capacity_percentage: float
    host: str
    port: int
    postgres_version: str
    cpu_limit: Optional[str]
    memory_limit: Optional[str]
    created_at: datetime
    last_health_check: Optional[datetime]


class PoolListResponse(BaseModel):
    """Response schema for pool listing"""
    pools: List[PoolInfo]
    total_count: int


class PoolDetailResponse(BaseModel):
    """Response schema for detailed pool information"""
    pool: PoolInfo
    swarm_service_id: Optional[str]
    swarm_service_name: Optional[str]
    storage_path: Optional[str]
    allocated_storage_gb: Optional[int]
    provisioned_at: Optional[datetime]
    last_allocated_at: Optional[datetime]


class PoolStatsResponse(BaseModel):
    """Response schema for pool statistics"""
    total_pools: int
    active_pools: int
    total_capacity: int
    total_used: int
    overall_utilization: float
    by_status: Dict[str, int]
    by_type: Dict[str, int]


class HealthCheckResult(BaseModel):
    """Response schema for health check"""
    pool_id: str
    status: str
    health_status: str
    message: str
    checked_at: datetime


@router.get("/pools", response_model=PoolListResponse)
async def list_pools(
    status: Optional[str] = Query(None, description="Filter by status"),
    server_type: Optional[str] = Query(None, description="Filter by server type"),
    conn: Connection = Depends(get_db_connection)
):
    """
    List all database pools with optional filtering

    Query Parameters:
    - status: Filter by pool status (active, full, error, etc.)
    - server_type: Filter by type (shared, dedicated, platform)

    Returns list of pools with their current status and capacity information
    """
    try:
        logger.info("Listing database pools", status=status, server_type=server_type)

        # Build query with filters
        query = """
            SELECT
                id, name, server_type, status, health_status,
                current_instances, max_instances, host, port,
                postgres_version, cpu_limit, memory_limit, created_at,
                last_health_check
            FROM db_servers
            WHERE 1=1
        """
        params = []
        param_count = 1

        if status:
            query += f" AND status = ${param_count}"
            params.append(status)
            param_count += 1

        if server_type:
            query += f" AND server_type = ${param_count}"
            params.append(server_type)
            param_count += 1

        query += " ORDER BY created_at DESC"

        # Execute query
        rows = await conn.fetch(query, *params)

        # Transform results
        pools = []
        for row in rows:
            capacity_pct = (row['current_instances'] / row['max_instances'] * 100) if row['max_instances'] > 0 else 0

            pools.append(PoolInfo(
                id=str(row['id']),
                name=row['name'],
                server_type=row['server_type'],
                status=row['status'],
                health_status=row['health_status'],
                current_instances=row['current_instances'],
                max_instances=row['max_instances'],
                capacity_percentage=round(capacity_pct, 2),
                host=row['host'],
                port=row['port'],
                postgres_version=row['postgres_version'],
                cpu_limit=row['cpu_limit'],
                memory_limit=row['memory_limit'],
                created_at=row['created_at'],
                last_health_check=row['last_health_check']
            ))

        logger.info("Pools retrieved", count=len(pools))

        return PoolListResponse(
            pools=pools,
            total_count=len(pools)
        )

    except Exception as e:
        logger.error("Failed to list pools", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list pools: {str(e)}")


@router.get("/pools/{pool_id}", response_model=PoolDetailResponse)
async def get_pool_details(
    pool_id: str,
    conn: Connection = Depends(get_db_connection)
):
    """
    Get detailed information about a specific database pool

    Includes all pool metadata, Docker Swarm service information,
    and storage details
    """
    try:
        logger.info("Getting pool details", pool_id=pool_id)

        # Query pool information
        query = """
            SELECT *
            FROM db_servers
            WHERE id = $1
        """
        row = await conn.fetchrow(query, pool_id)

        if not row:
            raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")

        # Calculate capacity percentage
        capacity_pct = (row['current_instances'] / row['max_instances'] * 100) if row['max_instances'] > 0 else 0

        pool_info = PoolInfo(
            id=str(row['id']),
            name=row['name'],
            server_type=row['server_type'],
            status=row['status'],
            health_status=row['health_status'],
            current_instances=row['current_instances'],
            max_instances=row['max_instances'],
            capacity_percentage=round(capacity_pct, 2),
            host=row['host'],
            port=row['port'],
            postgres_version=row['postgres_version'],
            cpu_limit=row['cpu_limit'],
            memory_limit=row['memory_limit'],
            created_at=row['created_at'],
            last_health_check=row['last_health_check']
        )

        logger.info("Pool details retrieved", pool_id=pool_id, name=row['name'])

        return PoolDetailResponse(
            pool=pool_info,
            swarm_service_id=row['swarm_service_id'],
            swarm_service_name=row['swarm_service_name'],
            storage_path=row['storage_path'],
            allocated_storage_gb=row['allocated_storage_gb'],
            provisioned_at=row['provisioned_at'],
            last_allocated_at=row['last_allocated_at']
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("Failed to get pool details", pool_id=pool_id, error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get pool details: {str(e)}")


@router.get("/stats", response_model=PoolStatsResponse)
async def get_pool_statistics(
    conn: Connection = Depends(get_db_connection)
):
    """
    Get aggregated statistics about all database pools

    Returns:
    - Total number of pools
    - Active pools count
    - Total capacity vs used capacity
    - Overall utilization percentage
    - Breakdown by status and type
    """
    try:
        logger.info("Getting pool statistics")

        # Get overall stats
        overall_query = """
            SELECT
                COUNT(*) as total_pools,
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active_pools,
                SUM(max_instances) as total_capacity,
                SUM(current_instances) as total_used
            FROM db_servers
        """
        overall = await conn.fetchrow(overall_query)

        # Get breakdown by status
        status_query = """
            SELECT status, COUNT(*) as count
            FROM db_servers
            GROUP BY status
        """
        status_rows = await conn.fetch(status_query)
        by_status = {row['status']: row['count'] for row in status_rows}

        # Get breakdown by type
        type_query = """
            SELECT server_type, COUNT(*) as count
            FROM db_servers
            GROUP BY server_type
        """
        type_rows = await conn.fetch(type_query)
        by_type = {row['server_type']: row['count'] for row in type_rows}

        # Calculate utilization
        total_capacity = overall['total_capacity'] or 0
        total_used = overall['total_used'] or 0
        utilization = (total_used / total_capacity * 100) if total_capacity > 0 else 0

        logger.info(
            "Pool statistics retrieved",
            total_pools=overall['total_pools'],
            utilization=round(utilization, 2)
        )

        return PoolStatsResponse(
            total_pools=overall['total_pools'],
            active_pools=overall['active_pools'],
            total_capacity=total_capacity,
            total_used=total_used,
            overall_utilization=round(utilization, 2),
            by_status=by_status,
            by_type=by_type
        )

    except Exception as e:
        logger.error("Failed to get pool statistics", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.post("/pools/{pool_id}/health-check", response_model=HealthCheckResult)
async def trigger_health_check(
    pool_id: str,
    conn: Connection = Depends(get_db_connection)
):
    """
    Trigger immediate health check on a specific pool

    This endpoint:
    1. Attempts to connect to the PostgreSQL server
    2. Executes a test query
    3. Updates health status in database
    4. Returns health check result

    Use for manual verification or debugging connection issues
    """
    try:
        logger.info("Manual health check triggered", pool_id=pool_id)

        # Get pool information
        pool_query = """
            SELECT id, name, host, port, status
            FROM db_servers
            WHERE id = $1
        """
        pool = await conn.fetchrow(pool_query, pool_id)

        if not pool:
            raise HTTPException(status_code=404, detail=f"Pool {pool_id} not found")

        # TODO: Implement actual health check
        # For now, return placeholder response
        # In production, this would:
        # 1. Connect to PostgreSQL server
        # 2. Execute SELECT 1
        # 3. Check response time
        # 4. Update health_status and last_health_check

        logger.warning(
            "Health check not fully implemented",
            pool_id=pool_id,
            pool_name=pool['name']
        )

        return HealthCheckResult(
            pool_id=str(pool['id']),
            status=pool['status'],
            health_status="unknown",
            message="Health check implementation pending",
            checked_at=datetime.utcnow()
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Health check failed",
            pool_id=pool_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Health check failed: {str(e)}"
        )


class ProvisionPoolRequest(BaseModel):
    """Request schema for manual pool provisioning"""
    max_instances: int = 50
    server_type: str = "shared"


class ProvisionPoolResponse(BaseModel):
    """Response schema for pool provisioning"""
    task_id: str
    message: str
    max_instances: int


@router.post("/provision-pool", response_model=ProvisionPoolResponse)
async def provision_pool(
    request: ProvisionPoolRequest
):
    """
    Manually trigger provisioning of a new shared database pool

    This is an admin/testing endpoint to manually create new pools.
    In production, pools are typically auto-provisioned when needed.

    Request:
    - max_instances: Maximum number of databases this pool can host (default: 50)
    - server_type: Type of pool - currently only "shared" is supported

    Returns task_id for monitoring the provisioning progress
    """
    try:
        from app.tasks.provisioning import provision_database_pool

        logger.info(
            "Manual pool provisioning requested",
            max_instances=request.max_instances,
            server_type=request.server_type
        )

        if request.server_type != "shared":
            raise HTTPException(
                status_code=400,
                detail="Only 'shared' pool type is supported for manual provisioning"
            )

        # Queue provisioning task
        result = provision_database_pool.delay(max_instances=request.max_instances)

        logger.info(
            "Pool provisioning task queued",
            task_id=result.id,
            max_instances=request.max_instances
        )

        return ProvisionPoolResponse(
            task_id=result.id,
            message=f"Pool provisioning started. Expected completion in 2-3 minutes.",
            max_instances=request.max_instances
        )

    except Exception as e:
        logger.error("Failed to queue pool provisioning", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start pool provisioning: {str(e)}"
        )
