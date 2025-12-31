"""
Template Service
Database-backed template metadata with Jinja2 file rendering
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

import asyncpg
from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound

from app.utils.config import get_db_config, get_app_config

logger = logging.getLogger(__name__)


class TemplateService:
    """Template service for file-based Jinja2 templates with database metadata"""

    def __init__(self, templates_dir: str = None):
        app_config = get_app_config()

        self.templates_dir = templates_dir or os.path.join(
            os.path.dirname(__file__), "..", "templates"
        )

        self.jinja_env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Default template variables available to all templates
        self.default_variables = {
            "platform_name": app_config.platform_name,
            "support_email": app_config.support_email,
            "support_url": app_config.support_url,
            "current_year": datetime.now().year,
        }

        self._db_pool: Optional[asyncpg.Pool] = None

    async def get_db_pool(self) -> asyncpg.Pool:
        """Get or create database connection pool"""
        if self._db_pool is None:
            db_config = get_db_config()
            self._db_pool = await asyncpg.create_pool(
                host=db_config.postgres_host,
                port=db_config.postgres_port,
                database=db_config.db_name,
                user=db_config.db_service_user,
                password=db_config.db_service_password,
                min_size=2,
                max_size=10
            )
            logger.info("Template service database pool created")
        return self._db_pool

    async def close(self):
        """Close database pool"""
        if self._db_pool:
            await self._db_pool.close()
            self._db_pool = None

    async def get_template(self, template_name: str) -> Optional[Dict[str, Any]]:
        """Get template metadata from database"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, name, display_name, description, subject_template,
                       from_email, from_name, category, variables, is_active
                FROM email_templates
                WHERE name = $1 AND is_active = true
                """,
                template_name
            )
            if row:
                result = dict(row)
                if result.get('variables') and isinstance(result['variables'], str):
                    result['variables'] = json.loads(result['variables'])
                return result
            return None

    async def list_templates(self, category: str = None) -> List[Dict[str, Any]]:
        """List all available templates, optionally filtered by category"""
        pool = await self.get_db_pool()
        async with pool.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    """
                    SELECT id, name, display_name, description, category, is_active
                    FROM email_templates
                    WHERE category = $1 AND is_active = true
                    ORDER BY name
                    """,
                    category
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, name, display_name, description, category, is_active
                    FROM email_templates
                    WHERE is_active = true
                    ORDER BY category, name
                    """
                )
            return [dict(row) for row in rows]

    async def render_template(
        self,
        template_name: str,
        variables: Dict[str, Any]
    ) -> Dict[str, str]:
        """Render template with variables"""

        # Get template metadata from database
        template_info = await self.get_template(template_name)
        if not template_info:
            raise ValueError(f"Template '{template_name}' not found or inactive")

        # Merge variables with defaults
        template_vars = {
            **self.default_variables,
            **variables
        }

        # Render subject from database subject_template
        from jinja2 import Template
        subject_template = Template(template_info["subject_template"])
        rendered_subject = subject_template.render(**template_vars)

        # Determine template category for file path
        category = template_info.get("category", "system")

        # Render HTML template from file
        html_content = None
        try:
            html_template = self.jinja_env.get_template(f"{category}/{template_name}.html.j2")
            html_content = html_template.render(**template_vars)
        except TemplateNotFound:
            logger.warning(f"HTML template not found: {category}/{template_name}.html.j2")

        # Render text template from file
        text_content = None
        try:
            text_template = self.jinja_env.get_template(f"{category}/{template_name}.txt.j2")
            text_content = text_template.render(**template_vars)
        except TemplateNotFound:
            logger.warning(f"Text template not found: {category}/{template_name}.txt.j2")
            # Generate basic text from HTML if no text template
            if html_content:
                text_content = self._html_to_text(html_content)

        if not html_content and not text_content:
            raise ValueError(f"No template files found for '{template_name}'")

        return {
            "subject": rendered_subject,
            "html_content": html_content,
            "text_content": text_content
        }

    async def preview_template(
        self,
        template_name: str,
        sample_variables: Dict[str, Any] = None
    ) -> Dict[str, str]:
        """Preview template with sample data"""
        variables = sample_variables or self._generate_sample_variables(template_name)
        return await self.render_template(template_name, variables)

    async def get_template_variables(self, template_name: str) -> List[str]:
        """Get required variables for a template"""
        template_info = await self.get_template(template_name)
        if not template_info:
            raise ValueError(f"Template '{template_name}' not found")
        return template_info.get('variables', [])

    def _generate_sample_variables(self, template_name: str) -> Dict[str, Any]:
        """Generate sample variables for template preview"""
        return {
            "first_name": "John",
            "instance_name": "demo-instance",
            "instance_url": "https://demo.odoo.saasodoo.com",
            "admin_email": "admin@example.com",
            "admin_password": "SamplePassword123!",
            "amount": "49.99",
            "invoice_number": "INV-2025-0001",
            "due_date": datetime.now().strftime("%Y-%m-%d"),
            "backup_name": "backup-2025-01-01",
            "backup_size": "1.5 GB",
            "reset_url": "https://app.saasodoo.com/reset?token=sample",
            "verification_url": "https://app.saasodoo.com/verify?token=sample",
            "expiry_hours": "24",
            "error_message": "Sample error message for preview",
            "reason": "Sample reason for preview",
            "end_date": datetime.now().strftime("%Y-%m-%d"),
            "payment_url": "https://app.saasodoo.com/billing",
            "renewal_url": "https://app.saasodoo.com/renew",
            "days_overdue": "7",
            "payment_date": datetime.now().strftime("%Y-%m-%d"),
            "error_reason": "Card declined",
            "retry_url": "https://app.saasodoo.com/billing/retry",
            "invoice_url": "https://app.saasodoo.com/invoice/123",
            "backup_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "restore_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "maintenance_start": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "maintenance_end": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "description": "Sample maintenance description",
        }

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text (basic conversion)"""
        import re

        # Remove HTML tags
        text = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        text = re.sub(r'<p[^>]*>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<li[^>]*>', '- ', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)

        # Decode HTML entities
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&quot;', '"')

        # Clean up whitespace
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = text.strip()

        return text


# Global instance
_template_service: Optional[TemplateService] = None


def get_template_service() -> TemplateService:
    """Get template service singleton"""
    global _template_service
    if _template_service is None:
        _template_service = TemplateService()
    return _template_service
