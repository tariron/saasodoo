"""
Database Allocation API Endpoints
Handles database allocation requests from instance-service
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import structlog
from asyncpg import Connection

from app.utils.database import get_db_connection
from app.services.db_allocation_service import DatabaseAllocationService

logger = structlog.get_logger(__name__)

router = APIRouter()


class AllocationRequest(BaseModel):
    """Request schema for database allocation"""
    instance_id: str
    customer_id: str
    plan_tier: str
    require_dedicated: Optional[bool] = None


class AllocationResponse(BaseModel):
    """Response schema for successful allocation"""
    status: str
    db_server_id: Optional[str] = None
    db_host: Optional[str] = None
    db_port: Optional[int] = None
    db_name: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    message: Optional[str] = None
    retry_after: Optional[int] = None


class ProvisionDedicatedRequest(BaseModel):
    """Request schema for dedicated server provisioning"""
    instance_id: str
    customer_id: str
    plan_tier: str


class ProvisionDedicatedResponse(BaseModel):
    """Response schema for dedicated server provisioning"""
    status: str
    db_server_id: Optional[str] = None
    db_host: Optional[str] = None
    message: Optional[str] = None


@router.post("/allocate", response_model=AllocationResponse)
async def allocate_database(
    request: AllocationRequest,
    conn: Connection = Depends(get_db_connection)
):
    """
    Allocate a database for an Odoo instance

    Process:
    1. Check if plan requires dedicated database
    2. If shared pool required:
       - Find available pool with capacity
       - If found: Allocate database immediately
       - If not found: Return provisioning status
    3. If dedicated required:
       - Return provisioning status (caller must use provision-dedicated endpoint)

    Returns either:
    - Immediate allocation with database credentials (status='allocated')
    - Provisioning needed (status='provisioning')
    """
    try:
        logger.info(
            "Database allocation request received",
            instance_id=request.instance_id,
            customer_id=request.customer_id,
            plan_tier=request.plan_tier,
            require_dedicated=request.require_dedicated
        )

        # Initialize allocation service
        allocation_service = DatabaseAllocationService(conn)

        # Attempt allocation
        result = await allocation_service.allocate_database_for_instance(
            instance_id=request.instance_id,
            customer_id=request.customer_id,
            plan_tier=request.plan_tier,
            require_dedicated=request.require_dedicated
        )

        if result is None:
            # No pool available, provisioning needed
            logger.info(
                "No pool available, provisioning required",
                instance_id=request.instance_id,
                plan_tier=request.plan_tier
            )

            return AllocationResponse(
                status="provisioning",
                message="No database pool available. Provisioning new pool...",
                retry_after=30
            )

        # Allocation successful
        logger.info(
            "Database allocated successfully",
            instance_id=request.instance_id,
            db_server_id=result['db_server_id'],
            db_host=result['db_host']
        )

        return AllocationResponse(
            status="allocated",
            db_server_id=result['db_server_id'],
            db_host=result['db_host'],
            db_port=result['db_port'],
            db_name=result['db_name'],
            db_user=result['db_user'],
            db_password=result['db_password']
        )

    except ValueError as e:
        logger.error(
            "Invalid allocation request",
            instance_id=request.instance_id,
            error=str(e)
        )
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(
            "Database allocation failed",
            instance_id=request.instance_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Database allocation failed: {str(e)}"
        )


@router.post("/provision-dedicated", response_model=ProvisionDedicatedResponse)
async def provision_dedicated_server(
    request: ProvisionDedicatedRequest,
    conn: Connection = Depends(get_db_connection)
):
    """
    Provision a dedicated PostgreSQL server for premium customers

    This is a long-running operation (2-3 minutes) that:
    1. Creates dedicated PostgreSQL server via Docker Swarm
    2. Waits for server to become healthy
    3. Returns server details

    Note: This endpoint blocks until provisioning completes.
    Consider using as async task in production.
    """
    try:
        logger.info(
            "Dedicated server provisioning request",
            instance_id=request.instance_id,
            customer_id=request.customer_id,
            plan_tier=request.plan_tier
        )

        # Verify plan supports dedicated database
        if request.plan_tier not in ['premium', 'enterprise']:
            raise HTTPException(
                status_code=400,
                detail=f"Plan '{request.plan_tier}' does not support dedicated database"
            )

        # Initialize allocation service
        allocation_service = DatabaseAllocationService(conn)

        # Provision dedicated server (blocking operation)
        db_server = await allocation_service.provision_dedicated_db_for_instance(
            instance_id=request.instance_id,
            customer_id=request.customer_id,
            plan_tier=request.plan_tier
        )

        logger.info(
            "Dedicated server provisioned successfully",
            instance_id=request.instance_id,
            db_server_id=str(db_server['id']),
            db_host=db_server['host']
        )

        return ProvisionDedicatedResponse(
            status="provisioned",
            db_server_id=str(db_server['id']),
            db_host=db_server['host'],
            message="Dedicated database server provisioned successfully"
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Dedicated server provisioning failed",
            instance_id=request.instance_id,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to provision dedicated server: {str(e)}"
        )
