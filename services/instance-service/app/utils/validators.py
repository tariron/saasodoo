"""
Validation utilities for instance service
"""

from typing import List
from app.models.instance import InstanceType


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
    
    if database_name.endswith('_') or database_name.endswith('-'):
        errors.append("Database name cannot end with underscore or hyphen")
    
    # Reserved database names
    reserved_names = [
        'postgres', 'template0', 'template1', 'admin', 'root', 'master',
        'system', 'test', 'temp', 'public', 'information_schema'
    ]
    
    if database_name.lower() in reserved_names:
        errors.append(f"Database name '{database_name}' is reserved and cannot be used")
    
    # Check uniqueness if tenant databases provided
    if tenant_databases and database_name.lower() in [db.lower() for db in tenant_databases]:
        errors.append(f"Database name '{database_name}' already exists for this tenant")
    
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