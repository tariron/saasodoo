"""
Shared helper functions for instance routes
"""

import asyncio
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from fastapi import Request, HTTPException

from app.models.instance import InstanceStatus, InstanceAction, InstanceUpdate, BillingStatus
from app.utils.database import InstanceDatabase
from app.utils.kubernetes import KubernetesClient
import structlog

logger = structlog.get_logger(__name__)


def get_database(request: Request) -> InstanceDatabase:
    """Dependency to get database instance"""
    return request.app.state.db


def get_valid_actions_for_status(status: InstanceStatus) -> list:
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
        InstanceStatus.CONTAINER_MISSING: [InstanceAction.START, InstanceAction.BACKUP, InstanceAction.RESTORE, InstanceAction.SUSPEND, InstanceAction.TERMINATE],
        InstanceStatus.PAUSED: [InstanceAction.UNPAUSE, InstanceAction.TERMINATE]
    }
    return action_map.get(status, [])


def instance_to_response_dict(instance) -> Dict[str, Any]:
    """Convert instance model to response dictionary"""
    return {
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
        "subdomain": getattr(instance, 'subdomain', None),
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


def instance_dict_to_response_dict(instance_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert instance dict (from list query) to response dictionary"""
    return {
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


async def start_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Start instance containers"""
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


async def stop_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Stop instance containers"""
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


async def restart_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Restart instance containers"""
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


async def update_instance_software(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Update instance software/modules"""
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


async def backup_instance(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Create instance backup"""
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


async def restore_instance(instance_id: UUID, db: InstanceDatabase, parameters: dict) -> dict:
    """Restore instance from backup"""
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


async def stop_deployment_for_suspension(instance):
    """Stop Kubernetes deployment for suspension - scale to 0"""
    deployment_name = f"odoo-{instance.database_name}-{instance.id.hex[:8]}"

    try:
        k8s_client = KubernetesClient()

        # Check current replicas
        deployment = k8s_client.apps_v1.read_namespaced_deployment(
            name=deployment_name,
            namespace=k8s_client.namespace
        )

        if deployment.spec.replicas == 0:
            logger.info("Deployment already scaled to 0", deployment_name=deployment_name)
            return

        logger.info("Scaling deployment to 0 for suspension", deployment_name=deployment_name)

        # Scale to 0 replicas
        success = k8s_client.scale_deployment(deployment_name, replicas=0)

        if not success:
            raise Exception(f"Failed to scale deployment {deployment_name} to 0")

        # Wait for pods to terminate (30 second timeout)
        for _ in range(30):
            await asyncio.sleep(1)
            pod_status = k8s_client.get_pod_status(deployment_name)
            if not pod_status:
                break

        logger.info("Deployment stopped for suspension", deployment_name=deployment_name)

    except Exception as e:
        logger.error("Failed to stop deployment for suspension", deployment_name=deployment_name, error=str(e))
        raise


async def suspend_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Suspend instance due to billing issues - ACTUALLY stops the deployment"""
    try:
        # Get current instance to check if it needs to be stopped first
        instance = await db.get_instance(instance_id)
        if not instance:
            raise Exception("Instance not found")

        # If instance is running, stop the actual Kubernetes deployment first
        if instance.status == InstanceStatus.RUNNING:
            logger.info("Stopping running instance deployment before suspension", instance_id=str(instance_id))

            # Use Kubernetes scaling to stop deployment
            await stop_deployment_for_suspension(instance)
            logger.info("Deployment stopped for suspension", instance_id=str(instance_id))

        # Update status to suspended
        await db.update_instance_status(instance_id, InstanceStatus.PAUSED, "Instance suspended due to billing issues")

        # Update billing status to payment_required
        await db.update_instance_billing_status(str(instance_id), BillingStatus.PAYMENT_REQUIRED)

        logger.info("Instance suspended successfully with container stopped and billing status updated", instance_id=str(instance_id))
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


async def unsuspend_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Unsuspend instance after billing issues resolved"""
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


async def terminate_instance(instance_id: UUID, db: InstanceDatabase) -> dict:
    """Terminate instance permanently - stops deployment and sets status to terminated"""
    print(f"DEBUG: terminate_instance called for {instance_id}")

    try:
        # Get current instance to check if it needs to be stopped first
        instance = await db.get_instance(instance_id)
        if not instance:
            raise Exception("Instance not found")

        print(f"DEBUG: Instance current status: {instance.status}")

        # If instance has a deployment that might exist, stop it first
        deployment_states = [InstanceStatus.RUNNING, InstanceStatus.STOPPED, InstanceStatus.STARTING,
                          InstanceStatus.STOPPING, InstanceStatus.PAUSED, InstanceStatus.RESTARTING]
        # Note: CONTAINER_MISSING is not included as there's no deployment to stop

        if instance.status in deployment_states:
            print(f"DEBUG: Instance in deployment_states, attempting to stop deployment")
            logger.info("Stopping instance deployment before termination",
                       instance_id=str(instance_id), current_status=instance.status)

            # Use Kubernetes scaling to stop deployment
            await stop_deployment_for_suspension(instance)
            print(f"DEBUG: Deployment stop completed")
            logger.info("Deployment stopped for termination", instance_id=str(instance_id))

        # Update status to terminated (permanent)
        print(f"DEBUG: About to update status to TERMINATED")
        logger.info("Updating instance status to TERMINATED", instance_id=str(instance_id))
        update_success = await db.update_instance_status(instance_id, InstanceStatus.TERMINATED, "Instance terminated due to subscription cancellation")
        print(f"DEBUG: update_success = {update_success}")

        if not update_success:
            print(f"DEBUG: update_success is False!")
            error_msg = f"Database update returned False - instance {instance_id} status not updated to TERMINATED"
            logger.error(error_msg, instance_id=str(instance_id))
            raise Exception(error_msg)

        # Verify the update actually happened by reading back from database
        print(f"DEBUG: Verifying database update...")
        updated_instance = await db.get_instance(instance_id)
        print(f"DEBUG: Verification - status is {updated_instance.status if updated_instance else 'NOT_FOUND'}")
        if not updated_instance or updated_instance.status != InstanceStatus.TERMINATED:
            actual_status = updated_instance.status if updated_instance else "NOT_FOUND"
            error_msg = f"Database update verification failed - instance {instance_id} status is {actual_status}, expected TERMINATED"
            print(f"DEBUG: VERIFICATION FAILED - {error_msg}")
            logger.error(error_msg, instance_id=str(instance_id), actual_status=actual_status)
            raise Exception(error_msg)

        print(f"DEBUG: Termination successful!")
        logger.info("Instance terminated successfully with container stopped and database verified",
                   instance_id=str(instance_id), verified_status=updated_instance.status)
        return {
            "status": "success",
            "message": "Instance terminated successfully",
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        print(f"DEBUG: Exception in terminate_instance: {e}")
        logger.error("Failed to terminate instance", instance_id=str(instance_id), error=str(e))
        await db.update_instance_status(instance_id, InstanceStatus.ERROR, f"Termination failed: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to terminate instance: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        }


async def get_db_server_type(db_server_id: Optional[UUID]) -> Optional[Dict[str, Any]]:
    """Get database server type (shared/dedicated) from db_servers table"""
    if not db_server_id:
        return None

    try:
        import asyncpg
        import os

        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'postgres'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database=os.getenv('POSTGRES_DB', 'instance'),
            user=os.getenv('DB_SERVICE_USER', 'instance_service'),
            password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
        )

        try:
            row = await conn.fetchrow("""
                SELECT id, name, server_type
                FROM db_servers
                WHERE id = $1
            """, db_server_id)

            if row:
                return dict(row)
            return None

        finally:
            await conn.close()

    except Exception as e:
        logger.error("Error getting database server type",
                    db_server_id=str(db_server_id),
                    error=str(e))
        return None
