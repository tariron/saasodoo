"""
Shared helper functions for Celery tasks.

This module consolidates common database operations and utility functions
used across provisioning, lifecycle, maintenance, and migration tasks.
"""

import os
import json
import asyncio
import asyncpg
import httpx
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import UUID

import structlog

from app.models.instance import InstanceStatus

logger = structlog.get_logger(__name__)


def get_db_connection_params() -> Dict[str, Any]:
    """
    Get database connection parameters from environment variables.

    Returns:
        Dict with host, port, database, user, password keys
    """
    return {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': int(os.getenv('POSTGRES_PORT', '5432')),
        'database': os.getenv('POSTGRES_DB', 'instance'),
        'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
        'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    }


async def get_instance_from_db(instance_id: str) -> Optional[Dict[str, Any]]:
    """
    Get instance details from database.

    Args:
        instance_id: UUID string of the instance

    Returns:
        Instance data dict with deserialized JSON fields, or None if not found
    """
    params = get_db_connection_params()
    conn = await asyncpg.connect(**params)

    try:
        row = await conn.fetchrow("SELECT * FROM instances WHERE id = $1", UUID(instance_id))
        if row:
            instance_data = dict(row)

            # Deserialize JSON fields
            if instance_data.get('custom_addons'):
                instance_data['custom_addons'] = json.loads(instance_data['custom_addons'])
            else:
                instance_data['custom_addons'] = []

            if instance_data.get('disabled_modules'):
                instance_data['disabled_modules'] = json.loads(instance_data['disabled_modules'])
            else:
                instance_data['disabled_modules'] = []

            if instance_data.get('environment_vars'):
                instance_data['environment_vars'] = json.loads(instance_data['environment_vars'])
            else:
                instance_data['environment_vars'] = {}

            if instance_data.get('metadata'):
                instance_data['metadata'] = json.loads(instance_data['metadata'])
            else:
                instance_data['metadata'] = {}

            return instance_data
        return None
    finally:
        await conn.close()


async def update_instance_status(
    instance_id: str,
    status: InstanceStatus,
    error_message: Optional[str] = None
) -> None:
    """
    Update instance status in database.

    Args:
        instance_id: UUID string of the instance
        status: New InstanceStatus value
        error_message: Optional error message to store
    """
    params = get_db_connection_params()
    conn = await asyncpg.connect(**params)

    try:
        await conn.execute("""
            UPDATE instances
            SET status = $1, error_message = $2, updated_at = $3
            WHERE id = $4
        """, status.value, error_message, datetime.utcnow(), UUID(instance_id))

        logger.info("Instance status updated", instance_id=instance_id, status=status.value)
    finally:
        await conn.close()


async def wait_for_odoo_startup(container_info: Dict[str, Any], timeout: int = 300) -> bool:
    """
    Wait for Odoo to start up and be accessible.

    Args:
        container_info: Dict containing 'internal_url' key
        timeout: Maximum seconds to wait (default 300)

    Returns:
        True if Odoo became accessible

    Raises:
        TimeoutError: If Odoo did not start within timeout
    """
    url = container_info['internal_url']
    start_time = datetime.utcnow()

    logger.info("Waiting for Odoo startup", url=url, timeout=timeout)

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(url, timeout=10)
                if response.status_code in [200, 303, 302]:  # Odoo redirects are normal
                    logger.info("Odoo is accessible")
                    return True
            except Exception:
                pass  # Continue waiting

            await asyncio.sleep(10)  # Check every 10 seconds

    raise TimeoutError(f"Odoo did not start within {timeout} seconds")


async def update_instance_network_info(
    instance_id: str,
    container_info: Dict[str, Any],
    db_info: Optional[Dict[str, str]] = None
) -> None:
    """
    Update instance with network and container information.

    Args:
        instance_id: UUID string of the instance
        container_info: Dict with service_id, service_name, internal_url, external_url
        db_info: Optional dict with db_host and db_port (used during provisioning)
    """
    params = get_db_connection_params()
    conn = await asyncpg.connect(**params)

    try:
        if db_info:
            # Full update including database info (used in provisioning)
            await conn.execute("""
                UPDATE instances
                SET service_id = $1, service_name = $2,
                    internal_url = $3, external_url = $4,
                    db_host = $5, db_port = $6, updated_at = $7
                WHERE id = $8
            """,
                container_info.get('service_id'),
                container_info.get('service_name'),
                container_info['internal_url'],
                container_info['external_url'],
                db_info['db_host'],
                int(db_info['db_port']),
                datetime.utcnow(),
                UUID(instance_id)
            )
            logger.info("Instance network and database info updated",
                       instance_id=instance_id,
                       db_host=db_info['db_host'],
                       db_port=db_info['db_port'])
        else:
            # Simple update without database info (used in lifecycle/maintenance)
            await conn.execute("""
                UPDATE instances
                SET service_id = $1, service_name = $2,
                    internal_url = $3, external_url = $4, updated_at = $5
                WHERE id = $6
            """,
                container_info.get('service_id'),
                container_info.get('service_name'),
                container_info['internal_url'],
                container_info['external_url'],
                datetime.utcnow(),
                UUID(instance_id)
            )
            logger.info("Instance network info updated", instance_id=instance_id)
    finally:
        await conn.close()


async def get_user_info(customer_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user information from user-service for email notifications.

    Args:
        customer_id: UUID string of the customer

    Returns:
        Dict with email, first_name, last_name keys, or None on failure
    """
    try:
        user_service_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{user_service_url}/users/internal/{customer_id}")

            if response.status_code == 200:
                user_data = response.json()
                return {
                    'email': user_data.get('email', ''),
                    'first_name': user_data.get('first_name', 'there'),
                    'last_name': user_data.get('last_name', '')
                }
            else:
                logger.warning("Failed to get user info from user-service",
                              customer_id=customer_id, status_code=response.status_code)
                return None

    except Exception as e:
        logger.error("Error getting user info", customer_id=customer_id, error=str(e))
        return None


async def get_db_server_for_instance(instance: Dict[str, Any]) -> Dict[str, str]:
    """
    Get database server connection info for an instance (CNPG).

    For CNPG-managed clusters:
    - Password is read from K8s Secret: {server_name}-superuser
    - Returns direct host {server_name}-rw for backup/restore operations

    Args:
        instance: Instance data dict

    Returns:
        Dict with host, port, admin_user, admin_password keys
    """
    from app.utils.kubernetes import KubernetesClient

    params = get_db_connection_params()
    conn = await asyncpg.connect(**params)

    try:
        row = None

        # Get server info by db_server_id
        if instance.get('db_server_id'):
            row = await conn.fetchrow("""
                SELECT name, port, admin_user
                FROM db_servers
                WHERE id = $1
            """, instance['db_server_id'])

        # Fallback: Query by db_host
        if not row and instance.get('db_host'):
            row = await conn.fetchrow("""
                SELECT name, port, admin_user
                FROM db_servers
                WHERE host = $1
            """, instance['db_host'])

        if not row:
            raise Exception(f"Database server not found for instance {instance['id']}")

        server_name = row['name']
        secret_name = f"{server_name}-superuser"

        # Read password from K8s Secret
        k8s_client = KubernetesClient()
        admin_password = k8s_client.get_secret_value(secret_name, "password")

        # Use direct host for backup/restore (not pooler)
        direct_host = f"{server_name}-rw"

        logger.info("Retrieved CNPG database server info",
                   instance_id=str(instance['id']),
                   server_name=server_name,
                   direct_host=direct_host)

        return {
            'host': direct_host,
            'port': str(row['port']),
            'admin_user': row['admin_user'],
            'admin_password': admin_password
        }

    finally:
        await conn.close()


# Backward compatibility aliases (with underscore prefix)
# These allow existing code to work without changes during migration
_get_instance_from_db = get_instance_from_db
_update_instance_status = update_instance_status
_wait_for_odoo_startup = wait_for_odoo_startup
_update_instance_network_info = update_instance_network_info
_get_user_info = get_user_info
_get_db_server_for_instance = get_db_server_for_instance
