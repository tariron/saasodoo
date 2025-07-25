"""
Email API Routes
Email sending and management endpoints
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional
import logging
import uuid
from datetime import datetime

from app.models.email import (
    EmailRequest, TemplateEmailRequest, EmailResponse, 
    EmailHistoryResponse, BulkEmailRequest, BulkEmailResponse
)
from app.utils.smtp_client import get_smtp_client, EmailMessage, SMTPError
from app.services.email_service import get_email_service
from app.services.template_service import get_template_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/send", response_model=EmailResponse)
async def send_email(request: EmailRequest):
    """
    Send a single email
    
    Send an email with HTML and/or text content to one or more recipients.
    """
    try:
        smtp_client = get_smtp_client()
        email_service = get_email_service()
        
        # Create email message
        email_message = EmailMessage(
            to_emails=request.to_emails,
            subject=request.subject,
            html_content=request.html_content,
            text_content=request.text_content,
            from_email=request.from_email,
            from_name=request.from_name,
            reply_to=request.reply_to,
            headers=request.headers or {}
        )
        
        # Generate email ID for tracking
        email_id = str(uuid.uuid4())
        
        # Record email in database (if database is configured)
        try:
            await email_service.create_email_record({
                "id": email_id,
                "to_emails": request.to_emails,
                "subject": request.subject,
                "status": "sending",
                "priority": request.priority,
                "from_email": email_message.from_email,
                "from_name": email_message.from_name,
                "tags": request.tags,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.warning(f"Failed to record email in database: {e}")
        
        # Send email
        result = await smtp_client.send_email(email_message)
        
        # Update email record with success
        try:
            await email_service.update_email_status(email_id, "sent", {
                "sent_at": datetime.utcnow(),
                "message_id": result.get("message_id"),
                "attempts": result.get("attempts", 1)
            })
        except Exception as e:
            logger.warning(f"Failed to update email status in database: {e}")
        
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
        # Update email record with failure
        try:
            await email_service.update_email_status(email_id, "failed", {
                "failed_at": datetime.utcnow(),
                "error_message": str(e)
            })
        except:
            pass
        
        logger.error(f"SMTP error sending email: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to send email: {str(e)}")
    
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/send-template", response_model=EmailResponse)
async def send_template_email(request: TemplateEmailRequest):
    """
    Send an email using a template
    
    Send an email using a predefined template with variable substitution.
    """
    try:
        template_service = get_template_service()
        email_service = get_email_service()
        smtp_client = get_smtp_client()
        
        # Get template
        template = await template_service.get_template(request.template_name)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{request.template_name}' not found")
        
        # Render template with variables
        rendered_content = await template_service.render_template(
            request.template_name,
            request.template_variables or {}
        )
        
        # Use subject override or template default
        subject = request.subject_override or rendered_content["subject"]
        from_email = request.from_email_override or template.get("from_email")
        from_name = request.from_name_override or template.get("from_name")
        
        # Create email message
        email_message = EmailMessage(
            to_emails=request.to_emails,
            subject=subject,
            html_content=rendered_content.get("html_content"),
            text_content=rendered_content.get("text_content"),
            from_email=from_email,
            from_name=from_name
        )
        
        # Generate email ID for tracking
        email_id = str(uuid.uuid4())
        
        # Record email in database
        try:
            await email_service.create_email_record({
                "id": email_id,
                "to_emails": request.to_emails,
                "subject": subject,
                "status": "sending",
                "priority": request.priority,
                "from_email": email_message.from_email,
                "from_name": email_message.from_name,
                "template_name": request.template_name,
                "tags": request.tags,
                "created_at": datetime.utcnow()
            })
        except Exception as e:
            logger.warning(f"Failed to record email in database: {e}")
        
        # Send email
        result = await smtp_client.send_email(email_message)
        
        # Update email record with success
        try:
            await email_service.update_email_status(email_id, "sent", {
                "sent_at": datetime.utcnow(),
                "message_id": result.get("message_id"),
                "attempts": result.get("attempts", 1)
            })
        except Exception as e:
            logger.warning(f"Failed to update email status in database: {e}")
        
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
        
        # Create new email message from original
        email_message = EmailMessage(
            to_emails=original_email["to_emails"],
            subject=original_email["subject"],
            html_content=original_email.get("html_content"),
            text_content=original_email.get("text_content"),
            from_email=original_email["from_email"],
            from_name=original_email.get("from_name")
        )
        
        # Update status to sending
        await email_service.update_email_status(email_id, "sending", {
            "attempts": original_email.get("attempts", 0) + 1
        })
        
        # Send email
        result = await smtp_client.send_email(email_message)
        
        # Update email record with success
        await email_service.update_email_status(email_id, "sent", {
            "sent_at": datetime.utcnow(),
            "message_id": result.get("message_id"),
            "attempts": original_email.get("attempts", 0) + 1,
            "error_message": None
        })
        
        return EmailResponse(
            success=True,
            message="Email resent successfully",
            email_id=email_id,
            message_id=result.get("message_id"),
            recipients=original_email["to_emails"],
            sent_at=datetime.fromisoformat(result["sent_at"]),
            attempts=original_email.get("attempts", 0) + 1
        )
        
    except HTTPException:
        raise
    except SMTPError as e:
        # Update email record with failure
        try:
            await email_service.update_email_status(email_id, "failed", {
                "failed_at": datetime.utcnow(),
                "error_message": str(e),
                "attempts": original_email.get("attempts", 0) + 1
            })
        except:
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