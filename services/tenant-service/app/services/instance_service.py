"""
Instance service business logic for Odoo instance management
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog

from app.utils.database import TenantDatabase
from app.models.instance import Instance, InstanceCreate, InstanceUpdate, InstanceStatus


logger = structlog.get_logger(__name__)


class InstanceService:
    """High-level instance business logic service"""
    
    def __init__(self, db: TenantDatabase):
        self.db = db
    
    async def create_instance_for_tenant(self, tenant_id: UUID, instance_data: InstanceCreate) -> Instance:
        """
        Create a new Odoo instance for a tenant with business logic validation
        """
        try:
            # Validate tenant exists and is active
            tenant = await self.db.get_tenant(tenant_id)
            if not tenant:
                raise ValueError("Tenant not found")
            
            if tenant.status != "active":
                raise ValueError(f"Cannot create instance for tenant with status: {tenant.status}")
            
            # Check instance limits
            instances_data = await self.db.get_instances_by_tenant(tenant_id, page=1, page_size=1)
            current_count = instances_data['total']
            
            if current_count >= tenant.max_instances:
                raise ValueError(f"Tenant has reached maximum instance limit: {tenant.max_instances}")
            
            # Set tenant_id in instance data
            instance_data.tenant_id = tenant_id
            
            # Create instance in database
            instance = await self.db.create_instance(instance_data)
            
            # TODO: Trigger async provisioning
            # await self._provision_instance_async(instance.id)
            
            logger.info("Instance created for tenant", 
                       instance_id=str(instance.id), 
                       tenant_id=str(tenant_id),
                       name=instance.name)
            
            return instance
            
        except Exception as e:
            logger.error("Failed to create instance for tenant", 
                        tenant_id=str(tenant_id), error=str(e))
            raise
    
    async def get_customer_instance_summary(self, customer_id: UUID) -> Dict[str, Any]:
        """
        Get instance summary for a customer across all tenants
        This is used by user-service for customer profile
        """
        try:
            total_instances = await self.db.get_instances_by_customer(customer_id)
            
            # Get tenant information
            tenants_data = await self.db.get_tenants_by_customer(customer_id, page=1, page_size=100)
            
            # Calculate statistics
            tenant_count = len(tenants_data['tenants'])
            max_instances_allowed = sum(t['max_instances'] for t in tenants_data['tenants'])
            
            # Get instances by status across all tenants
            instances_by_status = {
                'running': 0,
                'stopped': 0,
                'creating': 0,
                'error': 0,
                'total': total_instances
            }
            
            for tenant_data in tenants_data['tenants']:
                tenant_id = UUID(tenant_data['id'])
                tenant_instances = await self.db.get_instances_by_tenant(tenant_id, page=1, page_size=100)
                
                for instance in tenant_instances['instances']:
                    status = instance['status']
                    if status in instances_by_status:
                        instances_by_status[status] += 1
            
            summary = {
                'customer_id': str(customer_id),
                'tenant_count': tenant_count,
                'instance_count': total_instances,
                'max_instances_allowed': max_instances_allowed,
                'instances_by_status': instances_by_status,
                'utilization_percentage': (total_instances / max_instances_allowed * 100) if max_instances_allowed > 0 else 0
            }
            
            return summary
            
        except Exception as e:
            logger.error("Failed to get customer instance summary", 
                        customer_id=str(customer_id), error=str(e))
            return {
                'customer_id': str(customer_id),
                'tenant_count': 0,
                'instance_count': 0,
                'max_instances_allowed': 0,
                'instances_by_status': {'total': 0},
                'utilization_percentage': 0
            }
    
    async def start_instance(self, instance_id: UUID) -> Dict[str, Any]:
        """Start an Odoo instance"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            if instance.status == InstanceStatus.RUNNING:
                return {"status": "already_running", "message": "Instance is already running"}
            
            if instance.status not in [InstanceStatus.STOPPED, InstanceStatus.ERROR]:
                raise ValueError(f"Cannot start instance with status: {instance.status}")
            
            # Update status to starting
            await self.db.update_instance_status(instance_id, InstanceStatus.STARTING)
            
            # TODO: Implement actual Docker container starting
            # result = await self._start_docker_container(instance)
            
            # For now, simulate successful start
            await self.db.update_instance_status(instance_id, InstanceStatus.RUNNING)
            
            # TODO: Update instance URLs and connection info
            # await self._update_instance_network_info(instance_id)
            
            logger.info("Instance started", instance_id=str(instance_id))
            
            return {
                "status": "success",
                "message": "Instance started successfully",
                "instance_status": InstanceStatus.RUNNING.value
            }
            
        except Exception as e:
            await self.db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
            logger.error("Failed to start instance", instance_id=str(instance_id), error=str(e))
            raise
    
    async def stop_instance(self, instance_id: UUID) -> Dict[str, Any]:
        """Stop an Odoo instance"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            if instance.status == InstanceStatus.STOPPED:
                return {"status": "already_stopped", "message": "Instance is already stopped"}
            
            if instance.status not in [InstanceStatus.RUNNING, InstanceStatus.ERROR]:
                raise ValueError(f"Cannot stop instance with status: {instance.status}")
            
            # Update status to stopping
            await self.db.update_instance_status(instance_id, InstanceStatus.STOPPING)
            
            # TODO: Implement actual Docker container stopping
            # result = await self._stop_docker_container(instance)
            
            # For now, simulate successful stop
            await self.db.update_instance_status(instance_id, InstanceStatus.STOPPED)
            
            logger.info("Instance stopped", instance_id=str(instance_id))
            
            return {
                "status": "success",
                "message": "Instance stopped successfully",
                "instance_status": InstanceStatus.STOPPED.value
            }
            
        except Exception as e:
            await self.db.update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
            logger.error("Failed to stop instance", instance_id=str(instance_id), error=str(e))
            raise
    
    async def delete_instance(self, instance_id: UUID) -> Dict[str, Any]:
        """Delete an Odoo instance and its resources"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            # Stop instance first if running
            if instance.status == InstanceStatus.RUNNING:
                await self.stop_instance(instance_id)
            
            # TODO: Delete Docker container and volumes
            # await self._delete_docker_resources(instance)
            
            # TODO: Delete Odoo database
            # await self._delete_odoo_database(instance)
            
            # Soft delete in database
            success = await self.db.delete_instance(instance_id)
            
            if success:
                logger.info("Instance deleted", instance_id=str(instance_id))
                return {
                    "status": "success",
                    "message": "Instance deleted successfully"
                }
            else:
                raise ValueError("Failed to delete instance from database")
            
        except Exception as e:
            logger.error("Failed to delete instance", instance_id=str(instance_id), error=str(e))
            raise
    
    async def get_instance_health(self, instance_id: UUID) -> Dict[str, Any]:
        """Get detailed health information for an instance"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            # TODO: Check actual container health
            # container_health = await self._check_container_health(instance)
            # odoo_health = await self._check_odoo_health(instance)
            
            # For now, return basic status
            health = {
                "instance_id": str(instance_id),
                "status": instance.status,
                "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
                "error_message": instance.error_message,
                "uptime_seconds": None,  # TODO: Calculate from started_at
                "container_status": "unknown",  # TODO: Get from Docker
                "odoo_status": "unknown",  # TODO: Check Odoo health endpoint
                "database_status": "unknown",  # TODO: Check database connectivity
                "external_url": instance.external_url,
                "internal_url": instance.internal_url
            }
            
            return health
            
        except Exception as e:
            logger.error("Failed to get instance health", instance_id=str(instance_id), error=str(e))
            raise
    
    async def scale_instance_resources(self, instance_id: UUID, cpu_limit: Optional[float] = None,
                                     memory_limit: Optional[str] = None) -> Dict[str, Any]:
        """Scale instance resources (CPU, memory)"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            # Prepare update data
            update_data = InstanceUpdate()
            if cpu_limit is not None:
                update_data.cpu_limit = cpu_limit
            if memory_limit is not None:
                update_data.memory_limit = memory_limit
            
            # Update database
            updated_instance = await self.db.update_instance(instance_id, update_data)
            
            # TODO: Apply resource changes to running container
            # if instance.status == InstanceStatus.RUNNING:
            #     await self._update_container_resources(instance_id, cpu_limit, memory_limit)
            
            logger.info("Instance resources scaled", 
                       instance_id=str(instance_id),
                       cpu_limit=cpu_limit,
                       memory_limit=memory_limit)
            
            return {
                "status": "success",
                "message": "Instance resources updated successfully",
                "new_cpu_limit": updated_instance.cpu_limit,
                "new_memory_limit": updated_instance.memory_limit
            }
            
        except Exception as e:
            logger.error("Failed to scale instance resources", 
                        instance_id=str(instance_id), error=str(e))
            raise
    
    async def backup_instance(self, instance_id: UUID, backup_name: Optional[str] = None) -> Dict[str, Any]:
        """Create a backup of an instance"""
        try:
            instance = await self.db.get_instance(instance_id)
            if not instance:
                raise ValueError("Instance not found")
            
            if not backup_name:
                from datetime import datetime
                backup_name = f"backup_{instance.name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            
            # TODO: Implement actual backup logic
            # backup_result = await self._create_instance_backup(instance, backup_name)
            
            logger.info("Instance backup created", 
                       instance_id=str(instance_id),
                       backup_name=backup_name)
            
            return {
                "status": "success",
                "message": "Instance backup created successfully",
                "backup_name": backup_name,
                "backup_id": "backup_placeholder_id"  # TODO: Return actual backup ID
            }
            
        except Exception as e:
            logger.error("Failed to backup instance", 
                        instance_id=str(instance_id), error=str(e))
            raise
    
    # Private helper methods (TODO: Implement these with actual Docker operations)
    
    async def _provision_instance_async(self, instance_id: UUID):
        """Provision instance asynchronously (placeholder)"""
        # TODO: Implement actual instance provisioning
        pass
    
    async def _start_docker_container(self, instance: Instance):
        """Start Docker container for instance (placeholder)"""
        # TODO: Implement Docker container starting
        pass
    
    async def _stop_docker_container(self, instance: Instance):
        """Stop Docker container for instance (placeholder)"""
        # TODO: Implement Docker container stopping
        pass
    
    async def _delete_docker_resources(self, instance: Instance):
        """Delete Docker resources for instance (placeholder)"""
        # TODO: Implement Docker resource cleanup
        pass
    
    async def _delete_odoo_database(self, instance: Instance):
        """Delete Odoo database for instance (placeholder)"""
        # TODO: Implement database deletion
        pass 