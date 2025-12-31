"""
Bulk email background tasks
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.celery_config import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def send_bulk_email_task(
    self,
    batch_id: str,
    template_name: Optional[str],
    subject: Optional[str],
    html_content: Optional[str],
    text_content: Optional[str],
    recipients: List[Dict[str, Any]],
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    batch_size: int = 10,
    delay_between_batches: float = 1.0,
    tags: Optional[List[str]] = None
):
    """
    Process bulk email batch.

    Args:
        batch_id: UUID of the bulk batch record
        template_name: Template to use (if template-based)
        subject: Subject line (if direct content)
        html_content: HTML content (if direct content)
        text_content: Text content (if direct content)
        recipients: List of {"email": "...", "variables": {...}}
        from_email: Override sender email
        from_name: Override sender name
        batch_size: Number of emails per sub-batch
        delay_between_batches: Seconds between batches
        tags: Tags for all emails
    """
    try:
        logger.info(
            f"Starting bulk email task: batch_id={batch_id}, "
            f"recipients={len(recipients)}, task_id={self.request.id}"
        )

        result = asyncio.run(_process_bulk_batch(
            batch_id=batch_id,
            template_name=template_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            recipients=recipients,
            from_email=from_email,
            from_name=from_name,
            batch_size=batch_size,
            delay_between_batches=delay_between_batches,
            tags=tags,
            task_id=self.request.id
        ))

        logger.info(f"Bulk email task completed: batch_id={batch_id}, result={result}")
        return result

    except Exception as e:
        logger.error(f"Bulk email task failed: batch_id={batch_id}, error={str(e)}")
        asyncio.run(_mark_batch_failed(batch_id, str(e)))
        raise


async def _process_bulk_batch(
    batch_id: str,
    template_name: Optional[str],
    subject: Optional[str],
    html_content: Optional[str],
    text_content: Optional[str],
    recipients: List[Dict[str, Any]],
    from_email: Optional[str],
    from_name: Optional[str],
    batch_size: int,
    delay_between_batches: float,
    tags: Optional[List[str]],
    task_id: str
) -> Dict[str, Any]:
    """Process bulk batch with rate limiting"""
    # Create fresh instances per task to avoid asyncpg pool conflicts
    from app.services.email_service import EmailService
    from app.services.template_service import TemplateService
    from app.utils.smtp_client import SMTPClient, EmailMessage
    from app.utils.config import get_smtp_config
    from jinja2 import Template

    email_service = EmailService()
    template_service = TemplateService()
    smtp_config = get_smtp_config()
    smtp_client = SMTPClient(smtp_config)

    # Update batch status
    await email_service.update_bulk_batch_status(batch_id, "processing", {
        "celery_task_id": task_id,
        "started_at": datetime.utcnow()
    })

    # Get template info if template-based
    template_info = None
    if template_name:
        template_info = await template_service.get_template(template_name)
        if not template_info:
            raise ValueError(f"Template '{template_name}' not found")

    # Determine sender
    effective_from_email = from_email or (template_info.get("from_email") if template_info else None) or smtp_config.default_from_email
    effective_from_name = from_name or (template_info.get("from_name") if template_info else None) or smtp_config.default_from_name

    successful = 0
    failed = 0

    # Process in batches
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]

        for recipient in batch:
            try:
                email = recipient["email"]
                variables = recipient.get("variables", {})

                if template_name:
                    # Render template with per-recipient variables
                    rendered = await template_service.render_template(template_name, variables)
                    email_subject = rendered["subject"]
                    email_html = rendered.get("html_content")
                    email_text = rendered.get("text_content")
                else:
                    # Use direct content with variable substitution
                    email_subject = Template(subject).render(**variables) if subject else ""
                    email_html = Template(html_content).render(**variables) if html_content else None
                    email_text = Template(text_content).render(**variables) if text_content else None

                # Create email record
                email_id = await email_service.create_email(
                    to_emails=[email],
                    subject=email_subject,
                    html_content=email_html,
                    text_content=email_text,
                    from_email=effective_from_email,
                    from_name=effective_from_name,
                    template_name=template_name,
                    template_variables=variables,
                    tags=tags,
                    status="sending",
                    metadata={"bulk_batch_id": batch_id}
                )

                # Send email
                email_message = EmailMessage(
                    to_emails=[email],
                    subject=email_subject,
                    html_content=email_html,
                    text_content=email_text,
                    from_email=effective_from_email,
                    from_name=effective_from_name,
                )

                result = await smtp_client.send_email(email_message)

                # Update to sent
                await email_service.update_email_status(email_id, "sent", {
                    "sent_at": datetime.utcnow(),
                    "message_id": result.get("message_id"),
                    "attempts": 1
                })

                successful += 1
                logger.debug(f"Bulk email sent: {email}")

            except Exception as e:
                logger.warning(f"Failed to send bulk email to {recipient.get('email')}: {e}")
                failed += 1

        # Update batch progress
        await email_service.update_bulk_batch_progress(batch_id, successful, failed)

        # Rate limit between batches
        if i + batch_size < len(recipients):
            logger.debug(f"Rate limiting: sleeping {delay_between_batches}s between batches")
            await asyncio.sleep(delay_between_batches)

    # Mark batch complete
    await email_service.update_bulk_batch_status(batch_id, "completed", {
        "completed_at": datetime.utcnow(),
        "successful_count": successful,
        "failed_count": failed
    })

    return {
        "batch_id": batch_id,
        "total": len(recipients),
        "successful": successful,
        "failed": failed,
        "status": "completed"
    }


async def _mark_batch_failed(batch_id: str, error: str):
    """Mark bulk batch as failed"""
    try:
        from app.services.email_service import EmailService
        email_service = EmailService()
        await email_service.update_bulk_batch_status(batch_id, "failed", {
            "error_message": error,
            "completed_at": datetime.utcnow()
        })
    except Exception as e:
        logger.error(f"Failed to mark batch as failed: {e}")
