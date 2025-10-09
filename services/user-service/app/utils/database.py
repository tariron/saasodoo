"""
Database Connection Utilities
Connects to the auth database for customer management
"""

import asyncpg
import os
from typing import Optional
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Database connection pool
_pool: Optional[asyncpg.Pool] = None

async def init_database():
    """Initialize database connection pool"""
    global _pool
    
    # Database connection parameters
    database_url = os.getenv("AUTH_DATABASE_URL")
    if not database_url:
        # Fallback to individual parameters
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "auth")  # Use POSTGRES_DB from environment
        user = os.getenv("DB_SERVICE_USER", "auth_service")
        password = os.getenv("DB_SERVICE_PASSWORD", "auth_service_secure_pass_change_me")
        
        database_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info("Database connection pool initialized successfully")
        
        # Test connection
        async with _pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            logger.info("Database connection test successful")
            
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

async def get_database_pool() -> asyncpg.Pool:
    """Get database connection pool"""
    global _pool
    if _pool is None:
        await init_database()
    return _pool

@asynccontextmanager
async def get_database_connection():
    """Get database connection from pool"""
    pool = await get_database_pool()
    async with pool.acquire() as connection:
        yield connection

async def close_database():
    """Close database connection pool"""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")

class DatabaseManager:
    """Database manager for customer operations"""
    
    def __init__(self):
        self.pool = None
    
    async def get_connection(self):
        """Get database connection"""
        if not self.pool:
            self.pool = await get_database_pool()
        return await self.pool.acquire()
    
    async def execute_query(self, query: str, *args):
        """Execute a query and return results"""
        async with get_database_connection() as conn:
            return await conn.fetch(query, *args)
    
    async def execute_single(self, query: str, *args):
        """Execute a query and return single result"""
        async with get_database_connection() as conn:
            return await conn.fetchrow(query, *args)
    
    async def execute_value(self, query: str, *args):
        """Execute a query and return single value"""
        async with get_database_connection() as conn:
            return await conn.fetchval(query, *args)
    
    async def execute_command(self, query: str, *args):
        """Execute a command (INSERT, UPDATE, DELETE)"""
        async with get_database_connection() as conn:
            return await conn.execute(query, *args)

# Global database manager instance
db_manager = DatabaseManager()

# Customer-specific database operations
class CustomerDatabase:
    """Database operations specific to customer management"""
    
    @staticmethod
    async def create_customer(customer_data: dict) -> str:
        """
        Create new customer in database
        
        Args:
            customer_data: Customer information
            
        Returns:
            str: Customer ID
        """
        query = """
        INSERT INTO users (email, password_hash, first_name, last_name, 
                          is_active, is_verified, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        RETURNING id
        """
        
        customer_id = await db_manager.execute_value(
            query,
            customer_data['email'],
            customer_data['password_hash'],
            customer_data['first_name'],
            customer_data['last_name'],
            customer_data.get('is_active', True),
            customer_data.get('is_verified', False)
        )
        
        logger.info(f"Customer created with ID: {customer_id}")
        return str(customer_id)
    
    @staticmethod
    async def get_customer_by_email(email: str) -> Optional[dict]:
        """
        Get customer by email address
        
        Args:
            email: Customer email
            
        Returns:
            dict: Customer data or None
        """
        query = """
        SELECT id, email, password_hash, first_name, last_name,
               is_active, is_verified, created_at, updated_at
        FROM users 
        WHERE email = $1
        """
        
        result = await db_manager.execute_single(query, email)
        
        if result:
            return dict(result)
        return None
    
    @staticmethod
    async def get_customer_by_id(customer_id: str) -> Optional[dict]:
        """
        Get customer by ID
        
        Args:
            customer_id: Customer ID
            
        Returns:
            dict: Customer data or None
        """
        query = """
        SELECT id, email, password_hash, first_name, last_name,
               is_active, is_verified, created_at, updated_at
        FROM users 
        WHERE id = $1
        """
        
        result = await db_manager.execute_single(query, customer_id)
        
        if result:
            return dict(result)
        return None
    
    @staticmethod
    async def update_customer(customer_id: str, update_data: dict) -> bool:
        """
        Update customer information
        
        Args:
            customer_id: Customer ID
            update_data: Data to update
            
        Returns:
            bool: Success status
        """
        # Build dynamic update query
        set_clauses = []
        values = []
        param_count = 1
        
        for key, value in update_data.items():
            if key not in ['id', 'created_at']:  # Don't update these fields
                set_clauses.append(f"{key} = ${param_count}")
                values.append(value)
                param_count += 1
        
        if not set_clauses:
            return False
        
        # Add updated_at
        from datetime import datetime, timezone
        set_clauses.append(f"updated_at = ${param_count}")
        values.append(datetime.now(timezone.utc))
        param_count += 1
        
        # Add customer_id for WHERE clause
        values.append(customer_id)
        
        query = f"""
        UPDATE users 
        SET {', '.join(set_clauses)}
        WHERE id = ${param_count}
        """
        
        result = await db_manager.execute_command(query, *values)
        return result == "UPDATE 1"
    
    @staticmethod
    async def verify_customer_email(customer_id: str) -> bool:
        """
        Mark customer email as verified
        
        Args:
            customer_id: Customer ID
            
        Returns:
            bool: Success status
        """
        query = """
        UPDATE users 
        SET is_verified = true, updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        
        result = await db_manager.execute_command(query, customer_id)
        return result == "UPDATE 1"

    # NOTE: Session and token management has been migrated to Redis
    # See: app/utils/redis_session.py
    # PostgreSQL tables (user_sessions, password_resets, email_verification_tokens)
    # are no longer used for authentication - tokens auto-expire in Redis 