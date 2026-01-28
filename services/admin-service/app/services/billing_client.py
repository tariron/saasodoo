import httpx
from app.config import settings


class BillingServiceClient:
    """HTTP client for billing-service"""

    def __init__(self):
        self.base_url = settings.billing_service_url
        self.timeout = 10.0

    async def get_mrr(self) -> float:
        """Get Monthly Recurring Revenue - TODO: implement aggregation endpoint"""
        # Note: billing-service doesn't have an MRR aggregation endpoint yet
        # Would need to iterate through subscriptions and sum up monthly amounts
        return 0.0  # Placeholder until endpoint is created

    async def health_check(self) -> str:
        """Check if billing-service is healthy"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return "healthy"
                return "unhealthy"
            except Exception:
                return "unreachable"


billing_service_client = BillingServiceClient()
