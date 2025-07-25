"""
Template API Routes
Email template management endpoints
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
import logging

from app.services.template_service import get_template_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def list_templates():
    """
    List all available email templates
    
    Get a list of all available email templates with their metadata.
    """
    try:
        template_service = get_template_service()
        templates = await template_service.list_templates()
        
        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
        
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list templates")

@router.get("/{template_name}")
async def get_template(template_name: str):
    """
    Get a specific template
    
    Retrieve details of a specific email template including variables and metadata.
    """
    try:
        template_service = get_template_service()
        template = await template_service.get_template(template_name)
        
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
        
        return {
            "success": True,
            "template": template
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template")

@router.post("/{template_name}/preview")
async def preview_template(
    template_name: str,
    variables: Optional[Dict[str, Any]] = None
):
    """
    Preview a template with variables
    
    Render a template with provided variables to preview the final email content.
    """
    try:
        template_service = get_template_service()
        
        # Check if template exists
        template = await template_service.get_template(template_name)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
        
        # Render template with variables
        rendered_content = await template_service.render_template(
            template_name,
            variables or {}
        )
        
        return {
            "success": True,
            "template_name": template_name,
            "variables_used": variables or {},
            "rendered_content": rendered_content
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error previewing template: {e}")
        raise HTTPException(status_code=500, detail="Failed to preview template")

@router.get("/{template_name}/variables")
async def get_template_variables(template_name: str):
    """
    Get template variable requirements
    
    Get the list of variables that a template expects for proper rendering.
    """
    try:
        template_service = get_template_service()
        template = await template_service.get_template(template_name)
        
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
        
        return {
            "success": True,
            "template_name": template_name,
            "required_variables": template.get("variables", []),
            "description": template.get("description", ""),
            "subject_template": template.get("subject", "")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template variables: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template variables")

@router.post("/test-render")
async def test_template_rendering(
    template_name: str = Query(..., description="Template name to test"),
    test_variables: Optional[Dict[str, Any]] = None
):
    """
    Test template rendering with sample data
    
    Test template rendering with either provided variables or default test data.
    """
    try:
        template_service = get_template_service()
        
        # Check if template exists
        template = await template_service.get_template(template_name)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_name}' not found")
        
        # Use provided variables or generate test data
        if not test_variables:
            test_variables = _generate_test_variables(template_name)
        
        # Render template
        rendered_content = await template_service.render_template(
            template_name,
            test_variables
        )
        
        return {
            "success": True,
            "template_name": template_name,
            "test_variables": test_variables,
            "rendered_content": rendered_content,
            "character_counts": {
                "subject": len(rendered_content["subject"]),
                "html_content": len(rendered_content.get("html_content", "")),
                "text_content": len(rendered_content.get("text_content", ""))
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing template rendering: {e}")
        raise HTTPException(status_code=500, detail="Failed to test template rendering")

def _generate_test_variables(template_name: str) -> Dict[str, Any]:
    """Generate test variables for a template"""
    base_variables = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "john.doe@example.com",
        "platform_name": "SaaS Odoo Platform",
        "support_email": "support@saasodoo.local",
        "current_year": 2024
    }
    
    if template_name == "welcome":
        return {
            **base_variables,
            "login_url": "https://app.saasodoo.local/login"
        }
    elif template_name == "password_reset":
        return {
            **base_variables,
            "reset_url": "https://app.saasodoo.local/reset-password?token=abc123",
            "expires_in": "24 hours"
        }
    elif template_name == "instance_ready":
        return {
            **base_variables,
            "instance_name": "My Test Instance",
            "instance_url": "https://test-instance.saasodoo.local",
            "admin_email": "admin@test-instance.saasodoo.local"
        }
    elif template_name == "billing_reminder":
        return {
            **base_variables,
            "instance_name": "My Production Instance",
            "amount": "$25.00",
            "due_date": "2024-02-15",
            "payment_url": "https://app.saasodoo.local/billing/pay"
        }
    else:
        return base_variables