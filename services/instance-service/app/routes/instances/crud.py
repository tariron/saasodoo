"""
Instance CRUD (Create, Read, Update, Delete) routes
"""

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query, Depends
import structlog

from app.models.instance import (
    InstanceCreate, InstanceUpdate, InstanceResponse, InstanceListResponse,
    InstanceStatus
)
from app.utils.validators import validate_instance_resources, validate_database_name, validate_addon_names
from app.utils.database import InstanceDatabase
from app.routes.instances.helpers import (
    get_database,
    instance_to_response_dict,
    instance_dict_to_response_dict
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/", response_model=InstanceResponse, status_code=201)
async def create_instance(
    instance_data: InstanceCreate,
    db: InstanceDatabase = Depends(get_database)
):
    """Create a new Odoo instance record (database allocation handled by provisioning task)"""

    try:
        logger.info("Creating instance",
                   name=instance_data.name,
                   customer_id=str(instance_data.customer_id),
                   db_type=instance_data.db_type)

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

        # Convert to response format and return immediately
        response_data = instance_to_response_dict(instance)

        logger.info("Instance record created successfully. Awaiting provisioning trigger.", instance_id=str(instance.id))
        return InstanceResponse(**response_data)

    except ValueError as e:
        logger.warning("Instance creation validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error("Failed to create instance",
                     error=str(e),
                     error_type=type(e).__name__,
                     traceback=error_details)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


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

        response_data = instance_to_response_dict(instance)
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
            response_data = instance_dict_to_response_dict(instance_data)

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

        response_data = instance_to_response_dict(instance)
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

        response_data = instance_to_response_dict(updated_instance)
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


@router.get("/check-subdomain/{subdomain}")
async def check_subdomain_availability(
    subdomain: str,
    db: InstanceDatabase = Depends(get_database)
):
    """Check if subdomain is available for use"""
    try:
        # Use the same validation as instance creation to ensure consistency
        validation_errors = validate_database_name(subdomain)

        if validation_errors:
            return {
                "subdomain": subdomain,
                "available": False,
                "message": validation_errors[0]  # Return the first validation error
            }

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
