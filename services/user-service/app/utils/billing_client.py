"""
Billing Service HTTP Client
Client for communicating with the billing service API from user service

Connection pooling implementation based on httpx best practices:
- Single shared AsyncClient initialized at app startup
- Proper limits to prevent connection exhaustion
- Pool timeout for fast failure under load
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
    """
    HTTP client for billing service operations.

    Uses a shared AsyncClient with connection pooling for efficient
    resource utilization under high concurrency.

    Lifecycle:
        - Call start() during app startup (FastAPI lifespan)
        - Call stop() during app shutdown
        - If not initialized, falls back to per-request client
    """

    # Connection pool settings (per worker)
    MAX_CONNECTIONS = 100         # Total concurrent connections to billing-service
    MAX_KEEPALIVE = 20            # Connections kept alive for reuse
    KEEPALIVE_EXPIRY = 5.0        # Seconds before idle connection is closed (reduced from 30s to avoid stale connections)

    # Timeout settings
    CONNECT_TIMEOUT = 5.0         # Time to establish connection
    READ_TIMEOUT = 30.0           # Time to receive response
    WRITE_TIMEOUT = 5.0           # Time to send request
    POOL_TIMEOUT = 30.0           # Time to wait for connection from pool

    def __init__(self, base_url: str = None):
        self.base_url = (base_url or os.getenv('BILLING_SERVICE_URL', 'http://billing-service:8004')).rstrip('/')
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """
        Initialize the shared HTTP client.
        Call this during FastAPI app startup via lifespan.
        """
        if self._client is not None:
            logger.warning("BillingServiceClient already started")
            return

        # Configure connection limits
        limits = httpx.Limits(
            max_connections=self.MAX_CONNECTIONS,
            max_keepalive_connections=self.MAX_KEEPALIVE,
            keepalive_expiry=self.KEEPALIVE_EXPIRY
        )

        # Configure timeouts with pool timeout for backpressure
        timeout = httpx.Timeout(
            connect=self.CONNECT_TIMEOUT,
            read=self.READ_TIMEOUT,
            write=self.WRITE_TIMEOUT,
            pool=self.POOL_TIMEOUT
        )

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            limits=limits,
            timeout=timeout
        )

        logger.info(
            f"BillingServiceClient started: base_url={self.base_url}, "
            f"max_connections={self.MAX_CONNECTIONS}, pool_timeout={self.POOL_TIMEOUT}s"
        )

    async def stop(self):
        """
        Close the HTTP client and release resources.
        Call this during FastAPI app shutdown via lifespan.
        """
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("BillingServiceClient stopped")

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Make HTTP request to billing service with connection pooling"""

        # Handle JSON data with UUID objects
        if 'json' in kwargs:
            kwargs['content'] = json.dumps(kwargs.pop('json'), cls=UUIDJSONEncoder)
            kwargs['headers'] = kwargs.get('headers', {})
            kwargs['headers']['Content-Type'] = 'application/json'

        try:
            # Use shared client if initialized (preferred)
            if self._client:
                response = await self._client.request(method, endpoint, **kwargs)
            else:
                # Fallback: per-request client (not initialized or during startup)
                logger.warning("BillingServiceClient not initialized, using per-request client")
                url = f"{self.base_url}{endpoint}"
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.request(method, url, **kwargs)

            response.raise_for_status()

            # Handle empty responses
            if response.status_code == 204 or not response.content:
                return None

            return response.json()

        except httpx.PoolTimeout:
            logger.error(f"Connection pool exhausted calling {endpoint} - system under heavy load")
            raise Exception("Service temporarily unavailable - connection pool exhausted")
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
