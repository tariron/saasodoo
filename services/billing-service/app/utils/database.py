"""
Database utilities for billing service
"""

import asyncpg
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None

async def init_db():
    """Initialize database connection pool"""
    global _pool
    
    if _pool is None:
        # Use environment variables for database connection
        db_host = os.getenv("POSTGRES_HOST", "postgres")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_name = os.getenv("POSTGRES_DB", "billing")
        db_user = os.getenv("DB_SERVICE_USER", "billing_service")
        db_password = os.getenv("DB_SERVICE_PASSWORD", "billing_service123")
        
        database_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        try:
            pool_size = int(os.getenv("DB_POOL_SIZE", "20"))
            _pool = await asyncpg.create_pool(
                database_url,
                min_size=10,
                max_size=pool_size,
                command_timeout=30
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise

async def close_db():
    """Close database connection pool"""
    global _pool
    
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")

def get_pool() -> asyncpg.Pool:
    """Get database connection pool"""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool

async def execute_query(query: str, *args):
    """Execute a database query"""
    pool = get_pool()
    async with pool.acquire() as connection:
        return await connection.execute(query, *args)

async def fetch_one(query: str, *args):
    """Fetch one row from database"""
    pool = get_pool()
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, *args)

async def fetch_all(query: str, *args):
    """Fetch all rows from database"""
    pool = get_pool()
    async with pool.acquire() as connection:
        return await connection.fetch(query, *args)

async def get_plan_entitlements(plan_name: str, effective_date: str = None):
    """
    Get plan entitlements for a specific plan at a given date.
    If effective_date not provided, returns latest version.

    Args:
        plan_name: Name of the plan (e.g., 'basic-monthly')
        effective_date: Date to query entitlements for (ISO format string or None for latest)

    Returns:
        asyncpg.Record with fields: plan_name, cpu_limit, memory_limit, storage_limit, description, effective_date, db_type
    """
    pool = get_pool()

    if effective_date:
        query = """
            SELECT plan_name, cpu_limit, memory_limit, storage_limit, description, effective_date, db_type
            FROM plan_entitlements
            WHERE plan_name = $1 AND effective_date <= $2
            ORDER BY effective_date DESC
            LIMIT 1
        """
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, plan_name, effective_date)
    else:
        query = """
            SELECT plan_name, cpu_limit, memory_limit, storage_limit, description, effective_date, db_type
            FROM plan_entitlements
            WHERE plan_name = $1
            ORDER BY effective_date DESC
            LIMIT 1
        """
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, plan_name)

async def get_all_current_entitlements():
    """
    Get current (latest) entitlements for all plans.

    Returns:
        List of asyncpg.Record objects with current entitlements for each plan
    """
    pool = get_pool()
    query = """
        SELECT DISTINCT ON (plan_name)
            plan_name, cpu_limit, memory_limit, storage_limit, description, effective_date, db_type
        FROM plan_entitlements
        ORDER BY plan_name, effective_date DESC
    """
    async with pool.acquire() as conn:
        return await conn.fetch(query)
