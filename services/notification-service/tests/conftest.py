"""
Pytest fixtures for notification service tests
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg database pool"""
    pool = AsyncMock()
    conn = AsyncMock()

    # Configure connection context manager
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

    return pool, conn


@pytest.fixture
def sample_email_data() -> Dict[str, Any]:
    """Sample email data for tests"""
    return {
        "id": "test-email-id-123",
        "to_emails": ["test@example.com"],
        "cc_emails": ["cc@example.com"],
        "bcc_emails": ["bcc@example.com"],
        "subject": "Test Subject",
        "html_content": "<h1>Test</h1>",
        "text_content": "Test",
        "from_email": "sender@example.com",
        "from_name": "Test Sender",
        "status": "pending",
        "priority": "normal",
        "template_name": None,
        "template_variables": {},
        "tags": ["test"],
        "headers": {},
        "created_at": "2025-01-01T00:00:00",
        "attempts": 0,
    }


@pytest.fixture
def sample_template_data() -> Dict[str, Any]:
    """Sample template metadata for tests"""
    return {
        "id": "test-template-id-123",
        "name": "welcome",
        "display_name": "Welcome Email",
        "description": "Welcome email for new users",
        "subject_template": "Welcome to {{ platform_name }}!",
        "from_email": "welcome@saasodoo.com",
        "from_name": "SaaSOdoo Team",
        "category": "account",
        "variables": ["first_name", "login_url"],
        "is_active": True,
    }


@pytest.fixture
def sample_bulk_batch_data() -> Dict[str, Any]:
    """Sample bulk batch data for tests"""
    return {
        "id": "test-batch-id-123",
        "template_name": "welcome",
        "subject": None,
        "total_recipients": 10,
        "successful_count": 0,
        "failed_count": 0,
        "pending_count": 10,
        "status": "pending",
        "metadata": {},
    }


@pytest.fixture
def mock_smtp_config():
    """Mock SMTP configuration"""
    config = MagicMock()
    config.smtp_host = "localhost"
    config.smtp_port = 1025
    config.smtp_use_tls = False
    config.smtp_timeout = 10
    config.smtp_username = None
    config.smtp_password = None
    config.default_from_email = "noreply@test.com"
    config.default_from_name = "Test Platform"
    config.max_emails_per_minute = 60
    config.max_emails_per_hour = 1000
    return config


@pytest.fixture
def mock_db_config():
    """Mock database configuration"""
    config = MagicMock()
    config.postgres_host = "localhost"
    config.postgres_port = 5432
    config.db_name = "test_communication"
    config.db_service_user = "test_user"
    config.db_service_password = "test_password"
    config.pool_size = 5
    config.pool_timeout = 30
    return config


@pytest.fixture
def mock_app_config():
    """Mock application configuration"""
    config = MagicMock()
    config.platform_name = "Test Platform"
    config.support_email = "support@test.com"
    config.support_url = "https://support.test.com"
    return config
