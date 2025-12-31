"""
Unit tests for API routes
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime


class TestEmailRoutes:
    """Test email API routes"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        # Mock the services before importing app
        with patch("app.routes.emails.get_email_service") as mock_email_svc:
            with patch("app.routes.emails.get_template_service") as mock_template_svc:
                with patch("app.routes.emails.get_smtp_client") as mock_smtp:
                    with patch("app.routes.emails.send_email_task") as mock_task:
                        with patch("app.routes.emails.send_template_email_task") as mock_template_task:
                            with patch("app.routes.emails.send_bulk_email_task") as mock_bulk_task:
                                from app.main import app
                                yield TestClient(app)

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_send_email_success(self):
        """Test POST /api/v1/emails/send"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_smtp_client") as mock_get_smtp:
                # Setup mocks
                mock_service = MagicMock()
                mock_service.create_email = AsyncMock(return_value="email-123")
                mock_service.update_email_status = AsyncMock()
                mock_get_email.return_value = mock_service

                mock_smtp = MagicMock()
                mock_smtp.send_email = AsyncMock(return_value={
                    "message_id": "msg-123",
                    "sent_at": datetime.utcnow().isoformat(),
                    "attempts": 1
                })
                mock_get_smtp.return_value = mock_smtp

                from app.main import app
                client = TestClient(app)

                response = client.post("/api/v1/emails/send", json={
                    "to_emails": ["test@example.com"],
                    "subject": "Test Email",
                    "html_content": "<h1>Test</h1>",
                    "text_content": "Test"
                })

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["email_id"] == "email-123"

    def test_send_email_with_cc_bcc(self):
        """Test POST /api/v1/emails/send with CC and BCC"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_smtp_client") as mock_get_smtp:
                # Setup mocks
                mock_service = MagicMock()
                mock_service.create_email = AsyncMock(return_value="email-123")
                mock_service.update_email_status = AsyncMock()
                mock_get_email.return_value = mock_service

                mock_smtp = MagicMock()
                mock_smtp.send_email = AsyncMock(return_value={
                    "message_id": "msg-123",
                    "sent_at": datetime.utcnow().isoformat(),
                    "attempts": 1
                })
                mock_get_smtp.return_value = mock_smtp

                from app.main import app
                client = TestClient(app)

                response = client.post("/api/v1/emails/send", json={
                    "to_emails": ["to@example.com"],
                    "cc_emails": ["cc@example.com"],
                    "bcc_emails": ["bcc@example.com"],
                    "subject": "Test Email",
                    "html_content": "<h1>Test</h1>"
                })

                assert response.status_code == 200
                # Verify create_email was called with CC/BCC
                call_kwargs = mock_service.create_email.call_args.kwargs
                assert call_kwargs.get("cc_emails") == ["cc@example.com"]
                assert call_kwargs.get("bcc_emails") == ["bcc@example.com"]

    def test_send_template_email_async(self):
        """Test POST /api/v1/emails/send-template (async mode)"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_template_service") as mock_get_template:
                with patch("app.routes.emails.send_template_email_task") as mock_task:
                    # Setup mocks
                    mock_service = MagicMock()
                    mock_service.create_email = AsyncMock(return_value="email-123")
                    mock_service.update_email_status = AsyncMock()
                    mock_get_email.return_value = mock_service

                    mock_template_svc = MagicMock()
                    mock_template_svc.get_template = AsyncMock(return_value={
                        "name": "welcome",
                        "subject_template": "Welcome!",
                        "from_email": None,
                        "from_name": None
                    })
                    mock_get_template.return_value = mock_template_svc

                    mock_celery_task = MagicMock()
                    mock_celery_task.id = "celery-task-123"
                    mock_task.delay.return_value = mock_celery_task

                    from app.main import app
                    client = TestClient(app)

                    response = client.post("/api/v1/emails/send-template", json={
                        "to_emails": ["test@example.com"],
                        "template_name": "welcome",
                        "template_variables": {"first_name": "Test"},
                        "async_send": True
                    })

                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["status"] == "queued"
                    assert data["celery_task_id"] == "celery-task-123"

    def test_send_template_email_sync(self):
        """Test POST /api/v1/emails/send-template (sync mode)"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_template_service") as mock_get_template:
                with patch("app.routes.emails.get_smtp_client") as mock_get_smtp:
                    # Setup mocks
                    mock_service = MagicMock()
                    mock_service.create_email = AsyncMock(return_value="email-123")
                    mock_service.update_email_status = AsyncMock()
                    mock_get_email.return_value = mock_service

                    mock_template_svc = MagicMock()
                    mock_template_svc.get_template = AsyncMock(return_value={
                        "name": "welcome",
                        "subject_template": "Welcome!",
                        "from_email": None,
                        "from_name": None
                    })
                    mock_template_svc.render_template = AsyncMock(return_value={
                        "subject": "Welcome!",
                        "html_content": "<h1>Welcome</h1>",
                        "text_content": "Welcome"
                    })
                    mock_get_template.return_value = mock_template_svc

                    mock_smtp = MagicMock()
                    mock_smtp.send_email = AsyncMock(return_value={
                        "message_id": "msg-123",
                        "sent_at": datetime.utcnow().isoformat(),
                        "attempts": 1
                    })
                    mock_get_smtp.return_value = mock_smtp

                    from app.main import app
                    client = TestClient(app)

                    response = client.post("/api/v1/emails/send-template", json={
                        "to_emails": ["test@example.com"],
                        "template_name": "welcome",
                        "template_variables": {"first_name": "Test"},
                        "async_send": False
                    })

                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert "sent_at" in data

    def test_send_template_email_not_found(self):
        """Test POST /api/v1/emails/send-template with nonexistent template"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_template_service") as mock_get_template:
                mock_service = MagicMock()
                mock_get_email.return_value = mock_service

                mock_template_svc = MagicMock()
                mock_template_svc.get_template = AsyncMock(return_value=None)
                mock_get_template.return_value = mock_template_svc

                from app.main import app
                client = TestClient(app)

                response = client.post("/api/v1/emails/send-template", json={
                    "to_emails": ["test@example.com"],
                    "template_name": "nonexistent"
                })

                assert response.status_code == 404

    def test_bulk_email_success(self):
        """Test POST /api/v1/emails/bulk"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_template_service") as mock_get_template:
                with patch("app.routes.emails.send_bulk_email_task") as mock_task:
                    # Setup mocks
                    mock_service = MagicMock()
                    mock_service.create_bulk_batch = AsyncMock(return_value="batch-123")
                    mock_service.update_bulk_batch_status = AsyncMock()
                    mock_get_email.return_value = mock_service

                    mock_template_svc = MagicMock()
                    mock_template_svc.get_template = AsyncMock(return_value={"name": "welcome"})
                    mock_get_template.return_value = mock_template_svc

                    mock_celery_task = MagicMock()
                    mock_celery_task.id = "celery-bulk-task-123"
                    mock_task.delay.return_value = mock_celery_task

                    from app.main import app
                    client = TestClient(app)

                    response = client.post("/api/v1/emails/bulk", json={
                        "template_name": "welcome",
                        "recipients": [
                            {"email": "user1@example.com", "variables": {"first_name": "User1"}},
                            {"email": "user2@example.com", "variables": {"first_name": "User2"}}
                        ]
                    })

                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert data["batch_id"] == "batch-123"
                    assert data["total_recipients"] == 2
                    assert data["status"] == "queued"

    def test_bulk_email_no_template_no_subject(self):
        """Test POST /api/v1/emails/bulk without template or subject"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.post("/api/v1/emails/bulk", json={
                "recipients": [
                    {"email": "user@example.com", "variables": {}}
                ]
            })

            assert response.status_code == 400

    def test_get_bulk_status(self):
        """Test GET /api/v1/emails/bulk/{batch_id}"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_service.get_bulk_batch = AsyncMock(return_value={
                "id": "batch-123",
                "status": "processing",
                "total_recipients": 100,
                "successful_count": 50,
                "failed_count": 5,
                "pending_count": 45,
                "started_at": datetime.utcnow(),
                "completed_at": None,
                "celery_task_id": "task-123"
            })
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/emails/bulk/batch-123")

            assert response.status_code == 200
            data = response.json()
            assert data["batch_id"] == "batch-123"
            assert data["status"] == "processing"
            assert data["successful_count"] == 50

    def test_get_bulk_status_not_found(self):
        """Test GET /api/v1/emails/bulk/{batch_id} when not found"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_service.get_bulk_batch = AsyncMock(return_value=None)
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/emails/bulk/nonexistent")

            assert response.status_code == 404

    def test_get_email_history(self):
        """Test GET /api/v1/emails/history"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_service.get_email_history = AsyncMock(return_value={
                "emails": [
                    {"id": "1", "subject": "Test 1", "status": "sent"},
                    {"id": "2", "subject": "Test 2", "status": "sent"}
                ],
                "total": 2,
                "page": 1,
                "per_page": 20,
                "pages": 1
            })
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/emails/history")

            assert response.status_code == 200
            data = response.json()
            assert "emails" in data
            assert data["total"] == 2

    def test_get_email_details(self):
        """Test GET /api/v1/emails/{email_id}"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_service.get_email_by_id = AsyncMock(return_value={
                "id": "email-123",
                "to_emails": ["test@example.com"],
                "subject": "Test",
                "status": "sent"
            })
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/emails/email-123")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "email-123"

    def test_resend_email_success(self):
        """Test POST /api/v1/emails/{email_id}/resend"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            with patch("app.routes.emails.get_smtp_client") as mock_get_smtp:
                mock_service = MagicMock()
                mock_service.get_email_by_id = AsyncMock(return_value={
                    "id": "email-123",
                    "to_emails": ["test@example.com"],
                    "cc_emails": None,
                    "bcc_emails": None,
                    "subject": "Test",
                    "html_content": "<h1>Test</h1>",
                    "text_content": "Test",
                    "from_email": "sender@example.com",
                    "from_name": "Sender",
                    "status": "failed",
                    "attempts": 1
                })
                mock_service.update_email_status = AsyncMock()
                mock_get_email.return_value = mock_service

                mock_smtp = MagicMock()
                mock_smtp.send_email = AsyncMock(return_value={
                    "message_id": "msg-123",
                    "sent_at": datetime.utcnow().isoformat()
                })
                mock_get_smtp.return_value = mock_smtp

                from app.main import app
                client = TestClient(app)

                response = client.post("/api/v1/emails/email-123/resend")

                assert response.status_code == 200
                data = response.json()
                assert data["success"] is True
                assert data["attempts"] == 2

    def test_resend_email_not_failed(self):
        """Test POST /api/v1/emails/{email_id}/resend when email not failed"""
        with patch("app.routes.emails.get_email_service") as mock_get_email:
            mock_service = MagicMock()
            mock_service.get_email_by_id = AsyncMock(return_value={
                "id": "email-123",
                "status": "sent",  # Already sent
                "attempts": 1
            })
            mock_get_email.return_value = mock_service

            from app.main import app
            client = TestClient(app)

            response = client.post("/api/v1/emails/email-123/resend")

            assert response.status_code == 400

    def test_test_smtp_connection(self):
        """Test GET /api/v1/emails/test/connection"""
        with patch("app.routes.emails.get_smtp_client") as mock_get_smtp:
            mock_smtp = MagicMock()
            mock_smtp.test_connection = AsyncMock(return_value={
                "success": True,
                "connection_time": 0.05,
                "host": "localhost",
                "port": 1025
            })
            mock_get_smtp.return_value = mock_smtp

            from app.main import app
            client = TestClient(app)

            response = client.get("/api/v1/emails/test/connection")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
