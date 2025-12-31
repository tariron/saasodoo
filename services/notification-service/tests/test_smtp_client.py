"""
Unit tests for SMTPClient
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestEmailMessage:
    """Test EmailMessage class"""

    def test_email_message_basic(self):
        """Test basic email message creation"""
        from app.utils.smtp_client import EmailMessage

        msg = EmailMessage(
            to_emails=["to@example.com"],
            subject="Test Subject",
            html_content="<h1>Test</h1>",
            text_content="Test"
        )

        assert msg.to_emails == ["to@example.com"]
        assert msg.subject == "Test Subject"
        assert msg.html_content == "<h1>Test</h1>"
        assert msg.text_content == "Test"
        assert msg.cc_emails == []
        assert msg.bcc_emails == []

    def test_email_message_with_cc_bcc(self):
        """Test email message with CC and BCC"""
        from app.utils.smtp_client import EmailMessage

        msg = EmailMessage(
            to_emails=["to@example.com"],
            cc_emails=["cc1@example.com", "cc2@example.com"],
            bcc_emails=["bcc@example.com"],
            subject="Test Subject",
            html_content="<h1>Test</h1>"
        )

        assert msg.to_emails == ["to@example.com"]
        assert msg.cc_emails == ["cc1@example.com", "cc2@example.com"]
        assert msg.bcc_emails == ["bcc@example.com"]

    def test_email_message_get_all_recipients(self):
        """Test getting all recipients (To + CC + BCC)"""
        from app.utils.smtp_client import EmailMessage

        msg = EmailMessage(
            to_emails=["to1@example.com", "to2@example.com"],
            cc_emails=["cc@example.com"],
            bcc_emails=["bcc1@example.com", "bcc2@example.com"],
            subject="Test",
            text_content="Test"
        )

        all_recipients = msg.get_all_recipients()

        assert len(all_recipients) == 5
        assert "to1@example.com" in all_recipients
        assert "to2@example.com" in all_recipients
        assert "cc@example.com" in all_recipients
        assert "bcc1@example.com" in all_recipients
        assert "bcc2@example.com" in all_recipients

    def test_email_message_string_to_emails_conversion(self):
        """Test that string to_emails is converted to list"""
        from app.utils.smtp_client import EmailMessage

        msg = EmailMessage(
            to_emails="single@example.com",
            subject="Test",
            text_content="Test"
        )

        assert isinstance(msg.to_emails, list)
        assert msg.to_emails == ["single@example.com"]

    def test_email_message_validation_no_recipients(self):
        """Test validation fails with no recipients"""
        from app.utils.smtp_client import EmailMessage

        with pytest.raises(ValueError) as excinfo:
            EmailMessage(
                to_emails=[],
                subject="Test",
                text_content="Test"
            )

        assert "recipient" in str(excinfo.value).lower()

    def test_email_message_validation_no_subject(self):
        """Test validation fails with no subject"""
        from app.utils.smtp_client import EmailMessage

        with pytest.raises(ValueError) as excinfo:
            EmailMessage(
                to_emails=["test@example.com"],
                subject="",
                text_content="Test"
            )

        assert "subject" in str(excinfo.value).lower()

    def test_email_message_validation_no_content(self):
        """Test validation fails with no content"""
        from app.utils.smtp_client import EmailMessage

        with pytest.raises(ValueError) as excinfo:
            EmailMessage(
                to_emails=["test@example.com"],
                subject="Test",
                html_content=None,
                text_content=None
            )

        assert "content" in str(excinfo.value).lower()


class TestSMTPClient:
    """Test SMTPClient class"""

    @pytest.fixture
    def smtp_client(self, mock_smtp_config):
        """Create SMTPClient with mocked config"""
        from app.utils.smtp_client import SMTPClient
        return SMTPClient(config=mock_smtp_config)

    def test_create_mime_message_with_cc(self, smtp_client):
        """Test MIME message includes CC header"""
        from app.utils.smtp_client import EmailMessage

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            cc_emails=["cc@example.com"],
            subject="Test",
            text_content="Test content"
        )

        mime_msg = smtp_client._create_mime_message(email_msg)

        assert mime_msg["To"] == "to@example.com"
        assert mime_msg["Cc"] == "cc@example.com"
        assert mime_msg["Subject"] == "Test"

    def test_create_mime_message_without_bcc_header(self, smtp_client):
        """Test MIME message does NOT include BCC header"""
        from app.utils.smtp_client import EmailMessage

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            bcc_emails=["bcc@example.com"],
            subject="Test",
            text_content="Test content"
        )

        mime_msg = smtp_client._create_mime_message(email_msg)

        # BCC should NOT be in headers (invisible to recipients)
        assert mime_msg.get("Bcc") is None

    def test_create_mime_message_alternative(self, smtp_client):
        """Test MIME message with both HTML and text"""
        from app.utils.smtp_client import EmailMessage

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            subject="Test",
            html_content="<h1>HTML</h1>",
            text_content="Text"
        )

        mime_msg = smtp_client._create_mime_message(email_msg)

        # Should be multipart/alternative
        assert mime_msg.get_content_type() == "multipart/alternative"

    def test_create_mime_message_reply_to(self, smtp_client):
        """Test MIME message with Reply-To header"""
        from app.utils.smtp_client import EmailMessage

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            subject="Test",
            text_content="Test",
            reply_to="reply@example.com"
        )

        mime_msg = smtp_client._create_mime_message(email_msg)

        assert mime_msg["Reply-To"] == "reply@example.com"

    def test_create_mime_message_custom_headers(self, smtp_client):
        """Test MIME message with custom headers"""
        from app.utils.smtp_client import EmailMessage

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            subject="Test",
            text_content="Test",
            headers={"X-Custom-Header": "custom-value"}
        )

        mime_msg = smtp_client._create_mime_message(email_msg)

        assert mime_msg["X-Custom-Header"] == "custom-value"

    @pytest.mark.asyncio
    async def test_send_email_rate_limit(self, smtp_client):
        """Test rate limiting prevents sending"""
        from app.utils.smtp_client import EmailMessage, SMTPError

        # Exhaust rate limit
        smtp_client._rate_limiter.minute_counter[datetime.utcnow().replace(second=0, microsecond=0)] = 1000

        email_msg = EmailMessage(
            to_emails=["to@example.com"],
            subject="Test",
            text_content="Test"
        )

        with pytest.raises(SMTPError) as excinfo:
            await smtp_client.send_email(email_msg)

        assert "rate limit" in str(excinfo.value).lower()


class TestRateLimiter:
    """Test RateLimiter class"""

    def test_can_send_under_limit(self):
        """Test can send when under rate limit"""
        from app.utils.smtp_client import RateLimiter

        limiter = RateLimiter(max_per_minute=60, max_per_hour=1000)

        assert limiter.can_send() is True

    def test_cannot_send_over_minute_limit(self):
        """Test cannot send when over minute limit"""
        from app.utils.smtp_client import RateLimiter

        limiter = RateLimiter(max_per_minute=2, max_per_hour=1000)

        # Record 2 sends
        limiter.record_send()
        limiter.record_send()

        assert limiter.can_send() is False

    def test_cannot_send_over_hour_limit(self):
        """Test cannot send when over hour limit"""
        from app.utils.smtp_client import RateLimiter

        limiter = RateLimiter(max_per_minute=1000, max_per_hour=2)

        # Record 2 sends
        limiter.record_send()
        limiter.record_send()

        assert limiter.can_send() is False

    def test_record_send_increments_counters(self):
        """Test recording send increments counters"""
        from app.utils.smtp_client import RateLimiter

        limiter = RateLimiter(max_per_minute=60, max_per_hour=1000)
        initial_minute = sum(limiter.minute_counter.values())
        initial_hour = sum(limiter.hour_counter.values())

        limiter.record_send()

        assert sum(limiter.minute_counter.values()) == initial_minute + 1
        assert sum(limiter.hour_counter.values()) == initial_hour + 1
