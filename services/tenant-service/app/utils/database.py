"""
Database utilities for tenant service
"""

import os
import asyncio
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

import asyncpg
import structlog
from asyncpg import Pool, Connection

from app.models.tenant import Tenant, TenantCreate, TenantUpdate, TenantStatus
from app.models.instance import Instance, InstanceCreate, InstanceUpdate, InstanceStatus


logger = structlog.get_logger(__name__)


class TenantDatabase:
    """Database connection and operations for tenant service"""
    
    def __init__(self):
        self.pool: Optional[Pool] = None
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'tenant'),
            'user': os.getenv('DB_SERVICE_USER', 'tenant_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'tenant_service_secure_pass_change_me'),
            'min_size': 5,
            'max_size': 20,
            'command_timeout': 30
        }
    
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(**self.db_config)
            logger.info("Database pool created", database=self.db_config['database'])
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute('SELECT 1')
                logger.info("Database connection test successful")
                
        except Exception as e:
            logger.error("Failed to initialize database", error=str(e))
            raise
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database pool closed")
    
    async def get_connection(self) -> Connection:
        """Get database connection from pool"""
        if not self.pool:
            raise RuntimeError("Database pool not initialized")
        return await self.pool.acquire()
    
    # ===== TENANT OPERATIONS =====
    
    async def create_tenant(self, tenant_data: TenantCreate) -> Tenant:
        """Create a new tenant"""
        async with self.pool.acquire() as conn:
            try:
                # Check if subdomain already exists
                existing = await conn.fetchrow(
                    "SELECT id FROM tenants WHERE subdomain = $1",
                    tenant_data.subdomain
                )
                if existing:
                    raise ValueError(f"Subdomain '{tenant_data.subdomain}' already exists")
                
                # Insert new tenant
                tenant_id = await conn.fetchval("""
                    INSERT INTO tenants (
                        customer_id, name, subdomain, plan, max_instances, max_users,
                        custom_domain, metadata, status, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                """, 
                    tenant_data.customer_id,
                    tenant_data.name,
                    tenant_data.subdomain,
                    tenant_data.plan.value,
                    tenant_data.max_instances,
                    tenant_data.max_users,
                    tenant_data.custom_domain,
                    tenant_data.metadata,
                    TenantStatus.PROVISIONING.value,
                    datetime.utcnow(),
                    datetime.utcnow()
                )
                
                logger.info("Tenant created", tenant_id=str(tenant_id), subdomain=tenant_data.subdomain)
                
                # Return the created tenant
                return await self.get_tenant(tenant_id)
                
            except Exception as e:
                logger.error("Failed to create tenant", error=str(e))
                raise
    
    async def get_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Get tenant by ID"""
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM tenants WHERE id = $1",
                    tenant_id
                )
                if row:
                    return Tenant(**dict(row))
                return None
                
            except Exception as e:
                logger.error("Failed to get tenant", tenant_id=str(tenant_id), error=str(e))
                raise
    
    async def get_tenant_by_subdomain(self, subdomain: str) -> Optional[Tenant]:
        """Get tenant by subdomain"""
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM tenants WHERE subdomain = $1",
                    subdomain
                )
                if row:
                    return Tenant(**dict(row))
                return None
                
            except Exception as e:
                logger.error("Failed to get tenant by subdomain", subdomain=subdomain, error=str(e))
                raise
    
    async def get_tenants_by_customer(self, customer_id: UUID, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """Get tenants for a customer with pagination"""
        async with self.pool.acquire() as conn:
            try:
                offset = (page - 1) * page_size
                
                # Get total count
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM tenants WHERE customer_id = $1",
                    customer_id
                )
                
                # Get tenants
                rows = await conn.fetch("""
                    SELECT t.*, 
                           COALESCE(i.instance_count, 0) as instance_count
                    FROM tenants t
                    LEFT JOIN (
                        SELECT tenant_id, COUNT(*) as instance_count 
                        FROM instances 
                        WHERE status != 'terminated'
                        GROUP BY tenant_id
                    ) i ON t.id = i.tenant_id
                    WHERE t.customer_id = $1
                    ORDER BY t.created_at DESC
                    LIMIT $2 OFFSET $3
                """, customer_id, page_size, offset)
                
                tenants = [dict(row) for row in rows]
                
                return {
                    'tenants': tenants,
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
                
            except Exception as e:
                logger.error("Failed to get tenants by customer", customer_id=str(customer_id), error=str(e))
                raise
    
    async def update_tenant(self, tenant_id: UUID, update_data: TenantUpdate) -> Optional[Tenant]:
        """Update tenant information"""
        async with self.pool.acquire() as conn:
            try:
                # Build update query dynamically
                update_fields = []
                update_values = []
                param_index = 1
                
                for field, value in update_data.dict(exclude_unset=True).items():
                    if value is not None:
                        update_fields.append(f"{field} = ${param_index}")
                        if hasattr(value, 'value'):  # Handle enum values
                            update_values.append(value.value)
                        else:
                            update_values.append(value)
                        param_index += 1
                
                if not update_fields:
                    # No fields to update
                    return await self.get_tenant(tenant_id)
                
                # Add updated_at
                update_fields.append(f"updated_at = ${param_index}")
                update_values.append(datetime.utcnow())
                
                query = f"""
                    UPDATE tenants 
                    SET {', '.join(update_fields)}
                    WHERE id = ${param_index + 1}
                    RETURNING id
                """
                update_values.append(tenant_id)
                
                result = await conn.fetchval(query, *update_values)
                if result:
                    logger.info("Tenant updated", tenant_id=str(tenant_id))
                    return await self.get_tenant(tenant_id)
                return None
                
            except Exception as e:
                logger.error("Failed to update tenant", tenant_id=str(tenant_id), error=str(e))
                raise
    
    async def delete_tenant(self, tenant_id: UUID) -> bool:
        """Delete tenant (soft delete by setting status to terminated)"""
        async with self.pool.acquire() as conn:
            try:
                # Check if tenant has active instances
                instance_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM instances WHERE tenant_id = $1 AND status != 'terminated'",
                    tenant_id
                )
                
                if instance_count > 0:
                    raise ValueError(f"Cannot delete tenant with {instance_count} active instances")
                
                # Soft delete by updating status
                result = await conn.fetchval("""
                    UPDATE tenants 
                    SET status = $1, updated_at = $2
                    WHERE id = $3
                    RETURNING id
                """, TenantStatus.TERMINATED.value, datetime.utcnow(), tenant_id)
                
                if result:
                    logger.info("Tenant deleted", tenant_id=str(tenant_id))
                    return True
                return False
                
            except Exception as e:
                logger.error("Failed to delete tenant", tenant_id=str(tenant_id), error=str(e))
                raise
    
    # ===== INSTANCE OPERATIONS =====
    
    async def create_instance(self, instance_data: InstanceCreate) -> Instance:
        """Create a new instance"""
        async with self.pool.acquire() as conn:
            try:
                # Check tenant exists and has capacity
                tenant = await self.get_tenant(instance_data.tenant_id)
                if not tenant:
                    raise ValueError("Tenant not found")
                
                if tenant.status != TenantStatus.ACTIVE:
                    raise ValueError(f"Cannot create instance for tenant with status: {tenant.status}")
                
                # Check instance limit
                current_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM instances WHERE tenant_id = $1 AND status != 'terminated'",
                    instance_data.tenant_id
                )
                
                if current_count >= tenant.max_instances:
                    raise ValueError(f"Tenant has reached maximum instance limit: {tenant.max_instances}")
                
                # Check if database name is unique for this tenant
                existing = await conn.fetchrow(
                    "SELECT id FROM instances WHERE tenant_id = $1 AND database_name = $2",
                    instance_data.tenant_id, instance_data.database_name
                )
                if existing:
                    raise ValueError(f"Database name '{instance_data.database_name}' already exists for this tenant")
                
                # Insert new instance
                instance_id = await conn.fetchval("""
                    INSERT INTO instances (
                        tenant_id, name, odoo_version, instance_type, description,
                        cpu_limit, memory_limit, storage_limit, admin_email, database_name,
                        demo_data, custom_addons, disabled_modules, environment_vars,
                        metadata, status, created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                    RETURNING id
                """,
                    instance_data.tenant_id,
                    instance_data.name,
                    instance_data.odoo_version.value,
                    instance_data.instance_type.value,
                    instance_data.description,
                    instance_data.cpu_limit,
                    instance_data.memory_limit,
                    instance_data.storage_limit,
                    instance_data.admin_email,
                    instance_data.database_name,
                    instance_data.demo_data,
                    instance_data.custom_addons,
                    instance_data.disabled_modules,
                    instance_data.environment_vars,
                    instance_data.metadata,
                    InstanceStatus.CREATING.value,
                    datetime.utcnow(),
                    datetime.utcnow()
                )
                
                logger.info("Instance created", instance_id=str(instance_id), tenant_id=str(instance_data.tenant_id))
                
                return await self.get_instance(instance_id)
                
            except Exception as e:
                logger.error("Failed to create instance", error=str(e))
                raise
    
    async def get_instance(self, instance_id: UUID) -> Optional[Instance]:
        """Get instance by ID"""
        async with self.pool.acquire() as conn:
            try:
                row = await conn.fetchrow(
                    "SELECT * FROM instances WHERE id = $1",
                    instance_id
                )
                if row:
                    return Instance(**dict(row))
                return None
                
            except Exception as e:
                logger.error("Failed to get instance", instance_id=str(instance_id), error=str(e))
                raise
    
    async def get_instances_by_tenant(self, tenant_id: UUID, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """Get instances for a tenant with pagination"""
        async with self.pool.acquire() as conn:
            try:
                offset = (page - 1) * page_size
                
                # Get total count
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM instances WHERE tenant_id = $1",
                    tenant_id
                )
                
                # Get instances
                rows = await conn.fetch("""
                    SELECT * FROM instances 
                    WHERE tenant_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                """, tenant_id, page_size, offset)
                
                instances = [dict(row) for row in rows]
                
                return {
                    'instances': instances,
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
                
            except Exception as e:
                logger.error("Failed to get instances by tenant", tenant_id=str(tenant_id), error=str(e))
                raise
    
    async def get_instances_by_customer(self, customer_id: UUID) -> int:
        """Get total instance count for a customer across all tenants"""
        async with self.pool.acquire() as conn:
            try:
                count = await conn.fetchval("""
                    SELECT COUNT(i.id)
                    FROM instances i
                    JOIN tenants t ON i.tenant_id = t.id
                    WHERE t.customer_id = $1 AND i.status != 'terminated'
                """, customer_id)
                
                return count or 0
                
            except Exception as e:
                logger.error("Failed to get instances by customer", customer_id=str(customer_id), error=str(e))
                raise
    
    async def update_instance(self, instance_id: UUID, update_data: InstanceUpdate) -> Optional[Instance]:
        """Update instance information"""
        async with self.pool.acquire() as conn:
            try:
                # Build update query dynamically
                update_fields = []
                update_values = []
                param_index = 1
                
                for field, value in update_data.dict(exclude_unset=True).items():
                    if value is not None:
                        update_fields.append(f"{field} = ${param_index}")
                        if hasattr(value, 'value'):  # Handle enum values
                            update_values.append(value.value)
                        else:
                            update_values.append(value)
                        param_index += 1
                
                if not update_fields:
                    return await self.get_instance(instance_id)
                
                # Add updated_at
                update_fields.append(f"updated_at = ${param_index}")
                update_values.append(datetime.utcnow())
                
                query = f"""
                    UPDATE instances 
                    SET {', '.join(update_fields)}
                    WHERE id = ${param_index + 1}
                    RETURNING id
                """
                update_values.append(instance_id)
                
                result = await conn.fetchval(query, *update_values)
                if result:
                    logger.info("Instance updated", instance_id=str(instance_id))
                    return await self.get_instance(instance_id)
                return None
                
            except Exception as e:
                logger.error("Failed to update instance", instance_id=str(instance_id), error=str(e))
                raise
    
    async def update_instance_status(self, instance_id: UUID, status: InstanceStatus, 
                                   error_message: Optional[str] = None) -> bool:
        """Update instance status"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    UPDATE instances 
                    SET status = $1, error_message = $2, updated_at = $3,
                        last_health_check = CASE WHEN $1 = 'running' THEN $3 ELSE last_health_check END
                    WHERE id = $4
                """, status.value, error_message, datetime.utcnow(), instance_id)
                
                logger.info("Instance status updated", instance_id=str(instance_id), status=status.value)
                return True
                
            except Exception as e:
                logger.error("Failed to update instance status", instance_id=str(instance_id), error=str(e))
                raise
    
    async def delete_instance(self, instance_id: UUID) -> bool:
        """Delete instance (soft delete by setting status to terminated)"""
        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchval("""
                    UPDATE instances 
                    SET status = $1, updated_at = $2
                    WHERE id = $3
                    RETURNING id
                """, InstanceStatus.TERMINATED.value, datetime.utcnow(), instance_id)
                
                if result:
                    logger.info("Instance deleted", instance_id=str(instance_id))
                    return True
                return False
                
            except Exception as e:
                logger.error("Failed to delete instance", instance_id=str(instance_id), error=str(e))
                raise 