"""
User Management Tests
"""

import pytest
from app.services.user_service import UserService

class TestUserService:
    def test_user_service_exists(self):
        """Test that UserService class exists"""
        assert UserService is not None
    
    @pytest.mark.asyncio
    async def test_get_customer_stats_default(self):
        """Test getting default customer stats"""
        stats = await UserService.get_customer_stats("test-id")
        assert stats.total_instances == 0
        assert stats.active_instances == 0 