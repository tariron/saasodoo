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
    
    async def get_instances_by_customer(self, customer_id: str) -> List[Dict[str, Any]]:
        """Get all instances for a customer via tenant mapping"""
        try:
            # Step 1: Get tenant_id for this customer from user service
            tenant_id = await self._get_tenant_id_for_customer(customer_id)
            if not tenant_id:
                logger.warning(f"No tenant found for customer {customer_id}")
                return []
            
            # Step 2: Get instances for this tenant
            endpoint = f"/api/v1/instances/?tenant_id={tenant_id}"
            result = await self._make_request("GET", endpoint)
            
            if result and result.get('instances'):
                logger.info(f"Found {len(result['instances'])} instances for customer {customer_id}")
                return result['instances']
            
            logger.info(f"No instances found for customer {customer_id}")
            return []
            
        except Exception as e:
            logger.error(f"Failed to get instances for customer {customer_id}: {e}")
            return []
    
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
    
    async def get_instance_status(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get instance status"""
        endpoint = f"/api/v1/instances/{instance_id}/status"
        
        try:
            result = await self._make_request("GET", endpoint)
            return result
        except Exception as e:
            logger.error(f"Failed to get instance {instance_id} status: {e}")
            return None

# Global instance of the client
instance_client = InstanceServiceClient()