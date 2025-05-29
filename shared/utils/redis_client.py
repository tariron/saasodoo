"""
Redis client utilities for Odoo SaaS Kit

Provides Redis connection management and common caching operations.
"""

import os
import json
import logging
from typing import Optional, Any, Dict, Union
import redis
from redis.connection import ConnectionPool

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper with connection management and utility methods"""
    
    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize Redis client
        
        Args:
            redis_url: Redis connection URL. If None, will use environment variables.
        """
        self.redis_url = redis_url or self._build_redis_url()
        self.client = None
        self.pool = None
        self._initialize_client()
    
    def _build_redis_url(self) -> str:
        """Build Redis URL from environment variables"""
        host = os.getenv("REDIS_HOST", "localhost")
        port = os.getenv("REDIS_PORT", "6379")
        password = os.getenv("REDIS_PASSWORD", "")
        db = os.getenv("REDIS_DB", "0")
        
        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        else:
            return f"redis://{host}:{port}/{db}"
    
    def _initialize_client(self):
        """Initialize Redis client with connection pool"""
        try:
            # Create connection pool
            self.pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            # Create Redis client
            self.client = redis.Redis(
                connection_pool=self.pool,
                decode_responses=True
            )
            
            # Test connection
            self.client.ping()
            logger.info("Redis client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        Test Redis connection
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client.ping()
            logger.info("Redis connection test successful")
            return True
        except Exception as e:
            logger.error(f"Redis connection test failed: {e}")
            return False
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set a key-value pair in Redis
        
        Args:
            key: Redis key
            value: Value to store (will be JSON serialized if not string)
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize value if not string
            if not isinstance(value, str):
                value = json.dumps(value)
            
            if ttl:
                return self.client.setex(key, ttl, value)
            else:
                return self.client.set(key, value)
                
        except Exception as e:
            logger.error(f"Failed to set Redis key {key}: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from Redis
        
        Args:
            key: Redis key
            default: Default value if key not found
            
        Returns:
            Value from Redis or default
        """
        try:
            value = self.client.get(key)
            if value is None:
                return default
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Failed to get Redis key {key}: {e}")
            return default
    
    def delete(self, *keys: str) -> int:
        """
        Delete keys from Redis
        
        Args:
            keys: Redis keys to delete
            
        Returns:
            Number of keys deleted
        """
        try:
            return self.client.delete(*keys)
        except Exception as e:
            logger.error(f"Failed to delete Redis keys {keys}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """
        Check if key exists in Redis
        
        Args:
            key: Redis key
            
        Returns:
            True if key exists, False otherwise
        """
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Failed to check Redis key existence {key}: {e}")
            return False
    
    def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration time for a key
        
        Args:
            key: Redis key
            ttl: Time to live in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return self.client.expire(key, ttl)
        except Exception as e:
            logger.error(f"Failed to set expiration for Redis key {key}: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """
        Get time to live for a key
        
        Args:
            key: Redis key
            
        Returns:
            TTL in seconds, -1 if no expiration, -2 if key doesn't exist
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Failed to get TTL for Redis key {key}: {e}")
            return -2
    
    def increment(self, key: str, amount: int = 1) -> int:
        """
        Increment a numeric value
        
        Args:
            key: Redis key
            amount: Amount to increment by
            
        Returns:
            New value after increment
        """
        try:
            return self.client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to increment Redis key {key}: {e}")
            return 0
    
    def decrement(self, key: str, amount: int = 1) -> int:
        """
        Decrement a numeric value
        
        Args:
            key: Redis key
            amount: Amount to decrement by
            
        Returns:
            New value after decrement
        """
        try:
            return self.client.decrby(key, amount)
        except Exception as e:
            logger.error(f"Failed to decrement Redis key {key}: {e}")
            return 0
    
    def hash_set(self, name: str, mapping: Dict[str, Any]) -> bool:
        """
        Set hash fields
        
        Args:
            name: Hash name
            mapping: Dictionary of field-value pairs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize values
            serialized_mapping = {}
            for field, value in mapping.items():
                if not isinstance(value, str):
                    serialized_mapping[field] = json.dumps(value)
                else:
                    serialized_mapping[field] = value
            
            return self.client.hset(name, mapping=serialized_mapping)
        except Exception as e:
            logger.error(f"Failed to set Redis hash {name}: {e}")
            return False
    
    def hash_get(self, name: str, key: str, default: Any = None) -> Any:
        """
        Get hash field value
        
        Args:
            name: Hash name
            key: Field name
            default: Default value if field not found
            
        Returns:
            Field value or default
        """
        try:
            value = self.client.hget(name, key)
            if value is None:
                return default
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Failed to get Redis hash field {name}.{key}: {e}")
            return default
    
    def hash_get_all(self, name: str) -> Dict[str, Any]:
        """
        Get all hash fields
        
        Args:
            name: Hash name
            
        Returns:
            Dictionary of all field-value pairs
        """
        try:
            hash_data = self.client.hgetall(name)
            
            # Deserialize values
            result = {}
            for field, value in hash_data.items():
                try:
                    result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[field] = value
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get Redis hash {name}: {e}")
            return {}
    
    def hash_delete(self, name: str, *keys: str) -> int:
        """
        Delete hash fields
        
        Args:
            name: Hash name
            keys: Field names to delete
            
        Returns:
            Number of fields deleted
        """
        try:
            return self.client.hdel(name, *keys)
        except Exception as e:
            logger.error(f"Failed to delete Redis hash fields {name}.{keys}: {e}")
            return 0
    
    def list_push(self, name: str, *values: Any) -> int:
        """
        Push values to list (left push)
        
        Args:
            name: List name
            values: Values to push
            
        Returns:
            New length of list
        """
        try:
            # Serialize values
            serialized_values = []
            for value in values:
                if not isinstance(value, str):
                    serialized_values.append(json.dumps(value))
                else:
                    serialized_values.append(value)
            
            return self.client.lpush(name, *serialized_values)
        except Exception as e:
            logger.error(f"Failed to push to Redis list {name}: {e}")
            return 0
    
    def list_pop(self, name: str, timeout: int = 0) -> Any:
        """
        Pop value from list (blocking right pop)
        
        Args:
            name: List name
            timeout: Timeout in seconds (0 for no timeout)
            
        Returns:
            Popped value or None
        """
        try:
            if timeout > 0:
                result = self.client.brpop(name, timeout=timeout)
                if result:
                    value = result[1]
                else:
                    return None
            else:
                value = self.client.rpop(name)
            
            if value is None:
                return None
            
            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
                
        except Exception as e:
            logger.error(f"Failed to pop from Redis list {name}: {e}")
            return None
    
    def list_length(self, name: str) -> int:
        """
        Get list length
        
        Args:
            name: List name
            
        Returns:
            List length
        """
        try:
            return self.client.llen(name)
        except Exception as e:
            logger.error(f"Failed to get Redis list length {name}: {e}")
            return 0
    
    def flush_db(self) -> bool:
        """
        Flush current database
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.flushdb()
            logger.info("Redis database flushed")
            return True
        except Exception as e:
            logger.error(f"Failed to flush Redis database: {e}")
            return False
    
    def get_info(self) -> Dict[str, Any]:
        """
        Get Redis server information
        
        Returns:
            Server information dictionary
        """
        try:
            return self.client.info()
        except Exception as e:
            logger.error(f"Failed to get Redis info: {e}")
            return {}


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


def get_redis_client() -> RedisClient:
    """
    Get global Redis client instance
    
    Returns:
        RedisClient instance
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client


# Cache decorator
def cache(ttl: int = 3600, key_prefix: str = "cache"):
    """
    Cache decorator for functions
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Cache key prefix
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            # Try to get from cache
            redis_client = get_redis_client()
            cached_result = redis_client.get(cache_key)
            
            if cached_result is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            redis_client.set(cache_key, result, ttl)
            logger.debug(f"Cache miss for {cache_key}, result cached")
            
            return result
        return wrapper
    return decorator 