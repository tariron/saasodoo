"""
KillBill API Client
Handles all interactions with KillBill billing system
"""

import httpx
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

class KillBillClient:
    """Client for interacting with KillBill API"""
    
    def __init__(self, base_url: str, api_key: str, api_secret: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.api_secret = api_secret
        self.username = username
        self.password = password
        
        # Default headers for all requests
        self.headers = {
            "X-Killbill-ApiKey": api_key,
            "X-Killbill-ApiSecret": api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to KillBill API"""
        url = f"{self.base_url}{endpoint}"
        
        headers = self.headers.copy()
        headers["X-Killbill-CreatedBy"] = "billing-service"
        headers["X-Killbill-Reason"] = "API request"
        headers["X-Killbill-Comment"] = f"Request from billing service at {datetime.utcnow().isoformat()}"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=data,
                    params=params,
                    auth=(self.username, self.password),
                    timeout=30.0
                )
                
                logger.info(f"KillBill API {method} {endpoint}: {response.status_code}")
                
                if response.status_code >= 400:
                    logger.error(f"KillBill API error: {response.status_code} - {response.text}")
                    response.raise_for_status()
                
                if response.status_code in [201, 204]:
                    # For creation requests, check if there's a Location header
                    if response.status_code == 201 and 'Location' in response.headers:
                        # Extract ID from Location header
                        location_parts = response.headers['Location'].split('/')
                        if location_parts:
                            created_id = location_parts[-1]
                            return {"id": created_id, "location": response.headers['Location']}
                    
                    if not response.text:
                        return {}
                
                return response.json() if response.text else {}
                
        except httpx.HTTPError as e:
            logger.error(f"KillBill API request failed: {e}")
            raise Exception(f"KillBill API error: {str(e)}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Check KillBill service health"""
        try:
            response = await self._make_request("GET", "/1.0/healthcheck")
            return {"status": "healthy", "killbill_response": response}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def create_account(
        self, 
        customer_id: str, 
        email: str, 
        name: str,
        company: Optional[str] = None,
        currency: str = "USD"
    ) -> Dict[str, Any]:
        """Create a new KillBill account"""
        account_data = {
            "externalKey": customer_id,
            "name": name,
            "email": email,
            "currency": currency,
            "company": company or "",
            "notes": f"Account created for customer {customer_id}"
        }
        
        try:
            response = await self._make_request("POST", "/1.0/kb/accounts", data=account_data)
            logger.info(f"Created KillBill account for customer {customer_id}")
            
            # KillBill returns 201 with empty body, so fetch the created account
            created_account = await self.get_account_by_external_key(customer_id)
            if not created_account:
                raise Exception(f"Account was created but could not be retrieved for customer {customer_id}")
            
            return created_account
        except Exception as e:
            logger.error(f"Failed to create KillBill account for customer {customer_id}: {e}")
            raise
    
    async def get_account_by_external_key(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Get account by external key (customer ID)"""
        try:
            response = await self._make_request(
                "GET", 
                f"/1.0/kb/accounts",
                params={"externalKey": customer_id}
            )
            return response if response else None
        except Exception as e:
            logger.error(f"Failed to get account for customer {customer_id}: {e}")
            return None
    
    async def get_account_by_id(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get account by KillBill account ID"""
        try:
            response = await self._make_request("GET", f"/1.0/kb/accounts/{account_id}")
            return response if response else None
        except Exception as e:
            logger.error(f"Failed to get account by ID {account_id}: {e}")
            return None
    
    async def create_subscription(
        self, 
        account_id: str, 
        plan_name: str,
        billing_period: str = "MONTHLY",
        product_category: str = "BASE"
    ) -> Dict[str, Any]:
        """Create a subscription for an account"""
        subscription_data = {
            "accountId": account_id,
            "planName": plan_name
        }
        
        try:
            response = await self._make_request("POST", "/1.0/kb/subscriptions", data=subscription_data)
            logger.info(f"Created subscription for account {account_id} with plan {plan_name}")
            
            # If we got a subscription ID, add it to the response
            if response.get("id"):
                response["subscriptionId"] = response["id"]
            
            return response
        except Exception as e:
            logger.error(f"Failed to create subscription for account {account_id}: {e}")
            raise
    
    async def start_trial(
        self, 
        account_id: str, 
        plan_name: str,
        trial_days: int = 14
    ) -> Dict[str, Any]:
        """Start a trial subscription for an account"""
        # For trial, we create a subscription with the trial phase
        subscription_data = {
            "accountId": account_id,
            "planName": plan_name
        }
        
        try:
            response = await self._make_request("POST", "/1.0/kb/subscriptions", data=subscription_data)
            logger.info(f"Started trial subscription for account {account_id} with {trial_days} days trial")
            return response
        except Exception as e:
            logger.error(f"Failed to start trial for account {account_id}: {e}")
            raise
    
    async def get_account_subscriptions(self, account_id: str) -> List[Dict[str, Any]]:
        """Get all subscriptions for an account"""
        try:
            response = await self._make_request("GET", f"/1.0/kb/accounts/{account_id}/subscriptions")
            return response if isinstance(response, list) else []
        except Exception as e:
            logger.error(f"Failed to get subscriptions for account {account_id}: {e}")
            raise
    
    async def cancel_subscription(self, subscription_id: str, reason: str = "User cancellation") -> Dict[str, Any]:
        """Cancel a subscription"""
        try:
            # KillBill expects a DELETE request with query parameters
            params = {
                "requestedDate": datetime.utcnow().isoformat(),
                "callCompletion": "true",
                "callTimeoutSec": "10"
            }
            
            response = await self._make_request("DELETE", f"/1.0/kb/subscriptions/{subscription_id}", params=params)
            logger.info(f"Cancelled subscription {subscription_id}: {reason}")
            return response or {"status": "cancelled"}
        except Exception as e:
            logger.error(f"Failed to cancel subscription {subscription_id}: {e}")
            raise
    
    async def get_subscription_by_id(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription details by ID"""
        try:
            response = await self._make_request("GET", f"/1.0/kb/subscriptions/{subscription_id}")
            return response if response else None
        except Exception as e:
            logger.error(f"Failed to get subscription {subscription_id}: {e}")
            return None
    
    async def register_webhook(self, webhook_url: str) -> Dict[str, Any]:
        """Register webhook URL with KillBill using proper notification callback API"""
        try:
            headers = self.headers.copy()
            headers["X-Killbill-ApiKey"] = self.api_key
            headers["X-Killbill-ApiSecret"] = self.api_secret
            headers["X-Killbill-CreatedBy"] = "billing-service"
            
            # Use the correct KillBill webhook registration endpoint
            url = f"{self.base_url}/1.0/kb/tenants/registerNotificationCallback"
            params = {"cb": webhook_url}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=url,
                    headers=headers,
                    params=params,
                    auth=(self.username, self.password),
                    timeout=30.0
                )
                
                logger.info(f"KillBill webhook registration POST {url}: {response.status_code}")
                
                if response.status_code >= 400:
                    logger.error(f"KillBill webhook registration error: {response.status_code} - {response.text}")
                    response.raise_for_status()
            
            logger.info(f"Successfully registered webhook URL: {webhook_url}")
            return {"status": "registered", "url": webhook_url}
            
        except Exception as e:
            logger.error(f"Failed to register webhook {webhook_url}: {e}")
            raise
