import httpx
from typing import List, Dict, Any
from app.config import settings


class UserServiceClient:
    """HTTP client for user-service"""

    def __init__(self):
        self.base_url = settings.user_service_url
        self.timeout = 10.0

    async def get_customer_by_id(self, customer_id: str) -> Dict[str, Any]:
        """Get single customer by ID using /internal/{customer_id} endpoint"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/internal/{customer_id}")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                print(f"Error fetching customer {customer_id}: {e}")
                return {}

    async def health_check(self) -> str:
        """Check if user-service is healthy"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return "healthy"
                return "unhealthy"
            except Exception:
                return "unreachable"


user_service_client = UserServiceClient()
