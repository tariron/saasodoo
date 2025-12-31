"""
Unit tests for TemplateService
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os


class TestTemplateService:
    """Test TemplateService class"""

    @pytest.fixture
    def template_service(self, mock_db_config, mock_app_config):
        """Create TemplateService instance with mocked configs"""
        with patch("app.services.template_service.get_db_config", return_value=mock_db_config):
            with patch("app.services.template_service.get_app_config", return_value=mock_app_config):
                from app.services.template_service import TemplateService
                # Use a test templates directory
                templates_dir = os.path.join(os.path.dirname(__file__), "..", "app", "templates")
                service = TemplateService(templates_dir=templates_dir)
                return service

    @pytest.mark.asyncio
    async def test_get_template_found(self, template_service, mock_db_pool, sample_template_data):
        """Test getting template metadata when found"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool

        # Mock the database row
        mock_row = MagicMock()
        for key, value in sample_template_data.items():
            setattr(mock_row, key, value)
        mock_row.keys = lambda: sample_template_data.keys()
        mock_row.__iter__ = lambda self: iter(sample_template_data.items())
        mock_row.__getitem__ = lambda self, key: sample_template_data[key]
        conn.fetchrow = AsyncMock(return_value=mock_row)

        result = await template_service.get_template("welcome")

        assert result is not None
        conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, template_service, mock_db_pool):
        """Test getting template when not found"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool
        conn.fetchrow = AsyncMock(return_value=None)

        result = await template_service.get_template("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_templates(self, template_service, mock_db_pool):
        """Test listing all templates"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool

        mock_rows = [
            {"id": "1", "name": "welcome", "category": "account"},
            {"id": "2", "name": "password_reset", "category": "account"},
        ]
        conn.fetch = AsyncMock(return_value=[
            MagicMock(**{**row, 'keys': lambda r=row: r.keys(), '__iter__': lambda s, r=row: iter(r.items())})
            for row in mock_rows
        ])

        result = await template_service.list_templates()

        assert isinstance(result, list)
        conn.fetch.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_templates_by_category(self, template_service, mock_db_pool):
        """Test listing templates filtered by category"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool

        mock_rows = [
            {"id": "1", "name": "billing_reminder", "category": "billing"},
        ]
        conn.fetch = AsyncMock(return_value=[
            MagicMock(**{**row, 'keys': lambda r=row: r.keys(), '__iter__': lambda s, r=row: iter(r.items())})
            for row in mock_rows
        ])

        result = await template_service.list_templates(category="billing")

        assert isinstance(result, list)
        # Verify category filter was passed
        call_args = conn.fetch.call_args
        assert "billing" in str(call_args)

    @pytest.mark.asyncio
    async def test_render_template_not_found(self, template_service, mock_db_pool):
        """Test rendering template when not found"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool
        conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(ValueError) as excinfo:
            await template_service.render_template("nonexistent", {})

        assert "not found" in str(excinfo.value).lower()

    def test_generate_sample_variables(self, template_service):
        """Test generating sample variables for preview"""
        variables = template_service._generate_sample_variables("welcome")

        assert "first_name" in variables
        assert "instance_name" in variables
        assert "instance_url" in variables

    def test_html_to_text_conversion(self, template_service):
        """Test HTML to text conversion"""
        html = "<h1>Title</h1><p>Paragraph</p><br><ul><li>Item 1</li><li>Item 2</li></ul>"
        text = template_service._html_to_text(html)

        assert "Title" in text
        assert "Paragraph" in text
        assert "- Item 1" in text
        assert "<" not in text  # No HTML tags

    def test_html_to_text_entities(self, template_service):
        """Test HTML entity decoding"""
        html = "&amp; &lt; &gt; &quot; &nbsp;"
        text = template_service._html_to_text(html)

        assert "&" in text
        assert "<" in text
        assert ">" in text

    def test_default_variables(self, template_service, mock_app_config):
        """Test default template variables"""
        assert "platform_name" in template_service.default_variables
        assert "support_email" in template_service.default_variables
        assert "current_year" in template_service.default_variables

    @pytest.mark.asyncio
    async def test_close_pool(self, template_service, mock_db_pool):
        """Test closing database pool"""
        pool, conn = mock_db_pool
        template_service._db_pool = pool
        pool.close = AsyncMock()

        await template_service.close()

        pool.close.assert_called_once()
        assert template_service._db_pool is None
