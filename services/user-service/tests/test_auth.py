"""
Authentication Tests
"""

import pytest
from app.services.auth_service import AuthService


class TestAuthService:
    @pytest.mark.asyncio
    async def test_hash_password(self):
        password = "test123"
        hashed = await AuthService.hash_password(password)
        assert hashed != password
        assert await AuthService.verify_password(password, hashed)

    def test_generate_session_token(self):
        token = AuthService.generate_session_token()
        assert len(token) > 20
