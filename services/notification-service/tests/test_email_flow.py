"""
Test Email Flow with MailHog
Simple integration test to verify email functionality
"""

import asyncio
import httpx
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EmailFlowTester:
    """Test email functionality with MailHog"""
    
    def __init__(self, notification_url: str = "http://localhost:5000"):
        self.notification_url = notification_url
        self.mailhog_url = "http://localhost:8025"
    
    async def test_notification_service_health(self):
        """Test notification service health check"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.notification_url}/health")
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Notification service health: {result['status']}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Notification service health check failed: {e}")
            return False
    
    async def test_smtp_connection(self):
        """Test SMTP connection through notification service"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.notification_url}/api/v1/emails/test/connection")
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ SMTP connection test: {result['status']}")
                return result['status'] == 'success'
                
        except Exception as e:
            logger.error(f"❌ SMTP connection test failed: {e}")
            return False
    
    async def send_test_email(self, to_email: str = "test@example.com"):
        """Send a simple test email"""
        try:
            payload = {
                "to_emails": [to_email],
                "subject": f"Test Email - {datetime.now().strftime('%H:%M:%S')}",
                "html_content": f"""
                <html>
                <body>
                    <h2>🎉 Test Email from Notification Service</h2>
                    <p>This is a test email sent at <strong>{datetime.now().isoformat()}</strong>.</p>
                    <p>If you see this in MailHog, the notification service is working correctly!</p>
                    <ul>
                        <li>✅ SMTP connection working</li>
                        <li>✅ Email sending working</li>
                        <li>✅ HTML content rendering</li>
                    </ul>
                    <hr>
                    <small>Sent from SaaS Odoo Platform Notification Service Test</small>
                </body>
                </html>
                """,
                "text_content": f"""
Test Email from Notification Service

This is a test email sent at {datetime.now().isoformat()}.

If you see this in MailHog, the notification service is working correctly!

- SMTP connection working
- Email sending working
- Text content working

---
Sent from SaaS Odoo Platform Notification Service Test
                """,
                "priority": "normal",
                "tags": ["test", "integration"]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.notification_url}/api/v1/emails/send", json=payload)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Test email sent successfully - ID: {result.get('email_id')}")
                return result
                
        except Exception as e:
            logger.error(f"❌ Failed to send test email: {e}")
            return None
    
    async def send_welcome_template_email(self, to_email: str = "newuser@example.com"):
        """Send a welcome email using template"""
        try:
            payload = {
                "to_emails": [to_email],
                "template_name": "welcome",
                "template_variables": {
                    "first_name": "John",
                    "login_url": "http://app.saasodoo.local/login"
                },
                "priority": "normal",
                "tags": ["welcome", "template-test"]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.notification_url}/api/v1/emails/send-template", json=payload)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Welcome template email sent - ID: {result.get('email_id')}")
                return result
                
        except Exception as e:
            logger.error(f"❌ Failed to send welcome template email: {e}")
            return None
    
    async def send_password_reset_template_email(self, to_email: str = "resetuser@example.com"):
        """Send a password reset email using template"""
        try:
            payload = {
                "to_emails": [to_email],
                "template_name": "password_reset",
                "template_variables": {
                    "first_name": "Jane",
                    "reset_url": "http://app.saasodoo.local/reset-password?token=abc123xyz",
                    "expires_in": "24 hours"
                },
                "priority": "normal",
                "tags": ["password_reset", "template-test"]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(f"{self.notification_url}/api/v1/emails/send-template", json=payload)
                response.raise_for_status()
                
                result = response.json()
                logger.info(f"✅ Password reset template email sent - ID: {result.get('email_id')}")
                return result
                
        except Exception as e:
            logger.error(f"❌ Failed to send password reset template email: {e}")
            return None
    
    async def check_mailhog(self):
        """Check MailHog for received emails"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.mailhog_url}/api/v2/messages")
                response.raise_for_status()
                
                messages = response.json()
                logger.info(f"📧 MailHog has {len(messages.get('items', []))} messages")
                
                # Show recent messages
                for i, msg in enumerate(messages.get('items', [])[:3]):  # Show last 3
                    subject = msg.get('Content', {}).get('Headers', {}).get('Subject', ['Unknown'])[0]
                    from_addr = msg.get('Content', {}).get('Headers', {}).get('From', ['Unknown'])[0]
                    to_addr = msg.get('Content', {}).get('Headers', {}).get('To', ['Unknown'])[0]
                    logger.info(f"  📨 Message {i+1}: '{subject}' from {from_addr} to {to_addr}")
                
                return len(messages.get('items', []))
                
        except Exception as e:
            logger.error(f"❌ Failed to check MailHog: {e}")
            return 0
    
    async def run_full_test(self):
        """Run complete email flow test"""
        logger.info("🚀 Starting notification service email flow test...")
        
        # Test service health
        if not await self.test_notification_service_health():
            logger.error("❌ Notification service is not healthy. Aborting test.")
            return False
        
        # Test SMTP connection
        if not await self.test_smtp_connection():
            logger.error("❌ SMTP connection failed. Aborting test.")
            return False
        
        # Count initial emails in MailHog
        initial_count = await self.check_mailhog()
        logger.info(f"📊 Initial email count in MailHog: {initial_count}")
        
        # Send test emails
        results = []
        results.append(await self.send_test_email())
        results.append(await self.send_welcome_template_email())
        results.append(await self.send_password_reset_template_email())
        
        # Wait a moment for emails to be processed
        await asyncio.sleep(2)
        
        # Check final count
        final_count = await self.check_mailhog()
        logger.info(f"📊 Final email count in MailHog: {final_count}")
        
        # Verify emails were sent
        emails_sent = sum(1 for r in results if r is not None)
        emails_received = final_count - initial_count
        
        logger.info(f"📈 Test Summary:")
        logger.info(f"  - Emails sent: {emails_sent}")
        logger.info(f"  - Emails received in MailHog: {emails_received}")
        
        success = emails_sent > 0 and emails_received >= emails_sent
        
        if success:
            logger.info("✅ Email flow test completed successfully!")
            logger.info(f"🌐 Check MailHog web interface at: http://localhost:8025")
        else:
            logger.error("❌ Email flow test failed!")
        
        return success

async def main():
    """Main test function"""
    tester = EmailFlowTester()
    success = await tester.run_full_test()
    
    if success:
        print("\n🎉 All tests passed! Your notification service is working with MailHog.")
        print("📧 Check http://localhost:8025 to see the emails in MailHog web interface.")
    else:
        print("\n💥 Some tests failed. Check the logs above for details.")
    
    return success

if __name__ == "__main__":
    asyncio.run(main())