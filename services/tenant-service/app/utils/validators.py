"""
Validation utilities for tenant service
"""

from typing import Dict, Any, List
from uuid import UUID

from app.models.tenant import TenantPlan, TenantStatus
from app.models.instance import InstanceType, OdooVersion


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


def validate_instance_resources(instance_type: InstanceType, cpu_limit: float, 
                               memory_limit: str, storage_limit: str) -> List[str]:
    """
    Validate instance resource allocation based on instance type
    Returns list of validation errors
    """
    errors = []
    
    # Define resource limits by instance type
    type_limits = {
        InstanceType.DEVELOPMENT: {
            'max_cpu': 2.0,
            'max_memory_gb': 4,
            'max_storage_gb': 20
        },
        InstanceType.STAGING: {
            'max_cpu': 4.0,
            'max_memory_gb': 8,
            'max_storage_gb': 50
        },
        InstanceType.PRODUCTION: {
            'max_cpu': 8.0,
            'max_memory_gb': 16,
            'max_storage_gb': 100
        }
    }
    
    limits = type_limits.get(instance_type)
    if not limits:
        errors.append(f"Invalid instance type: {instance_type}")
        return errors
    
    # Validate CPU
    if cpu_limit > limits['max_cpu']:
        errors.append(
            f"Instance type {instance_type} allows maximum {limits['max_cpu']} CPU cores, "
            f"but {cpu_limit} requested"
        )
    
    # Validate memory
    try:
        memory_value = int(memory_limit[:-1])
        memory_unit = memory_limit[-1].upper()
        
        if memory_unit == 'G':
            memory_gb = memory_value
        elif memory_unit == 'M':
            memory_gb = memory_value / 1024
        else:
            errors.append(f"Invalid memory format: {memory_limit}")
            return errors
        
        if memory_gb > limits['max_memory_gb']:
            errors.append(
                f"Instance type {instance_type} allows maximum {limits['max_memory_gb']}GB memory, "
                f"but {memory_gb}GB requested"
            )
    except (ValueError, IndexError):
        errors.append(f"Invalid memory format: {memory_limit}")
    
    # Validate storage
    try:
        storage_value = int(storage_limit[:-1])
        storage_unit = storage_limit[-1].upper()
        
        if storage_unit == 'G':
            storage_gb = storage_value
        elif storage_unit == 'M':
            storage_gb = storage_value / 1024
        else:
            errors.append(f"Invalid storage format: {storage_limit}")
            return errors
        
        if storage_gb > limits['max_storage_gb']:
            errors.append(
                f"Instance type {instance_type} allows maximum {limits['max_storage_gb']}GB storage, "
                f"but {storage_gb}GB requested"
            )
    except (ValueError, IndexError):
        errors.append(f"Invalid storage format: {storage_limit}")
    
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


def validate_database_name(database_name: str, tenant_databases: List[str] = None) -> List[str]:
    """
    Validate database name format and uniqueness within tenant
    Returns list of validation errors
    """
    errors = []
    
    if not database_name:
        errors.append("Database name is required")
        return errors
    
    if len(database_name) < 1:
        errors.append("Database name must be at least 1 character long")
    
    if len(database_name) > 50:
        errors.append("Database name must be no more than 50 characters long")
    
    # Character validation
    if not database_name.replace('_', '').replace('-', '').isalnum():
        errors.append("Database name must contain only alphanumeric characters, underscores, and hyphens")
    
    if database_name.startswith('_') or database_name.startswith('-'):
        errors.append("Database name cannot start with underscore or hyphen")
    
    # PostgreSQL reserved names
    reserved_names = [
        'postgres', 'template0', 'template1', 'information_schema',
        'pg_catalog', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1'
    ]
    
    if database_name.lower() in reserved_names:
        errors.append(f"Database name '{database_name}' is reserved and cannot be used")
    
    # Check uniqueness within tenant if provided
    if tenant_databases and database_name.lower() in [db.lower() for db in tenant_databases]:
        errors.append(f"Database name '{database_name}' already exists in this tenant")
    
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
        errors.append("Domain must contain at least one dot")
        return errors
    
    parts = domain.split('.')
    
    for part in parts:
        if not part:
            errors.append("Domain parts cannot be empty")
            break
        
        if len(part) > 63:
            errors.append("Domain parts cannot be longer than 63 characters")
            break
        
        if not part.replace('-', '').isalnum():
            errors.append("Domain parts must contain only alphanumeric characters and hyphens")
            break
        
        if part.startswith('-') or part.endswith('-'):
            errors.append("Domain parts cannot start or end with hyphen")
            break
    
    if len(domain) > 253:
        errors.append("Domain cannot be longer than 253 characters")
    
    return errors


def validate_addon_names(addon_names: List[str]) -> List[str]:
    """
    Validate addon names format
    Returns list of validation errors
    """
    errors = []
    
    for addon in addon_names:
        if not addon:
            errors.append("Addon names cannot be empty")
            continue
        
        if not addon.replace('_', '').isalnum():
            errors.append(f"Addon name '{addon}' must contain only alphanumeric characters and underscores")
        
        if addon.startswith('_') or addon.endswith('_'):
            errors.append(f"Addon name '{addon}' cannot start or end with underscore")
    
    return errors 