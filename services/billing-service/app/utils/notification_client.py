"""
Notification Service Client for Billing Service
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
    
    async def send_payment_failure_email(
        self, 
        email: str, 
        first_name: str, 
        amount_due: str,
        payment_method_url: str
    ) -> Dict[str, Any]:
        """
        Send payment failure notification email
        
        Args:
            email: Customer's email address
            first_name: Customer's first name
            amount_due: Amount that failed to process
            payment_method_url: URL to update payment method
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="payment_failure",
            template_variables={
                "first_name": first_name,
                "amount_due": amount_due,
                "payment_method_url": payment_method_url
            },
            tags=["billing", "payment_failure", "urgent"]
        )
    
    async def send_subscription_cancelled_email(
        self, 
        email: str, 
        first_name: str,
        subscription_name: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Send subscription cancellation confirmation email
        
        Args:
            email: Customer's email address
            first_name: Customer's first name
            subscription_name: Name of cancelled subscription
            end_date: When subscription ends
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="subscription_cancelled",
            template_variables={
                "first_name": first_name,
                "subscription_name": subscription_name,
                "end_date": end_date
            },
            tags=["billing", "subscription", "cancellation"]
        )
    
    async def send_service_terminated_email(
        self, 
        email: str, 
        first_name: str,
        service_name: str,
        backup_info: str = None
    ) -> Dict[str, Any]:
        """
        Send service termination notification email
        
        Args:
            email: Customer's email address
            first_name: Customer's first name
            service_name: Name of terminated service
            backup_info: Information about data backup
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="service_terminated",
            template_variables={
                "first_name": first_name,
                "service_name": service_name,
                "backup_info": backup_info or "Your data has been backed up and will be available for 30 days."
            },
            tags=["billing", "service", "termination"]
        )
    
    async def send_invoice_created_email(
        self, 
        email: str, 
        first_name: str,
        invoice_number: str,
        amount_due: str,
        due_date: str,
        payment_url: str
    ) -> Dict[str, Any]:
        """
        Send new invoice notification email
        
        Args:
            email: Customer's email address
            first_name: Customer's first name
            invoice_number: Invoice number
            amount_due: Amount due
            due_date: Payment due date
            payment_url: URL to pay invoice
            
        Returns:
            Response from notification service
        """
        return await self.send_template_email(
            to_emails=[email],
            template_name="invoice_created",
            template_variables={
                "first_name": first_name,
                "invoice_number": invoice_number,
                "amount_due": amount_due,
                "due_date": due_date,
                "payment_url": payment_url
            },
            tags=["billing", "invoice", "payment"]
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

# Convenience functions for billing-specific emails
async def send_payment_failure_email(email: str, first_name: str, amount_due: str, payment_method_url: str) -> Dict[str, Any]:
    """Send payment failure email (convenience function)"""
    client = get_notification_client()
    return await client.send_payment_failure_email(email, first_name, amount_due, payment_method_url)

async def send_subscription_cancelled_email(email: str, first_name: str, subscription_name: str, end_date: str) -> Dict[str, Any]:
    """Send subscription cancelled email (convenience function)"""
    client = get_notification_client()
    return await client.send_subscription_cancelled_email(email, first_name, subscription_name, end_date)

async def send_service_terminated_email(email: str, first_name: str, service_name: str, backup_info: str = None) -> Dict[str, Any]:
    """Send service terminated email (convenience function)"""
    client = get_notification_client()
    return await client.send_service_terminated_email(email, first_name, service_name, backup_info)

async def send_invoice_created_email(email: str, first_name: str, invoice_number: str, amount_due: str, due_date: str, payment_url: str) -> Dict[str, Any]:
    """Send invoice created email (convenience function)"""
    client = get_notification_client()
    return await client.send_invoice_created_email(email, first_name, invoice_number, amount_due, due_date, payment_url)