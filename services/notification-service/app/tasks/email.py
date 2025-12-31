"""
Email sending background tasks
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.celery_config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def send_email_task(self, email_id: str):
    """
    Background task to send a single email by ID.

    Args:
        email_id: UUID of the email record to send
    """
    try:
        logger.info(f"Starting email send task: email_id={email_id}, task_id={self.request.id}")

        result = asyncio.run(_send_email_workflow(email_id, self.request.id))

        logger.info(f"Email send task completed: email_id={email_id}, result={result}")
        return result

    except Exception as e:
        logger.error(f"Email send task failed: email_id={email_id}, error={str(e)}")

        # Update email status to failed
        asyncio.run(_mark_email_failed(email_id, str(e)))

        # Retry on transient errors
        if _is_transient_error(e):
            logger.info(f"Retrying email task due to transient error: {str(e)}")
            raise self.retry(exc=e)

        raise


@celery_app.task(bind=True)
def send_template_email_task(
    self,
    to_emails: List[str],
    template_name: str,
    template_variables: Dict[str, Any],
    cc_emails: Optional[List[str]] = None,
    bcc_emails: Optional[List[str]] = None,
    priority: str = "normal",
    tags: Optional[List[str]] = None,
    scheduled_at: Optional[str] = None
):
    """
    Background task to create and send a template email.

    Creates the email record in database, then sends it.
    """
    try:
        logger.info(
            f"Creating template email: template={template_name}, "
            f"recipients={len(to_emails)}, task_id={self.request.id}"
        )

        result = asyncio.run(_create_and_send_template_email(
            to_emails=to_emails,
            template_name=template_name,
            template_variables=template_variables,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            priority=priority,
            tags=tags,
            scheduled_at=scheduled_at,
            task_id=self.request.id
        ))

        logger.info(f"Template email task completed: result={result}")
        return result

    except Exception as e:
        logger.error(f"Template email task failed: error={str(e)}")
        raise


async def _send_email_workflow(email_id: str, task_id: str) -> Dict[str, Any]:
    """Actual email sending workflow"""
    # Create fresh instance per task to avoid asyncpg pool conflicts
    from app.services.email_service import EmailService
    from app.utils.smtp_client import SMTPClient, EmailMessage
    from app.utils.config import get_smtp_config

    email_service = EmailService()
    smtp_config = get_smtp_config()
    smtp_client = SMTPClient(smtp_config)

    # Get email record
    email = await email_service.get_email_by_id(email_id)
    if not email:
        raise ValueError(f"Email {email_id} not found")

    # Update status to sending
    await email_service.update_email_status(email_id, "sending", {
        "celery_task_id": task_id,
        "last_attempt_at": datetime.utcnow()
    })

    # Create SMTP message
    email_message = EmailMessage(
        to_emails=email["to_emails"],
        subject=email["subject"],
        html_content=email.get("html_content"),
        text_content=email.get("text_content"),
        from_email=email["from_email"],
        from_name=email.get("from_name"),
        reply_to=email.get("reply_to"),
        cc_emails=email.get("cc_emails", []),
        bcc_emails=email.get("bcc_emails", []),
        headers=email.get("headers", {})
    )

    # Send via SMTP
    result = await smtp_client.send_email(email_message)

    # Update status to sent
    await email_service.update_email_status(email_id, "sent", {
        "sent_at": datetime.utcnow(),
        "message_id": result.get("message_id"),
        "smtp_response": str(result),
        "attempts": email.get("attempts", 0) + 1
    })

    # Record event
    await email_service.record_email_event(email_id, "sent", {
        "message_id": result.get("message_id"),
        "smtp_result": result
    })

    return {
        "success": True,
        "email_id": email_id,
        "message_id": result.get("message_id"),
        "sent_at": datetime.utcnow().isoformat()
    }


async def _create_and_send_template_email(
    to_emails: List[str],
    template_name: str,
    template_variables: Dict[str, Any],
    cc_emails: Optional[List[str]],
    bcc_emails: Optional[List[str]],
    priority: str,
    tags: Optional[List[str]],
    scheduled_at: Optional[str],
    task_id: str
) -> Dict[str, Any]:
    """Create email record from template and send it"""
    # Create fresh instances per task to avoid asyncpg pool conflicts
    # across different event loops created by asyncio.run()
    from app.services.email_service import EmailService
    from app.services.template_service import TemplateService
    from app.utils.smtp_client import SMTPClient, EmailMessage
    from app.utils.config import get_smtp_config

    email_service = EmailService()
    template_service = TemplateService()
    smtp_config = get_smtp_config()
    smtp_client = SMTPClient(smtp_config)

    # Render template
    rendered = await template_service.render_template(template_name, template_variables)
    template_info = await template_service.get_template(template_name)

    if not template_info:
        raise ValueError(f"Template '{template_name}' not found")

    from_email = template_info.get("from_email") or smtp_config.default_from_email
    from_name = template_info.get("from_name") or smtp_config.default_from_name

    # Create email record
    email_id = await email_service.create_email(
        to_emails=to_emails,
        cc_emails=cc_emails,
        bcc_emails=bcc_emails,
        subject=rendered["subject"],
        html_content=rendered.get("html_content"),
        text_content=rendered.get("text_content"),
        from_email=from_email,
        from_name=from_name,
        template_name=template_name,
        template_variables=template_variables,
        priority=priority,
        tags=tags,
        status="sending",
        celery_task_id=task_id
    )

    try:
        # Create and send SMTP message
        email_message = EmailMessage(
            to_emails=to_emails,
            subject=rendered["subject"],
            html_content=rendered.get("html_content"),
            text_content=rendered.get("text_content"),
            from_email=from_email,
            from_name=from_name,
            cc_emails=cc_emails or [],
            bcc_emails=bcc_emails or [],
        )

        result = await smtp_client.send_email(email_message)

        # Update status to sent
        await email_service.update_email_status(email_id, "sent", {
            "sent_at": datetime.utcnow(),
            "message_id": result.get("message_id"),
            "smtp_response": str(result),
            "attempts": 1
        })

        # Record event
        await email_service.record_email_event(email_id, "sent", {
            "message_id": result.get("message_id")
        })

        return {
            "success": True,
            "email_id": email_id,
            "message_id": result.get("message_id"),
            "sent_at": datetime.utcnow().isoformat()
        }

    except Exception as e:
        # Mark as failed
        await email_service.update_email_status(email_id, "failed", {
            "error_message": str(e),
            "last_attempt_at": datetime.utcnow()
        })
        raise


async def _mark_email_failed(email_id: str, error: str):
    """Mark email as failed in database"""
    try:
        from app.services.email_service import EmailService
        email_service = EmailService()
        await email_service.update_email_status(email_id, "failed", {
            "error_message": error,
            "last_attempt_at": datetime.utcnow()
        })
    except Exception as e:
        logger.error(f"Failed to mark email as failed: {e}")


def _is_transient_error(error: Exception) -> bool:
    """Check if error is transient and worth retrying"""
    transient_indicators = [
        "connection refused",
        "timeout",
        "temporary",
        "try again",
        "too many connections",
        "rate limit",
        "connection reset",
        "server busy",
        "service unavailable",
        "421",  # SMTP temporary failure
        "450",  # SMTP mailbox unavailable
        "451",  # SMTP local error
        "452",  # SMTP insufficient storage
    ]
    error_str = str(error).lower()
    return any(indicator in error_str for indicator in transient_indicators)
