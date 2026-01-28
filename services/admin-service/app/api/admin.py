from fastapi import APIRouter
from typing import List
from app.models.schemas import PlatformMetrics, SystemStatus, Customer
from app.services.user_client import user_service_client
from app.services.instance_client import instance_service_client
from app.services.billing_client import billing_service_client
from app.services.database_client import database_service_client

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics", response_model=PlatformMetrics)
async def get_platform_metrics():
    """Get platform overview metrics by aggregating from services"""

    # Get instance stats
    instance_stats = await instance_service_client.get_instance_stats()

    # Get all instances to count unique customers
    instances = await instance_service_client.get_all_instances()
    unique_customers = len(set(inst.get("customer_id") for inst in instances if inst.get("customer_id")))

    # Get MRR (placeholder for now)
    mrr = await billing_service_client.get_mrr()

    # Check service health
    user_health = await user_service_client.health_check()
    instance_health = await instance_service_client.health_check()
    billing_health = await billing_service_client.health_check()
    database_health = await database_service_client.health_check()

    return PlatformMetrics(
        total_customers=unique_customers,
        active_instances=instance_stats.get("active", 0),
        total_instances=instance_stats.get("total", 0),
        revenue_mrr=mrr,
        system_status=SystemStatus(
            user_service=user_health,
            billing_service=billing_health,
            instance_service=instance_health,
            database_service=database_health
        )
    )


@router.get("/customers", response_model=List[Customer])
async def get_customers():
    """Get list of all customers by aggregating from instances"""
    # Get all instances
    instances = await instance_service_client.get_all_instances()

    # Group instances by customer_id
    customer_instances = {}
    for inst in instances:
        cust_id = inst.get("customer_id")
        if cust_id:
            if cust_id not in customer_instances:
                customer_instances[cust_id] = []
            customer_instances[cust_id].append(inst)

    # Fetch customer details for each unique customer_id
    customers = []
    for customer_id, cust_instances in customer_instances.items():
        # Get customer info from user-service
        customer_data = await user_service_client.get_customer_by_id(customer_id)

        if customer_data:
            # Use first instance's created_at as proxy for customer created_at
            first_instance = min(cust_instances, key=lambda x: x.get("created_at", ""))

            customers.append(Customer(
                id=customer_id,
                email=customer_data.get("email", "unknown"),
                full_name=customer_data.get("first_name", "") + " " + customer_data.get("last_name", ""),
                status=customer_data.get("status", "unknown"),
                created_at=first_instance.get("created_at", ""),
                total_instances=len(cust_instances)
            ))

    # Sort by created_at descending (most recent first)
    customers.sort(key=lambda x: x.created_at, reverse=True)

    return customers
