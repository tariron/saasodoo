"""
Billing Service HTTP Client
Client for communicating with the billing service API from user service
"""

import httpx
import logging
from typing import Optional, Dict, Any
import os
import json
from uuid import UUID

logger = logging.getLogger(__name__)

class UUIDJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles UUID objects"""
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)

class BillingServiceClient:
    """HTTP client for billing service operations"""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv('BILLING_SERVICE_URL', 'http://billing-service:8004')).rstrip('/')
        self.timeout = 30.0
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to billing service"""
        url = f"{self.base_url}{endpoint}"
        
        # Handle JSON data with UUID objects
        if 'json' in kwargs:
            kwargs['content'] = json.dumps(kwargs.pop('json'), cls=UUIDJSONEncoder)
            kwargs['headers'] = kwargs.get('headers', {})
            kwargs['headers']['Content-Type'] = 'application/json'
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                
                # Handle empty responses
                if response.status_code == 204 or not response.content:
                    return None
                
                return response.json()
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling billing service: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Billing service error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error calling billing service: {e}")
            raise Exception(f"Failed to connect to billing service: {e}")
        except Exception as e:
            logger.error(f"Unexpected error calling billing service: {e}")
            raise
    
    async def create_customer_account(self, customer_id: str, email: str, name: str, company: str = None) -> Dict[str, Any]:
        """Create a KillBill account for a new customer"""
        endpoint = "/api/billing/accounts/"
        payload = {
            "customer_id": customer_id,
            "email": email,
            "name": name,
            "company": company
        }
        
        logger.info(f"Creating billing account for customer {customer_id}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("success"):
            logger.info(f"Successfully created billing account for customer {customer_id}: {result.get('killbill_account_id')}")
        else:
            logger.error(f"Failed to create billing account for customer {customer_id}: {result}")
        
        return result or {}
    
    async def create_instance_subscription(self, customer_id: str, instance_id: str, plan_name: str) -> Dict[str, Any]:
        """Create a subscription for an instance with 14-day trial"""
        endpoint = "/api/billing/subscriptions/"
        payload = {
            "customer_id": customer_id,
            "instance_id": instance_id,
            "plan_name": plan_name,
            "billing_period": "MONTHLY"
        }
        
        logger.info(f"Creating instance subscription for customer {customer_id}, instance {instance_id}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("success"):
            logger.info(f"Successfully created instance subscription for customer {customer_id}")
        else:
            logger.error(f"Failed to create instance subscription for customer {customer_id}: {result}")
        
        return result or {}
    
    async def get_customer_billing_info(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get billing information for a customer"""
        endpoint = f"/api/billing/accounts/{customer_id}"
        
        try:
            result = await self._make_request("GET", endpoint)
            return result
        except Exception as e:
            logger.error(f"Failed to get billing info for customer {customer_id}: {e}")
            return None

# Global instance of the client
billing_client = BillingServiceClient()