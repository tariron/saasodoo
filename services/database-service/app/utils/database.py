"""
Database connection utilities for Database Service
Provides database session management using asyncpg connection pool
"""

import os
import structlog
from typing import Optional
from contextlib import asynccontextmanager
import asyncpg
from asyncpg import Pool

logger = structlog.get_logger(__name__)


class DatabaseService:
    """
    Database service for managing connection pool to platform database
    Uses asyncpg for async PostgreSQL operations
    """

    def __init__(self):
        self.pool: Optional[Pool] = None
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', '5432')),
            'database': os.getenv('POSTGRES_DB', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'database_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD'),
            'min_size': int(os.getenv('DB_POOL_MIN_SIZE', '5')),
            'max_size': int(os.getenv('DB_POOL_MAX_SIZE', '20')),
        }

        if not self.db_config['password']:
            raise ValueError(
                "DB_SERVICE_PASSWORD must be set for database connection. "
                "Database service requires its specific database user credentials."
            )

    async def connect(self):
        """Initialize database connection pool"""
        if self.pool is None:
            try:
                self.pool = await asyncpg.create_pool(
                    host=self.db_config['host'],
                    port=self.db_config['port'],
                    database=self.db_config['database'],
                    user=self.db_config['user'],
                    password=self.db_config['password'],
                    min_size=self.db_config['min_size'],
                    max_size=self.db_config['max_size'],
                    command_timeout=60
                )
                logger.info(
                    "Database connection pool created",
                    host=self.db_config['host'],
                    database=self.db_config['database'],
                    user=self.db_config['user']
                )
            except Exception as e:
                logger.error("Failed to create database pool", error=str(e))
                raise

    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
            self.pool = None

    @asynccontextmanager
    async def get_connection(self):
        """
        Get database connection from pool

        Yields:
            asyncpg.Connection: Database connection with automatic cleanup
        """
        if not self.pool:
            raise RuntimeError("Database pool not initialized. Call connect() first.")

        connection = await self.pool.acquire()
        try:
            yield connection
        finally:
            await self.pool.release(connection)

    async def health_check(self) -> bool:
        """
        Check database connectivity

        Returns:
            bool: True if database is accessible, False otherwise
        """
        try:
            async with self.get_connection() as conn:
                await conn.fetchval("SELECT 1")
                return True
        except Exception as e:
            logger.error("Database health check failed", error=str(e))
            return False


# Global database service instance
db_service = DatabaseService()


async def get_db_connection():
    """
    FastAPI dependency to get database connection

    Yields:
        asyncpg.Connection: Database connection for use in route handlers
    """
    async with db_service.get_connection() as conn:
        yield conn
