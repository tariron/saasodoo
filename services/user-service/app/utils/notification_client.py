"""
Notification Service Client
HTTP client for communication with notification-service
"""

import httpx
import logging
from typing import Dict, Any, Optional, List
import os
import asyncio

logger = logging.getLogger(__name__)

class NotificationClient:
    """HTTP client for notification service"""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.getenv('NOTIFICATION_SERVICE_URL', 'http://notification-service:5000')
        self.timeout = httpx.Timeout(10.0)
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={'Content-Type': 'application/json'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    async def send_email(
        self,
        to_emails: List[str],
        subject: str,
        html_content: Optional[str] = None,
        text_content: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send an email via notification service
        
        Args:
            to_emails: List of recipient email addresses
            subject: Email subject
            html_content: HTML email content
            text_content: Plain text email content
            from_email: Sender email address
            from_name: Sender name
            tags: Optional tags for categorization
            
        Returns:
            Response from notification service
        """
        try:
            payload = {
                "to_emails": to_emails,
                "subject": subject,
                "html_content": html_content,
                "text_content": text_content,
                "priority": "normal",
                "tags": tags or []
            }
            
            if from_email:
                payload["from_email"] = from_email
            if from_name:
                payload["from_name"] = from_name
            
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post('/api/v1/emails/send', json=payload)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Email sent successfully via notification service: {result.get('email_id')}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error sending email: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Failed to send email: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"❌ Request error sending email: {e}")
            raise Exception(f"Failed to connect to notification service: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error sending email: {e}")
            raise
    
    async def send_template_email(
        self,
        to_emails: List[str],
        template_name: str,
        template_variables: Optional[Dict[str, Any]] = None,
        subject_override: Optional[str] = None,
        from_email_override: Optional[str] = None,
        from_name_override: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send an email using a template
        
        Args:
            to_emails: List of recipient email addresses
            template_name: Name of the email template
            template_variables: Variables to substitute in template
            subject_override: Override template subject
            from_email_override: Override template from email
            from_name_override: Override template from name
            tags: Optional tags for categorization
            
        Returns:
            Response from notification service
        """
        try:
            payload = {
                "to_emails": to_emails,
                "template_name": template_name,
                "template_variables": template_variables or {},
                "priority": "normal",
                "tags": tags or []
            }
            
            if subject_override:
                payload["subject_override"] = subject_override
            if from_email_override:
                payload["from_email_override"] = from_email_override
            if from_name_override:
                payload["from_name_override"] = from_name_override
            
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.post('/api/v1/emails/send-template', json=payload)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Template email sent successfully: {template_name} -> {result.get('email_id')}")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error sending template email: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Failed to send template email: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"❌ Request error sending template email: {e}")
            raise Exception(f"Failed to connect to notification service: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error sending template email: {e}")
            raise
    
    async def send_welcome_email(self, email: str, first_name: str) -> Dict[str, Any]:
        """
        Send welcome email to new user
        
        Args:
            email: User's email address
            first_name: User's first name
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="welcome",
            template_variables={
                "first_name": first_name,
                "login_url": f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/login"
            },
            tags=["welcome", "registration"]
        )
    
    async def send_password_reset_email(self, email: str, first_name: str, reset_token: str) -> Dict[str, Any]:
        """
        Send password reset email
        
        Args:
            email: User's email address
            first_name: User's first name
            reset_token: Password reset token
            
        Returns:
            Response from notification service
        """
        frontend_url = os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')
        reset_url = f"{frontend_url}/reset-password?token={reset_token}"
        
        return await self.send_template_email(
            to_emails=[email],
            template_name="password_reset",
            template_variables={
                "first_name": first_name,
                "reset_url": reset_url,
                "expires_in": "24 hours"
            },
            tags=["password_reset", "security"]
        )
    
    async def send_instance_ready_email(
        self, 
        email: str, 
        first_name: str, 
        instance_name: str, 
        instance_url: str,
        admin_email: str
    ) -> Dict[str, Any]:
        """
        Send instance ready notification email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the Odoo instance
            instance_url: URL to access the instance
            admin_email: Admin email for the instance
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="instance_ready",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "instance_url": instance_url,
                "admin_email": admin_email
            },
            tags=["instance", "provisioning", "ready"]
        )
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to notification service
        
        Returns:
            Health check response
        """
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.get('/health')
                response.raise_for_status()
                
                result = response.json()
                logger.info("✅ Notification service connection test successful")
                return result
                
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error testing notification service: {e.response.status_code}")
            raise Exception(f"Notification service health check failed: HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"❌ Request error testing notification service: {e}")
            raise Exception(f"Failed to connect to notification service: {str(e)}")
        except Exception as e:
            logger.error(f"❌ Unexpected error testing notification service: {e}")
            raise

# Global notification client instance
notification_client = NotificationClient()

def get_notification_client() -> NotificationClient:
    """Get notification client instance"""
    return notification_client

# Convenience functions for backward compatibility
async def send_welcome_email(email: str, first_name: str) -> Dict[str, Any]:
    """Send welcome email (convenience function)"""
    client = get_notification_client()
    return await client.send_welcome_email(email, first_name)

async def send_password_reset_email(email: str, first_name: str, reset_token: str) -> Dict[str, Any]:
    """Send password reset email (convenience function)"""
    client = get_notification_client()
    return await client.send_password_reset_email(email, first_name, reset_token)