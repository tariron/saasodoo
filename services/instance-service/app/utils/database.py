"""
Instance database operations and connection management
"""

import os
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
import asyncpg
from asyncpg import Connection
import structlog

from app.models.instance import Instance, InstanceCreate, InstanceUpdate, InstanceStatus, BillingStatus, ProvisioningStatus

logger = structlog.get_logger(__name__)


class InstanceDatabase:
    """Database operations for instance service"""
    
    def __init__(self):
        self.pool = None
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
            'min_size': 1,
            'max_size': 10,
            'command_timeout': 30
        }
    
    async def initialize(self):
        """Initialize database connection pool"""
        try:
            self.pool = await asyncpg.create_pool(**self.db_config)
            logger.info("Instance database pool initialized", database=self.db_config['database'])
            
            # Test connection
            async with self.pool.acquire() as conn:
                await conn.execute('SELECT 1')
                logger.info("Instance database connection test successful")
                
        except Exception as e:
            logger.error("Failed to initialize instance database pool", error=str(e))
            raise
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Instance database pool closed")
    
    async def get_connection(self) -> Connection:
        """Get database connection from pool"""
        return await self.pool.acquire()
    
    # ===== INSTANCE OPERATIONS =====
    
    async def create_instance(
        self, 
        instance_data: InstanceCreate, 
        billing_status: BillingStatus = BillingStatus.PENDING_PAYMENT,
        provisioning_status: ProvisioningStatus = ProvisioningStatus.PENDING
    ) -> Instance:
        """Create a new instance"""
        async with self.pool.acquire() as conn:
            try:
                # Check if database name is unique for this customer
                existing = await conn.fetchrow(
                    "SELECT id FROM instances WHERE customer_id = $1 AND database_name = $2",
                    instance_data.customer_id, instance_data.database_name
                )
                if existing:
                    raise ValueError(f"Database name '{instance_data.database_name}' already exists for this customer")
                
                # Insert new instance
                instance_id = await conn.fetchval("""
                    INSERT INTO instances (
                        customer_id, name, odoo_version, instance_type, description,
                        cpu_limit, memory_limit, storage_limit, admin_email, admin_password,
                        database_name, subdomain, demo_data, custom_addons, disabled_modules, 
                        environment_vars, metadata, status, billing_status, provisioning_status,
                        created_at, updated_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
                    RETURNING id
                """,
                    instance_data.customer_id,
                    instance_data.name,
                    instance_data.odoo_version.value,
                    instance_data.instance_type.value,
                    instance_data.description,
                    instance_data.cpu_limit,
                    instance_data.memory_limit,
                    instance_data.storage_limit,
                    instance_data.admin_email,
                    instance_data.admin_password,
                    instance_data.database_name,
                    instance_data.subdomain,
                    instance_data.demo_data,
                    json.dumps(instance_data.custom_addons),
                    json.dumps(instance_data.disabled_modules),
                    json.dumps(instance_data.environment_vars),
                    json.dumps(instance_data.metadata or {}),
                    InstanceStatus.CREATING.value,
                    billing_status.value,
                    provisioning_status.value,
                    datetime.utcnow(),
                    datetime.utcnow()
                )
                
                logger.info("Instance created", instance_id=str(instance_id), customer_id=str(instance_data.customer_id))
                
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
                    # Convert row to dict and deserialize JSON fields
                    instance_data = dict(row)
                    
                    # Deserialize JSON fields
                    if instance_data.get('custom_addons'):
                        instance_data['custom_addons'] = json.loads(instance_data['custom_addons'])
                    else:
                        instance_data['custom_addons'] = []
                        
                    if instance_data.get('disabled_modules'):
                        instance_data['disabled_modules'] = json.loads(instance_data['disabled_modules'])
                    else:
                        instance_data['disabled_modules'] = []
                        
                    if instance_data.get('environment_vars'):
                        instance_data['environment_vars'] = json.loads(instance_data['environment_vars'])
                    else:
                        instance_data['environment_vars'] = {}
                        
                    if instance_data.get('metadata'):
                        instance_data['metadata'] = json.loads(instance_data['metadata'])
                    else:
                        instance_data['metadata'] = {}
                    
                    return Instance(**instance_data)
                return None
                
            except Exception as e:
                logger.error("Failed to get instance", instance_id=str(instance_id), error=str(e))
                raise
    
    async def update_instance_subscription(self, instance_id: str, subscription_id: str) -> bool:
        """Update instance with subscription ID"""
        async with self.pool.acquire() as conn:
            try:
                result = await conn.execute(
                    "UPDATE instances SET subscription_id = $1, updated_at = $2 WHERE id = $3",
                    UUID(subscription_id), datetime.utcnow(), UUID(instance_id)
                )
                
                if result == "UPDATE 1":
                    logger.info("Instance subscription updated", 
                              instance_id=instance_id, 
                              subscription_id=subscription_id)
                    return True
                return False
                
            except Exception as e:
                logger.error("Failed to update instance subscription", 
                           instance_id=instance_id, 
                           subscription_id=subscription_id, 
                           error=str(e))
                raise
    
    async def update_instance_billing_status(
        self, 
        instance_id: str, 
        billing_status: BillingStatus, 
        provisioning_status: ProvisioningStatus = None
    ) -> bool:
        """Update instance billing and provisioning status"""
        async with self.pool.acquire() as conn:
            try:
                if provisioning_status:
                    result = await conn.execute("""
                        UPDATE instances 
                        SET billing_status = $1, provisioning_status = $2, updated_at = $3 
                        WHERE id = $4
                    """, billing_status.value, provisioning_status.value, datetime.utcnow(), UUID(instance_id))
                else:
                    result = await conn.execute("""
                        UPDATE instances 
                        SET billing_status = $1, updated_at = $2 
                        WHERE id = $3
                    """, billing_status.value, datetime.utcnow(), UUID(instance_id))
                
                if result == "UPDATE 1":
                    logger.info("Instance billing status updated", 
                              instance_id=instance_id, 
                              billing_status=billing_status.value,
                              provisioning_status=provisioning_status.value if provisioning_status else None)
                    return True
                return False
                
            except Exception as e:
                logger.error("Failed to update instance billing status", 
                           instance_id=instance_id, 
                           billing_status=billing_status.value, 
                           error=str(e))
                raise
    
    async def get_instances_by_customer(self, customer_id: UUID, page: int = 1, page_size: int = 10) -> Dict[str, Any]:
        """Get instances for a customer with pagination"""
        async with self.pool.acquire() as conn:
            try:
                offset = (page - 1) * page_size
                
                # Get total count
                total = await conn.fetchval(
                    "SELECT COUNT(*) FROM instances WHERE customer_id = $1",
                    customer_id
                )
                
                # Get instances
                rows = await conn.fetch("""
                    SELECT * FROM instances 
                    WHERE customer_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2 OFFSET $3
                """, customer_id, page_size, offset)
                
                instances = []
                for row in rows:
                    instance_data = dict(row)
                    
                    # Deserialize JSON fields
                    if instance_data.get('custom_addons'):
                        instance_data['custom_addons'] = json.loads(instance_data['custom_addons'])
                    else:
                        instance_data['custom_addons'] = []
                        
                    if instance_data.get('disabled_modules'):
                        instance_data['disabled_modules'] = json.loads(instance_data['disabled_modules'])
                    else:
                        instance_data['disabled_modules'] = []
                        
                    if instance_data.get('environment_vars'):
                        instance_data['environment_vars'] = json.loads(instance_data['environment_vars'])
                    else:
                        instance_data['environment_vars'] = {}
                        
                    if instance_data.get('metadata'):
                        instance_data['metadata'] = json.loads(instance_data['metadata'])
                    else:
                        instance_data['metadata'] = {}
                    
                    instances.append(instance_data)
                
                return {
                    'instances': instances,
                    'total': total,
                    'page': page,
                    'page_size': page_size
                }
                
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
                        elif field in ['custom_addons', 'disabled_modules', 'environment_vars', 'metadata']:
                            # JSON serialize list/dict fields
                            update_values.append(json.dumps(value))
                        else:
                            update_values.append(value)
                        param_index += 1
                
                if not update_fields:
                    # No fields to update
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
        """Update instance status and optional error message"""
        async with self.pool.acquire() as conn:
            try:
                result = await conn.fetchval("""
                    UPDATE instances 
                    SET status = $1, error_message = $2, updated_at = $3
                    WHERE id = $4
                    RETURNING id
                """, status.value, error_message, datetime.utcnow(), instance_id)
                
                if result:
                    logger.info("Instance status updated", instance_id=str(instance_id), status=status.value)
                    return True
                return False
                
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
    
    
    
    async def get_instances_by_status(self, status: InstanceStatus, limit: int = 50) -> List[Dict[str, Any]]:
        """Get instances by status"""
        async with self.pool.acquire() as conn:
            try:
                rows = await conn.fetch("""
                    SELECT id, name, customer_id, status, error_message, created_at, updated_at
                    FROM instances 
                    WHERE status = $1
                    ORDER BY updated_at DESC
                    LIMIT $2
                """, status.value, limit)
                
                return [dict(row) for row in rows]
                
            except Exception as e:
                logger.error("Failed to get instances by status", status=status.value, error=str(e))
                raise

    async def check_subdomain_availability(self, subdomain: str) -> bool:
        """Check if subdomain is available (not taken by any active instance)"""
        async with self.pool.acquire() as conn:
            try:
                # Check if subdomain exists for any active instance (not terminated)
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM instances 
                    WHERE subdomain = $1 AND status != $2
                """, subdomain.lower(), InstanceStatus.TERMINATED.value)
                
                # Return True if available (count is 0), False if taken
                is_available = count == 0
                
                logger.info("Subdomain availability check", 
                           subdomain=subdomain, 
                           available=is_available,
                           existing_count=count)
                
                return is_available
                
            except Exception as e:
                logger.error("Failed to check subdomain availability", 
                           subdomain=subdomain, 
                           error=str(e))
                raise 