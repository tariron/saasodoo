"""
Unit tests for EmailService
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import json


class TestEmailService:
    """Test EmailService class"""

    @pytest.fixture
    def email_service(self, mock_db_config):
        """Create EmailService instance with mocked config"""
        with patch("app.services.email_service.get_db_config", return_value=mock_db_config):
            from app.services.email_service import EmailService
            service = EmailService()
            return service

    @pytest.mark.asyncio
    async def test_create_email_success(self, email_service, mock_db_pool):
        """Test successful email creation"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.execute = AsyncMock()

        email_id = await email_service.create_email(
            to_emails=["test@example.com"],
            subject="Test Subject",
            html_content="<h1>Test</h1>",
            text_content="Test",
            status="pending"
        )

        # Verify email ID is returned
        assert email_id is not None
        assert isinstance(email_id, str)

        # Verify database was called
        conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_create_email_with_cc_bcc(self, email_service, mock_db_pool):
        """Test email creation with CC and BCC"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.execute = AsyncMock()

        email_id = await email_service.create_email(
            to_emails=["to@example.com"],
            cc_emails=["cc@example.com"],
            bcc_emails=["bcc@example.com"],
            subject="Test Subject",
            html_content="<h1>Test</h1>",
            status="pending"
        )

        assert email_id is not None
        # Verify execute was called (CC/BCC should be JSON serialized)
        call_args = conn.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_get_email_by_id_found(self, email_service, mock_db_pool, sample_email_data):
        """Test getting email by ID when found"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool

        # Mock fetchrow to return sample data
        mock_row = MagicMock()
        mock_row.__iter__ = lambda self: iter(sample_email_data.items())
        mock_row.keys = lambda: sample_email_data.keys()
        conn.fetchrow = AsyncMock(return_value=mock_row)

        # Convert to dict behavior
        def dict_side_effect():
            return sample_email_data.copy()
        type(mock_row).__iter__ = lambda s: iter(sample_email_data.items())

        result = await email_service.get_email_by_id("test-email-id-123")

        assert result is not None
        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_email_by_id_not_found(self, email_service, mock_db_pool):
        """Test getting email by ID when not found"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.fetchrow = AsyncMock(return_value=None)

        result = await email_service.get_email_by_id("nonexistent-id")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_email_status(self, email_service, mock_db_pool):
        """Test updating email status"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.execute = AsyncMock()

        await email_service.update_email_status(
            email_id="test-email-id-123",
            status="sent",
            update_data={
                "sent_at": datetime.utcnow(),
                "message_id": "msg-123",
                "attempts": 1
            }
        )

        # Verify update was called
        conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_create_bulk_batch(self, email_service, mock_db_pool):
        """Test creating bulk email batch"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.execute = AsyncMock()

        batch_id = await email_service.create_bulk_batch(
            template_name="welcome",
            subject=None,
            total_recipients=100,
            metadata={"campaign": "test"}
        )

        assert batch_id is not None
        assert isinstance(batch_id, str)
        conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_update_bulk_batch_progress(self, email_service, mock_db_pool):
        """Test updating bulk batch progress"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        conn.execute = AsyncMock()

        await email_service.update_bulk_batch_progress(
            batch_id="test-batch-id",
            successful=50,
            failed=5
        )

        conn.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_email_history_pagination(self, email_service, mock_db_pool):
        """Test email history with pagination"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool

        # Mock count query
        conn.fetchval = AsyncMock(return_value=100)

        # Mock fetch results
        mock_rows = [
            {"id": "1", "to_emails": '["a@test.com"]', "subject": "Test 1", "status": "sent"},
            {"id": "2", "to_emails": '["b@test.com"]', "subject": "Test 2", "status": "sent"},
        ]
        conn.fetch = AsyncMock(return_value=[MagicMock(**{**row, 'get': lambda k, d=None, r=row: r.get(k, d)}) for row in mock_rows])

        result = await email_service.get_email_history(page=1, per_page=20)

        assert "emails" in result
        assert "total" in result
        assert "page" in result
        assert result["page"] == 1

    @pytest.mark.asyncio
    async def test_close_pool(self, email_service, mock_db_pool):
        """Test closing database pool"""
        pool, conn = mock_db_pool
        email_service._db_pool = pool
        pool.close = AsyncMock()

        await email_service.close()

        pool.close.assert_called_once()
        assert email_service._db_pool is None
