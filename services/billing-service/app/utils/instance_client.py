"""
Instance Service HTTP Client
Client for communicating with the instance service API
"""

import httpx
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID

logger = logging.getLogger(__name__)

class InstanceServiceClient:
    """HTTP client for instance service operations"""
    
    def __init__(self, base_url: str = "http://instance-service:8003"):
        self.base_url = base_url.rstrip('/')
        self.timeout = 30.0
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to instance service"""
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                
                # Handle empty responses
                if response.status_code == 204 or not response.content:
                    return None
                
                return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling instance service: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Instance service error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error calling instance service: {e}")
            raise Exception(f"Failed to connect to instance service: {e}")
        except Exception as e:
            logger.error(f"Unexpected error calling instance service: {e}")
            raise
    
    async def get_instances_by_customer_and_status(self, customer_id: str, provisioning_status: str) -> List[Dict[str, Any]]:
        """Get instances for a customer by provisioning status"""
        try:
            # Call instance service API with customer_id parameter directly
            endpoint = f"/api/v1/instances/?customer_id={customer_id}"
            result = await self._make_request("GET", endpoint)
            
            if result and result.get('instances'):
                # Filter by provisioning status if specified
                if provisioning_status:
                    filtered_instances = [
                        instance for instance in result['instances'] 
                        if instance.get('provisioning_status') == provisioning_status
                    ]
                    logger.info(f"Found {len(filtered_instances)} {provisioning_status} instances for customer {customer_id}")
                    return filtered_instances
                else:
                    logger.info(f"Found {len(result['instances'])} instances for customer {customer_id}")
                    return result['instances']
            
            logger.info(f"No {provisioning_status} instances found for customer {customer_id}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get {provisioning_status} instances for customer {customer_id}: {e}")
            return []
    
    async def get_instances_by_customer(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get all instances for a customer"""
        try:
            # Call instance service API with customer_id parameter directly
            endpoint = f"/api/v1/instances/?customer_id={customer_id}"
            result = await self._make_request("GET", endpoint)
            
            if result and result.get('instances'):
                logger.info(f"Found {len(result['instances'])} instances for customer {customer_id}")
                return result['instances']
            
            logger.info(f"No instances found for customer {customer_id}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get instances for customer {customer_id}: {e}")
            return []
    
    async def get_instance_by_subscription_id(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get an instance by its subscription ID"""
        endpoint = f"/api/v1/instances/by-subscription/{subscription_id}"
        try:
            result = await self._make_request("GET", endpoint)
            if result:
                logger.info(f"Found instance {result.get('id')} for subscription {subscription_id}")
                return result
            
            logger.info(f"No instance found for subscription_id {subscription_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to get instance by subscription_id {subscription_id}: {e}")
            return None

    async def _get_tenant_id_for_customer(self, customer_id: str) -> Optional[str]:
        """Get tenant_id for a customer from user service"""
        try:
            # Call user service to get tenant for this customer
            # For now, we'll use a simple assumption: customer_id = tenant_id
            # In a full implementation, this would call the user service API
            logger.info(f"Using customer_id as tenant_id for {customer_id} (simplified mapping)")
            return customer_id
            
        except Exception as e:
            logger.error(f"Failed to get tenant_id for customer {customer_id}: {e}")
            return None
    
    async def suspend_instance(self, instance_id: str, reason: str = "Billing suspension") -> Dict[str, Any]:
        """Suspend an instance"""
        endpoint = f"/api/v1/instances/{instance_id}/actions"
        payload = {
            "action": "suspend",
            "parameters": {
                "reason": reason
            }
        }
        
        logger.info(f"Suspending instance {instance_id}: {reason}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("status") == "success":
            logger.info(f"Successfully suspended instance {instance_id}")
        else:
            logger.error(f"Failed to suspend instance {instance_id}: {result}")
        
        return result or {}
    
    async def unsuspend_instance(self, instance_id: str, reason: str = "Billing restored") -> Dict[str, Any]:
        """Unsuspend an instance"""
        endpoint = f"/api/v1/instances/{instance_id}/actions"
        payload = {
            "action": "unsuspend",
            "parameters": {
                "reason": reason
            }
        }
        
        logger.info(f"Unsuspending instance {instance_id}: {reason}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("status") == "success":
            logger.info(f"Successfully unsuspended instance {instance_id}")
        else:
            logger.error(f"Failed to unsuspend instance {instance_id}: {result}")
        
        return result or {}
    
    async def terminate_instance(self, instance_id: str, reason: str = "Subscription cancelled") -> Dict[str, Any]:
        """Terminate an instance permanently"""
        endpoint = f"/api/v1/instances/{instance_id}/actions"
        payload = {
            "action": "terminate",
            "parameters": {
                "reason": reason
            }
        }
        
        logger.info(f"Terminating instance {instance_id}: {reason}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("status") == "success":
            logger.info(f"Successfully terminated instance {instance_id}")
        else:
            logger.error(f"Failed to terminate instance {instance_id}: {result}")
        
        return result or {}

    async def start_instance(self, instance_id: str, reason: str = "Payment successful") -> Dict[str, Any]:
        """Start an instance"""
        endpoint = f"/api/v1/instances/{instance_id}/actions"
        payload = {
            "action": "start",
            "parameters": {
                "reason": reason
            }
        }

        logger.info(f"Starting instance {instance_id}: {reason}")
        result = await self._make_request("POST", endpoint, json=payload)

        if result and result.get("status") == "success":
            logger.info(f"Successfully started instance {instance_id}")
        else:
            logger.error(f"Failed to start instance {instance_id}: {result}")

        return result or {}

    async def get_instance_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get instance status"""
        endpoint = f"/api/v1/instances/{instance_id}/status"
        
        try:
            result = await self._make_request("GET", endpoint)
            return result
        except Exception as e:
            logger.error(f"Failed to get instance {instance_id} status: {e}")
            return None
    
    async def provision_instance(
        self, 
        instance_id: str, 
        subscription_id: str = None, 
        billing_status: str = "payment_required",
        provisioning_trigger: str = "webhook"
    ) -> Dict[str, Any]:
        """Trigger instance provisioning from billing webhook"""
        endpoint = f"/api/v1/instances/{instance_id}/provision"
        payload = {
            "subscription_id": subscription_id,
            "billing_status": billing_status,
            "provisioning_trigger": provisioning_trigger,
            "triggered_by": "billing_webhook"
        }
        
        logger.info(f"Triggering provisioning for instance {instance_id} with {billing_status} status")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("status") == "success":
            logger.info(f"Successfully triggered provisioning for instance {instance_id}")
        else:
            logger.error(f"Failed to trigger provisioning for instance {instance_id}: {result}")
        
        return result or {}
    
    async def create_instance_with_subscription(self, instance_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create instance with subscription linkage"""
        endpoint = "/api/v1/instances/"

        # Validate required fields are present
        required_fields = ["customer_id", "subscription_id", "name", "admin_email", "database_name"]
        missing_fields = [field for field in required_fields if not instance_data.get(field)]
        
        if missing_fields:
            logger.error(f"Missing required fields for instance creation: {missing_fields}")
            raise Exception(f"Cannot create instance - missing required fields: {', '.join(missing_fields)}")
        
        # Create instance payload with provided fields
        payload = {
            "name": instance_data["name"],
            "description": instance_data.get("description", "Instance created via billing webhook"),
            "odoo_version": instance_data.get("odoo_version", "17"),
            "instance_type": instance_data.get("instance_type", "production"),
            "admin_email": instance_data["admin_email"],
            "database_name": instance_data["database_name"],
            "subdomain": instance_data.get("subdomain"),
            "demo_data": instance_data.get("demo_data", False),
            "cpu_limit": instance_data.get("cpu_limit", 1.0),
            "memory_limit": instance_data.get("memory_limit", "1G"),
            "storage_limit": instance_data.get("storage_limit", "10G"),
            "custom_addons": instance_data.get("custom_addons", []),
            "customer_id": instance_data["customer_id"],
            "subscription_id": instance_data["subscription_id"],
            "billing_status": instance_data.get("billing_status", "payment_required"),
            "provisioning_status": instance_data.get("provisioning_status", "pending")
        }
        
        logger.info(f"Creating instance for customer {instance_data['customer_id']} with subscription {instance_data['subscription_id']}")
        
        try:
            result = await self._make_request("POST", endpoint, json=payload)
            
            if result and result.get("id"):
                logger.info(f"Successfully created instance {result['id']} with subscription {instance_data['subscription_id']}")
            else:
                logger.error(f"Failed to create instance - no ID returned: {result}")
                
            return result
            
        except Exception as e:
            logger.error(f"Failed to create instance with subscription: {e}")
            return None
    
    async def restart_instance_with_new_subscription(
        self, 
        instance_id: str, 
        subscription_id: str,
        billing_status: str = "payment_required",
        skip_status_change: bool = False
    ) -> Dict[str, Any]:
        """Restart a terminated instance with a new subscription ID"""
        endpoint = f"/api/v1/instances/{instance_id}/restart-with-subscription"
        payload = {
            "subscription_id": subscription_id,
            "billing_status": billing_status,
            "reason": "Instance reactivated with new subscription",
            "skip_status_change": skip_status_change
        }
        
        logger.info(f"Restarting terminated instance {instance_id} with new subscription {subscription_id}")
        
        try:
            result = await self._make_request("POST", endpoint, json=payload)
            
            if result and result.get("status") == "success":
                logger.info(f"Successfully restarted instance {instance_id} with subscription {subscription_id}")
            else:
                logger.error(f"Failed to restart instance {instance_id}: {result}")
                
            return result or {}
            
        except Exception as e:
            logger.error(f"Failed to restart instance {instance_id} with new subscription: {e}")
            return {"status": "error", "message": str(e)}

    async def update_instance_resources(
        self,
        instance_id: str,
        cpu_limit: float,
        memory_limit: str,
        storage_limit: str
    ) -> Dict[str, Any]:
        """Update instance resource limits in database"""
        endpoint = f"/api/v1/instances/{instance_id}"
        payload = {
            "cpu_limit": cpu_limit,
            "memory_limit": memory_limit,
            "storage_limit": storage_limit
        }

        logger.info(f"Updating instance {instance_id} resources: {cpu_limit} CPU, {memory_limit} RAM, {storage_limit} storage")

        try:
            result = await self._make_request("PUT", endpoint, json=payload)
            logger.info(f"Successfully updated instance {instance_id} resource limits in database")
            return result

        except Exception as e:
            logger.error(f"Failed to update instance {instance_id} resources: {e}")
            raise

    async def apply_resource_upgrade(self, instance_id: str) -> Dict[str, Any]:
        """Apply live resource upgrades to running container"""
        endpoint = f"/api/v1/instances/{instance_id}/apply-resources"

        logger.info(f"Applying live resource upgrade to instance {instance_id}")

        try:
            result = await self._make_request("POST", endpoint)
            logger.info(f"Successfully applied live resource upgrade to instance {instance_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to apply resource upgrade to instance {instance_id}: {e}")
            raise

# Global instance of the client
instance_client = InstanceServiceClient()