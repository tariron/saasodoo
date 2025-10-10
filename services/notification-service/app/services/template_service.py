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
            "email_verification": {
                "name": "email_verification",
                "subject": "Verify your email address",
                "description": "Email verification for new user accounts",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "verification_url", "expires_in"],
                "created_at": datetime.utcnow()
            },
            "instance_ready": {
                "name": "instance_ready",
                "subject": "Your Odoo instance is ready!",
                "description": "Notification when instance is provisioned",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "instance_url", "admin_email", "admin_password"],
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
            },
            "instance_provisioning_started": {
                "name": "instance_provisioning_started",
                "subject": "Your Odoo instance is being prepared",
                "description": "Notification when instance provisioning begins",
                "from_email": "noreply@saasodoo.local",  
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "estimated_time"],
                "created_at": datetime.utcnow()
            },
            "instance_provisioning_failed": {
                "name": "instance_provisioning_failed",
                "subject": "Instance provisioning failed",
                "description": "Notification when instance provisioning fails",
                "from_email": "support@saasodoo.local",
                "from_name": "SaaS Odoo Support",
                "variables": ["first_name", "instance_name", "error_reason", "support_url"],
                "created_at": datetime.utcnow()
            },
            "instance_creation_failed": {
                "name": "instance_creation_failed",
                "subject": "Instance creation failed",
                "description": "Notification when instance creation fails during validation or setup",
                "from_email": "support@saasodoo.local",
                "from_name": "SaaS Odoo Support",
                "variables": ["instance_name", "subscription_id", "error_reason", "support_url"],
                "created_at": datetime.utcnow()
            },
            "instance_stopped": {
                "name": "instance_stopped",
                "subject": "Instance stopped - {{ instance_name }}",
                "description": "Notification when instance is stopped",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "reason"],
                "created_at": datetime.utcnow()
            },
            "instance_started": {
                "name": "instance_started",
                "subject": "Instance started - {{ instance_name }}",
                "description": "Notification when instance is started",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "instance_url"],
                "created_at": datetime.utcnow()
            },
            "instance_suspended": {
                "name": "instance_suspended",
                "subject": "Instance suspended - {{ instance_name }}",
                "description": "Notification when instance is suspended due to billing issues",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "instance_name", "reason", "payment_url"],
                "created_at": datetime.utcnow()
            },
            "instance_resumed": {
                "name": "instance_resumed",
                "subject": "Instance restored - {{ instance_name }}",
                "description": "Notification when instance is restored after suspension",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "instance_url"],
                "created_at": datetime.utcnow()
            },
            "instance_deleted": {
                "name": "instance_deleted",
                "subject": "Instance permanently deleted - {{ instance_name }}",
                "description": "Notification when instance is permanently deleted",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform", 
                "variables": ["first_name", "instance_name", "backup_info"],
                "created_at": datetime.utcnow()
            },
            "maintenance_notification": {
                "name": "maintenance_notification",
                "subject": "Scheduled maintenance - {{ instance_name }}",
                "description": "Notification for scheduled maintenance window",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "maintenance_start", "maintenance_end", "expected_downtime"],
                "created_at": datetime.utcnow()
            },
            "payment_received": {
                "name": "payment_received",
                "subject": "Payment received - {{ amount }}",
                "description": "Notification when payment is successfully processed",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "amount", "payment_method", "transaction_id"],
                "created_at": datetime.utcnow()
            },
            "invoice_paid": {
                "name": "invoice_paid",
                "subject": "Invoice paid - {{ invoice_number }}",
                "description": "Notification when invoice is paid in full",
                "from_email": "billing@saasodoo.local",
                "from_name": "SaaS Odoo Billing",
                "variables": ["first_name", "invoice_number", "amount_paid", "payment_date"],
                "created_at": datetime.utcnow()
            },
            "backup_completed": {
                "name": "backup_completed",
                "subject": "Backup completed - {{ instance_name }}",
                "description": "Notification when instance backup completes successfully",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "backup_name", "backup_size", "backup_date"],
                "created_at": datetime.utcnow()
            },
            "backup_failed": {
                "name": "backup_failed",
                "subject": "Backup failed - {{ instance_name }}",
                "description": "Notification when instance backup fails",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "error_message", "support_url"],
                "created_at": datetime.utcnow()
            },
            "restore_completed": {
                "name": "restore_completed",
                "subject": "Restore completed - {{ instance_name }}",
                "description": "Notification when instance restore completes successfully",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "backup_name", "restore_date", "instance_url"],
                "created_at": datetime.utcnow()
            },
            "restore_failed": {
                "name": "restore_failed",
                "subject": "Restore failed - {{ instance_name }}",
                "description": "Notification when instance restore fails",
                "from_email": "noreply@saasodoo.local",
                "from_name": "SaaS Odoo Platform",
                "variables": ["first_name", "instance_name", "backup_name", "error_message", "support_url"],
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
        elif template_name == "email_verification":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2c3e50; text-align: center; margin-bottom: 30px;">Verify Your Email Address</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Thank you for registering with {variables.get('platform_name', 'SaaS Odoo Platform')}! To complete your account setup, please verify your email address.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('verification_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Verify Email Address</a>
                    </div>
                    <p>This verification link will expire in {variables.get('expires_in', '24 hours')}.</p>
                    <p>If you didn't create an account with us, you can safely ignore this email.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">If you're having trouble clicking the button, copy and paste this URL into your browser:<br>
                    <a href="{variables.get('verification_url', '#')}" style="color: #3498db;">{variables.get('verification_url', '#')}</a></p>
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
                        <p><strong>Admin Password:</strong> <code style="background-color: #e8f5e9; padding: 4px 8px; border-radius: 3px; font-family: monospace; font-size: 14px;">{variables.get('admin_password', 'N/A')}</code></p>
                        <p><strong>URL:</strong> <a href="{variables.get('instance_url', '#')}">{variables.get('instance_url', 'N/A')}</a></p>
                    </div>
                    <div style="background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 20px 0;">
                        <p style="margin: 0;"><strong>🔒 Security Note:</strong> Please change your password after your first login. This password is only sent once for security reasons.</p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('instance_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Access Your Instance</a>
                    </div>
                    <p>You can now log in to your Odoo instance using the credentials above and start configuring your business processes.</p>
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
        elif template_name == "payment_received":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">✅ Payment Received</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Thank you! We have successfully received your payment.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Payment Details</h3>
                        <p><strong>Amount:</strong> ${variables.get('amount', 'N/A')}</p>
                        <p><strong>Payment Method:</strong> {variables.get('payment_method', 'N/A')}</p>
                        <p><strong>Transaction ID:</strong> {variables.get('transaction_id', 'N/A')}</p>
                    </div>
                    <p>Your account has been updated and your services will continue without interruption.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "invoice_paid":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">✅ Invoice Paid</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Great news! Your invoice has been paid in full.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Payment Details</h3>
                        <p><strong>Invoice Number:</strong> {variables.get('invoice_number', 'N/A')}</p>
                        <p><strong>Amount Paid:</strong> ${variables.get('amount_paid', 'N/A')}</p>
                        <p><strong>Payment Date:</strong> {variables.get('payment_date', 'N/A')}</p>
                    </div>
                    <p>Thank you for your payment. Your services will continue uninterrupted.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "backup_completed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">✅ Backup Completed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Great news! Your instance backup has been completed successfully.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Backup Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Backup Name:</strong> {variables.get('backup_name', 'N/A')}</p>
                        <p><strong>Backup Size:</strong> {variables.get('backup_size', 'N/A')}</p>
                        <p><strong>Created:</strong> {variables.get('backup_date', 'N/A')}</p>
                    </div>
                    <p>Your data has been safely backed up and can be restored at any time through your dashboard.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "backup_failed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e74c3c; text-align: center; margin-bottom: 30px;">❌ Backup Failed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We encountered an issue while creating a backup of your instance <strong>{variables.get('instance_name', 'N/A')}</strong>.</p>
                    <div style="background-color: #fdedec; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #e74c3c;">
                        <h3 style="margin-top: 0; color: #c0392b;">Error Details</h3>
                        <p><strong>Error:</strong> {variables.get('error_message', 'Unknown error occurred')}</p>
                    </div>
                    <p>Please try again later or contact our support team if the problem persists.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('support_url', '#')}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Contact Support</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "restore_completed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">✅ Restore Completed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Excellent! Your instance has been successfully restored from backup.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Restore Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Backup Used:</strong> {variables.get('backup_name', 'N/A')}</p>
                        <p><strong>Restored:</strong> {variables.get('restore_date', 'N/A')}</p>
                    </div>
                    <p>Your instance is now running with the restored data and ready to use.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('instance_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Access Instance</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "restore_failed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e74c3c; text-align: center; margin-bottom: 30px;">❌ Restore Failed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We encountered an issue while restoring your instance <strong>{variables.get('instance_name', 'N/A')}</strong> from backup <strong>{variables.get('backup_name', 'N/A')}</strong>.</p>
                    <div style="background-color: #fdedec; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #e74c3c;">
                        <h3 style="margin-top: 0; color: #c0392b;">Error Details</h3>
                        <p><strong>Error:</strong> {variables.get('error_message', 'Unknown error occurred')}</p>
                    </div>
                    <p>Your instance remains in its previous state. Please try again later or contact our support team for assistance.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('support_url', '#')}" style="background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Contact Support</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© 2025 SaaS Odoo Platform. All rights reserved.</p>
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
        elif template_name == "instance_provisioning_started":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #3498db; text-align: center; margin-bottom: 30px;">🚀 Instance Provisioning Started</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Great news! We've started provisioning your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong>.</p>
                    <div style="background-color: #ebf3fd; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Provisioning Details</h3>
                        <p><strong>Instance Name:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Estimated Time:</strong> {variables.get('estimated_time', '10-15 minutes')}</p>
                        <p>We're setting up your database, configuring your Odoo instance, and preparing everything for you.</p>
                    </div>
                    <p>You'll receive another email once your instance is ready to use. You can also check the status in your dashboard.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_provisioning_failed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e74c3c; text-align: center; margin-bottom: 30px;">❌ Instance Provisioning Failed</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We're sorry, but the provisioning of your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has failed.</p>
                    <div style="background-color: #fdf2f2; padding: 20px; border-radius: 5px; border-left: 4px solid #e74c3c; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #e74c3c;">Error Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Error:</strong> {variables.get('error_reason', 'Unknown error occurred during provisioning')}</p>
                    </div>
                    <p>Our technical team has been automatically notified and will investigate this issue. You can try provisioning again or contact our support team for assistance.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('support_url', '#')}" style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Contact Support</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_creation_failed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e74c3c; text-align: center; margin-bottom: 30px;">❌ Instance Creation Failed</h1>
                    <p>Hello,</p>
                    <p>We're sorry, but the creation of your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has failed.</p>
                    <div style="background-color: #fdf2f2; padding: 20px; border-radius: 5px; border-left: 4px solid #e74c3c; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #e74c3c;">Error Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Subscription ID:</strong> {variables.get('subscription_id', 'N/A')}</p>
                        <p><strong>Error:</strong> {variables.get('error_reason', 'Unknown error occurred during instance creation')}</p>
                    </div>
                    <p>This may have occurred due to validation errors (such as reserved names or invalid configuration) or system issues. Please check your configuration and try again.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('support_url', '#')}" style="background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Contact Support</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_stopped":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #f39c12; text-align: center; margin-bottom: 30px;">⏸️ Instance Stopped</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been stopped.</p>
                    <div style="background-color: #fef9e7; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Instance Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Reason:</strong> {variables.get('reason', 'Instance stopped by user request')}</p>
                    </div>
                    <p>Your data is safely stored and you can restart your instance at any time from your dashboard.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_started":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">▶️ Instance Started</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been successfully started and is now accessible.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Instance Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Status:</strong> Running</p>
                        <p><strong>URL:</strong> <a href="{variables.get('instance_url', '#')}">{variables.get('instance_url', 'N/A')}</a></p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('instance_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Access Your Instance</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_suspended":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #e67e22; text-align: center; margin-bottom: 30px;">⚠️ Instance Suspended</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been suspended.</p>
                    <div style="background-color: #fdf6e3; padding: 20px; border-radius: 5px; border-left: 4px solid #e67e22; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #e67e22;">Suspension Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Reason:</strong> {variables.get('reason', 'Billing issue - payment required')}</p>
                    </div>
                    <p>To restore access to your instance, please resolve the billing issue by updating your payment method.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('payment_url', '#')}" style="background-color: #e67e22; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Update Payment Method</a>
                    </div>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_resumed":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #27ae60; text-align: center; margin-bottom: 30px;">✅ Instance Restored</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Great news! Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been restored and is now accessible again.</p>
                    <div style="background-color: #eafaf1; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Instance Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Status:</strong> Active and Running</p>
                        <p><strong>URL:</strong> <a href="{variables.get('instance_url', '#')}">{variables.get('instance_url', 'N/A')}</a></p>
                    </div>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{variables.get('instance_url', '#')}" style="background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block;">Access Your Instance</a>
                    </div>
                    <p>Thank you for resolving the billing issue. Your instance is now fully operational.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "instance_deleted":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #c0392b; text-align: center; margin-bottom: 30px;">🗑️ Instance Permanently Deleted</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>Your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong> has been permanently deleted as requested.</p>
                    <div style="background-color: #fdedec; padding: 20px; border-radius: 5px; border-left: 4px solid #c0392b; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #c0392b;">Deletion Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Data Backup:</strong> {variables.get('backup_info', 'All data has been permanently removed')}</p>
                    </div>
                    <p><strong>Important:</strong> This action cannot be undone. All data, configurations, and customizations have been permanently removed.</p>
                    <p>If you need to create a new instance, you can do so from your dashboard at any time.</p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #666; text-align: center;">© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.</p>
                </div>
            </body>
            </html>
            """
        elif template_name == "maintenance_notification":
            return f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2980b9; text-align: center; margin-bottom: 30px;">🔧 Scheduled Maintenance</h1>
                    <p>Hello {variables.get('first_name', 'there')},</p>
                    <p>We have scheduled maintenance for your Odoo instance <strong>{variables.get('instance_name', 'your instance')}</strong>.</p>
                    <div style="background-color: #ebf3fd; padding: 20px; border-radius: 5px; margin: 20px 0;">
                        <h3 style="margin-top: 0;">Maintenance Details</h3>
                        <p><strong>Instance:</strong> {variables.get('instance_name', 'N/A')}</p>
                        <p><strong>Start Time:</strong> {variables.get('maintenance_start', 'N/A')}</p>
                        <p><strong>End Time:</strong> {variables.get('maintenance_end', 'N/A')}</p>
                        <p><strong>Expected Downtime:</strong> {variables.get('expected_downtime', 'Minimal')}</p>
                    </div>
                    <p>During this maintenance window, your instance may be temporarily unavailable. We apologize for any inconvenience and will work to minimize downtime.</p>
                    <p>No action is required from you. Your instance will be automatically restored after maintenance is complete.</p>
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
        elif template_name == "email_verification":
            return f"""
Verify Your Email Address

Hello {variables.get('first_name', 'there')},

Thank you for registering with {variables.get('platform_name', 'SaaS Odoo Platform')}! To complete your account setup, please verify your email address.

Click here to verify your email: {variables.get('verification_url', '#')}

This verification link will expire in {variables.get('expires_in', '24 hours')}.

If you didn't create an account with us, you can safely ignore this email.

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
        elif template_name == "payment_received":
            return f"""
Payment Received - ${variables.get('amount', 'N/A')}

Hello {variables.get('first_name', 'there')},

Thank you! We have successfully received your payment.

Payment Details:
- Amount: ${variables.get('amount', 'N/A')}
- Payment Method: {variables.get('payment_method', 'N/A')}
- Transaction ID: {variables.get('transaction_id', 'N/A')}

Your account has been updated and your services will continue without interruption.

© 2025 SaaS Odoo Platform. All rights reserved.
            """
        elif template_name == "invoice_paid":
            return f"""
Invoice Paid - {variables.get('invoice_number', 'N/A')}

Hello {variables.get('first_name', 'there')},

Great news! Your invoice has been paid in full.

Payment Details:
- Invoice Number: {variables.get('invoice_number', 'N/A')}
- Amount Paid: ${variables.get('amount_paid', 'N/A')}
- Payment Date: {variables.get('payment_date', 'N/A')}

Thank you for your payment. Your services will continue uninterrupted.

© 2025 SaaS Odoo Platform. All rights reserved.
            """
        elif template_name == "backup_completed":
            return f"""
Backup Completed - {variables.get('instance_name', 'N/A')}

Hello {variables.get('first_name', 'there')},

Great news! Your instance backup has been completed successfully.

Backup Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Backup Name: {variables.get('backup_name', 'N/A')}
- Backup Size: {variables.get('backup_size', 'N/A')}
- Created: {variables.get('backup_date', 'N/A')}

Your data has been safely backed up and can be restored at any time through your dashboard.

© 2025 SaaS Odoo Platform. All rights reserved.
            """
        elif template_name == "backup_failed":
            return f"""
Backup Failed - {variables.get('instance_name', 'N/A')}

Hello {variables.get('first_name', 'there')},

We encountered an issue while creating a backup of your instance "{variables.get('instance_name', 'N/A')}".

Error Details:
- Error: {variables.get('error_message', 'Unknown error occurred')}

Please try again later or contact our support team if the problem persists.

Support: {variables.get('support_url', 'Contact support through your dashboard')}

© 2025 SaaS Odoo Platform. All rights reserved.
            """
        elif template_name == "restore_completed":
            return f"""
Restore Completed - {variables.get('instance_name', 'N/A')}

Hello {variables.get('first_name', 'there')},

Excellent! Your instance has been successfully restored from backup.

Restore Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Backup Used: {variables.get('backup_name', 'N/A')}
- Restored: {variables.get('restore_date', 'N/A')}

Your instance is now running with the restored data and ready to use.

Access your instance: {variables.get('instance_url', 'Check your dashboard for access details')}

© 2025 SaaS Odoo Platform. All rights reserved.
            """
        elif template_name == "restore_failed":
            return f"""
Restore Failed - {variables.get('instance_name', 'N/A')}

Hello {variables.get('first_name', 'there')},

We encountered an issue while restoring your instance "{variables.get('instance_name', 'N/A')}" from backup "{variables.get('backup_name', 'N/A')}".

Error Details:
- Error: {variables.get('error_message', 'Unknown error occurred')}

Your instance remains in its previous state. Please try again later or contact our support team for assistance.

Support: {variables.get('support_url', 'Contact support through your dashboard')}

© 2025 SaaS Odoo Platform. All rights reserved.
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
        elif template_name == "instance_provisioning_started":
            return f"""
Instance Provisioning Started

Hello {variables.get('first_name', 'there')},

Great news! We've started provisioning your Odoo instance "{variables.get('instance_name', 'your instance')}".

Provisioning Details:
- Instance Name: {variables.get('instance_name', 'N/A')}
- Estimated Time: {variables.get('estimated_time', '10-15 minutes')}

We're setting up your database, configuring your Odoo instance, and preparing everything for you.

You'll receive another email once your instance is ready to use. You can also check the status in your dashboard.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_provisioning_failed":
            return f"""
Instance Provisioning Failed

Hello {variables.get('first_name', 'there')},

We're sorry, but the provisioning of your Odoo instance "{variables.get('instance_name', 'your instance')}" has failed.

Error Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Error: {variables.get('error_reason', 'Unknown error occurred during provisioning')}

Our technical team has been automatically notified and will investigate this issue. You can try provisioning again or contact our support team for assistance.

Contact Support: {variables.get('support_url', '#')}

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_creation_failed":
            return f"""
Instance Creation Failed

Hello,

We're sorry, but the creation of your Odoo instance "{variables.get('instance_name', 'your instance')}" has failed.

Error Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Subscription ID: {variables.get('subscription_id', 'N/A')}
- Error: {variables.get('error_reason', 'Unknown error occurred during instance creation')}

This may have occurred due to validation errors (such as reserved names or invalid configuration) or system issues. Please check your configuration and try again.

Contact Support: {variables.get('support_url', '#')}

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_stopped":
            return f"""
Instance Stopped

Hello {variables.get('first_name', 'there')},

Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been stopped.

Instance Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Reason: {variables.get('reason', 'Instance stopped by user request')}

Your data is safely stored and you can restart your instance at any time from your dashboard.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_started":
            return f"""
Instance Started

Hello {variables.get('first_name', 'there')},

Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been successfully started and is now accessible.

Instance Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Status: Running
- URL: {variables.get('instance_url', 'N/A')}

Access your instance: {variables.get('instance_url', '#')}

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_suspended":
            return f"""
Instance Suspended

Hello {variables.get('first_name', 'there')},

Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been suspended.

Suspension Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Reason: {variables.get('reason', 'Billing issue - payment required')}

To restore access to your instance, please resolve the billing issue by updating your payment method.

Update Payment Method: {variables.get('payment_url', '#')}

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_resumed":
            return f"""
Instance Restored

Hello {variables.get('first_name', 'there')},

Great news! Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been restored and is now accessible again.

Instance Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Status: Active and Running
- URL: {variables.get('instance_url', 'N/A')}

Access your instance: {variables.get('instance_url', '#')}

Thank you for resolving the billing issue. Your instance is now fully operational.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "instance_deleted":
            return f"""
Instance Permanently Deleted

Hello {variables.get('first_name', 'there')},

Your Odoo instance "{variables.get('instance_name', 'your instance')}" has been permanently deleted as requested.

Deletion Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Data Backup: {variables.get('backup_info', 'All data has been permanently removed')}

IMPORTANT: This action cannot be undone. All data, configurations, and customizations have been permanently removed.

If you need to create a new instance, you can do so from your dashboard at any time.

© {variables.get('current_year')} {variables.get('platform_name', 'SaaS Odoo Platform')}. All rights reserved.
            """
        elif template_name == "maintenance_notification":
            return f"""
Scheduled Maintenance

Hello {variables.get('first_name', 'there')},

We have scheduled maintenance for your Odoo instance "{variables.get('instance_name', 'your instance')}".

Maintenance Details:
- Instance: {variables.get('instance_name', 'N/A')}
- Start Time: {variables.get('maintenance_start', 'N/A')}
- End Time: {variables.get('maintenance_end', 'N/A')}
- Expected Downtime: {variables.get('expected_downtime', 'Minimal')}

During this maintenance window, your instance may be temporarily unavailable. We apologize for any inconvenience and will work to minimize downtime.

No action is required from you. Your instance will be automatically restored after maintenance is complete.

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