"""
Database utilities for Odoo SaaS Kit

Provides database connection management and common database operations.
"""

import os
import logging
from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Database connection and session management"""
    
    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager
        
        Args:
            database_url: Database connection URL. If None, will use environment variables.
        """
        self.database_url = database_url or self._build_database_url()
        self.engine = None
        self.SessionLocal = None
        self._initialize_engine()
    
    def _build_database_url(self) -> str:
        """Build database URL from environment variables"""
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        database = os.getenv("POSTGRES_DB", "saas_odoo")
        
        # Enforce service-specific database users for security
        service_user = os.getenv("DB_SERVICE_USER")
        service_password = os.getenv("DB_SERVICE_PASSWORD")
        
        if not service_user or not service_password:
            raise ValueError(
                "DB_SERVICE_USER and DB_SERVICE_PASSWORD must be set for database security. "
                "Each service must use its specific database user (e.g., auth_service, billing_service)."
            )
        
        username = service_user
        password = service_password
        
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"
    
    def _initialize_engine(self):
        """Initialize SQLAlchemy engine and session factory"""
        try:
            # Engine configuration
            pool_size = int(os.getenv("DB_POOL_SIZE", "10"))
            max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "20"))
            pool_timeout = int(os.getenv("DB_POOL_TIMEOUT", "30"))
            
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
                pool_pre_ping=True,
                echo=os.getenv("DEBUG", "false").lower() == "true"
            )
            
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            logger.info("Database engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database engine: {e}")
            raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get database session with automatic cleanup
        
        Yields:
            SQLAlchemy session
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def test_connection(self) -> bool:
        """
        Test database connection
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> list:
        """
        Execute a raw SQL query
        
        Args:
            query: SQL query string
            params: Query parameters
            
        Returns:
            Query results as list of dictionaries
        """
        try:
            with self.engine.connect() as connection:
                result = connection.execute(text(query), params or {})
                return [dict(row) for row in result]
        except SQLAlchemyError as e:
            logger.error(f"Query execution failed: {e}")
            raise
    
    def create_database(self, database_name: str) -> bool:
        """
        Create a new database (for Odoo instances)
        
        Args:
            database_name: Name of the database to create
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Connect to default postgres database to create new database
            admin_url = self.database_url.rsplit('/', 1)[0] + '/postgres'
            admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT')
            
            with admin_engine.connect() as connection:
                # Check if database already exists
                result = connection.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                    {"db_name": database_name}
                )
                
                if result.fetchone():
                    logger.warning(f"Database {database_name} already exists")
                    return True
                
                # Create database
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
                logger.info(f"Database {database_name} created successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create database {database_name}: {e}")
            return False
    
    def drop_database(self, database_name: str) -> bool:
        """
        Drop a database (for Odoo instance cleanup)
        
        Args:
            database_name: Name of the database to drop
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Connect to default postgres database
            admin_url = self.database_url.rsplit('/', 1)[0] + '/postgres'
            admin_engine = create_engine(admin_url, isolation_level='AUTOCOMMIT')
            
            with admin_engine.connect() as connection:
                # Terminate existing connections to the database
                connection.execute(
                    text("""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = :db_name AND pid <> pg_backend_pid()
                    """),
                    {"db_name": database_name}
                )
                
                # Drop database
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
                logger.info(f"Database {database_name} dropped successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to drop database {database_name}: {e}")
            return False
    
    def backup_database(self, database_name: str, backup_path: str) -> bool:
        """
        Create database backup using pg_dump
        
        Args:
            database_name: Name of the database to backup
            backup_path: Path where backup file will be saved
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import subprocess
            
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            username = os.getenv("POSTGRES_USER", "odoo_user")
            
            cmd = [
                "pg_dump",
                "-h", host,
                "-p", port,
                "-U", username,
                "-d", database_name,
                "-f", backup_path,
                "--verbose"
            ]
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Database {database_name} backed up to {backup_path}")
                return True
            else:
                logger.error(f"Backup failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to backup database {database_name}: {e}")
            return False
    
    def restore_database(self, database_name: str, backup_path: str) -> bool:
        """
        Restore database from backup using psql
        
        Args:
            database_name: Name of the database to restore
            backup_path: Path to backup file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import subprocess
            
            # First create the database if it doesn't exist
            if not self.create_database(database_name):
                return False
            
            host = os.getenv("POSTGRES_HOST", "localhost")
            port = os.getenv("POSTGRES_PORT", "5432")
            username = os.getenv("POSTGRES_USER", "odoo_user")
            
            cmd = [
                "psql",
                "-h", host,
                "-p", port,
                "-U", username,
                "-d", database_name,
                "-f", backup_path
            ]
            
            # Set PGPASSWORD environment variable
            env = os.environ.copy()
            env["PGPASSWORD"] = os.getenv("POSTGRES_PASSWORD", "")
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"Database {database_name} restored from {backup_path}")
                return True
            else:
                logger.error(f"Restore failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to restore database {database_name}: {e}")
            return False


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_db_connection() -> DatabaseManager:
    """
    Get global database manager instance
    
    Returns:
        DatabaseManager instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_raw_connection():
    """
    Get raw psycopg2 connection for direct database operations
    
    Returns:
        psycopg2 connection
    """
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "saas_odoo")
    username = os.getenv("POSTGRES_USER", "odoo_user")
    password = os.getenv("POSTGRES_PASSWORD", "")
    
    return psycopg2.connect(
        host=host,
        port=port,
        database=database,
        user=username,
        password=password,
        cursor_factory=RealDictCursor
    ) 