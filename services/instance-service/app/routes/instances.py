"""
Instance management routes
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Request, HTTPException, Query, Depends
import structlog

from app.models.instance import (
    InstanceCreate, InstanceUpdate, InstanceResponse, InstanceListResponse,
    InstanceAction, InstanceActionRequest, InstanceActionResponse,
    InstanceStatus
)
from app.utils.validators import validate_instance_resources, validate_database_name, validate_addon_names
from app.utils.database import InstanceDatabase

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_database(request: Request) -> InstanceDatabase:
    """Dependency to get database instance"""
    return request.app.state.db


@router.post("/", response_model=InstanceResponse, status_code=201)
async def create_instance(
    instance_data: InstanceCreate,
    db: InstanceDatabase = Depends(get_database)
):
    """Create a new Odoo instance"""
    try:
        logger.info("Creating instance", name=instance_data.name, tenant_id=str(instance_data.tenant_id))
        
        # Validate instance resources
        resource_errors = validate_instance_resources(
            instance_data.instance_type,
            instance_data.cpu_limit,
            instance_data.memory_limit,
            instance_data.storage_limit
        )
        if resource_errors:
            raise HTTPException(status_code=400, detail={"errors": resource_errors})
        
        # Validate database name format
        db_name_errors = validate_database_name(instance_data.database_name)
        if db_name_errors:
            raise HTTPException(status_code=400, detail={"errors": db_name_errors})
        
        # Validate addon names
        addon_errors = validate_addon_names(instance_data.custom_addons)
        if addon_errors:
            raise HTTPException(status_code=400, detail={"errors": addon_errors})
        
        # Create instance in database
        instance = await db.create_instance(instance_data)
        
        # Convert to response format
        response_data = {
            "id": str(instance.id),
            "tenant_id": str(instance.tenant_id),
            "name": instance.name,
            "description": instance.description,
            "odoo_version": instance.odoo_version,
            "instance_type": instance.instance_type,
            "status": instance.status,
            "cpu_limit": instance.cpu_limit,
            "memory_limit": instance.memory_limit,
            "storage_limit": instance.storage_limit,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url,
            "admin_email": instance.admin_email,
            "error_message": instance.error_message,
            "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
            "created_at": instance.created_at.isoformat(),
            "updated_at": instance.updated_at.isoformat(),
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "demo_data": instance.demo_data,
            "database_name": instance.database_name,
            "custom_addons": instance.custom_addons,
            "metadata": instance.metadata or {}
        }
        
        logger.info("Instance created successfully", instance_id=str(instance.id))
        
        # TODO: Trigger async instance provisioning here
        # await provision_instance_async(instance.id)
        
        return InstanceResponse(**response_data)
        
    except ValueError as e:
        logger.warning("Instance creation validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to create instance", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Get instance by ID"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        response_data = {
            "id": str(instance.id),
            "tenant_id": str(instance.tenant_id),
            "name": instance.name,
            "description": instance.description,
            "odoo_version": instance.odoo_version,
            "instance_type": instance.instance_type,
            "status": instance.status,
            "cpu_limit": instance.cpu_limit,
            "memory_limit": instance.memory_limit,
            "storage_limit": instance.storage_limit,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url,
            "admin_email": instance.admin_email,
            "error_message": instance.error_message,
            "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
            "created_at": instance.created_at.isoformat(),
            "updated_at": instance.updated_at.isoformat(),
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "demo_data": instance.demo_data,
            "database_name": instance.database_name,
            "custom_addons": instance.custom_addons,
            "metadata": instance.metadata or {}
        }
        
        return InstanceResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get instance", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/", response_model=InstanceListResponse)
async def list_instances(
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant ID"),
    status: Optional[InstanceStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: InstanceDatabase = Depends(get_database)
):
    """List instances with optional filtering"""
    try:
        if tenant_id:
            result = await db.get_instances_by_tenant(tenant_id, page, page_size)
        else:
            # For now, require tenant_id. In future, could support listing all instances for admins
            raise HTTPException(status_code=400, detail="tenant_id parameter is required")
        
        # Convert instances to response format
        instance_responses = []
        for instance_data in result['instances']:
            response_data = {
                "id": str(instance_data['id']),
                "tenant_id": str(instance_data['tenant_id']),
                "name": instance_data['name'],
                "description": instance_data['description'],
                "odoo_version": instance_data['odoo_version'],
                "instance_type": instance_data['instance_type'],
                "status": instance_data['status'],
                "cpu_limit": instance_data['cpu_limit'],
                "memory_limit": instance_data['memory_limit'],
                "storage_limit": instance_data['storage_limit'],
                "external_url": instance_data['external_url'],
                "internal_url": instance_data['internal_url'],
                "admin_email": instance_data['admin_email'],
                "error_message": instance_data['error_message'],
                "last_health_check": instance_data['last_health_check'].isoformat() if instance_data['last_health_check'] else None,
                "created_at": instance_data['created_at'].isoformat(),
                "updated_at": instance_data['updated_at'].isoformat(),
                "started_at": instance_data['started_at'].isoformat() if instance_data['started_at'] else None,
                "demo_data": instance_data['demo_data'],
                "database_name": instance_data['database_name'],
                "custom_addons": instance_data['custom_addons'],
                "metadata": instance_data['metadata'] or {}
            }
            
            # Apply status filter if specified
            if status is None or instance_data['status'] == status.value:
                instance_responses.append(InstanceResponse(**response_data))
        
        # Adjust totals if filtering by status
        total = len(instance_responses) if status else result['total']
        
        return InstanceListResponse(
            instances=instance_responses,
            total=total,
            page=result['page'],
            page_size=result['page_size']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list instances", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{instance_id}", response_model=InstanceResponse)
async def update_instance(
    instance_id: UUID,
    update_data: InstanceUpdate,
    db: InstanceDatabase = Depends(get_database)
):
    """Update instance information"""
    try:
        # Validate if instance exists
        existing_instance = await db.get_instance(instance_id)
        if not existing_instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Validate resource changes if being updated
        if any([update_data.cpu_limit, update_data.memory_limit, update_data.storage_limit, update_data.instance_type]):
            instance_type = update_data.instance_type or existing_instance.instance_type
            cpu_limit = update_data.cpu_limit or existing_instance.cpu_limit
            memory_limit = update_data.memory_limit or existing_instance.memory_limit
            storage_limit = update_data.storage_limit or existing_instance.storage_limit
            
            resource_errors = validate_instance_resources(instance_type, cpu_limit, memory_limit, storage_limit)
            if resource_errors:
                raise HTTPException(status_code=400, detail={"errors": resource_errors})
        
        # Validate addon names if being updated
        if update_data.custom_addons is not None:
            addon_errors = validate_addon_names(update_data.custom_addons)
            if addon_errors:
                raise HTTPException(status_code=400, detail={"errors": addon_errors})
        
        # Update instance
        updated_instance = await db.update_instance(instance_id, update_data)
        if not updated_instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        response_data = {
            "id": str(updated_instance.id),
            "tenant_id": str(updated_instance.tenant_id),
            "name": updated_instance.name,
            "description": updated_instance.description,
            "odoo_version": updated_instance.odoo_version,
            "instance_type": updated_instance.instance_type,
            "status": updated_instance.status,
            "cpu_limit": updated_instance.cpu_limit,
            "memory_limit": updated_instance.memory_limit,
            "storage_limit": updated_instance.storage_limit,
            "external_url": updated_instance.external_url,
            "internal_url": updated_instance.internal_url,
            "admin_email": updated_instance.admin_email,
            "error_message": updated_instance.error_message,
            "last_health_check": updated_instance.last_health_check.isoformat() if updated_instance.last_health_check else None,
            "created_at": updated_instance.created_at.isoformat(),
            "updated_at": updated_instance.updated_at.isoformat(),
            "started_at": updated_instance.started_at.isoformat() if updated_instance.started_at else None,
            "demo_data": updated_instance.demo_data,
            "database_name": updated_instance.database_name,
            "custom_addons": updated_instance.custom_addons,
            "metadata": updated_instance.metadata or {}
        }
        
        logger.info("Instance updated successfully", instance_id=str(instance_id))
        return InstanceResponse(**response_data)
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Instance update validation failed", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to update instance", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{instance_id}")
async def delete_instance(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Delete instance (soft delete)"""
    try:
        # TODO: Stop instance containers before deletion
        # await stop_instance_containers(instance_id)
        
        success = await db.delete_instance(instance_id)
        if not success:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        logger.info("Instance deleted successfully", instance_id=str(instance_id))
        return {"message": "Instance deleted successfully"}
        
    except Exception as e:
        logger.error("Failed to delete instance", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


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
        valid_actions = _get_valid_actions_for_status(instance.status)
        if action not in valid_actions:
            raise HTTPException(
                status_code=400, 
                detail=f"Action '{action}' not allowed for instance with status '{instance.status}'"
            )
        
        # Perform the action
        if action == InstanceAction.START:
            result = await _start_instance(instance_id, db)
        elif action == InstanceAction.STOP:
            result = await _stop_instance(instance_id, db)
        elif action == InstanceAction.RESTART:
            result = await _restart_instance(instance_id, db)
        elif action == InstanceAction.UPDATE:
            result = await _update_instance_software(instance_id, db, action_request.parameters)
        elif action == InstanceAction.BACKUP:
            result = await _backup_instance(instance_id, db, action_request.parameters)
        elif action == InstanceAction.RESTORE:
            result = await _restore_instance(instance_id, db, action_request.parameters)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")
        
        return InstanceActionResponse(
            instance_id=str(instance_id),
            action=action,
            status=result["status"],
            message=result["message"],
            timestamp=result["timestamp"]
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


# Helper functions for instance actions

def _get_valid_actions_for_status(status: InstanceStatus) -> list[InstanceAction]:
    """Get valid actions for current instance status"""
    action_map = {
        InstanceStatus.CREATING: [],
        InstanceStatus.STARTING: [InstanceAction.STOP],
        InstanceStatus.RUNNING: [InstanceAction.STOP, InstanceAction.RESTART, InstanceAction.UPDATE, InstanceAction.BACKUP],
        InstanceStatus.STOPPING: [],
        InstanceStatus.STOPPED: [InstanceAction.START, InstanceAction.BACKUP, InstanceAction.RESTORE],
        InstanceStatus.RESTARTING: [],
        InstanceStatus.UPDATING: [],
        InstanceStatus.ERROR: [InstanceAction.START, InstanceAction.STOP, InstanceAction.RESTART],
        InstanceStatus.TERMINATED: []
    }
    return action_map.get(status, [])


async def _start_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Start instance containers"""
    from datetime import datetime
    
    try:
        # Update status to starting
        await db.update_instance_status(instance_id, InstanceStatus.STARTING)
        
        # TODO: Implement actual container starting logic
        # await docker_service.start_container(instance.container_id)
        
        # Update status to running and set started_at
        await db.update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        # Update started_at timestamp (this would be done in the update method)
        instance = await db.get_instance(instance_id)
        if instance:
            update_data = InstanceUpdate()
            # The started_at would be set in a more complete implementation
        
        return {
            "status": "success",
            "message": "Instance started successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _stop_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Stop instance containers"""
    from datetime import datetime
    
    try:
        # Update status to stopping
        await db.update_instance_status(instance_id, InstanceStatus.STOPPING)
        
        # TODO: Implement actual container stopping logic
        # await docker_service.stop_container(instance.container_id)
        
        # Update status to stopped
        await db.update_instance_status(instance_id, InstanceStatus.STOPPED)
        
        return {
            "status": "success",
            "message": "Instance stopped successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _restart_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Restart instance containers"""
    from datetime import datetime
    
    try:
        # Update status to restarting
        await db.update_instance_status(instance_id, InstanceStatus.RESTARTING)
        
        # TODO: Implement actual container restarting logic
        # await docker_service.restart_container(instance.container_id)
        
        # Update status to running
        await db.update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "message": "Instance restarted successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _update_instance_software(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Update instance software/modules"""
    from datetime import datetime
    
    try:
        # Update status to updating
        await db.update_instance_status(instance_id, InstanceStatus.UPDATING)
        
        # TODO: Implement actual update logic
        # target_version = parameters.get('version')
        # await docker_service.update_instance(instance_id, target_version)
        
        # Update status back to running
        await db.update_instance_status(instance_id, InstanceStatus.RUNNING)
        
        return {
            "status": "success",
            "message": "Instance updated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _backup_instance(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Create instance backup"""
    from datetime import datetime
    
    try:
        # TODO: Implement actual backup logic
        # backup_name = parameters.get('name', f'backup_{datetime.utcnow().isoformat()}')
        # await backup_service.create_backup(instance_id, backup_name)
        
        return {
            "status": "success",
            "message": "Instance backup created successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Backup failed", instance_id=str(instance_id), error=str(e))
        return {
            "status": "error",
            "message": f"Backup failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


async def _restore_instance(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Restore instance from backup"""
    from datetime import datetime
    
    try:
        # TODO: Implement actual restore logic
        # backup_id = parameters.get('backup_id')
        # await backup_service.restore_backup(instance_id, backup_id)
        
        return {
            "status": "success",
            "message": "Instance restored successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Restore failed", instance_id=str(instance_id), error=str(e))
        return {
            "status": "error",
            "message": f"Restore failed: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        } 