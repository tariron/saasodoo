"""
Validation utilities for tenant service
"""

from typing import Dict, Any, List
from uuid import UUID

from app.models.tenant import TenantPlan, TenantStatus


def validate_tenant_limits(plan: TenantPlan, max_instances: int, max_users: int) -> List[str]:
    """
    Validate tenant limits based on subscription plan
    Returns list of validation errors
    """
    errors = []
    
    # Define plan limits
    plan_limits = {
        TenantPlan.STARTER: {'max_instances': 1, 'max_users': 5},
        TenantPlan.BASIC: {'max_instances': 3, 'max_users': 25},
        TenantPlan.PROFESSIONAL: {'max_instances': 10, 'max_users': 100},
        TenantPlan.ENTERPRISE: {'max_instances': 50, 'max_users': 1000}
    }
    
    limits = plan_limits.get(plan)
    if not limits:
        errors.append(f"Invalid plan: {plan}")
        return errors
    
    if max_instances > limits['max_instances']:
        errors.append(
            f"Plan {plan} allows maximum {limits['max_instances']} instances, "
            f"but {max_instances} requested"
        )
    
    if max_users > limits['max_users']:
        errors.append(
            f"Plan {plan} allows maximum {limits['max_users']} users per instance, "
            f"but {max_users} requested"
        )
    
    return errors


def validate_subdomain(subdomain: str, existing_subdomains: List[str] = None) -> List[str]:
    """
    Validate subdomain format and uniqueness
    Returns list of validation errors
    """
    errors = []
    
    # Basic format validation
    if not subdomain:
        errors.append("Subdomain is required")
        return errors
    
    if len(subdomain) < 3:
        errors.append("Subdomain must be at least 3 characters long")
    
    if len(subdomain) > 50:
        errors.append("Subdomain must be no more than 50 characters long")
    
    # Character validation
    if not subdomain.replace('-', '').isalnum():
        errors.append("Subdomain must contain only alphanumeric characters and hyphens")
    
    if subdomain.startswith('-') or subdomain.endswith('-'):
        errors.append("Subdomain cannot start or end with hyphen")
    
    if '--' in subdomain:
        errors.append("Subdomain cannot contain consecutive hyphens")
    
    # Reserved subdomains
    reserved_subdomains = [
        'api', 'www', 'mail', 'admin', 'root', 'test', 'staging', 'dev',
        'production', 'prod', 'app', 'apps', 'web', 'ftp', 'ssh', 'ssl',
        'secure', 'auth', 'login', 'signup', 'register', 'dashboard',
        'panel', 'control', 'manage', 'config', 'setup', 'install',
        'update', 'upgrade', 'backup', 'restore', 'help', 'support',
        'docs', 'documentation', 'blog', 'news', 'about', 'contact'
    ]
    
    if subdomain.lower() in reserved_subdomains:
        errors.append(f"Subdomain '{subdomain}' is reserved and cannot be used")
    
    # Check uniqueness if existing subdomains provided
    if existing_subdomains and subdomain.lower() in [s.lower() for s in existing_subdomains]:
        errors.append(f"Subdomain '{subdomain}' is already taken")
    
    return errors


def validate_custom_domain(domain: str) -> List[str]:
    """
    Validate custom domain format
    Returns list of validation errors
    """
    errors = []
    
    if not domain:
        return errors  # Custom domain is optional
    
    # Basic domain validation
    if '.' not in domain:
        errors.append("Invalid domain format - must contain at least one dot")
    
    if len(domain) > 253:
        errors.append("Domain name is too long (max 253 characters)")
    
    if domain.startswith('.') or domain.endswith('.'):
        errors.append("Domain cannot start or end with dot")
    
    if '..' in domain:
        errors.append("Domain cannot contain consecutive dots")
    
    # Check each label
    labels = domain.split('.')
    for label in labels:
        if not label:
            errors.append("Domain contains empty label")
            continue
        
        if len(label) > 63:
            errors.append(f"Domain label '{label}' is too long (max 63 characters)")
        
        if not label.replace('-', '').isalnum():
            errors.append(f"Domain label '{label}' contains invalid characters")
        
        if label.startswith('-') or label.endswith('-'):
            errors.append(f"Domain label '{label}' cannot start or end with hyphen")
    
    return errors 