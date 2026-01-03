"""
Instance action routes (start, stop, restart, backup, restore, etc.)
"""

from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends
import structlog

from app.models.instance import (
    InstanceAction, InstanceActionRequest, InstanceActionResponse
)
from app.utils.database import InstanceDatabase
from app.tasks.lifecycle import restart_instance_task, start_instance_task, stop_instance_task, unpause_instance_task
from app.tasks.maintenance import backup_instance_task, restore_instance_task, update_instance_task
from app.routes.instances.helpers import (
    get_database,
    get_valid_actions_for_status,
    suspend_instance,
    unsuspend_instance,
    terminate_instance
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/{instance_id}/actions", response_model=InstanceActionResponse)
async def perform_instance_action(
    instance_id: UUID,
    action_request: InstanceActionRequest,
    db: InstanceDatabase = Depends(get_database)
):
    """Perform action on instance (start, stop, restart, etc.)"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        action = action_request.action
        logger.info("Performing instance action", instance_id=str(instance_id), action=action.value)

        # Validate action based on current status
        valid_actions = get_valid_actions_for_status(instance.status)
        if action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Action '{action}' not allowed for instance with status '{instance.status}'"
            )

        # Perform the action
        if action == InstanceAction.START:
            # Queue start task instead of direct execution
            job = start_instance_task.delay(str(instance_id))
            result = {
                "status": "queued",
                "message": f"Instance start queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.STOP:
            # Queue stop task instead of direct execution
            job = stop_instance_task.delay(str(instance_id))
            result = {
                "status": "queued",
                "message": f"Instance stop queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.RESTART:
            # Queue restart task instead of direct execution
            job = restart_instance_task.delay(str(instance_id))
            result = {
                "status": "queued",
                "message": f"Instance restart queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.UPDATE:
            # Queue update task
            target_version = action_request.parameters.get('version') if action_request.parameters else None
            if not target_version:
                raise HTTPException(status_code=400, detail="Target version required for update action")
            job = update_instance_task.delay(str(instance_id), target_version)
            result = {
                "status": "queued",
                "message": f"Instance update to {target_version} queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.BACKUP:
            # Queue backup task
            backup_name = action_request.parameters.get('name') if action_request.parameters else None
            job = backup_instance_task.delay(str(instance_id), backup_name)
            result = {
                "status": "queued",
                "message": f"Instance backup queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.RESTORE:
            # Queue restore task
            backup_id = action_request.parameters.get('backup_id') if action_request.parameters else None
            if not backup_id:
                raise HTTPException(status_code=400, detail="Backup ID required for restore action")
            job = restore_instance_task.delay(str(instance_id), backup_id)
            result = {
                "status": "queued",
                "message": f"Instance restore from backup {backup_id} queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.SUSPEND:
            # Suspend instance (immediate status change)
            result = await suspend_instance(instance_id, db)
        elif action == InstanceAction.UNSUSPEND:
            # Unsuspend instance (immediate status change)
            result = await unsuspend_instance(instance_id, db)
        elif action == InstanceAction.UNPAUSE:
            # Queue unpause task instead of direct execution
            job = unpause_instance_task.delay(str(instance_id))
            result = {
                "status": "queued",
                "message": f"Instance unpause queued for processing",
                "timestamp": datetime.utcnow().isoformat(),
                "job_id": job.id
            }
        elif action == InstanceAction.TERMINATE:
            # Terminate instance (immediate status change)
            result = await terminate_instance(instance_id, db)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

        return InstanceActionResponse(
            instance_id=str(instance_id),
            action=action,
            status=result["status"],
            message=result["message"],
            timestamp=result["timestamp"],
            job_id=result.get("job_id")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to perform instance action", instance_id=str(instance_id), action=action_request.action, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{instance_id}/status")
async def get_instance_status(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Get current instance status and health"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # TODO: Check actual container status and health
        # container_status = await check_container_status(instance.container_id)

        return {
            "instance_id": str(instance_id),
            "status": instance.status,
            "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
            "error_message": instance.error_message,
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get instance status", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{instance_id}/logs")
async def get_instance_logs(
    instance_id: UUID,
    lines: int = Query(100, ge=1, le=1000, description="Number of log lines to retrieve"),
    db: InstanceDatabase = Depends(get_database)
):
    """Get instance logs"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # TODO: Implement log retrieval from container
        # logs = await get_container_logs(instance.container_id, lines)

        # Placeholder response
        logs = [
            f"[INFO] Instance {instance.name} log entry {i}" for i in range(min(lines, 10))
        ]

        return {
            "instance_id": str(instance_id),
            "logs": logs,
            "timestamp": instance.updated_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get instance logs", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
