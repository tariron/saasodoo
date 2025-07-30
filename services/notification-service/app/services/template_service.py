"""
Template Service
Email template management and rendering
"""

from typing import Dict, Any, Optional, List
import logging
from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class TemplateService:
    """Template service for email template management"""
    
    def __init__(self):
        # Set up Jinja2 environment
        template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Built-in templates (in-memory for development)
        self._templates = {
            "welcome": {
                "name": "welcome",
                "subject": "Welcome to {{ platform_name }}!",
                "description": "Welcome email for new users",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "platform_name", "login_url"],
                "created_at": datetime.utcnow()
            },
            "password_reset": {
                "name": "password_reset",
                "subject": "Reset your password",
                "description": "Password reset email",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "reset_url", "expires_in"],
                "created_at": datetime.utcnow()
            },
            "instance_ready": {
                "name": "instance_ready",
                "subject": "Your Odoo instance is ready!",
                "description": "Notification when instance is provisioned",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "instance_url", "admin_email"],
                "created_at": datetime.utcnow()
            },
            "billing_reminder": {
                "name": "billing_reminder",
                "subject": "Payment reminder for {{ instance_name }}",
                "description": "Billing reminder for unpaid invoices",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "instance_name", "amount", "due_date", "payment_url"],
                "created_at": datetime.utcnow()
            },
            "payment_failure": {
                "name": "payment_failure",
                "subject": "Payment Failed - Action Required",
                "description": "Notification for failed payment processing",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "amount_due", "payment_method_url"],
                "created_at": datetime.utcnow()
            },
            "subscription_cancelled": {
                "name": "subscription_cancelled",
                "subject": "Subscription Cancelled - {{ subscription_name }}",
                "description": "Confirmation email for subscription cancellation",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "subscription_name", "end_date"],
                "created_at": datetime.utcnow()
            },
            "service_terminated": {
                "name": "service_terminated",
                "subject": "Service Terminated - {{ service_name }}",
                "description": "Notification for service termination",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "service_name", "backup_info"],
                "created_at": datetime.utcnow()
            },
            "invoice_created": {
                "name": "invoice_created",
                "subject": "New Invoice - {{ invoice_number }}",
                "description": "Notification for new invoice creation",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "invoice_number", "amount_due", "due_date", "payment_url"],
                "created_at": datetime.utcnow()
            },
            "subscription_expired": {
                "name": "subscription_expired",
                "subject": "Subscription Expired - {{ subscription_name }}",
                "description": "Notification for subscription expiration",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "subscription_name", "service_name"],
                "created_at": datetime.utcnow()
            },
            "overdue_payment": {
                "name": "overdue_payment",
                "subject": "Overdue Payment - Immediate Action Required",
                "description": "Notification for overdue payment with suspension warning",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "invoice_number", "amount_due", "days_overdue", "payment_url"],
                "created_at": datetime.utcnow()
            }
        }
    
    async def get_template(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Get template by name"""
        try:
            return self._templates.get(template_name)
        except Exception as e:
            logger.error(f"Failed to get template: {e}")
            raise
    
    async def list_templates(self) -> List[Dict[str, Any]]:
        """List all available templates"""
        try:
            return list(self._templates.values())
        except Exception as e:
            logger.error(f"Failed to list templates: {e}")
            raise
    
    async def render_template(self, template_name: str, variables: Dict[str, Any]) -> Dict[str, str]:
        """Render template with variables"""
        try:
            template_config = self._templates.get(template_name)
            if not template_config:
                raise ValueError(f"Template '{template_name}' not found")
            
            # Add default variables
            template_vars = {
                "platform_name": "SaaS Odoo Platform",
                "support_email": "support@saasodoo.local",
                "current_year": datetime.now().year,
                **variables
            }
            
            # Render subject
            subject_template = Template(template_config["subject"])
            rendered_subject = subject_template.render(**template_vars)
            
            # Render HTML content (if template file exists)
            html_content = None
            try:
                html_template = self.jinja_env.get_template(f"{template_name}.html")
                html_content = html_template.render(**template_vars)
            except Exception as e:
                logger.warning(f"HTML template not found for {template_name}: {e}")
                html_content = self._get_default_html_content(template_name, template_vars)
            
            # Render text content (if template file exists)
            text_content = None
            try:
                text_template = self.jinja_env.get_template(f"{template_name}.txt")
                text_content = text_template.render(**template_vars)
            except Exception as e:
                logger.warning(f"Text template not found for {template_name}: {e}")
                text_content = self._get_default_text_content(template_name, template_vars)
            
            return {
                "subject": rendered_subject,
                "html_content": html_content,
                "text_content": text_content
            }
            
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            raise
    
    def _get_default_html_content(self, template_name: str, variables: Dict[str, Any]) -> str:
        """Generate default HTML content for templates without files"""
        if template_name == "welcome":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2c3e50; text-align: center; margin-bottom: 30px;">Welcome to {variables.get('platform_name', 'SaaS Odoo Platform')}!</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Welcome to our platform! We're excited to have you on board.</p>
                    <p>You can now start using your Odoo instances and explore all the features we have to offer.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('login_url', '#')}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Get Started</a>
                    </div>
                    <p>If you have any questions, feel free to contact our support team at {variables.get('support_email', 'support@saasodoo.local')}.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "password_reset":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2c3e50; text-align: center; margin-bottom: 30px;">Reset Your Password</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We received a request to reset your password. Click the button below to set a new password:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('reset_url', '#')}" style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Reset Password</a>
                    </div>
                    <p>This link will expire in {variables.get('expires_in', '24 hours')}.</p>
                    <p>If you didn't request this password reset, you can safely ignore this email.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_ready":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">🎉 Your Odoo Instance is Ready!</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Great news! Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been successfully provisioned and is ready to use.</p>
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Instance Details:</h3>
                        <p><strong>Instance Name:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Admin Email:</strong> {variables.get('admin_email', 'N/A')}</p>
                        <p><strong>URL:</strong> <a href="{variables.get('instance_url', '#')}">{variables.get('instance_url', 'N/A')}</a></p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('instance_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Access Your Instance</a>
                    </div>
                    <p>You can now log in to your Odoo instance and start configuring your business processes.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "payment_failure":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e74c3c; text-align: center; margin-bottom: 30px;">⚠️ Payment Failed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We were unable to process your payment of <strong>${variables.get('amount_due', 'N/A')}</strong>. Your services may be suspended if payment is not received within 48 hours.</p>
                    <div style="background-color: #fdf2f2; padding: 20px; border-radius: 5px; border-left: 4px solid #e74c3c; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #e74c3c;">Action Required</h3>
                        <p>Please update your payment method or retry your payment to avoid service interruption.</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('payment_method_url', '#')}" style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Update Payment Method</a>
                    </div>
                    <p>If you need assistance, please contact our billing support team.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "subscription_cancelled":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #f39c12; text-align: center; margin-bottom: 30px;">Subscription Cancelled</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We've received your request to cancel your subscription: <strong>{variables.get('subscription_name', 'N/A')}</strong></p>
                    <div style="background-color: #fef9e7; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Cancellation Details</h3>
                        <p><strong>Subscription:</strong> {variables.get('subscription_name', 'N/A')}</p>
                        <p><strong>End Date:</strong> {variables.get('end_date', 'N/A')}</p>
                        <p>Your subscription will remain active until the end date above.</p>
                    </div>
                    <p>We're sorry to see you go! If you have feedback about your experience, we'd love to hear from you.</p>
                    <p>You can reactivate your subscription at any time before the end date.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "service_terminated":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #c0392b; text-align: center; margin-bottom: 30px;">Service Terminated</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your service <strong>{variables.get('service_name', 'N/A')}</strong> has been terminated due to subscription expiration.</p>
                    <div style="background-color: #fdedec; padding: 20px; border-radius: 5px; border-left: 4px solid #c0392b; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #c0392b;">Data Backup Information</h3>
                        <p>{variables.get('backup_info', 'Your data has been backed up and will be available for 30 days.')}</p>
                    </div>
                    <p>If you'd like to restore your service, please contact our support team or create a new subscription.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "invoice_created":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2980b9; text-align: center; margin-bottom: 30px;">📄 New Invoice</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>A new invoice has been generated for your account.</p>
                    <div style="background-color: #ebf3fd; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Invoice Details</h3>
                        <p><strong>Invoice Number:</strong> {variables.get('invoice_number', 'N/A')}</p>
                        <p><strong>Amount Due:</strong> ${variables.get('amount_due', 'N/A')}</p>
                        <p><strong>Due Date:</strong> {variables.get('due_date', 'N/A')}</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('payment_url', '#')}" style="background-color: #2980b9; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Pay Invoice</a>
                    </div>
                    <p>Please ensure payment is made by the due date to avoid any service interruption.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "subscription_expired":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e67e22; text-align: center; margin-bottom: 30px;">⏰ Subscription Expired</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your subscription <strong>{variables.get('subscription_name', 'N/A')}</strong> has expired.</p>
                    <div style="background-color: #fdf6e3; padding: 20px; border-radius: 5px; border-left: 4px solid #e67e22; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #e67e22;">Service Impact</h3>
                        <p>Your service <strong>{variables.get('service_name', 'N/A')}</strong> has been terminated due to subscription expiration.</p>
                        <p>To restore access, please renew your subscription or contact our support team.</p>
                    </div>
                    <p>We'd love to have you back! Contact us to discuss renewal options that work for your needs.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "overdue_payment":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #c0392b; text-align: center; margin-bottom: 30px;">🚨 Overdue Payment - Urgent</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p><strong>URGENT:</strong> Your payment is now <strong>{variables.get('days_overdue', 'N/A')} days overdue</strong>. Your services have been suspended to prevent further charges.</p>
                    <div style="background-color: #fdedec; padding: 20px; border-radius: 5px; border-left: 4px solid #c0392b; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #c0392b;">Payment Details</h3>
                        <p><strong>Invoice Number:</strong> {variables.get('invoice_number', 'N/A')}</p>
                        <p><strong>Amount Due:</strong> ${variables.get('amount_due', 'N/A')}</p>
                        <p><strong>Days Overdue:</strong> {variables.get('days_overdue', 'N/A')} days</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('payment_url', '#')}" style="background-color: #c0392b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Pay Now to Restore Service</a>
                    </div>
                    <p><strong>Important:</strong> Pay immediately to restore your services. Continued non-payment may result in account termination and data loss.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        else:
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
                <h1>Email from {variables.get('platform_name', 'SaaS Odoo Platform')}</h1>
                <p>This is a default template for {template_name}.</p>
                <p>Template variables: {variables}</p>
            </body>
            </html>
            """
    
    def _get_default_text_content(self, template_name: str, variables: Dict[str, Any]) -> str:
        """Generate default text content for templates without files"""
        if template_name == "welcome":
            return f"""
Welcome to {variables.get('platform_name', 'SaaS Odoo Platform')}!

Hello {variables.get('first_name', 'there')},

Welcome to our platform! We're excited to have you on board.

You can now start using your Odoo instances and explore all the features we have to offer.

Get Started: {variables.get('login_url', '#')}

If you have any questions, feel free to contact our support team at {variables.get('support_email', 'support@saasodoo.local')}.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "password_reset":
            return f"""
Reset Your Password

Hello {variables.get('first_name', 'there')},

We received a request to reset your password. Use the link below to set a new password:

{variables.get('reset_url', '#')}

This link will expire in {variables.get('expires_in', '24 hours')}.

If you didn't request this password reset, you can safely ignore this email.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_ready":
            return f"""
Your Odoo Instance is Ready!

Hello {variables.get('first_name', 'there')},

Great news! Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been successfully provisioned and is ready to use.

Instance Details:
- Instance Name: {variables.get('instance_name', 'N/A')}
- Admin Email: {variables.get('admin_email', 'N/A')}
- URL: {variables.get('instance_url', 'N/A')}

Access your instance: {variables.get('instance_url', '#')}

You can now log in to your Odoo instance and start configuring your business processes.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "payment_failure":
            return f"""
Payment Failed - Action Required

Hello {variables.get('first_name', 'there')},

We were unable to process your payment of ${variables.get('amount_due', 'N/A')}. Your services may be suspended if payment is not received within 48 hours.

ACTION REQUIRED:
Please update your payment method or retry your payment to avoid service interruption.

Update Payment Method: {variables.get('payment_method_url', '#')}

If you need assistance, please contact our billing support team.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "subscription_cancelled":
            return f"""
Subscription Cancelled

Hello {variables.get('first_name', 'there')},

We've received your request to cancel your subscription: {variables.get('subscription_name', 'N/A')}

Cancellation Details:
- Subscription: {variables.get('subscription_name', 'N/A')}
- End Date: {variables.get('end_date', 'N/A')}

Your subscription will remain active until the end date above.

We're sorry to see you go! If you have feedback about your experience, we'd love to hear from you.

You can reactivate your subscription at any time before the end date.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "service_terminated":
            return f"""
Service Terminated

Hello {variables.get('first_name', 'there')},

Your service {variables.get('service_name', 'N/A')} has been terminated due to subscription expiration.

Data Backup Information:
{variables.get('backup_info', 'Your data has been backed up and will be available for 30 days.')}

If you'd like to restore your service, please contact our support team or create a new subscription.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "invoice_created":
            return f"""
New Invoice - {variables.get('invoice_number', 'N/A')}

Hello {variables.get('first_name', 'there')},

A new invoice has been generated for your account.

Invoice Details:
- Invoice Number: {variables.get('invoice_number', 'N/A')}
- Amount Due: ${variables.get('amount_due', 'N/A')}
- Due Date: {variables.get('due_date', 'N/A')}

Pay Invoice: {variables.get('payment_url', '#')}

Please ensure payment is made by the due date to avoid any service interruption.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "subscription_expired":
            return f"""
Subscription Expired

Hello {variables.get('first_name', 'there')},

Your subscription {variables.get('subscription_name', 'N/A')} has expired.

Service Impact:
Your service {variables.get('service_name', 'N/A')} has been terminated due to subscription expiration.

To restore access, please renew your subscription or contact our support team.

We'd love to have you back! Contact us to discuss renewal options that work for your needs.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "overdue_payment":
            return f"""
URGENT: Overdue Payment - Immediate Action Required

Hello {variables.get('first_name', 'there')},

URGENT: Your payment is now {variables.get('days_overdue', 'N/A')} days overdue. Your services have been suspended to prevent further charges.

Payment Details:
- Invoice Number: {variables.get('invoice_number', 'N/A')}
- Amount Due: ${variables.get('amount_due', 'N/A')}
- Days Overdue: {variables.get('days_overdue', 'N/A')} days

Pay Now to Restore Service: {variables.get('payment_url', '#')}

IMPORTANT: Pay immediately to restore your services. Continued non-payment may result in account termination and data loss.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        else:
            return f"""
Email from {variables.get('platform_name', 'SaaS Odoo Platform')}

This is a default template for {template_name}.

Template variables: {variables}
            """

# Global template service instance
template_service = TemplateService()

def get_template_service() -> TemplateService:
    """Get template service instance"""
    return template_service