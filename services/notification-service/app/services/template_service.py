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