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
        product_category: str = "BASE",
        instance_id: Optional[str] = None,
        phase_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a subscription for an account with optional instance metadata and phase type"""
        subscription_data = {
            "accountId": account_id,
            "planName": plan_name
        }
        
        # Add phase type to control trial/skip trial behavior
        if phase_type:
            subscription_data["phaseType"] = phase_type
        
        try:
            response = await self._make_request("POST", "/1.0/kb/subscriptions", data=subscription_data)
            logger.info(f"Created subscription for account {account_id} with plan {plan_name}")
            
            subscription_id = response.get("id")
            if subscription_id:
                response["subscriptionId"] = subscription_id
                
                # Add instance metadata if provided
                if instance_id:
                    try:
                        await self._add_subscription_metadata(subscription_id, {"instance_id": instance_id})
                        logger.info(f"Added instance metadata {instance_id} to subscription {subscription_id}")
                    except Exception as meta_error:
                        logger.warning(f"Failed to add metadata to subscription {subscription_id}: {meta_error}")
                        # Don't fail the subscription creation for metadata issues
            
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
        """Get all subscriptions for an account using the bundles endpoint (subscriptions endpoint is broken)"""
        try:
            # Use bundles endpoint instead of subscriptions endpoint due to KillBill API bug
            response = await self._make_request("GET", f"/1.0/kb/accounts/{account_id}/bundles")
            
            subscriptions = []
            if isinstance(response, list):
                # Extract subscriptions from each bundle
                for bundle in response:
                    bundle_subscriptions = bundle.get('subscriptions', [])
                    if isinstance(bundle_subscriptions, list):
                        subscriptions.extend(bundle_subscriptions)
            
            logger.info(f"Found {len(subscriptions)} subscriptions for account {account_id} via bundles endpoint")
            return subscriptions
            
        except Exception as e:
            # For 404 errors (new accounts with no bundles), return empty list
            if "404" in str(e):
                logger.info(f"No bundles found for account {account_id} (404 - new account)")
                return []
            logger.error(f"Failed to get subscriptions for account {account_id}: {e}")
            raise
    
    async def cancel_subscription(self, subscription_id: str, reason: str = "User cancellation") -> Dict[str, Any]:
        """Cancel a subscription with END_OF_TERM policy (graceful cancellation)"""
        try:
            # KillBill expects a DELETE request with END_OF_TERM policies
            params = {
                "entitlementPolicy": "END_OF_TERM",  # Keep access until period end
                "billingPolicy": "END_OF_TERM",      # Stop billing at period end
                "useRequestedDateForBilling": "true",
                "callCompletion": "true",
                "callTimeoutSec": "10"
            }
            
            # Add reason to plugin properties if provided
            if reason:
                params["pluginProperty"] = f"reason={reason}"
            
            response = await self._make_request("DELETE", f"/1.0/kb/subscriptions/{subscription_id}", params=params)
            logger.info(f"Scheduled end-of-term cancellation for subscription {subscription_id}: {reason}")
            return response or {"status": "scheduled_for_cancellation"}
        except Exception as e:
            logger.error(f"Failed to schedule cancellation for subscription {subscription_id}: {e}")
            raise
    
    async def get_subscription_by_id(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription details by ID"""
        try:
            response = await self._make_request("GET", f"/1.0/kb/subscriptions/{subscription_id}")
            return response if response else None
        except Exception as e:
            logger.error(f"Failed to get subscription {subscription_id}: {e}")
            return None
    
    async def check_tenant_exists(self) -> bool:
        """Check if KillBill tenant exists"""
        try:
            headers = {
                "X-Killbill-ApiKey": self.api_key,
                "X-Killbill-ApiSecret": self.api_secret,
                "Accept": "application/json"
            }

            url = f"{self.base_url}/1.0/kb/tenants"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url=url,
                    headers=headers,
                    auth=(self.username, self.password),
                    timeout=30.0
                )

                if response.status_code == 200:
                    logger.info("KillBill tenant exists")
                    return True
                elif response.status_code == 404:
                    logger.info("KillBill tenant does not exist")
                    return False
                else:
                    logger.warning(f"Unexpected response checking tenant: {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Failed to check if tenant exists: {e}")
            return False

    async def create_tenant(self) -> Dict[str, Any]:
        """Create KillBill tenant"""
        try:
            tenant_data = {
                "apiKey": self.api_key,
                "apiSecret": self.api_secret
            }

            headers = {
                "Content-Type": "application/json",
                "X-Killbill-CreatedBy": "billing-service"
            }

            url = f"{self.base_url}/1.0/kb/tenants"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=url,
                    headers=headers,
                    json=tenant_data,
                    auth=(self.username, self.password),
                    timeout=30.0
                )

                logger.info(f"KillBill tenant creation POST {url}: {response.status_code}")

                if response.status_code >= 400:
                    logger.error(f"KillBill tenant creation error: {response.status_code} - {response.text}")
                    response.raise_for_status()

            logger.info(f"Successfully created KillBill tenant with apiKey: {self.api_key}")
            return {"status": "created", "apiKey": self.api_key}

        except Exception as e:
            logger.error(f"Failed to create tenant: {e}")
            raise

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

    async def get_overdue_config(self) -> Optional[str]:
        """Get overdue configuration from KillBill"""
        try:
            url = f"{self.base_url}/1.0/kb/overdue/xml"
            headers = self.headers.copy()
            headers["Accept"] = "text/xml"

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url=url,
                    headers=headers,
                    auth=(self.username, self.password),
                    timeout=30.0
                )

                if response.status_code == 404:
                    logger.info("No overdue configuration found in KillBill")
                    return None

                if response.status_code >= 400:
                    logger.error(f"Error fetching overdue config: {response.status_code} - {response.text}")
                    return None

                return response.text

        except Exception as e:
            logger.error(f"Failed to get overdue config: {e}")
            return None

    async def upload_overdue_config(self, overdue_xml: str) -> Dict[str, Any]:
        """Upload overdue configuration to KillBill"""
        try:
            url = f"{self.base_url}/1.0/kb/overdue/xml"
            headers = {
                "X-Killbill-ApiKey": self.api_key,
                "X-Killbill-ApiSecret": self.api_secret,
                "X-Killbill-CreatedBy": "billing-service",
                "Content-Type": "text/xml"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=url,
                    headers=headers,
                    content=overdue_xml,
                    auth=(self.username, self.password),
                    timeout=30.0
                )

                logger.info(f"KillBill overdue config upload: {response.status_code}")

                if response.status_code >= 400:
                    logger.error(f"Error uploading overdue config: {response.status_code} - {response.text}")
                    response.raise_for_status()

            logger.info("Successfully uploaded overdue configuration")
            return {"status": "uploaded"}

        except Exception as e:
            logger.error(f"Failed to upload overdue config: {e}")
            raise

    async def upload_catalog_config(self, catalog_xml: str) -> Dict[str, Any]:
        """Upload catalog configuration to KillBill"""
        try:
            url = f"{self.base_url}/1.0/kb/tenants/uploadPluginConfig/killbill-catalog"
            headers = {
                "X-Killbill-ApiKey": self.api_key,
                "X-Killbill-ApiSecret": self.api_secret,
                "X-Killbill-CreatedBy": "billing-service",
                "Content-Type": "text/plain"  # Must be text/plain for catalog upload
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=url,
                    headers=headers,
                    content=catalog_xml,
                    auth=(self.username, self.password),
                    timeout=30.0
                )

                logger.info(f"KillBill catalog config upload: {response.status_code}")

                if response.status_code >= 400:
                    logger.error(f"Error uploading catalog config: {response.status_code} - {response.text}")
                    response.raise_for_status()

            logger.info("Successfully uploaded catalog configuration")
            return {"status": "uploaded"}

        except Exception as e:
            logger.error(f"Failed to upload catalog config: {e}")
            raise

    async def _add_subscription_metadata(self, subscription_id: str, metadata: Dict[str, str]) -> Dict[str, Any]:
        """Add custom metadata to a subscription"""
        try:
            # KillBill expects an array of custom field objects
            custom_fields = []
            for key, value in metadata.items():
                # Ensure value is not None or empty
                if value is not None and str(value).strip():
                    custom_fields.append({
                        "name": key,
                        "value": str(value).strip()
                    })
                else:
                    logger.warning(f"Skipping custom field '{key}' with empty/null value: '{value}'")
            
            if not custom_fields:
                logger.warning(f"No valid custom fields to add to subscription {subscription_id}")
                return {"status": "success", "metadata": {}}
            
            field_summary = [f"{f['name']}={f['value']}" for f in custom_fields]
            logger.info(f"Adding {len(custom_fields)} custom fields to subscription {subscription_id}: {field_summary}")
            
            endpoint = f"/1.0/kb/subscriptions/{subscription_id}/customFields"
            
            # Add required headers for custom fields
            headers = self.headers.copy()
            headers["X-Killbill-CreatedBy"] = "billing-service"
            headers["X-Killbill-Reason"] = "Instance metadata"
            headers["X-Killbill-Comment"] = f"Adding instance metadata to subscription {subscription_id}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=f"{self.base_url}{endpoint}",
                    headers=headers,
                    json=custom_fields,
                    auth=(self.username, self.password),
                    timeout=30.0
                )
                
                logger.info(f"KillBill custom fields POST {endpoint}: {response.status_code}")
                
                if response.status_code >= 400:
                    logger.error(f"KillBill custom fields error: {response.status_code} - {response.text}")
                    response.raise_for_status()
            
            logger.info(f"Successfully added {len(custom_fields)} custom fields to subscription {subscription_id}")
            
            return {"status": "success", "metadata": metadata}
            
        except Exception as e:
            logger.error(f"Failed to add metadata to subscription {subscription_id}: {e}")
            raise
    
    async def get_subscription_metadata(self, subscription_id: str) -> Dict[str, str]:
        """Get custom metadata from a subscription"""
        try:
            endpoint = f"/1.0/kb/subscriptions/{subscription_id}/customFields"
            response = await self._make_request("GET", endpoint)
            
            metadata = {}
            if isinstance(response, list):
                for field in response:
                    if field.get("name") and field.get("value"):
                        metadata[field["name"]] = field["value"]
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to get metadata for subscription {subscription_id}: {e}")
            return {}
    
    async def get_invoice_by_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Get invoice details by ID including line items"""
        try:
            endpoint = f"/1.0/kb/invoices/{invoice_id}?withItems=true"
            response = await self._make_request("GET", endpoint)
            return response if response else None
        except Exception as e:
            logger.error(f"Failed to get invoice {invoice_id}: {e}")
            return None
    
    async def get_subscription_id_from_invoice(self, invoice_id: str) -> Optional[str]:
        """Extract subscription ID from invoice items"""
        try:
            invoice = await self.get_invoice_by_id(invoice_id)
            if not invoice or not invoice.get("items"):
                logger.warning(f"Invoice {invoice_id} has no items")
                return None
            
            # Look for subscription ID in invoice items
            for item in invoice["items"]:
                subscription_id = item.get("subscriptionId")
                if subscription_id:
                    logger.info(f"Found subscription {subscription_id} in invoice {invoice_id}")
                    return subscription_id
            
            logger.warning(f"No subscription ID found in invoice {invoice_id} items")
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract subscription ID from invoice {invoice_id}: {e}")
            return None
    
    async def get_catalog_plans(self, entitlements: dict = None) -> List[Dict[str, Any]]:
        """Get available plans from KillBill catalog with entitlements merged

        Args:
            entitlements: Dict mapping plan_name to entitlement data (cpu_limit, memory_limit, storage_limit)
        """
        try:
            endpoint = "/1.0/kb/catalog"
            response = await self._make_request("GET", endpoint)
            
            plans = []
            if isinstance(response, list) and len(response) > 0:
                # KillBill catalog response is an array of catalog versions
                catalog = response[0]  # Use the first (latest) catalog
                products = catalog.get("products", [])
                
                for product in products:
                    product_name = product.get("name", "")
                    product_type = product.get("type", "BASE")
                    product_plans = product.get("plans", [])
                    
                    for plan in product_plans:
                        plan_name = plan.get("name", "")
                        billing_period = plan.get("billingPeriod", "MONTHLY")
                        phases = plan.get("phases", [])
                        
                        # Extract trial and pricing information from phases
                        trial_length = 0
                        trial_time_unit = "DAYS"
                        price = 0
                        currency = "USD"
                        
                        for phase in phases:
                            phase_type = phase.get("type", "")
                            
                            if phase_type == "TRIAL":
                                duration = phase.get("duration", {})
                                trial_length = duration.get("number", 0)
                                trial_time_unit = duration.get("unit", "DAYS")
                                
                            elif phase_type == "EVERGREEN":
                                # Get recurring price
                                prices = phase.get("prices", [])
                                if prices:
                                    price = prices[0].get("value", 0)
                                    currency = prices[0].get("currency", "USD")
                        
                        plan_info = {
                            "name": plan_name,
                            "product": product_name,
                            "type": product_type,
                            "description": f"{product_name} - {plan_name}",
                            "billing_period": billing_period,
                            "trial_length": trial_length,
                            "trial_time_unit": trial_time_unit,
                            "price": price,
                            "currency": currency,
                            "available": True
                        }

                        # Merge entitlements from database
                        if entitlements and plan_name in entitlements:
                            ent = entitlements[plan_name]
                            plan_info["cpu_limit"] = ent["cpu_limit"]
                            plan_info["memory_limit"] = ent["memory_limit"]
                            plan_info["storage_limit"] = ent["storage_limit"]

                        plans.append(plan_info)
            
            logger.info(f"Retrieved {len(plans)} plans from KillBill catalog")
            return plans
            
        except Exception as e:
            logger.error(f"Failed to get catalog plans: {e}")
            # Return fallback plans if catalog API fails
            return [
                {
                    "name": "basic-trial",
                    "product": "Basic",
                    "type": "BASE",
                    "description": "Basic plan with 14-day trial",
                    "billing_period": "MONTHLY",
                    "trial_length": 14,
                    "trial_time_unit": "DAYS",
                    "price": 0,
                    "currency": "USD",
                    "available": True,
                    "fallback": True
                },
                {
                    "name": "basic-immediate",
                    "product": "Basic",
                    "type": "BASE", 
                    "description": "Basic plan - immediate billing",
                    "billing_period": "MONTHLY",
                    "trial_length": 0,
                    "trial_time_unit": "DAYS",
                    "price": 5.00,
                    "currency": "USD",
                    "available": True,
                    "fallback": True
                },
                {
                    "name": "basic-monthly",
                    "product": "Basic",
                    "type": "BASE",
                    "description": "Basic monthly plan",
                    "billing_period": "MONTHLY", 
                    "trial_length": 14,
                    "trial_time_unit": "DAYS",
                    "price": 5.00,
                    "currency": "USD",
                    "available": True,
                    "fallback": True
                }
            ]
    
    async def get_account_balance(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get account balance from KillBill"""
        try:
            endpoint = f"/1.0/kb/accounts/{account_id}"
            response = await self._make_request("GET", endpoint)
            
            if response:
                return {
                    'accountBalance': response.get('accountBalance', 0.0),
                    'accountCBA': response.get('accountCBA', 0.0),
                    'currency': response.get('currency', 'USD')
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get account balance for {account_id}: {e}")
            return None
    
    async def get_account_invoices(self, account_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get invoices for an account from KillBill - fetch each invoice individually for complete data"""
        try:
            # First, get the list of invoices (without items due to API bug)
            endpoint = f"/1.0/kb/accounts/{account_id}/invoices"
            params = {"withItems": "false", "audit": "NONE"}
            
            response = await self._make_request("GET", endpoint, params=params)
            
            invoices = []
            if isinstance(response, list):
                # Sort by invoice date (most recent first) and limit
                sorted_invoices = sorted(response, key=lambda x: x.get('invoiceDate', ''), reverse=True)
                
                # Fetch all invoice details in parallel
                limited_invoices = sorted_invoices[:limit]
                invoice_ids = [invoice.get('invoiceId') for invoice in limited_invoices]
                
                # Batch fetch all complete invoice data in parallel
                import asyncio
                complete_invoice_tasks = [self.get_invoice_by_id(invoice_id) for invoice_id in invoice_ids]
                complete_invoices = await asyncio.gather(*complete_invoice_tasks, return_exceptions=True)
                
                for i, invoice in enumerate(limited_invoices):
                    try:
                        invoice_id = invoice.get('invoiceId')
                        
                        # Use complete invoice data if available, otherwise fallback to basic data
                        if i < len(complete_invoices) and not isinstance(complete_invoices[i], Exception):
                            complete_invoice = complete_invoices[i]
                            invoice_data = {
                                'id': complete_invoice.get('invoiceId'),
                                'account_id': account_id,
                                'invoice_number': complete_invoice.get('invoiceNumber'),
                                'invoice_date': complete_invoice.get('invoiceDate'),
                                'target_date': complete_invoice.get('targetDate'),
                                'amount': float(complete_invoice.get('amount', 0)),
                                'currency': complete_invoice.get('currency', 'USD'),
                                'status': complete_invoice.get('status', 'DRAFT'),
                                'balance': float(complete_invoice.get('balance', 0)),
                                'credit_adj': float(complete_invoice.get('creditAdj', 0)),
                                'refund_adj': float(complete_invoice.get('refundAdj', 0)),
                                'created_at': complete_invoice.get('createdDate'),
                                'updated_at': complete_invoice.get('updatedDate'),
                                'items': complete_invoice.get('items', [])  # Include items for debugging
                            }
                        else:
                            # Fallback to basic data if individual fetch fails
                            if isinstance(complete_invoices[i], Exception):
                                logger.warning(f"Failed to fetch details for invoice {invoice_id}: {complete_invoices[i]}")
                            
                            invoice_data = {
                                'id': invoice.get('invoiceId'),
                                'account_id': account_id,
                                'invoice_number': invoice.get('invoiceNumber'),
                                'invoice_date': invoice.get('invoiceDate'),
                                'target_date': invoice.get('targetDate'),
                                'amount': float(invoice.get('amount', 0)),
                                'currency': invoice.get('currency', 'USD'),
                                'status': invoice.get('status', 'DRAFT'),
                                'balance': float(invoice.get('balance', 0)),
                                'credit_adj': float(invoice.get('creditAdj', 0)),
                                'refund_adj': float(invoice.get('refundAdj', 0)),
                                'created_at': invoice.get('createdDate'),
                                'updated_at': invoice.get('updatedDate')
                            }
                        
                        invoices.append(invoice_data)
                    except Exception as e:
                        logger.warning(f"Failed to process invoice {invoice.get('invoiceId')}: {e}")
            
            logger.info(f"Retrieved {len(invoices)} invoices for account {account_id}")
            return invoices
            
        except Exception as e:
            logger.error(f"Failed to get invoices for account {account_id}: {e}")
            return []
    
    async def get_account_payment_methods(self, account_id: str) -> List[Dict[str, Any]]:
        """Get payment methods for an account from KillBill"""
        try:
            endpoint = f"/1.0/kb/accounts/{account_id}/paymentMethods"
            response = await self._make_request("GET", endpoint)
            
            payment_methods = []
            if isinstance(response, list):
                for pm in response:
                    # Add null checks for payment method data
                    if not pm or not isinstance(pm, dict):
                        logger.warning(f"Invalid payment method data for account {account_id}: {pm}")
                        continue
                    
                    plugin_info = pm.get('pluginInfo', {})
                    if not isinstance(plugin_info, dict):
                        plugin_info = {}
                    
                    payment_method_data = {
                        'id': pm.get('paymentMethodId'),
                        'account_id': account_id,
                        'plugin_name': pm.get('pluginName', 'unknown'),
                        'is_default': pm.get('isDefault', False),
                        'plugin_info': {
                            'type': plugin_info.get('type', 'UNKNOWN') if plugin_info else 'UNKNOWN',
                            'card_type': plugin_info.get('ccType') if plugin_info else None,
                            'exp_month': plugin_info.get('ccExpirationMonth') if plugin_info else None,
                            'exp_year': plugin_info.get('ccExpirationYear') if plugin_info else None,
                            'last_4': plugin_info.get('ccLast4') if plugin_info else None,
                            'email': plugin_info.get('email') if plugin_info else None,
                            'account_name': plugin_info.get('accountName') if plugin_info else None
                        },
                        'created_at': pm.get('createdDate'),
                        'updated_at': pm.get('updatedDate')
                    }
                    payment_methods.append(payment_method_data)
            elif response is None:
                logger.info(f"No payment methods found for account {account_id}")
            else:
                logger.warning(f"Unexpected payment methods response for account {account_id}: {type(response)}")
            
            logger.info(f"Retrieved {len(payment_methods)} payment methods for account {account_id}")
            return payment_methods
            
        except Exception as e:
            logger.error(f"Failed to get payment methods for account {account_id}: {e}")
            return []
    
    async def get_invoice_payments(self, invoice_id: str) -> List[Dict[str, Any]]:
        """Get payments for a specific invoice from KillBill"""
        try:
            endpoint = f"/1.0/kb/invoices/{invoice_id}/payments"
            response = await self._make_request("GET", endpoint)
            
            payments = []
            if isinstance(response, list):
                for payment in response:
                    # Check transaction status for actual payment success
                    payment_status = 'UNKNOWN'
                    transactions = payment.get('transactions', [])
                    
                    if transactions:
                        # Check if any transaction was successful
                        for transaction in transactions:
                            if transaction.get('status') == 'SUCCESS':
                                payment_status = 'SUCCESS'
                                break
                        # If no successful transaction, use the last transaction status
                        if payment_status == 'UNKNOWN' and transactions:
                            payment_status = transactions[-1].get('status', 'UNKNOWN')
                    
                    payment_data = {
                        'id': payment.get('paymentId'),
                        'invoice_id': invoice_id,
                        'amount': float(payment.get('purchasedAmount', 0)),
                        'currency': payment.get('currency', 'USD'),
                        'status': payment_status,
                        'payment_method_id': payment.get('paymentMethodId'),
                        'gateway_error_code': payment.get('gatewayErrorCode'),
                        'gateway_error_msg': payment.get('gatewayErrorMsg'),
                        'created_at': payment.get('createdDate'),
                        'updated_at': payment.get('updatedDate'),
                        'transactions': transactions  # Include transaction details for debugging
                    }
                    payments.append(payment_data)
            
            logger.info(f"Retrieved {len(payments)} payments for invoice {invoice_id}")
            return payments
            
        except Exception as e:
            logger.error(f"Failed to get payments for invoice {invoice_id}: {e}")
            return []

    async def write_off_invoice(self, invoice_id: str, reason: str = "Subscription cancelled - debt forgiven") -> bool:
        """Write off an invoice by adding the WRITTEN_OFF tag - brings balance to zero without moving charges to next invoice"""
        try:
            # WRITTEN_OFF tag UUID (standard KillBill control tag)
            WRITTEN_OFF_TAG_UUID = "00000000-0000-0000-0000-000000000004"

            endpoint = f"/1.0/kb/invoices/{invoice_id}/tags"
            # data parameter is automatically sent as JSON by _make_request
            await self._make_request("POST", endpoint, data=[WRITTEN_OFF_TAG_UUID])
            logger.info(f"Successfully wrote off invoice {invoice_id} - debt forgiven, balance brought to zero")
            return True
        except Exception as e:
            logger.error(f"Failed to write off invoice {invoice_id}: {e}")
            return False

    async def get_unpaid_invoices_by_subscription(self, subscription_id: str) -> List[Dict[str, Any]]:
        """Get all unpaid invoices for a subscription"""
        try:
            # Get subscription details to get account_id
            subscription = await self.get_subscription_by_id(subscription_id)
            if not subscription:
                return []

            account_id = subscription.get('accountId')

            # Get unpaid invoices for account
            endpoint = f"/1.0/kb/accounts/{account_id}/invoices?unpaidInvoicesOnly=true&withItems=true"
            invoices = await self._make_request("GET", endpoint)

            # Filter by subscription_id
            unpaid = []
            for invoice in (invoices or []):
                for item in invoice.get('items', []):
                    if item.get('subscriptionId') == subscription_id:
                        unpaid.append(invoice)
                        break

            return unpaid
        except Exception as e:
            logger.error(f"Failed to get unpaid invoices for subscription {subscription_id}: {e}")
            return []
