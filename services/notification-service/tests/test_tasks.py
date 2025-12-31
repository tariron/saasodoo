"""
Unit tests for Celery tasks
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime


class TestEmailTasks:
    """Test email Celery tasks"""

    @pytest.mark.asyncio
    async def test_send_email_workflow_success(self, sample_email_data):
        """Test _send_email_workflow success path"""
        with patch("app.tasks.email.get_email_service") as mock_get_service:
            with patch("app.tasks.email.SMTPClient") as mock_smtp_class:
                with patch("app.tasks.email.get_smtp_config") as mock_get_config:
                    # Setup mocks
                    mock_service = MagicMock()
                    mock_service.get_email_by_id = AsyncMock(return_value=sample_email_data)
                    mock_service.update_email_status = AsyncMock()
                    mock_get_service.return_value = mock_service

                    mock_smtp = MagicMock()
                    mock_smtp.send_email = AsyncMock(return_value={
                        "message_id": "test-msg-id",
                        "sent_at": datetime.utcnow().isoformat()
                    })
                    mock_smtp_class.return_value = mock_smtp

                    mock_config = MagicMock()
                    mock_get_config.return_value = mock_config

                    from app.tasks.email import _send_email_workflow
                    result = await _send_email_workflow("test-email-id", "test-task-id")

                    assert result["status"] == "sent"
                    mock_service.update_email_status.assert_called()

    @pytest.mark.asyncio
    async def test_send_email_workflow_not_found(self):
        """Test _send_email_workflow when email not found"""
        with patch("app.tasks.email.get_email_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_email_by_id = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            from app.tasks.email import _send_email_workflow

            with pytest.raises(ValueError) as excinfo:
                await _send_email_workflow("nonexistent-id", "test-task-id")

            assert "not found" in str(excinfo.value).lower()

    @pytest.mark.asyncio
    async def test_send_template_email_workflow_success(self):
        """Test _send_template_email_workflow success path"""
        with patch("app.tasks.email.get_email_service") as mock_get_service:
            with patch("app.tasks.email.get_template_service") as mock_get_template:
                with patch("app.tasks.email.SMTPClient") as mock_smtp_class:
                    with patch("app.tasks.email.get_smtp_config") as mock_get_config:
                        # Setup mocks
                        mock_service = MagicMock()
                        mock_service.update_email_status = AsyncMock()
                        mock_get_service.return_value = mock_service

                        mock_template = MagicMock()
                        mock_template.render_template = AsyncMock(return_value={
                            "subject": "Test Subject",
                            "html_content": "<h1>Test</h1>",
                            "text_content": "Test"
                        })
                        mock_get_template.return_value = mock_template

                        mock_smtp = MagicMock()
                        mock_smtp.send_email = AsyncMock(return_value={
                            "message_id": "test-msg-id",
                            "sent_at": datetime.utcnow().isoformat()
                        })
                        mock_smtp_class.return_value = mock_smtp

                        mock_config = MagicMock()
                        mock_get_config.return_value = mock_config

                        from app.tasks.email import _send_template_email_workflow
                        result = await _send_template_email_workflow(
                            email_id="test-email-id",
                            template_name="welcome",
                            to_emails=["test@example.com"],
                            cc_emails=None,
                            bcc_emails=None,
                            variables={"first_name": "Test"},
                            subject_override=None,
                            from_email=None,
                            from_name=None,
                            task_id="test-task-id"
                        )

                        assert result["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_template_email_workflow_with_cc_bcc(self):
        """Test _send_template_email_workflow with CC and BCC"""
        with patch("app.tasks.email.get_email_service") as mock_get_service:
            with patch("app.tasks.email.get_template_service") as mock_get_template:
                with patch("app.tasks.email.SMTPClient") as mock_smtp_class:
                    with patch("app.tasks.email.get_smtp_config") as mock_get_config:
                        # Setup mocks
                        mock_service = MagicMock()
                        mock_service.update_email_status = AsyncMock()
                        mock_get_service.return_value = mock_service

                        mock_template = MagicMock()
                        mock_template.render_template = AsyncMock(return_value={
                            "subject": "Test Subject",
                            "html_content": "<h1>Test</h1>",
                            "text_content": "Test"
                        })
                        mock_get_template.return_value = mock_template

                        mock_smtp = MagicMock()
                        mock_smtp.send_email = AsyncMock(return_value={
                            "message_id": "test-msg-id",
                            "sent_at": datetime.utcnow().isoformat()
                        })
                        mock_smtp_class.return_value = mock_smtp

                        mock_config = MagicMock()
                        mock_get_config.return_value = mock_config

                        from app.tasks.email import _send_template_email_workflow
                        result = await _send_template_email_workflow(
                            email_id="test-email-id",
                            template_name="welcome",
                            to_emails=["to@example.com"],
                            cc_emails=["cc@example.com"],
                            bcc_emails=["bcc@example.com"],
                            variables={"first_name": "Test"},
                            subject_override=None,
                            from_email=None,
                            from_name=None,
                            task_id="test-task-id"
                        )

                        # Verify EmailMessage was created with CC/BCC
                        call_args = mock_smtp.send_email.call_args
                        email_msg = call_args[0][0]
                        assert email_msg.cc_emails == ["cc@example.com"]
                        assert email_msg.bcc_emails == ["bcc@example.com"]


class TestBulkTasks:
    """Test bulk email Celery tasks"""

    @pytest.mark.asyncio
    async def test_process_bulk_batch_success(self):
        """Test _process_bulk_batch success path"""
        with patch("app.tasks.bulk.get_email_service") as mock_get_service:
            with patch("app.tasks.bulk.get_template_service") as mock_get_template:
                with patch("app.tasks.bulk.SMTPClient") as mock_smtp_class:
                    with patch("app.tasks.bulk.get_smtp_config") as mock_get_config:
                        # Setup mocks
                        mock_service = MagicMock()
                        mock_service.update_bulk_batch_status = AsyncMock()
                        mock_service.create_email = AsyncMock(return_value="email-id-123")
                        mock_service.update_email_status = AsyncMock()
                        mock_service.update_bulk_batch_progress = AsyncMock()
                        mock_get_service.return_value = mock_service

                        mock_template = MagicMock()
                        mock_template.get_template = AsyncMock(return_value={
                            "name": "welcome",
                            "subject_template": "Welcome!",
                            "from_email": None,
                            "from_name": None
                        })
                        mock_template.render_template = AsyncMock(return_value={
                            "subject": "Welcome!",
                            "html_content": "<h1>Welcome</h1>",
                            "text_content": "Welcome"
                        })
                        mock_get_template.return_value = mock_template

                        mock_smtp = MagicMock()
                        mock_smtp.send_email = AsyncMock(return_value={
                            "message_id": "msg-id",
                            "sent_at": datetime.utcnow().isoformat()
                        })
                        mock_smtp_class.return_value = mock_smtp

                        mock_config = MagicMock()
                        mock_config.default_from_email = "noreply@test.com"
                        mock_config.default_from_name = "Test"
                        mock_get_config.return_value = mock_config

                        from app.tasks.bulk import _process_bulk_batch
                        result = await _process_bulk_batch(
                            batch_id="batch-123",
                            template_name="welcome",
                            subject=None,
                            html_content=None,
                            text_content=None,
                            recipients=[
                                {"email": "user1@example.com", "variables": {"first_name": "User1"}},
                                {"email": "user2@example.com", "variables": {"first_name": "User2"}}
                            ],
                            from_email=None,
                            from_name=None,
                            batch_size=10,
                            delay_between_batches=0.1,
                            tags=["test"],
                            task_id="task-123"
                        )

                        assert result["status"] == "completed"
                        assert result["total"] == 2
                        assert result["successful"] == 2
                        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_process_bulk_batch_partial_failure(self):
        """Test _process_bulk_batch with some failures"""
        with patch("app.tasks.bulk.get_email_service") as mock_get_service:
            with patch("app.tasks.bulk.get_template_service") as mock_get_template:
                with patch("app.tasks.bulk.SMTPClient") as mock_smtp_class:
                    with patch("app.tasks.bulk.get_smtp_config") as mock_get_config:
                        # Setup mocks
                        mock_service = MagicMock()
                        mock_service.update_bulk_batch_status = AsyncMock()
                        mock_service.create_email = AsyncMock(return_value="email-id-123")
                        mock_service.update_email_status = AsyncMock()
                        mock_service.update_bulk_batch_progress = AsyncMock()
                        mock_get_service.return_value = mock_service

                        mock_template = MagicMock()
                        mock_template.get_template = AsyncMock(return_value={
                            "name": "welcome",
                            "subject_template": "Welcome!",
                            "from_email": None,
                            "from_name": None
                        })
                        mock_template.render_template = AsyncMock(return_value={
                            "subject": "Welcome!",
                            "html_content": "<h1>Welcome</h1>",
                            "text_content": "Welcome"
                        })
                        mock_get_template.return_value = mock_template

                        # Make SMTP fail on second call
                        mock_smtp = MagicMock()
                        mock_smtp.send_email = AsyncMock(side_effect=[
                            {"message_id": "msg-1", "sent_at": datetime.utcnow().isoformat()},
                            Exception("SMTP Error")
                        ])
                        mock_smtp_class.return_value = mock_smtp

                        mock_config = MagicMock()
                        mock_config.default_from_email = "noreply@test.com"
                        mock_config.default_from_name = "Test"
                        mock_get_config.return_value = mock_config

                        from app.tasks.bulk import _process_bulk_batch
                        result = await _process_bulk_batch(
                            batch_id="batch-123",
                            template_name="welcome",
                            subject=None,
                            html_content=None,
                            text_content=None,
                            recipients=[
                                {"email": "user1@example.com", "variables": {}},
                                {"email": "user2@example.com", "variables": {}}
                            ],
                            from_email=None,
                            from_name=None,
                            batch_size=10,
                            delay_between_batches=0.1,
                            tags=None,
                            task_id="task-123"
                        )

                        assert result["status"] == "completed"
                        assert result["successful"] == 1
                        assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_process_bulk_batch_direct_content(self):
        """Test _process_bulk_batch with direct content (no template)"""
        with patch("app.tasks.bulk.get_email_service") as mock_get_service:
            with patch("app.tasks.bulk.get_template_service") as mock_get_template:
                with patch("app.tasks.bulk.SMTPClient") as mock_smtp_class:
                    with patch("app.tasks.bulk.get_smtp_config") as mock_get_config:
                        # Setup mocks
                        mock_service = MagicMock()
                        mock_service.update_bulk_batch_status = AsyncMock()
                        mock_service.create_email = AsyncMock(return_value="email-id-123")
                        mock_service.update_email_status = AsyncMock()
                        mock_service.update_bulk_batch_progress = AsyncMock()
                        mock_get_service.return_value = mock_service

                        mock_template = MagicMock()
                        mock_template.get_template = AsyncMock(return_value=None)
                        mock_get_template.return_value = mock_template

                        mock_smtp = MagicMock()
                        mock_smtp.send_email = AsyncMock(return_value={
                            "message_id": "msg-id",
                            "sent_at": datetime.utcnow().isoformat()
                        })
                        mock_smtp_class.return_value = mock_smtp

                        mock_config = MagicMock()
                        mock_config.default_from_email = "noreply@test.com"
                        mock_config.default_from_name = "Test"
                        mock_get_config.return_value = mock_config

                        from app.tasks.bulk import _process_bulk_batch
                        result = await _process_bulk_batch(
                            batch_id="batch-123",
                            template_name=None,
                            subject="Hello {{ name }}!",
                            html_content="<h1>Hello {{ name }}!</h1>",
                            text_content="Hello {{ name }}!",
                            recipients=[
                                {"email": "user@example.com", "variables": {"name": "User"}}
                            ],
                            from_email=None,
                            from_name=None,
                            batch_size=10,
                            delay_between_batches=0.1,
                            tags=None,
                            task_id="task-123"
                        )

                        assert result["status"] == "completed"
                        assert result["successful"] == 1
