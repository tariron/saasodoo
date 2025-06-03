"""
Tenant service business logic
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog

from app.utils.database import TenantDatabase
from app.models.tenant import Tenant, TenantCreate, TenantUpdate, TenantStatus


logger = structlog.get_logger(__name__)


class TenantService:
    """High-level tenant business logic service"""
    
    def __init__(self, db: TenantDatabase):
        self.db = db
    
    async def create_tenant_for_customer(self, customer_id: UUID, tenant_data: TenantCreate) -> Tenant:
        """
        Create a new tenant for a customer with business logic validation
        This method can be called by the user-service when customers upgrade plans
        """
        try:
            # TODO: Validate customer exists and is active via user-service API
            # customer = await user_service_client.get_customer(customer_id)
            # if not customer or customer.status != 'active':
            #     raise ValueError("Customer not found or inactive")
            
            # TODO: Check customer's subscription plan allows tenant creation
            # subscription = await billing_service_client.get_subscription(customer_id)
            # if not subscription.allows_tenants:
            #     raise ValueError("Customer subscription does not allow tenant creation")
            
            # Create tenant
            tenant = await self.db.create_tenant(tenant_data)
            
            # Set tenant to active status after creation
            update_data = TenantUpdate(status=TenantStatus.ACTIVE)
            tenant = await self.db.update_tenant(tenant.id, update_data)
            
            logger.info("Tenant created and activated", tenant_id=str(tenant.id), customer_id=str(customer_id))
            return tenant
            
        except Exception as e:
            logger.error("Failed to create tenant for customer", customer_id=str(customer_id), error=str(e))
            raise
    
    async def get_customer_tenants(self, customer_id: UUID) -> List[Dict[str, Any]]:
        """Get all tenants for a customer with instance counts"""
        try:
            result = await self.db.get_tenants_by_customer(customer_id, page=1, page_size=100)
            return result['tenants']
            
        except Exception as e:
            logger.error("Failed to get customer tenants", customer_id=str(customer_id), error=str(e))
            raise
    
    async def get_customer_total_instances(self, customer_id: UUID) -> int:
        """
        Get total instance count for a customer across all tenants
        NOTE: This method now returns 0 since instances are managed by instance-service
        The caller should query the instance-service directly for accurate counts
        """
        try:
            # Instance counts are now managed by instance-service
            # Return 0 for backward compatibility
            logger.warning("Instance counting moved to instance-service", customer_id=str(customer_id))
            return 0
            
        except Exception as e:
            logger.error("Failed to get customer instance count", customer_id=str(customer_id), error=str(e))
            return 0  # Return 0 on error to avoid breaking user profile
    
    async def suspend_customer_tenants(self, customer_id: UUID, reason: str = "Customer suspended") -> int:
        """
        Suspend all tenants for a customer (called when customer is suspended)
        Returns number of tenants suspended
        """
        try:
            tenants_data = await self.get_customer_tenants(customer_id)
            suspended_count = 0
            
            for tenant_data in tenants_data:
                if tenant_data['status'] == TenantStatus.ACTIVE.value:
                    tenant_id = UUID(tenant_data['id'])
                    update_data = TenantUpdate(
                        status=TenantStatus.SUSPENDED,
                        metadata={"suspension_reason": reason}
                    )
                    await self.db.update_tenant(tenant_id, update_data)
                    suspended_count += 1
            
            logger.info("Customer tenants suspended", customer_id=str(customer_id), count=suspended_count)
            return suspended_count
            
        except Exception as e:
            logger.error("Failed to suspend customer tenants", customer_id=str(customer_id), error=str(e))
            raise
    
    async def reactivate_customer_tenants(self, customer_id: UUID) -> int:
        """
        Reactivate all suspended tenants for a customer
        Returns number of tenants reactivated
        """
        try:
            tenants_data = await self.get_customer_tenants(customer_id)
            reactivated_count = 0
            
            for tenant_data in tenants_data:
                if tenant_data['status'] == TenantStatus.SUSPENDED.value:
                    tenant_id = UUID(tenant_data['id'])
                    update_data = TenantUpdate(
                        status=TenantStatus.ACTIVE,
                        metadata=tenant_data.get('metadata', {})
                    )
                    # Remove suspension reason from metadata
                    if 'suspension_reason' in update_data.metadata:
                        del update_data.metadata['suspension_reason']
                    
                    await self.db.update_tenant(tenant_id, update_data)
                    reactivated_count += 1
            
            logger.info("Customer tenants reactivated", customer_id=str(customer_id), count=reactivated_count)
            return reactivated_count
            
        except Exception as e:
            logger.error("Failed to reactivate customer tenants", customer_id=str(customer_id), error=str(e))
            raise
    
    async def delete_customer_tenants(self, customer_id: UUID) -> int:
        """
        Delete all tenants for a customer (called when customer is deleted)
        NOTE: Caller should ensure instances are deleted via instance-service first
        Returns number of tenants deleted
        """
        try:
            tenants_data = await self.get_customer_tenants(customer_id)
            deleted_count = 0
            
            for tenant_data in tenants_data:
                if tenant_data['status'] != TenantStatus.TERMINATED.value:
                    tenant_id = UUID(tenant_data['id'])
                    
                    # Note: Instance validation is now handled by instance-service
                    # The caller should check with instance-service before deleting tenant
                    logger.info("Deleting tenant", tenant_id=str(tenant_id))
                    
                    success = await self.db.delete_tenant(tenant_id)
                    if success:
                        deleted_count += 1
            
            logger.info("Customer tenants deleted", customer_id=str(customer_id), count=deleted_count)
            return deleted_count
            
        except Exception as e:
            logger.error("Failed to delete customer tenants", customer_id=str(customer_id), error=str(e))
            raise
    
    async def validate_tenant_subdomain_available(self, subdomain: str) -> bool:
        """Check if a subdomain is available for tenant creation"""
        try:
            existing_tenant = await self.db.get_tenant_by_subdomain(subdomain)
            return existing_tenant is None
            
        except Exception as e:
            logger.error("Failed to validate subdomain availability", subdomain=subdomain, error=str(e))
            return False
    
    async def get_tenant_statistics(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get comprehensive statistics for a tenant"""
        try:
            tenant = await self.db.get_tenant(tenant_id)
            if not tenant:
                raise ValueError("Tenant not found")
            
            # Instance statistics are now provided by instance-service
            # This method now returns basic tenant information only
            statistics = {
                'tenant_id': str(tenant_id),
                'tenant_name': tenant.name,
                'tenant_status': tenant.status,
                'subdomain': tenant.subdomain,
                'plan': tenant.plan,
                'limits': {
                    'max_instances': tenant.max_instances,
                    'max_users': tenant.max_users
                },
                'created_at': tenant.created_at.isoformat() if tenant.created_at else None,
                'updated_at': tenant.updated_at.isoformat() if tenant.updated_at else None,
                'custom_domain': tenant.custom_domain,
                'metadata': tenant.metadata or {}
            }
            
            logger.info("Retrieved tenant statistics", tenant_id=str(tenant_id))
            return statistics
            
        except Exception as e:
            logger.error("Failed to get tenant statistics", tenant_id=str(tenant_id), error=str(e))
            raise 