"""
Admin endpoints for manual job management
"""

from typing import List
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, Request
import structlog

from app.tasks.provisioning import provision_instance_task
from app.utils.database import InstanceDatabase
from app.models.instance import InstanceStatus

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_database(request: Request) -> InstanceDatabase:
    """Dependency to get database instance"""
    return request.app.state.db


@router.get("/failed-instances")
async def get_failed_instances(
    db: InstanceDatabase = Depends(get_database)
):
    """Get list of instances in ERROR status that can be retried"""
    try:
        failed_instances = await db.get_instances_by_status(InstanceStatus.ERROR)
        
        return {
            "failed_instances": failed_instances,
            "count": len(failed_instances)
        }
        
    except Exception as e:
        logger.error("Failed to get failed instances", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/retry-instance/{instance_id}")
async def retry_instance_provisioning(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Manually retry provisioning for a failed instance"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        if instance.status != InstanceStatus.ERROR:
            raise HTTPException(
                status_code=400, 
                detail=f"Instance is not in ERROR status (current: {instance.status})"
            )
        
        # Reset status to CREATING
        await db.update_instance_status(instance_id, InstanceStatus.CREATING)
        
        # Queue new job
        job = provision_instance_task.delay(str(instance_id))
        
        logger.info("Instance retry queued", instance_id=str(instance_id), job_id=job.id)
        
        return {
            "message": "Instance provisioning retry queued",
            "instance_id": str(instance_id),
            "job_id": job.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retry instance", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/instance-jobs/{instance_id}")
async def get_instance_job_history(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Get job history for an instance"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        return {
            "instance_id": str(instance_id),
            "current_status": instance.status,
            "error_message": instance.error_message,
            "last_updated": instance.updated_at.isoformat(),
            "job_history": []  # Would contain actual job attempts
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get job history", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/instance-stats")
async def get_instance_stats(
    db: InstanceDatabase = Depends(get_database)
):
    """Get overall instance statistics"""
    try:
        # Get instances by status
        creating_instances = await db.get_instances_by_status(InstanceStatus.CREATING)
        starting_instances = await db.get_instances_by_status(InstanceStatus.STARTING)
        running_instances = await db.get_instances_by_status(InstanceStatus.RUNNING)
        stopped_instances = await db.get_instances_by_status(InstanceStatus.STOPPED)
        error_instances = await db.get_instances_by_status(InstanceStatus.ERROR)
        terminated_instances = await db.get_instances_by_status(InstanceStatus.TERMINATED)
        container_missing_instances = await db.get_instances_by_status(InstanceStatus.CONTAINER_MISSING)

        return {
            "status_counts": {
                "creating": len(creating_instances),
                "starting": len(starting_instances),
                "running": len(running_instances),
                "stopped": len(stopped_instances),
                "error": len(error_instances),
                "terminated": len(terminated_instances),
                "container_missing": len(container_missing_instances)
            },
            "total_instances": (
                len(creating_instances) + len(starting_instances) +
                len(running_instances) + len(stopped_instances) +
                len(error_instances) + len(terminated_instances) +
                len(container_missing_instances)
            ),
            "healthy_instances": len(running_instances),
            "failed_instances": len(error_instances)
        }

    except Exception as e:
        logger.error("Failed to get instance stats", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/all-instances")
async def get_all_instances(
    db: InstanceDatabase = Depends(get_database)
):
    """Get all instances across all customers (admin only)"""
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    id, customer_id, name, subdomain, status,
                    subscription_id, billing_status, odoo_version,
                    created_at, updated_at
                FROM instances
                WHERE status != $1
                ORDER BY created_at DESC
            """, InstanceStatus.TERMINATED.value)

            instances = []
            for row in rows:
                instances.append({
                    "id": str(row['id']),
                    "customer_id": str(row['customer_id']),
                    "name": row['name'],
                    "subdomain": row['subdomain'],
                    "status": row['status'],
                    "subscription_id": row['subscription_id'],
                    "billing_status": row['billing_status'],
                    "odoo_version": row['odoo_version'],
                    "created_at": row['created_at'].isoformat() if row['created_at'] else None,
                    "updated_at": row['updated_at'].isoformat() if row['updated_at'] else None
                })

            return {
                "instances": instances,
                "total": len(instances)
            }

    except Exception as e:
        logger.error("Failed to get all instances", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")