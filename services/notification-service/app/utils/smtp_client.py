"""
SMTP Client
Production-ready SMTP client with retry logic and error handling
"""

import asyncio
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import time

from app.utils.config import get_smtp_config

logger = logging.getLogger(__name__)

class SMTPError(Exception):
    """Custom SMTP exception"""
    pass

class EmailMessage:
    """Email message container with CC/BCC support"""

    def __init__(
        self,
        to_emails: List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        self.to_emails = to_emails if isinstance(to_emails, list) else [to_emails]
        self.cc_emails = cc_emails or []
        self.bcc_emails = bcc_emails or []
        self.subject = subject
        self.html_content = html_content
        self.text_content = text_content
        self.from_email = from_email
        self.from_name = from_name
        self.reply_to = reply_to
        self.attachments = attachments or []
        self.headers = headers or {}

        # Validation
        if not self.to_emails:
            raise ValueError("At least one recipient email is required")
        if not self.subject:
            raise ValueError("Subject is required")
        if not self.html_content and not self.text_content:
            raise ValueError("Either HTML or text content is required")

    def get_all_recipients(self) -> List[str]:
        """Get all recipients (To + CC + BCC) for SMTP sending"""
        all_recipients = list(self.to_emails)
        all_recipients.extend(self.cc_emails)
        all_recipients.extend(self.bcc_emails)
        return all_recipients

class SMTPClient:
    """Production-ready SMTP client with retry logic"""

    def __init__(self, config=None):
        self.config = config or get_smtp_config()
        self._rate_limiter = RateLimiter(
            max_per_minute=self.config.max_emails_per_minute,
            max_per_hour=self.config.max_emails_per_hour
        )
    
    async def send_email(
        self,
        email_message: EmailMessage,
        retry_count: int = 3,
        retry_delay: float = 1.0
    ) -> Dict[str, Any]:
        """
        Send email with retry logic
        
        Args:
            email_message: Email message to send
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            Dictionary with send result
        """
        # Check rate limits
        if not self._rate_limiter.can_send():
            raise SMTPError("Rate limit exceeded. Please try again later.")
        
        last_error = None
        
        for attempt in range(retry_count + 1):
            try:
                # Create MIME message
                mime_message = self._create_mime_message(email_message)

                # Send to all recipients (To + CC + BCC)
                all_recipients = email_message.get_all_recipients()
                result = await self._send_mime_message(mime_message, all_recipients)

                # Record successful send for rate limiting
                self._rate_limiter.record_send()

                logger.info(f"Email sent successfully to {len(all_recipients)} recipients")
                return {
                    "success": True,
                    "message_id": result.get("message_id"),
                    "recipients": email_message.to_emails,
                    "attempts": attempt + 1,
                    "sent_at": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                last_error = e
                logger.warning(f"📧 Email send attempt {attempt + 1} failed: {e}")
                
                if attempt < retry_count:
                    await asyncio.sleep(retry_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error(f"❌ All email send attempts failed: {e}")
        
        # All attempts failed
        raise SMTPError(f"Failed to send email after {retry_count + 1} attempts: {last_error}")
    
    def _create_mime_message(self, email_message: EmailMessage) -> MIMEMultipart:
        """Create MIME message from EmailMessage"""
        # Determine from address
        from_email = email_message.from_email or self.config.default_from_email
        from_name = email_message.from_name or self.config.default_from_name
        from_address = f"{from_name} <{from_email}>" if from_name else from_email
        
        # Create message
        if email_message.html_content and email_message.text_content:
            msg = MIMEMultipart('alternative')
        else:
            msg = MIMEMultipart()
        
        msg['From'] = from_address
        msg['To'] = ', '.join(email_message.to_emails)
        msg['Subject'] = email_message.subject

        # Add CC header (BCC is intentionally not added to headers - invisible to recipients)
        if email_message.cc_emails:
            msg['Cc'] = ', '.join(email_message.cc_emails)

        if email_message.reply_to:
            msg['Reply-To'] = email_message.reply_to

        # Add custom headers
        for key, value in email_message.headers.items():
            msg[key] = value
        
        # Add text content
        if email_message.text_content:
            text_part = MIMEText(email_message.text_content, 'plain', 'utf-8')
            msg.attach(text_part)
        
        # Add HTML content
        if email_message.html_content:
            html_part = MIMEText(email_message.html_content, 'html', 'utf-8')
            msg.attach(html_part)
        
        # Add attachments
        for attachment in email_message.attachments:
            try:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment['content'])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {attachment["filename"]}'
                )
                msg.attach(part)
            except Exception as e:
                logger.warning(f"Failed to attach file {attachment.get('filename', 'unknown')}: {e}")
        
        return msg
    
    async def _send_mime_message(self, message: MIMEMultipart, recipients: List[str]) -> Dict[str, Any]:
        """Send MIME message via SMTP"""
        smtp = None
        try:
            # Create SMTP connection
            smtp = aiosmtplib.SMTP(
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                use_tls=self.config.smtp_use_tls,
                timeout=self.config.smtp_timeout
            )
            
            # Connect
            await smtp.connect()
            
            # Authenticate if credentials provided
            if self.config.smtp_username and self.config.smtp_password:
                await smtp.login(self.config.smtp_username, self.config.smtp_password)
            
            # Send message
            result = await smtp.send_message(message)
            
            return {
                "message_id": message.get('Message-ID'),
                "smtp_result": result
            }
            
        finally:
            if smtp:
                try:
                    await smtp.quit()
                except:
                    pass  # Ignore cleanup errors
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test SMTP connection"""
        try:
            smtp = aiosmtplib.SMTP(
                hostname=self.config.smtp_host,
                port=self.config.smtp_port,
                use_tls=self.config.smtp_use_tls,
                timeout=self.config.smtp_timeout
            )
            
            start_time = time.time()
            await smtp.connect()
            connection_time = time.time() - start_time
            
            # Test authentication if credentials provided
            auth_success = True
            if self.config.smtp_username and self.config.smtp_password:
                try:
                    await smtp.login(self.config.smtp_username, self.config.smtp_password)
                except Exception as e:
                    auth_success = False
                    logger.warning(f"SMTP authentication failed: {e}")
            
            await smtp.quit()
            
            return {
                "success": True,
                "connection_time": round(connection_time, 3),
                "host": self.config.smtp_host,
                "port": self.config.smtp_port,
                "tls": self.config.smtp_use_tls,
                "authentication": auth_success if self.config.smtp_username else None
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "host": self.config.smtp_host,
                "port": self.config.smtp_port
            }

class RateLimiter:
    """Simple rate limiter for email sending"""
    
    def __init__(self, max_per_minute: int, max_per_hour: int):
        self.max_per_minute = max_per_minute
        self.max_per_hour = max_per_hour
        self.minute_counter = {}
        self.hour_counter = {}
    
    def can_send(self) -> bool:
        """Check if we can send an email without exceeding rate limits"""
        now = datetime.utcnow()
        current_minute = now.replace(second=0, microsecond=0)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        # Clean old entries
        self._cleanup_counters(current_minute, current_hour)
        
        # Check limits
        minute_count = self.minute_counter.get(current_minute, 0)
        hour_count = self.hour_counter.get(current_hour, 0)
        
        return minute_count < self.max_per_minute and hour_count < self.max_per_hour
    
    def record_send(self):
        """Record a successful email send"""
        now = datetime.utcnow()
        current_minute = now.replace(second=0, microsecond=0)
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        
        self.minute_counter[current_minute] = self.minute_counter.get(current_minute, 0) + 1
        self.hour_counter[current_hour] = self.hour_counter.get(current_hour, 0) + 1
    
    def _cleanup_counters(self, current_minute: datetime, current_hour: datetime):
        """Remove old counter entries"""
        # Remove minute entries older than 2 minutes
        minute_cutoff = current_minute.timestamp() - 120
        self.minute_counter = {
            k: v for k, v in self.minute_counter.items() 
            if k.timestamp() > minute_cutoff
        }
        
        # Remove hour entries older than 2 hours
        hour_cutoff = current_hour.timestamp() - 7200
        self.hour_counter = {
            k: v for k, v in self.hour_counter.items() 
            if k.timestamp() > hour_cutoff
        }

# Global SMTP client instance
smtp_client = SMTPClient()

def get_smtp_client() -> SMTPClient:
    """Get SMTP client instance"""
    return smtp_client