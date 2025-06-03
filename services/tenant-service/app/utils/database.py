"""
Database utilities for tenant service
"""

import os
import asyncio
import json
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime

import asyncpg
import structlog
from asyncpg import Pool, Connection

from app.models.tenant import Tenant, TenantCreate, TenantUpdate, TenantStatus


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
                    json.dumps(tenant_data.metadata or {}),  # PostgreSQL handles dict to JSONB conversion
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
                    row_dict = dict(row)
                    # Parse JSON metadata back to dict
                    if row_dict.get('metadata'):
                        row_dict['metadata'] = json.loads(row_dict['metadata'])
                    return Tenant(**row_dict)
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
                    row_dict = dict(row)
                    # Parse JSON metadata back to dict
                    if row_dict.get('metadata'):
                        row_dict['metadata'] = json.loads(row_dict['metadata'])
                    return Tenant(**row_dict)
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
                
                # Get tenants (instance count removed - now handled by instance service)
                rows = await conn.fetch("""
                    SELECT * FROM tenants
                    WHERE customer_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                """, customer_id, page_size, offset)
                
                # Parse metadata for each tenant
                tenants = []
                for row in rows:
                    tenant_dict = dict(row)
                    # Parse JSON metadata back to dict
                    if tenant_dict.get('metadata'):
                        tenant_dict['metadata'] = json.loads(tenant_dict['metadata'])
                    tenants.append(tenant_dict)
                
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
                        elif field == 'metadata':
                            update_values.append(json.dumps(value))
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
                # Note: Instance validation is now handled by instance service
                # The caller should check with instance service before deleting tenant
                
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