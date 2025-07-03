"""
Billing Service HTTP Client for Instance Service
Client for communicating with the billing service API
"""

import httpx
import logging
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)

class BillingServiceClient:
    """HTTP client for billing service operations"""
    
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv('BILLING_SERVICE_URL', 'http://billing-service:8004')).rstrip('/')
        self.timeout = 30.0
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to billing service"""
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
            logger.error(f"HTTP error calling billing service: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Billing service error: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error calling billing service: {e}")
            raise Exception(f"Failed to connect to billing service: {e}")
        except Exception as e:
            logger.error(f"Unexpected error calling billing service: {e}")
            raise
    
    async def get_customer_billing_info(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get billing information for a customer"""
        endpoint = f"/api/billing/accounts/{customer_id}"
        
        try:
            result = await self._make_request("GET", endpoint)
            return result
        except Exception as e:
            logger.error(f"Failed to get billing info for customer {customer_id}: {e}")
            return None
    
    async def create_instance_subscription(
        self, 
        customer_id: str, 
        instance_id: str, 
        instance_type: str,
        trial_eligible: bool = False
    ) -> Dict[str, Any]:
        """Create a subscription for an instance with 14-day trial"""
        
        # Map instance type to catalog plan names (single source of truth in KillBill)
        plan_mapping = {
            "development": "basic-monthly",    # Basic plan with trial
            "staging": "standard-monthly",     # Standard plan with trial
            "production": "premium-monthly"    # Premium plan with trial
        }
        
        plan_name = plan_mapping.get(instance_type, "basic-monthly")
        
        endpoint = "/api/billing/subscriptions/"
        payload = {
            "customer_id": customer_id,
            "instance_id": instance_id,
            "plan_name": plan_name,
            "billing_period": "MONTHLY",
            "trial_eligible": trial_eligible
        }
        
        logger.info(f"Creating instance subscription for customer {customer_id}, instance {instance_id}, plan {plan_name}")
        result = await self._make_request("POST", endpoint, json=payload)
        
        if result and result.get("success"):
            logger.info(f"Successfully created instance subscription for customer {customer_id}")
        else:
            logger.error(f"Failed to create instance subscription for customer {customer_id}: {result}")
        
        return result or {}
    
    async def check_customer_trial_status(self, customer_id: str) -> Dict[str, Any]:
        """Check if customer is eligible for trial or needs payment method"""
        endpoint = f"/api/billing/subscriptions/{customer_id}"
        
        try:
            result = await self._make_request("GET", endpoint)
            subscriptions = result.get("subscriptions", []) if result else []
            
            # Business logic for trial eligibility
            # For dev mode: Allow trials for customers with no existing subscriptions
            # In production, this would have more sophisticated rules
            
            trial_eligible = len(subscriptions) == 0  # First-time customer gets trial
            
            # Return trial eligibility decision along with subscription data
            return {
                "subscriptions": subscriptions,
                "trial_eligible": trial_eligible,
                "reason": "first_time_customer" if trial_eligible else "existing_customer",
                "subscription_count": len(subscriptions)
            }
            
        except Exception as e:
            logger.error(f"Failed to check trial status for customer {customer_id}: {e}")
            # On error, default to allowing trial (dev-friendly)
            return {
                "subscriptions": [], 
                "trial_eligible": True,
                "reason": "error_default_to_trial",
                "error": str(e)
            }

# Global instance of the client
billing_client = BillingServiceClient()