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
            _pool = await asyncpg.create_pool(
                database_url,
                min_size=5,
                max_size=20,
                command_timeout=60
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
