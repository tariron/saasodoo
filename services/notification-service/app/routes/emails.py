"""
Email API Routes
Email sending and management endpoints with Celery integration
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Union
import logging
from datetime import datetime

from app.models.email import (
    EmailRequest, TemplateEmailRequest, EmailResponse,
    EmailHistoryResponse, BulkEmailRequest, BulkEmailResponse,
    AsyncEmailResponse, BulkEmailStatusResponse
)
from app.utils.smtp_client import get_smtp_client, EmailMessage, SMTPError
from app.services.email_service import get_email_service
from app.services.template_service import get_template_service
from app.tasks.email import send_email_task, send_template_email_task
from app.tasks.bulk import send_bulk_email_task

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/send", response_model=EmailResponse)
async def send_email(request: EmailRequest):
    """
    Send a single email (synchronous)

    Send an email with HTML and/or text content to one or more recipients.
    Supports CC and BCC recipients.
    """
    try:
        smtp_client = get_smtp_client()
        email_service = get_email_service()

        # Create email message with CC/BCC support
        email_message = EmailMessage(
            to_emails=request.to_emails,
            cc_emails=request.cc_emails,
            bcc_emails=request.bcc_emails,
            subject=request.subject,
            html_content=request.html_content,
            text_content=request.text_content,
            from_email=request.from_email,
            from_name=request.from_name,
            reply_to=request.reply_to,
            headers=request.headers or {}
        )

        # Record email in database
        email_id = await email_service.create_email(
            to_emails=list(request.to_emails),
            cc_emails=list(request.cc_emails) if request.cc_emails else None,
            bcc_emails=list(request.bcc_emails) if request.bcc_emails else None,
            subject=request.subject,
            html_content=request.html_content,
            text_content=request.text_content,
            from_email=request.from_email,
            from_name=request.from_name,
            reply_to=request.reply_to,
            priority=request.priority.value,
            tags=request.tags,
            headers=request.headers,
            status="sending"
        )

        # Send email synchronously
        result = await smtp_client.send_email(email_message)

        # Update email record with success
        await email_service.update_email_status(email_id, "sent", {
            "sent_at": datetime.utcnow(),
            "message_id": result.get("message_id"),
            "attempts": result.get("attempts", 1)
        })

        return EmailResponse(
            success=True,
            message="Email sent successfully",
            email_id=email_id,
            message_id=result.get("message_id"),
            recipients=[str(email) for email in request.to_emails],
            sent_at=datetime.fromisoformat(result["sent_at"]),
            attempts=result.get("attempts")
        )

    except SMTPError as e:
        # Update email record with failure if we have an ID
        if 'email_id' in locals():
            try:
                await email_service.update_email_status(email_id, "failed", {
                    "error_message": str(e),
                    "attempts": 1
                })
            except Exception:
                pass

        logger.error(f"SMTP error sending email: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to send email: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/send-template", response_model=Union[EmailResponse, AsyncEmailResponse])
async def send_template_email(request: TemplateEmailRequest):
    """
    Send an email using a template

    Send an email using a predefined template with variable substitution.
    By default uses async mode (queues via Celery). Set async_send=false for synchronous sending.
    """
    try:
        template_service = get_template_service()
        email_service = get_email_service()

        # Validate template exists
        template = await template_service.get_template(request.template_name)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{request.template_name}' not found")

        # Determine sender info
        from_email = request.from_email_override or template.get("from_email")
        from_name = request.from_name_override or template.get("from_name")

        if request.async_send:
            # Async mode: Queue via Celery
            # Task creates email record internally for atomicity
            task = send_template_email_task.delay(
                to_emails=list(request.to_emails),
                template_name=request.template_name,
                template_variables=request.template_variables or {},
                cc_emails=list(request.cc_emails) if request.cc_emails else None,
                bcc_emails=list(request.bcc_emails) if request.bcc_emails else None,
                priority=request.priority.value,
                tags=request.tags
            )

            logger.info(f"Template email queued: task_id={task.id}")

            return AsyncEmailResponse(
                success=True,
                message="Email queued for sending",
                email_id=None,  # Will be created by task
                status="queued",
                celery_task_id=task.id,
                queued_at=datetime.utcnow()
            )

        else:
            # Sync mode: Send immediately
            smtp_client = get_smtp_client()

            # Render template
            rendered_content = await template_service.render_template(
                request.template_name,
                request.template_variables or {}
            )

            subject = request.subject_override or rendered_content["subject"]

            # Create email message
            email_message = EmailMessage(
                to_emails=request.to_emails,
                cc_emails=request.cc_emails,
                bcc_emails=request.bcc_emails,
                subject=subject,
                html_content=rendered_content.get("html_content"),
                text_content=rendered_content.get("text_content"),
                from_email=from_email,
                from_name=from_name
            )

            # Record email in database
            email_id = await email_service.create_email(
                to_emails=list(request.to_emails),
                cc_emails=list(request.cc_emails) if request.cc_emails else None,
                bcc_emails=list(request.bcc_emails) if request.bcc_emails else None,
                subject=subject,
                html_content=rendered_content.get("html_content"),
                text_content=rendered_content.get("text_content"),
                from_email=from_email,
                from_name=from_name,
                template_name=request.template_name,
                template_variables=request.template_variables,
                priority=request.priority.value,
                tags=request.tags,
                status="sending"
            )

            # Send email
            result = await smtp_client.send_email(email_message)

            # Update email record with success
            await email_service.update_email_status(email_id, "sent", {
                "sent_at": datetime.utcnow(),
                "message_id": result.get("message_id"),
                "attempts": result.get("attempts", 1)
            })

            return EmailResponse(
                success=True,
                message="Template email sent successfully",
                email_id=email_id,
                message_id=result.get("message_id"),
                recipients=[str(email) for email in request.to_emails],
                sent_at=datetime.fromisoformat(result["sent_at"]),
                attempts=result.get("attempts")
            )

    except HTTPException:
        raise
    except SMTPError as e:
        logger.error(f"SMTP error sending template email: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to send email: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending template email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/bulk", response_model=BulkEmailResponse)
async def send_bulk_email(request: BulkEmailRequest):
    """
    Send bulk emails

    Queue bulk email batch for processing. Emails are sent asynchronously
    via Celery workers with rate limiting between batches.
    """
    try:
        email_service = get_email_service()

        # Validate template if specified
        if request.template_name:
            template_service = get_template_service()
            template = await template_service.get_template(request.template_name)
            if not template:
                raise HTTPException(
                    status_code=404,
                    detail=f"Template '{request.template_name}' not found"
                )
        elif not request.subject:
            raise HTTPException(
                status_code=400,
                detail="Either template_name or subject is required"
            )

        # Create bulk batch record
        batch_id = await email_service.create_bulk_batch(
            template_name=request.template_name,
            subject=request.subject,
            total_recipients=len(request.recipients),
            metadata={
                "priority": request.priority.value,
                "tags": request.tags,
                "batch_size": request.batch_size,
                "delay_between_batches": request.delay_between_batches
            }
        )

        # Queue Celery task
        task = send_bulk_email_task.delay(
            batch_id=batch_id,
            template_name=request.template_name,
            subject=request.subject,
            html_content=request.html_content,
            text_content=request.text_content,
            recipients=request.recipients,
            from_email=request.from_email,
            from_name=request.from_name,
            batch_size=request.batch_size,
            delay_between_batches=request.delay_between_batches,
            tags=request.tags
        )

        # Update batch with task ID
        await email_service.update_bulk_batch_status(batch_id, "queued", {
            "celery_task_id": task.id
        })

        logger.info(f"Bulk email batch queued: batch_id={batch_id}, recipients={len(request.recipients)}, task_id={task.id}")

        return BulkEmailResponse(
            success=True,
            message=f"Bulk email batch queued with {len(request.recipients)} recipients",
            batch_id=batch_id,
            total_recipients=len(request.recipients),
            status="queued",
            celery_task_id=task.id,
            queued_at=datetime.utcnow()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing bulk email batch: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue bulk email batch")


@router.get("/bulk/{batch_id}", response_model=BulkEmailStatusResponse)
async def get_bulk_status(batch_id: str):
    """
    Get bulk email batch status

    Retrieve the current status and progress of a bulk email batch.
    """
    try:
        email_service = get_email_service()

        batch = await email_service.get_bulk_batch(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Bulk batch not found")

        return BulkEmailStatusResponse(
            batch_id=batch["id"],
            status=batch["status"],
            total_recipients=batch["total_recipients"],
            successful_count=batch.get("successful_count", 0),
            failed_count=batch.get("failed_count", 0),
            pending_count=batch.get("pending_count", batch["total_recipients"]),
            started_at=batch.get("started_at"),
            completed_at=batch.get("completed_at"),
            celery_task_id=batch.get("celery_task_id")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving bulk batch status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve batch status")


@router.get("/history", response_model=EmailHistoryResponse)
async def get_email_history(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status"),
    template_name: Optional[str] = Query(None, description="Filter by template"),
    from_date: Optional[str] = Query(None, description="Filter from date (ISO format)"),
    to_date: Optional[str] = Query(None, description="Filter to date (ISO format)")
):
    """
    Get email history

    Retrieve a paginated list of sent emails with optional filtering.
    """
    try:
        email_service = get_email_service()

        # Build filters
        filters = {}
        if status:
            filters["status"] = status
        if template_name:
            filters["template_name"] = template_name
        if from_date:
            filters["from_date"] = from_date
        if to_date:
            filters["to_date"] = to_date

        # Get email history
        history = await email_service.get_email_history(
            page=page,
            per_page=per_page,
            filters=filters
        )

        return history

    except Exception as e:
        logger.error(f"Error retrieving email history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve email history")


@router.get("/{email_id}")
async def get_email_details(email_id: str):
    """
    Get details of a specific email

    Retrieve detailed information about a sent email including delivery status.
    """
    try:
        email_service = get_email_service()

        email_details = await email_service.get_email_by_id(email_id)
        if not email_details:
            raise HTTPException(status_code=404, detail="Email not found")

        return email_details

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving email details: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve email details")


@router.post("/{email_id}/resend", response_model=EmailResponse)
async def resend_email(email_id: str):
    """
    Resend a failed email

    Attempt to resend an email that previously failed.
    """
    try:
        email_service = get_email_service()
        smtp_client = get_smtp_client()

        # Get original email details
        original_email = await email_service.get_email_by_id(email_id)
        if not original_email:
            raise HTTPException(status_code=404, detail="Email not found")

        # Only allow resending failed emails
        if original_email["status"] not in ["failed", "bounced"]:
            raise HTTPException(status_code=400, detail="Can only resend failed or bounced emails")

        # Create new email message from original (with CC/BCC)
        email_message = EmailMessage(
            to_emails=original_email["to_emails"],
            cc_emails=original_email.get("cc_emails"),
            bcc_emails=original_email.get("bcc_emails"),
            subject=original_email["subject"],
            html_content=original_email.get("html_content"),
            text_content=original_email.get("text_content"),
            from_email=original_email.get("from_email"),
            from_name=original_email.get("from_name")
        )

        current_attempts = original_email.get("attempts", 0)

        # Update status to sending
        await email_service.update_email_status(email_id, "sending", {
            "attempts": current_attempts + 1,
            "last_attempt_at": datetime.utcnow()
        })

        # Send email
        result = await smtp_client.send_email(email_message)

        # Update email record with success
        await email_service.update_email_status(email_id, "sent", {
            "sent_at": datetime.utcnow(),
            "message_id": result.get("message_id"),
            "attempts": current_attempts + 1,
            "error_message": None
        })

        return EmailResponse(
            success=True,
            message="Email resent successfully",
            email_id=email_id,
            message_id=result.get("message_id"),
            recipients=original_email["to_emails"],
            sent_at=datetime.fromisoformat(result["sent_at"]),
            attempts=current_attempts + 1
        )

    except HTTPException:
        raise
    except SMTPError as e:
        # Update email record with failure
        try:
            await email_service.update_email_status(email_id, "failed", {
                "error_message": str(e),
                "attempts": original_email.get("attempts", 0) + 1,
                "last_attempt_at": datetime.utcnow()
            })
        except Exception:
            pass

        logger.error(f"SMTP error resending email: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to resend email: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error resending email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/test/connection")
async def test_smtp_connection():
    """
    Test SMTP connection

    Test the SMTP server connection and authentication.
    """
    try:
        smtp_client = get_smtp_client()
        result = await smtp_client.test_connection()

        if result["success"]:
            return {
                "status": "success",
                "message": "SMTP connection successful",
                "details": result
            }
        else:
            return {
                "status": "failed",
                "message": "SMTP connection failed",
                "error": result["error"],
                "details": result
            }

    except Exception as e:
        logger.error(f"Error testing SMTP connection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to test connection: {str(e)}")


@router.post("/test/send")
async def send_test_email(
    to_email: str = Query(..., description="Recipient email address"),
    subject: str = Query("Test Email", description="Email subject")
):
    """
    Send a test email

    Send a simple test email to verify email functionality.
    """
    try:
        smtp_client = get_smtp_client()

        # Create test email content
        html_content = f"""
        <html>
        <body>
            <h2>Test Email from Notification Service</h2>
            <p>This is a test email sent at {datetime.utcnow().isoformat()}.</p>
            <p>If you received this email, the notification service is working correctly!</p>
            <hr>
            <small>Sent from SaaS Odoo Platform Notification Service</small>
        </body>
        </html>
        """

        text_content = f"""
        Test Email from Notification Service

        This is a test email sent at {datetime.utcnow().isoformat()}.
        If you received this email, the notification service is working correctly!

        ---
        Sent from SaaS Odoo Platform Notification Service
        """

        email_message = EmailMessage(
            to_emails=[to_email],
            subject=f"[TEST] {subject}",
            html_content=html_content,
            text_content=text_content
        )

        # Send email
        result = await smtp_client.send_email(email_message)

        return {
            "success": True,
            "message": "Test email sent successfully",
            "recipient": to_email,
            "sent_at": result["sent_at"],
            "message_id": result.get("message_id")
        }

    except SMTPError as e:
        logger.error(f"SMTP error sending test email: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to send test email: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error sending test email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
