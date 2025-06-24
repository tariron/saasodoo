"""
Tenant management routes
"""

from typing import Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Request, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
import structlog

from app.models.tenant import (
    TenantCreate, TenantUpdate, TenantResponse, TenantListResponse,
    TenantStatus, TenantPlan
)
from app.utils.validators import validate_tenant_limits, validate_subdomain
from app.utils.database import TenantDatabase

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_database(request: Request) -> TenantDatabase:
    """Dependency to get database instance"""
    return request.app.state.db


@router.post("/", response_model=TenantResponse, status_code=201)
async def create_tenant(
    tenant_data: TenantCreate,
    db: TenantDatabase = Depends(get_database)
):
    """Create a new tenant"""
    try:
        logger.info("Creating tenant", name=tenant_data.name, customer_id=str(tenant_data.customer_id))
        
        # Validate tenant limits based on plan
        limit_errors = validate_tenant_limits(tenant_data.plan, tenant_data.max_instances, tenant_data.max_users)
        if limit_errors:
            raise HTTPException(status_code=400, detail={"errors": limit_errors})
        
        # Create tenant
        tenant = await db.create_tenant(tenant_data)
        
        # Convert to response format
        response_data = {
            "id": str(tenant.id),
            "customer_id": str(tenant.customer_id),
            "name": tenant.name,
            "plan": tenant.plan,
            "status": tenant.status,
            "max_instances": tenant.max_instances,
            "max_users": tenant.max_users,
            "custom_domain": tenant.custom_domain,
            "instance_count": 0,  # New tenant has no instances
            "created_at": tenant.created_at.isoformat(),
            "updated_at": tenant.updated_at.isoformat(),
            "metadata": tenant.metadata or {}
        }
        
        logger.info("Tenant created successfully", tenant_id=str(tenant.id))
        return TenantResponse(**response_data)
        
    except ValueError as e:
        logger.warning("Tenant creation validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to create tenant", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{tenant_id}", response_model=Dict[str, Any])
async def get_tenant(
    tenant_id: UUID,
    db: TenantDatabase = Depends(get_database)
):
    """Get tenant details"""
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Note: Instance count is now provided by instance-service
    # Return basic tenant information
    return {
        "id": str(tenant.id),
        "customer_id": str(tenant.customer_id),
        "name": tenant.name,
        "plan": tenant.plan.value,
        "status": tenant.status.value,
        "max_instances": tenant.max_instances,
        "max_users": tenant.max_users,
        "custom_domain": tenant.custom_domain,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at,
        "metadata": tenant.metadata
    }


@router.get("/", response_model=TenantListResponse)
async def list_tenants(
    customer_id: UUID = Query(..., description="Customer ID to filter tenants"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    db: TenantDatabase = Depends(get_database)
):
    """List tenants for a customer"""
    try:
        result = await db.get_tenants_by_customer(customer_id, page, page_size)
        
        # Convert tenants to response format
        tenant_responses = []
        for tenant_data in result['tenants']:
            response_data = {
                "id": str(tenant_data['id']),
                "customer_id": str(tenant_data['customer_id']),
                "name": tenant_data['name'],
                "plan": tenant_data['plan'],
                "status": tenant_data['status'],
                "max_instances": tenant_data['max_instances'],
                "max_users": tenant_data['max_users'],
                "custom_domain": tenant_data['custom_domain'],
                "instance_count": tenant_data.get('instance_count', 0),
                "created_at": tenant_data['created_at'].isoformat(),
                "updated_at": tenant_data['updated_at'].isoformat(),
                "metadata": tenant_data['metadata'] or {}
            }
            tenant_responses.append(TenantResponse(**response_data))
        
        return TenantListResponse(
            tenants=tenant_responses,
            total=result['total'],
            page=result['page'],
            page_size=result['page_size']
        )
        
    except Exception as e:
        logger.error("Failed to list tenants", customer_id=str(customer_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: UUID,
    update_data: TenantUpdate,
    db: TenantDatabase = Depends(get_database)
):
    """Update tenant information"""
    try:
        # Validate if tenant exists
        existing_tenant = await db.get_tenant(tenant_id)
        if not existing_tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Validate plan limits if being updated
        if update_data.plan is not None or update_data.max_instances is not None or update_data.max_users is not None:
            plan = update_data.plan or existing_tenant.plan
            max_instances = update_data.max_instances or existing_tenant.max_instances
            max_users = update_data.max_users or existing_tenant.max_users
            
            limit_errors = validate_tenant_limits(plan, max_instances, max_users)
            if limit_errors:
                raise HTTPException(status_code=400, detail={"errors": limit_errors})
        
        # Validate custom domain if being updated
        if update_data.custom_domain is not None:
            from app.utils.validators import validate_custom_domain
            domain_errors = validate_custom_domain(update_data.custom_domain)
            if domain_errors:
                raise HTTPException(status_code=400, detail={"errors": domain_errors})
        
        # Update tenant
        updated_tenant = await db.update_tenant(tenant_id, update_data)
        if not updated_tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Instance count is now managed by instance-service
        response_data = {
            "id": str(updated_tenant.id),
            "customer_id": str(updated_tenant.customer_id),
            "name": updated_tenant.name,
            "plan": updated_tenant.plan,
            "status": updated_tenant.status,
            "max_instances": updated_tenant.max_instances,
            "max_users": updated_tenant.max_users,
            "custom_domain": updated_tenant.custom_domain,
            "instance_count": 0,  # Instance count handled by instance-service
            "created_at": updated_tenant.created_at.isoformat(),
            "updated_at": updated_tenant.updated_at.isoformat(),
            "metadata": updated_tenant.metadata or {}
        }
        
        logger.info("Tenant updated successfully", tenant_id=str(tenant_id))
        return TenantResponse(**response_data)
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Tenant update validation failed", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to update tenant", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{tenant_id}")
async def delete_tenant(
    tenant_id: UUID,
    db: TenantDatabase = Depends(get_database)
):
    """Delete tenant (soft delete)"""
    try:
        success = await db.delete_tenant(tenant_id)
        if not success:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        logger.info("Tenant deleted successfully", tenant_id=str(tenant_id))
        return {"message": "Tenant deleted successfully"}
        
    except ValueError as e:
        logger.warning("Tenant deletion failed", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete tenant", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")




@router.post("/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: UUID,
    db: TenantDatabase = Depends(get_database)
):
    """Activate a tenant"""
    try:
        tenant = await db.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        if tenant.status == TenantStatus.ACTIVE:
            return {"message": "Tenant is already active"}
        
        update_data = TenantUpdate(status=TenantStatus.ACTIVE)
        await db.update_tenant(tenant_id, update_data)
        
        logger.info("Tenant activated", tenant_id=str(tenant_id))
        return {"message": "Tenant activated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to activate tenant", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: UUID,
    db: TenantDatabase = Depends(get_database)
):
    """Suspend a tenant"""
    try:
        tenant = await db.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        if tenant.status == TenantStatus.SUSPENDED:
            return {"message": "Tenant is already suspended"}
        
        update_data = TenantUpdate(status=TenantStatus.SUSPENDED)
        await db.update_tenant(tenant_id, update_data)
        
        logger.info("Tenant suspended", tenant_id=str(tenant_id))
        return {"message": "Tenant suspended successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to suspend tenant", tenant_id=str(tenant_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error") 