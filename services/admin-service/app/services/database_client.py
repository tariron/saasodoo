import httpx
from app.config import settings


class DatabaseServiceClient:
    """HTTP client for database-service"""

    def __init__(self):
        self.base_url = settings.database_service_url
        self.timeout = 10.0

    async def health_check(self) -> str:
        """Check if database-service is healthy"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return "healthy"
                return "unhealthy"
            except Exception:
                return "unreachable"


database_service_client = DatabaseServiceClient()
