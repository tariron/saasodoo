"""
Instance management routes
"""

from typing import Optional
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Query, Depends
import structlog

from app.models.instance import (
    InstanceCreate, InstanceUpdate, InstanceResponse, InstanceListResponse,
    InstanceAction, InstanceActionRequest, InstanceActionResponse,
    InstanceStatus, BillingStatus, ProvisioningStatus
)
from app.utils.validators import validate_instance_resources, validate_database_name, validate_addon_names
from app.utils.database import InstanceDatabase
# NOTE: billing_client import removed to prevent accidental subscription creation calls
from app.tasks.provisioning import provision_instance_task
from app.tasks.lifecycle import restart_instance_task, start_instance_task, stop_instance_task, unpause_instance_task
from app.tasks.maintenance import backup_instance_task, restore_instance_task, update_instance_task

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
        logger.info("Creating instance", name=instance_data.name, customer_id=str(instance_data.customer_id))
        
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
        
        # The billing service is the source of truth for billing status.
        # This service only creates an instance record in the database.
        # The subscription must be created first by the billing service.
        if not instance_data.subscription_id:
            logger.error("INSTANCE SERVICE: Instance creation called without a subscription_id - this could trigger unwanted subscription creation",
                         customer_id=str(instance_data.customer_id),
                         instance_name=instance_data.name)
            raise HTTPException(
                status_code=400,
                detail="Instance creation must include a valid subscription_id to prevent duplicate subscription creation."
            )
        
        logger.info(f"INSTANCE SERVICE: Creating instance with existing subscription {instance_data.subscription_id} for customer {instance_data.customer_id}")

        # Create instance in database with status provided by the billing service
        instance = await db.create_instance(
            instance_data,
            billing_status=instance_data.billing_status,
            provisioning_status=instance_data.provisioning_status
        )

        # Link instance to the provided subscription ID
        await db.update_instance_subscription(str(instance.id), str(instance_data.subscription_id))
        instance.subscription_id = instance_data.subscription_id
        logger.info("Instance linked to existing subscription",
                    instance_id=str(instance.id),
                    subscription_id=str(instance_data.subscription_id))

        # CRITICAL: NO subscription creation here! The subscription_id was provided by billing service
        # CRITICAL: NO immediate provisioning here!
        # Provisioning will be triggered by billing webhooks:
        # - For trial instances: SUBSCRIPTION_CREATION webhook
        # - For paid instances: INVOICE_PAYMENT_SUCCESS webhook
        
        # Convert to response format and return immediately
        response_data = {
            "id": str(instance.id),
            "customer_id": str(instance.customer_id),
            "subscription_id": str(instance.subscription_id) if instance.subscription_id else None,
            "name": instance.name,
            "description": instance.description,
            "odoo_version": instance.odoo_version,
            "instance_type": instance.instance_type,
            "status": instance.status,  # Will be "creating"
            "billing_status": instance.billing_status,
            "provisioning_status": instance.provisioning_status,
            "cpu_limit": instance.cpu_limit,
            "memory_limit": instance.memory_limit,
            "storage_limit": instance.storage_limit,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url,
            "admin_email": instance.admin_email,
            "admin_password": instance.admin_password,
            "subdomain": instance.subdomain,
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
            "customer_id": str(instance.customer_id),
            "subscription_id": str(instance.subscription_id) if instance.subscription_id else None,
            "name": instance.name,
            "description": instance.description,
            "odoo_version": instance.odoo_version,
            "instance_type": instance.instance_type,
            "status": instance.status,
            "billing_status": instance.billing_status,
            "provisioning_status": instance.provisioning_status,
            "cpu_limit": instance.cpu_limit,
            "memory_limit": instance.memory_limit,
            "storage_limit": instance.storage_limit,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url,
            "admin_email": instance.admin_email,
            "admin_password": instance.admin_password,
            "subdomain": instance.subdomain,
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
    customer_id: Optional[UUID] = Query(None, description="Filter by customer ID"),
    status: Optional[InstanceStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: InstanceDatabase = Depends(get_database)
):
    """List instances with optional filtering"""
    try:
        if customer_id:
            result = await db.get_instances_by_customer(customer_id, page, page_size)
        else:
            # For now, require customer_id. In future, could support listing all instances for admins
            raise HTTPException(status_code=400, detail="customer_id parameter is required")
        
        # Convert instances to response format
        instance_responses = []
        for instance_data in result['instances']:
            response_data = {
                "id": str(instance_data['id']),
                "customer_id": str(instance_data['customer_id']),
                "subscription_id": str(instance_data['subscription_id']) if instance_data.get('subscription_id') else None,
                "name": instance_data['name'],
                "description": instance_data['description'],
                "odoo_version": instance_data['odoo_version'],
                "instance_type": instance_data['instance_type'],
                "status": instance_data['status'],
                "billing_status": instance_data.get('billing_status', 'pending'),
                "provisioning_status": instance_data.get('provisioning_status', 'pending'),
                "cpu_limit": instance_data['cpu_limit'],
                "memory_limit": instance_data['memory_limit'],
                "storage_limit": instance_data['storage_limit'],
                "external_url": instance_data['external_url'],
                "internal_url": instance_data['internal_url'],
                "admin_email": instance_data['admin_email'],
                "admin_password": instance_data.get('admin_password'),
                "subdomain": instance_data.get('subdomain'),
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


@router.get("/by-subscription/{subscription_id}", response_model=InstanceResponse)
async def get_instance_by_subscription(
    subscription_id: str,
    db: InstanceDatabase = Depends(get_database)
):
    """Get instance by subscription ID"""
    try:
        logger.info("Getting instance by subscription_id", subscription_id=subscription_id)
        
        instance = await db.get_instance_by_subscription_id(subscription_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found for subscription")
        
        logger.info("Found instance by subscription_id", 
                   instance_id=str(instance.id), 
                   subscription_id=subscription_id)
        
        response_data = {
            "id": str(instance.id),
            "customer_id": str(instance.customer_id),
            "subscription_id": str(instance.subscription_id) if instance.subscription_id else None,
            "name": instance.name,
            "description": instance.description,
            "odoo_version": instance.odoo_version,
            "instance_type": instance.instance_type,
            "status": instance.status,
            "billing_status": instance.billing_status,
            "provisioning_status": instance.provisioning_status,
            "cpu_limit": instance.cpu_limit,
            "memory_limit": instance.memory_limit,
            "storage_limit": instance.storage_limit,
            "external_url": instance.external_url,
            "internal_url": instance.internal_url,
            "admin_email": instance.admin_email,
            "admin_password": instance.admin_password,
            "subdomain": instance.subdomain,
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
        logger.error("Failed to get instance by subscription", 
                    subscription_id=subscription_id, 
                    error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve instance: {str(e)}")


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
            "customer_id": str(updated_instance.customer_id),
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
    """Delete instance (hard delete with cleanup)"""
    try:
        # Get instance details before deletion
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Import cleanup function from provisioning
        from app.tasks.provisioning import _cleanup_failed_provisioning
        
        # Perform hard cleanup of all resources
        instance_dict = {
            'id': instance.id,
            'database_name': instance.database_name,
            'name': instance.name
        }
        await _cleanup_failed_provisioning(str(instance_id), instance_dict)
        
        # Remove from database
        success = await db.delete_instance(instance_id)
        if not success:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        logger.info("Instance and resources deleted successfully", instance_id=str(instance_id))
        return {"message": "Instance and all resources deleted successfully"}
        
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
            result = await _suspend_instance(instance_id, db)
        elif action == InstanceAction.UNSUSPEND:
            # Unsuspend instance (immediate status change)
            result = await _unsuspend_instance(instance_id, db)
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
            result = await _terminate_instance(instance_id, db)
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


@router.get("/{instance_id}/backups")
async def list_instance_backups(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """List available backups for an instance"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Get backups from filesystem (in a full implementation, this would query a backups table)
        import os
        import json
        from pathlib import Path
        
        backup_dir = "/var/lib/odoo/backups/active"
        backups = []
        
        if os.path.exists(backup_dir):
            for file in os.listdir(backup_dir):
                if file.endswith("_metadata.json"):
                    metadata_path = os.path.join(backup_dir, file)
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                            if metadata.get('instance_id') == str(instance_id):
                                backups.append({
                                    "backup_id": metadata.get('backup_name'),
                                    "backup_name": metadata.get('backup_name'),
                                    "instance_name": metadata.get('instance_name'),
                                    "created_at": metadata.get('created_at'),
                                    "database_size": metadata.get('database_size', 0),
                                    "data_size": metadata.get('data_size', 0),
                                    "total_size": metadata.get('total_size', 0),
                                    "odoo_version": metadata.get('odoo_version'),
                                    "status": metadata.get('status')
                                })
                    except Exception as e:
                        logger.warning("Failed to read backup metadata", file=file, error=str(e))
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return {
            "instance_id": str(instance_id),
            "instance_name": instance.name,
            "backups": backups,
            "total_backups": len(backups)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list instance backups", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/check-subdomain/{subdomain}")
async def check_subdomain_availability(
    subdomain: str,
    db: InstanceDatabase = Depends(get_database)
):
    """Check if subdomain is available for use"""
    try:
        # Validate subdomain format (basic validation)
        if not subdomain or len(subdomain) < 3 or len(subdomain) > 50:
            raise HTTPException(
                status_code=400, 
                detail="Subdomain must be between 3 and 50 characters"
            )
        
        # Check if subdomain contains only valid characters
        if not subdomain.replace('-', '').isalnum():
            raise HTTPException(
                status_code=400, 
                detail="Subdomain must contain only alphanumeric characters and hyphens"
            )
        
        # Check if subdomain starts or ends with hyphen
        if subdomain.startswith('-') or subdomain.endswith('-'):
            raise HTTPException(
                status_code=400, 
                detail="Subdomain cannot start or end with a hyphen"
            )
        
        # Check availability in database
        is_available = await db.check_subdomain_availability(subdomain)
        
        return {
            "subdomain": subdomain,
            "available": is_available,
            "message": "Available" if is_available else "Already taken"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to check subdomain availability", subdomain=subdomain, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# Helper functions for instance actions

def _get_valid_actions_for_status(status: InstanceStatus) -> list[InstanceAction]:
    """Get valid actions for current instance status"""
    action_map = {
        InstanceStatus.CREATING: [InstanceAction.TERMINATE],
        InstanceStatus.STARTING: [InstanceAction.STOP, InstanceAction.SUSPEND, InstanceAction.TERMINATE],
        InstanceStatus.RUNNING: [InstanceAction.STOP, InstanceAction.RESTART, InstanceAction.UPDATE, InstanceAction.BACKUP, InstanceAction.SUSPEND, InstanceAction.TERMINATE],
        InstanceStatus.STOPPING: [InstanceAction.TERMINATE],
        InstanceStatus.STOPPED: [InstanceAction.START, InstanceAction.BACKUP, InstanceAction.RESTORE, InstanceAction.SUSPEND, InstanceAction.TERMINATE],
        InstanceStatus.RESTARTING: [InstanceAction.TERMINATE],
        InstanceStatus.UPDATING: [InstanceAction.TERMINATE],
        InstanceStatus.MAINTENANCE: [InstanceAction.TERMINATE],  # Allow termination during maintenance
        InstanceStatus.ERROR: [InstanceAction.START, InstanceAction.STOP, InstanceAction.RESTART, InstanceAction.RESTORE, InstanceAction.SUSPEND, InstanceAction.TERMINATE],
        InstanceStatus.TERMINATED: [],  # No actions allowed on terminated instances
        InstanceStatus.PAUSED: [InstanceAction.UNPAUSE, InstanceAction.TERMINATE]
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
        
        # Update started_at timestamp (this would be done in a more complete implementation)
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


async def _suspend_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Suspend instance due to billing issues - ACTUALLY stops the container"""
    from datetime import datetime
    import docker
    
    try:
        # Get current instance to check if it needs to be stopped first
        instance = await db.get_instance(instance_id)
        if not instance:
            raise Exception("Instance not found")
        
        # If instance is running, stop the actual Docker container first
        if instance.status == InstanceStatus.RUNNING:
            logger.info("Stopping running instance container before suspension", instance_id=str(instance_id))
            
            # Use the same Docker stopping logic as the lifecycle module
            await _stop_container_for_suspension(instance)
            logger.info("Container stopped for suspension", instance_id=str(instance_id))
        
        # Update status to suspended
        await db.update_instance_status(instance_id, InstanceStatus.PAUSED, "Instance suspended due to billing issues")
        
        logger.info("Instance suspended successfully with container stopped", instance_id=str(instance_id))
        return {
            "status": "success",
            "message": "Instance suspended successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to suspend instance", instance_id=str(instance_id), error=str(e))
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, f"Suspension failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to suspend instance: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


async def _terminate_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Terminate instance permanently - stops container and sets status to terminated"""
    from datetime import datetime
    import docker
    
    try:
        # Get current instance to check if it needs to be stopped first
        instance = await db.get_instance(instance_id)
        if not instance:
            raise Exception("Instance not found")
        
        # If instance has a Docker container that might exist, stop it first
        container_states = [InstanceStatus.RUNNING, InstanceStatus.STOPPED, InstanceStatus.STARTING, 
                          InstanceStatus.STOPPING, InstanceStatus.PAUSED, InstanceStatus.RESTARTING]
        
        if instance.status in container_states:
            logger.info("Stopping instance container before termination", 
                       instance_id=str(instance_id), current_status=instance.status)
            
            # Use the same Docker stopping logic as the lifecycle module
            await _stop_container_for_suspension(instance)
            logger.info("Container stopped for termination", instance_id=str(instance_id))
        
        # Update status to terminated (permanent)
        await db.update_instance_status(instance_id, InstanceStatus.TERMINATED, "Instance terminated due to subscription cancellation")
        
        logger.info("Instance terminated successfully with container stopped", instance_id=str(instance_id))
        return {
            "status": "success",
            "message": "Instance terminated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to terminate instance", instance_id=str(instance_id), error=str(e))
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, f"Termination failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to terminate instance: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/{instance_id}/provision")
async def provision_instance_from_webhook(
    instance_id: UUID,
    provision_data: dict,
    db: InstanceDatabase = Depends(get_database)
):
    """Provision instance triggered by billing webhook"""
    try:
        logger.info("Webhook provisioning triggered", 
                   instance_id=str(instance_id),
                   trigger=provision_data.get("provisioning_trigger"))
        
        # Get instance from database
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Validate that instance is in pending state
        if instance.provisioning_status != ProvisioningStatus.PENDING:
            logger.warning("Instance not in pending state", 
                         instance_id=str(instance_id),
                         current_status=instance.provisioning_status)
            return {
                "status": "skipped",
                "message": f"Instance not in pending state (current: {instance.provisioning_status})",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        # Update billing and provisioning status
        billing_status = provision_data.get("billing_status", "paid")
        subscription_id = provision_data.get("subscription_id")
        
        # Update instance status to provisioning
        await db.update_instance_billing_status(
            str(instance_id), 
            BillingStatus(billing_status),
            ProvisioningStatus.PROVISIONING
        )
        
        # Update subscription ID if provided
        if subscription_id:
            await db.update_instance_subscription(str(instance_id), subscription_id)
        
        # Queue actual provisioning job (the real Docker/Odoo provisioning)
        job = provision_instance_task.delay(str(instance_id))
        logger.info("Provisioning job queued from webhook", 
                   instance_id=str(instance_id), 
                   job_id=job.id,
                   billing_status=billing_status)
        
        return {
            "status": "success",
            "message": "Instance provisioning started",
            "job_id": job.id,
            "billing_status": billing_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to trigger instance provisioning", 
                   instance_id=str(instance_id), 
                   error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to trigger provisioning: {str(e)}")


async def _stop_container_for_suspension(instance):
    """Stop Docker container for suspension - copied from lifecycle.py logic"""
    import docker
    import asyncio
    
    client = docker.from_env()
    container_name = f"odoo_{instance.database_name}_{str(instance.id).replace('-', '')[:8]}"
    
    try:
        container = client.containers.get(container_name)
        
        if container.status not in ['running']:
            logger.info("Container already stopped", container_name=container_name, status=container.status)
            return
        
        logger.info("Stopping container for suspension", container_name=container_name)
        container.stop(timeout=30)  # 30 second graceful shutdown
        
        # Wait for container to stop
        for _ in range(35):  # 35 second timeout (30 + 5 buffer)
            container.reload()
            if container.status in ['exited', 'stopped']:
                break
            await asyncio.sleep(1)
        else:
            logger.warning("Container did not stop gracefully, forcing stop", container_name=container_name)
            container.kill()
        
        logger.info("Container stopped for suspension", container_name=container_name)
        
    except docker.errors.NotFound:
        logger.warning("Container not found during suspension stop", container_name=container_name)
    except Exception as e:
        logger.error("Failed to stop container for suspension", container_name=container_name, error=str(e))
        raise


async def _unsuspend_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Unsuspend instance after billing issues resolved"""
    from datetime import datetime
    
    try:
        # Update status to stopped (ready to be started again)
        await db.update_instance_status(instance_id, InstanceStatus.STOPPED, "Instance unsuspended - ready to start")
        
        logger.info("Instance unsuspended successfully", instance_id=str(instance_id))
        return {
            "status": "success",
            "message": "Instance unsuspended successfully - you can now start it",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error("Failed to unsuspend instance", instance_id=str(instance_id), error=str(e))
        return {
            "status": "error",
            "message": f"Failed to unsuspend instance: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/{instance_id}/restart-with-subscription")
async def restart_instance_with_new_subscription(
    instance_id: UUID,
    restart_data: dict,
    db: InstanceDatabase = Depends(get_database)
):
    """Restart a terminated instance with a new subscription ID - for per-instance billing recovery"""
    try:
        logger.info("Restarting terminated instance with new subscription", 
                   instance_id=str(instance_id),
                   new_subscription_id=restart_data.get("subscription_id"))
        
        # Get instance from database
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        
        # Validate that instance is terminated (can be restarted)
        if instance.status != InstanceStatus.TERMINATED:
            logger.warning("Instance not in terminated state", 
                         instance_id=str(instance_id),
                         current_status=instance.status)
            raise HTTPException(
                status_code=400, 
                detail=f"Instance must be terminated to restart with new subscription (current: {instance.status})"
            )
        
        # Get new subscription details
        new_subscription_id = restart_data.get("subscription_id")
        billing_status = restart_data.get("billing_status", "paid")
        reason = restart_data.get("reason", "Instance reactivated with new subscription")
        
        if not new_subscription_id:
            raise HTTPException(status_code=400, detail="subscription_id is required")
        
        # Update instance with new subscription and billing status
        await db.update_instance_subscription(str(instance_id), new_subscription_id)
        await db.update_instance_billing_status(
            str(instance_id), 
            BillingStatus(billing_status),
            ProvisioningStatus.PENDING
        )
        
        # Change status from TERMINATED to STOPPED (ready to be started)
        await db.update_instance_status(instance_id, InstanceStatus.STOPPED, reason)
        
        logger.info("Instance restarted with new subscription successfully", 
                   instance_id=str(instance_id),
                   new_subscription_id=new_subscription_id,
                   billing_status=billing_status)
        
        return {
            "status": "success",
            "message": f"Instance reactivated with new subscription {new_subscription_id}",
            "instance_id": str(instance_id),
            "subscription_id": new_subscription_id,
            "billing_status": billing_status,
            "instance_status": "stopped",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to restart instance with new subscription", 
                   instance_id=str(instance_id), 
                   error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to restart instance: {str(e)}")