"""
Validation utilities for instance service
"""

from typing import List
from app.models.instance import InstanceType


def validate_instance_resources(instance_type: InstanceType, cpu_limit: float, 
                               memory_limit: str, storage_limit: str) -> List[str]:
    """
    Validate instance resource format (no limits enforced)
    Returns list of validation errors
    """
    errors = []
    
    # Validate instance type exists
    if instance_type not in [InstanceType.DEVELOPMENT, InstanceType.STAGING, InstanceType.PRODUCTION]:
        errors.append(f"Invalid instance type: {instance_type}")
        return errors
    
    # Validate memory format only
    try:
        memory_value = int(memory_limit[:-1])
        memory_unit = memory_limit[-1].upper()
        
        if memory_unit not in ['G', 'M']:
            errors.append(f"Invalid memory format: {memory_limit}")
        elif memory_value <= 0:
            errors.append(f"Memory value must be positive: {memory_limit}")
    except (ValueError, IndexError):
        errors.append(f"Invalid memory format: {memory_limit}")
    
    # Validate storage format only
    try:
        storage_value = int(storage_limit[:-1])
        storage_unit = storage_limit[-1].upper()
        
        if storage_unit not in ['G', 'M']:
            errors.append(f"Invalid storage format: {storage_limit}")
        elif storage_value <= 0:
            errors.append(f"Storage value must be positive: {storage_limit}")
    except (ValueError, IndexError):
        errors.append(f"Invalid storage format: {storage_limit}")
    
    # Validate CPU is positive
    if cpu_limit <= 0:
        errors.append(f"CPU limit must be positive: {cpu_limit}")
    
    return errors


def validate_database_name(database_name: str, tenant_databases: List[str] = None) -> List[str]:
    """
    Validate database name format and uniqueness within tenant
    Returns list of validation errors
    """
    errors = []

    if not database_name:
        errors.append("Subdomain is required")
        return errors

    if len(database_name) < 1:
        errors.append("Subdomain must be at least 1 character long")

    if len(database_name) > 50:
        errors.append("Subdomain must be no more than 50 characters long")

    # Character validation
    if not database_name.replace('_', '').replace('-', '').isalnum():
        errors.append("Subdomain must contain only alphanumeric characters, underscores, and hyphens")

    if database_name.startswith('_') or database_name.startswith('-'):
        errors.append("Subdomain cannot start with underscore or hyphen")

    if database_name.endswith('_') or database_name.endswith('-'):
        errors.append("Subdomain cannot end with underscore or hyphen")

    # Reserved database names
    reserved_names = [
        'postgres', 'template0', 'template1', 'admin', 'root', 'master',
        'system', 'test', 'temp', 'public', 'information_schema'
    ]

    if database_name.lower() in reserved_names:
        errors.append(f"Subdomain '{database_name}' is reserved and cannot be used")

    # Check uniqueness if tenant databases provided
    if tenant_databases and database_name.lower() in [db.lower() for db in tenant_databases]:
        errors.append(f"Subdomain '{database_name}' is already taken")

    return errors


def validate_addon_names(addon_names: List[str]) -> List[str]:
    """
    Validate custom addon names
    Returns list of validation errors
    """
    errors = []
    
    if not addon_names:
        return errors  # Empty list is valid
    
    for addon_name in addon_names:
        if not addon_name:
            errors.append("Addon name cannot be empty")
            continue
        
        if len(addon_name) > 100:
            errors.append(f"Addon name '{addon_name}' is too long (max 100 characters)")
        
        # Basic name validation
        if not addon_name.replace('_', '').replace('-', '').isalnum():
            errors.append(f"Addon name '{addon_name}' must contain only alphanumeric characters, underscores, and hyphens")
        
        if addon_name.startswith('_') or addon_name.startswith('-'):
            errors.append(f"Addon name '{addon_name}' cannot start with underscore or hyphen")
    
    # Check for duplicates
    if len(addon_names) != len(set(addon_names)):
        errors.append("Duplicate addon names are not allowed")
    
    return errors 