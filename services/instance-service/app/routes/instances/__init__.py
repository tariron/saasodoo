"""
Instance management routes package

This package organizes instance routes into focused modules:
- crud.py: Create, read, update, delete operations
- actions.py: Instance actions (start, stop, restart, etc.)
- backups.py: Backup listing
- lifecycle.py: Provisioning, termination, resource management
- helpers.py: Shared helper functions
"""

from fastapi import APIRouter

from app.routes.instances.crud import router as crud_router
from app.routes.instances.actions import router as actions_router
from app.routes.instances.backups import router as backups_router
from app.routes.instances.lifecycle import router as lifecycle_router

# Create main router that combines all sub-routers
router = APIRouter()

# Include all sub-routers
router.include_router(crud_router)
router.include_router(actions_router)
router.include_router(backups_router)
router.include_router(lifecycle_router)

__all__ = ['router']
