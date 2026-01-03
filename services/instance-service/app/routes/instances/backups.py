"""
Instance backup listing routes
"""

import os
import json
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
import structlog

from app.utils.database import InstanceDatabase
from app.routes.instances.helpers import get_database

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/{instance_id}/backups")
async def list_instance_backups(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """List available backups for an instance"""
    try:
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        # Get backups from filesystem (in a full implementation, this would query a backups table)
        backup_dir = "/mnt/cephfs/odoo_backups/active"
        backups = []

        if os.path.exists(backup_dir):
            for file in os.listdir(backup_dir):
                if file.endswith("_metadata.json"):
                    metadata_path = os.path.join(backup_dir, file)
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                            if metadata.get('instance_id') == str(instance_id):
                                backups.append({
                                    "backup_id": metadata.get('backup_name'),
                                    "backup_name": metadata.get('backup_name'),
                                    "instance_name": metadata.get('instance_name'),
                                    "created_at": metadata.get('created_at'),
                                    "database_size": metadata.get('database_size', 0),
                                    "data_size": metadata.get('data_size', 0),
                                    "total_size": metadata.get('total_size', 0),
                                    "odoo_version": metadata.get('odoo_version'),
                                    "status": metadata.get('status')
                                })
                    except Exception as e:
                        logger.warning("Failed to read backup metadata", file=file, error=str(e))

        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "instance_id": str(instance_id),
            "instance_name": instance.name,
            "backups": backups,
            "total_backups": len(backups)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list instance backups", instance_id=str(instance_id), error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
