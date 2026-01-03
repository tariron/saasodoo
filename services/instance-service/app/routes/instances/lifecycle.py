"""
Instance lifecycle routes (provisioning, termination, resource management)
"""

import subprocess
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
import structlog

from app.models.instance import InstanceStatus, BillingStatus, ProvisioningStatus
from app.utils.database import InstanceDatabase
from app.utils.kubernetes import KubernetesClient
from app.routes.instances.helpers import get_database, get_db_server_type

logger = structlog.get_logger(__name__)

router = APIRouter()


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

        # Check if this is a trial expiration billing update
        provisioning_trigger = provision_data.get("provisioning_trigger", "")
        billing_status = provision_data.get("billing_status", "paid")

        if provisioning_trigger == "trial_expired_billing_update":
            # For trial expiration, just update billing status without full provisioning
            logger.info("Trial expiration billing update",
                       instance_id=str(instance_id),
                       current_status=instance.provisioning_status)

            await db.update_instance_billing_status(
                str(instance_id),
                BillingStatus(billing_status),
                instance.provisioning_status  # Keep current provisioning status
            )

            logger.info("Updated billing status for trial expiration",
                       instance_id=str(instance_id),
                       billing_status=billing_status)

            return {
                "status": "success",
                "message": f"Billing status updated to {billing_status}",
                "billing_status": billing_status,
                "timestamp": datetime.utcnow().isoformat()
            }

        if provisioning_trigger == "invoice_payment_success_billing_update":
            # For payment success, just update billing status without full provisioning
            logger.info("Payment success billing update",
                       instance_id=str(instance_id),
                       current_status=instance.provisioning_status)

            await db.update_instance_billing_status(
                str(instance_id),
                BillingStatus(billing_status),
                instance.provisioning_status  # Keep current provisioning status
            )

            logger.info("Updated billing status for payment success",
                       instance_id=str(instance_id),
                       billing_status=billing_status)

            return {
                "status": "success",
                "message": f"Billing status updated to {billing_status}",
                "billing_status": billing_status,
                "timestamp": datetime.utcnow().isoformat()
            }

        if provisioning_trigger == "invoice_write_off_billing_resolved":
            # For invoice write-off, just update billing status to enable reactivation
            logger.info("Invoice write-off billing update",
                       instance_id=str(instance_id),
                       current_status=instance.provisioning_status)

            await db.update_instance_billing_status(
                str(instance_id),
                BillingStatus(billing_status),
                instance.provisioning_status  # Keep current provisioning status
            )

            logger.info("Updated billing status after invoice write-off",
                       instance_id=str(instance_id),
                       billing_status=billing_status)

            return {
                "status": "success",
                "message": f"Billing status updated to {billing_status} after invoice write-off",
                "billing_status": billing_status,
                "timestamp": datetime.utcnow().isoformat()
            }

        # Validate that instance is in pending state for regular provisioning
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

        # Queue database allocation and provisioning workflow
        # This will call database-service, wait for allocation, then provision
        from app.tasks.provisioning import wait_for_database_and_provision
        job = wait_for_database_and_provision.delay(
            str(instance_id),
            str(instance.customer_id),
            instance.db_type or 'shared'
        )
        logger.info("Database allocation and provisioning job queued from webhook",
                   instance_id=str(instance_id),
                   job_id=job.id,
                   billing_status=billing_status,
                   db_type=instance.db_type or 'shared')

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
        skip_status_change = restart_data.get("skip_status_change", False)

        if not new_subscription_id:
            raise HTTPException(status_code=400, detail="subscription_id is required")

        # Update instance with new subscription and billing status
        await db.update_instance_subscription(str(instance_id), new_subscription_id)
        await db.update_instance_billing_status(
            str(instance_id),
            BillingStatus(billing_status),
            ProvisioningStatus.PENDING
        )

        # Conditionally change instance status based on skip_status_change parameter
        if not skip_status_change:
            # Queue start task to actually restart the instance container
            from app.tasks.lifecycle import start_instance_task

            # First set to STOPPED, then queue the start
            await db.update_instance_status(instance_id, InstanceStatus.STOPPED, reason)

            # Queue the start task
            job = start_instance_task.delay(str(instance_id))
            final_status = "starting"
            job_id = job.id

            logger.info("Instance restart queued after reactivation",
                       instance_id=str(instance_id),
                       job_id=job_id)
        else:
            final_status = instance.status.value  # Keep current status
            job_id = None

        logger.info("Instance restarted with new subscription successfully",
                   instance_id=str(instance_id),
                   new_subscription_id=new_subscription_id,
                   billing_status=billing_status)

        return {
            "status": "success",
            "message": f"Instance reactivated with subscription {new_subscription_id} - status: {final_status}",
            "instance_id": str(instance_id),
            "subscription_id": new_subscription_id,
            "billing_status": billing_status,
            "instance_status": final_status,
            "job_id": job_id,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to restart instance with new subscription",
                   instance_id=str(instance_id),
                   error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to restart instance: {str(e)}")


@router.post("/{instance_id}/apply-resources")
async def apply_resource_upgrade(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Apply live resource upgrades to running service (zero downtime)"""
    # DEBUG: Log at the VERY START
    print(f"DEBUG: apply_resource_upgrade called for {instance_id}")
    # Import helper from provisioning task
    from app.tasks.provisioning import _parse_size_to_bytes

    try:
        print(f"DEBUG: Inside try block for {instance_id}")
        logger.info("Applying live resource upgrade", instance_id=str(instance_id))

        # Get instance from database
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Check if database migration is needed (db_type='dedicated' but still on shared pool)
        if instance.db_type == 'dedicated':
            # Check if we're still on a shared pool
            db_server_info = await get_db_server_type(instance.db_server_id)

            if db_server_info and db_server_info['server_type'] == 'shared':
                logger.info("Database migration needed: shared pool → dedicated server",
                           instance_id=str(instance_id),
                           current_pool=db_server_info['name'],
                           db_type=instance.db_type)

                # Queue database migration task
                from app.tasks.migration import migrate_database_task
                job = migrate_database_task.delay(str(instance_id))

                return {
                    "status": "migrating",
                    "message": "Database migration from shared to dedicated queued",
                    "instance_id": str(instance_id),
                    "job_id": job.id,
                    "timestamp": datetime.utcnow().isoformat()
                }

        # FIX: Use service_name for Swarm (with fallback if missing in DB)
        service_name = instance.service_name
        if not service_name:
            service_name = f"odoo-{instance.database_name}-{instance.id.hex[:8]}"

        cpu_limit = instance.cpu_limit
        memory_limit = instance.memory_limit
        storage_limit = instance.storage_limit

        logger.info("Upgrading service resources",
                   service_name=service_name,
                   cpu_limit=cpu_limit,
                   memory_limit=memory_limit,
                   storage_limit=storage_limit)

        # Apply docker update for CPU and memory (zero downtime)
        try:
            # Parse memory limit to bytes
            memory_bytes = _parse_size_to_bytes(memory_limit)

            # Update Kubernetes deployment resources
            k8s_client = KubernetesClient()

            success = k8s_client.update_deployment_resources(service_name, cpu_limit, memory_bytes)

            if not success:
                raise HTTPException(status_code=500, detail="Failed to update service resources")

            logger.info("Successfully updated service CPU/memory",
                       service_name=service_name,
                       cpu_limit=cpu_limit,
                       memory_mb=memory_bytes // (1024 * 1024))
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to update service resources",
                        service_name=service_name,
                        error=str(e))
            raise HTTPException(status_code=500, detail=f"Docker update failed: {str(e)}")

        # Apply CephFS storage quota update
        try:
            # Build CephFS path - matches provisioning logic
            volume_name = f"odoo_data_{instance.database_name}_{instance.id.hex[:8]}"
            cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

            # Parse storage limit to bytes
            storage_bytes = _parse_size_to_bytes(storage_limit)

            # Update CephFS quota
            subprocess.run([
                'setfattr',
                '-n', 'ceph.quota.max_bytes',
                '-v', str(storage_bytes),
                cephfs_path
            ], capture_output=True, text=True, check=True)

            logger.info("Successfully updated CephFS storage quota",
                       path=cephfs_path,
                       storage_limit=storage_limit,
                       storage_bytes=storage_bytes)
        except subprocess.CalledProcessError as e:
            logger.error("Failed to update CephFS quota",
                        path=cephfs_path,
                        error=e.stderr)
            # Don't fail the whole operation - service resources were updated
            logger.warning("Continuing despite CephFS quota update failure")
        except Exception as e:
            logger.error("Error updating storage quota", error=str(e))
            logger.warning("Continuing despite storage quota update failure")

        return {
            "status": "success",
            "message": "Live resource upgrade applied successfully",
            "instance_id": str(instance_id),
            "service_name": service_name,
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
            "storage_limit": storage_limit,
            "timestamp": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to apply resource upgrade",
                   instance_id=str(instance_id),
                   error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to apply resource upgrade: {str(e)}")
