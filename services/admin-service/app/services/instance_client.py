import httpx
from typing import Dict, Any
from app.config import settings


class InstanceServiceClient:
    """HTTP client for instance-service"""

    def __init__(self):
        self.base_url = settings.instance_service_url
        self.timeout = 10.0

    async def get_instance_stats(self) -> Dict[str, Any]:
        """Get instance statistics from /admin/instance-stats"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/admin/instance-stats")
                response.raise_for_status()
                data = response.json()
                # Returns: status_counts, total_instances, healthy_instances, failed_instances
                return {
                    "active": data.get("healthy_instances", 0),
                    "total": data.get("total_instances", 0),
                    "status_counts": data.get("status_counts", {})
                }
            except httpx.HTTPError as e:
                print(f"Error fetching instance stats: {e}")
                return {"active": 0, "total": 0, "status_counts": {}}

    async def get_all_instances(self) -> list[Dict[str, Any]]:
        """Get all instances from /admin/all-instances endpoint"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/admin/all-instances")
                response.raise_for_status()
                data = response.json()
                return data.get("instances", [])
            except httpx.HTTPError as e:
                print(f"Error fetching instances: {e}")
                return []

    async def health_check(self) -> str:
        """Check if instance-service is healthy"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return "healthy"
                return "unhealthy"
            except Exception:
                return "unreachable"


instance_service_client = InstanceServiceClient()
