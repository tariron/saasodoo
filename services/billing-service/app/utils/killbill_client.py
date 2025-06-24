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
                
                if response.status_code in [201, 204] and not response.text:
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
