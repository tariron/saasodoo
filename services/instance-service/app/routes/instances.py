"""
Instance management routes

This module provides backward-compatible imports from the instances package.
The implementation has been moved to app/routes/instances/ for better organization.
"""

from app.routes.instances import router

# Re-export helper functions for backward compatibility
from app.routes.instances.helpers import (
    get_database,
    get_valid_actions_for_status as _get_valid_actions_for_status,
    instance_to_response_dict,
    instance_dict_to_response_dict,
    start_instance as _start_instance,
    stop_instance as _stop_instance,
    restart_instance as _restart_instance,
    update_instance_software as _update_instance_software,
    backup_instance as _backup_instance,
    restore_instance as _restore_instance,
    suspend_instance as _suspend_instance,
    unsuspend_instance as _unsuspend_instance,
    terminate_instance as _terminate_instance,
    stop_deployment_for_suspension as _stop_deployment_for_suspension,
    get_db_server_type as _get_db_server_type,
)

__all__ = ['router']
