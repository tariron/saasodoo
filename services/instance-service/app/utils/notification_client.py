"""
Notification Service Client for Instance Service
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
    
    async def send_instance_provisioning_started_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        estimated_time: str = "10-15 minutes"
    ) -> Dict[str, Any]:
        """
        Send instance provisioning started email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance being provisioned
            estimated_time: Estimated completion time
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="instance_provisioning_started",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "estimated_time": estimated_time
            },
            tags=["instance", "provisioning", "started"]
        )
    
    async def send_instance_provisioning_failed_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        error_reason: str = None,
        support_url: str = None
    ) -> Dict[str, Any]:
        """
        Send instance provisioning failed email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance that failed
            error_reason: Brief description of the error
            support_url: URL to contact support
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="instance_provisioning_failed",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "error_reason": error_reason or "We encountered an unexpected issue during provisioning.",
                "support_url": support_url or f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
            },
            tags=["instance", "provisioning", "failed", "support"]
        )
    
    async def send_backup_completed_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        backup_name: str,
        backup_size: str,
        backup_date: str
    ) -> Dict[str, Any]:
        """
        Send backup completed notification email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance that was backed up
            backup_name: Name of the backup
            backup_size: Size of the backup
            backup_date: Date when backup was created
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="backup_completed",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "backup_name": backup_name,
                "backup_size": backup_size,
                "backup_date": backup_date
            },
            tags=["instance", "backup", "completed"]
        )
    
    async def send_backup_failed_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        error_message: str,
        support_url: str = None
    ) -> Dict[str, Any]:
        """
        Send backup failed notification email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance that failed to backup
            error_message: Error message describing the failure
            support_url: URL to contact support
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="backup_failed",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "error_message": error_message,
                "support_url": support_url or f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
            },
            tags=["instance", "backup", "failed", "support"]
        )
    
    async def send_restore_completed_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        backup_name: str,
        restore_date: str,
        instance_url: str
    ) -> Dict[str, Any]:
        """
        Send restore completed notification email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance that was restored
            backup_name: Name of the backup used for restore
            restore_date: Date when restore was completed
            instance_url: URL to access the restored instance
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="restore_completed",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "backup_name": backup_name,
                "restore_date": restore_date,
                "instance_url": instance_url
            },
            tags=["instance", "restore", "completed"]
        )
    
    async def send_restore_failed_email(
        self, 
        email: str, 
        first_name: str,
        instance_name: str,
        backup_name: str,
        error_message: str,
        support_url: str = None
    ) -> Dict[str, Any]:
        """
        Send restore failed notification email
        
        Args:
            email: User's email address
            first_name: User's first name
            instance_name: Name of the instance that failed to restore
            backup_name: Name of the backup that failed to restore
            error_message: Error message describing the failure
            support_url: URL to contact support
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="restore_failed",
            template_variables={
                "first_name": first_name,
                "instance_name": instance_name,
                "backup_name": backup_name,
                "error_message": error_message,
                "support_url": support_url or f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
            },
            tags=["instance", "restore", "failed", "support"]
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

# Convenience functions for instance-specific emails
async def send_instance_ready_email(email: str, first_name: str, instance_name: str, instance_url: str, admin_email: str) -> Dict[str, Any]:
    """Send instance ready email (convenience function)"""
    client = get_notification_client()
    return await client.send_instance_ready_email(email, first_name, instance_name, instance_url, admin_email)

async def send_instance_provisioning_started_email(email: str, first_name: str, instance_name: str, estimated_time: str = "10-15 minutes") -> Dict[str, Any]:
    """Send instance provisioning started email (convenience function)"""
    client = get_notification_client()
    return await client.send_instance_provisioning_started_email(email, first_name, instance_name, estimated_time)

async def send_instance_provisioning_failed_email(email: str, first_name: str, instance_name: str, error_reason: str = None, support_url: str = None) -> Dict[str, Any]:
    """Send instance provisioning failed email (convenience function)"""
    client = get_notification_client()
    return await client.send_instance_provisioning_failed_email(email, first_name, instance_name, error_reason, support_url)

async def send_backup_completed_email(email: str, first_name: str, instance_name: str, backup_name: str, backup_size: str, backup_date: str) -> Dict[str, Any]:
    """Send backup completed email (convenience function)"""
    client = get_notification_client()
    return await client.send_backup_completed_email(email, first_name, instance_name, backup_name, backup_size, backup_date)

async def send_backup_failed_email(email: str, first_name: str, instance_name: str, error_message: str, support_url: str = None) -> Dict[str, Any]:
    """Send backup failed email (convenience function)"""
    client = get_notification_client()
    return await client.send_backup_failed_email(email, first_name, instance_name, error_message, support_url)

async def send_restore_completed_email(email: str, first_name: str, instance_name: str, backup_name: str, restore_date: str, instance_url: str) -> Dict[str, Any]:
    """Send restore completed email (convenience function)"""
    client = get_notification_client()
    return await client.send_restore_completed_email(email, first_name, instance_name, backup_name, restore_date, instance_url)

async def send_restore_failed_email(email: str, first_name: str, instance_name: str, backup_name: str, error_message: str, support_url: str = None) -> Dict[str, Any]:
    """Send restore failed email (convenience function)"""
    client = get_notification_client()
    return await client.send_restore_failed_email(email, first_name, instance_name, backup_name, error_message, support_url)