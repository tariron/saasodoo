"""
Shared utilities for Odoo SaaS Kit

This package contains common utilities used across all microservices.
"""

from .database import DatabaseManager, get_db_connection
from .redis_client import RedisClient, get_redis_client
from .logger import setup_logging, get_logger
from .security import SecurityUtils, hash_password, verify_password, generate_token

__all__ = [
    "DatabaseManager",
    "get_db_connection", 
    "RedisClient",
    "get_redis_client",
    "setup_logging",
    "get_logger",
    "SecurityUtils",
    "hash_password",
    "verify_password", 
    "generate_token",
]

__version__ = "1.0.0" 