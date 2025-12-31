"""
Redis Session Manager
Manages user sessions, password reset tokens, and email verification tokens using Redis

Uses async Redis (redis.asyncio) to avoid blocking the event loop.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
import redis.asyncio as aioredis
from redis.asyncio.sentinel import Sentinel

logger = logging.getLogger(__name__)

# Global async Redis client instance
_redis_client: Optional[aioredis.Redis] = None
_redis_initialized = False


async def init_redis_client():
    """Initialize async Redis client with Sentinel support"""
    global _redis_client, _redis_initialized

    if _redis_initialized and _redis_client is not None:
        return _redis_client

    use_sentinel = os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true"

    if use_sentinel:
        # Sentinel connection
        sentinel_host = os.getenv("REDIS_SENTINEL_HOST", "rfs-redis-cluster.saasodoo.svc.cluster.local")
        sentinel_port = int(os.getenv("REDIS_SENTINEL_PORT", "26379"))
        master_name = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")
        password = os.getenv("REDIS_PASSWORD") or None
        db = int(os.getenv("REDIS_DB", "0"))

        # Parse comma-separated hosts if provided
        if "," in sentinel_host:
            sentinel_hosts = [(h.strip(), sentinel_port) for h in sentinel_host.split(",")]
        else:
            sentinel_hosts = [(sentinel_host, sentinel_port)]

        logger.info(f"Initializing async Redis with Sentinel: hosts={sentinel_hosts}, master={master_name}")

        # Create async Sentinel instance
        sentinel = Sentinel(
            sentinel_hosts,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            socket_keepalive=True,
            retry_on_timeout=True
        )

        # Get master client (async)
        _redis_client = sentinel.master_for(
            master_name,
            socket_timeout=5.0,
            password=password,
            db=db,
            decode_responses=True,
            retry_on_timeout=True
        )

        # Test connection
        await _redis_client.ping()
        _redis_initialized = True
        logger.info("Async Redis client initialized successfully with Sentinel")

    else:
        # Direct connection (fallback)
        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        password = os.getenv("REDIS_PASSWORD", "")
        db = int(os.getenv("REDIS_DB", "0"))

        _redis_client = aioredis.Redis(
            host=host,
            port=port,
            password=password if password else None,
            db=db,
            decode_responses=True,
            socket_keepalive=True,
            health_check_interval=30
        )

        # Test connection
        await _redis_client.ping()
        _redis_initialized = True
        logger.info("Async Redis client initialized successfully with direct connection")

    return _redis_client


async def get_redis_client() -> aioredis.Redis:
    """Get async Redis client instance"""
    global _redis_client, _redis_initialized

    if not _redis_initialized or _redis_client is None:
        return await init_redis_client()

    return _redis_client


async def close_redis_client():
    """Close async Redis client connection"""
    global _redis_client, _redis_initialized

    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        _redis_initialized = False
        logger.info("Async Redis client closed")


class RedisSessionManager:
    """Manages sessions and tokens in Redis with automatic expiration (async)"""

    # Key prefixes
    SESSION_PREFIX = "session"
    RESET_TOKEN_PREFIX = "reset"
    VERIFY_TOKEN_PREFIX = "verify"

    @staticmethod
    async def _get_redis_client() -> aioredis.Redis:
        """Get async Redis client instance"""
        return await get_redis_client()

    @staticmethod
    def _serialize(data):
        """Serialize data to JSON string"""
        # Convert UUIDs to strings before serialization
        def convert_uuid(obj):
            if isinstance(obj, dict):
                return {k: convert_uuid(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_uuid(item) for item in obj]
            elif hasattr(obj, '__class__') and obj.__class__.__name__ == 'UUID':
                return str(obj)
            else:
                return obj

        converted_data = convert_uuid(data)
        return json.dumps(converted_data)

    @staticmethod
    def _deserialize(data):
        """Deserialize JSON string to data"""
        if data is None:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return data

    @staticmethod
    async def create_session(
        customer_id: str,
        session_token: str,
        expires_at: datetime,
        customer_data: Optional[Dict] = None
    ) -> bool:
        """
        Create a new session in Redis (async)

        Args:
            customer_id: Customer ID
            session_token: Unique session token
            expires_at: Session expiration datetime
            customer_data: Optional customer data to store with session

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()

            # Calculate TTL in seconds
            from datetime import timezone
            ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl <= 0:
                logger.error(f"Invalid TTL for session: {ttl}")
                return False

            # Prepare session data
            session_data = {
                'customer_id': customer_id,
                'session_token': session_token,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': expires_at.isoformat()
            }

            # Add customer data if provided
            if customer_data:
                session_data.update(customer_data)

            # Store in Redis with TTL (async)
            key = f"{RedisSessionManager.SESSION_PREFIX}:{session_token}"
            serialized_data = RedisSessionManager._serialize(session_data)
            success = await redis_client.setex(key, ttl, serialized_data)

            if success:
                logger.info(f"Session created for customer {customer_id} with TTL {ttl}s")
            else:
                logger.error(f"Failed to create session for customer {customer_id}")

            return bool(success)

        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return False

    @staticmethod
    async def get_session(session_token: str) -> Optional[Dict]:
        """
        Get session data from Redis (async)

        Args:
            session_token: Session token

        Returns:
            dict: Session data or None if not found/expired
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.SESSION_PREFIX}:{session_token}"

            session_data_raw = await redis_client.get(key)

            if session_data_raw:
                session_data = RedisSessionManager._deserialize(session_data_raw)
                logger.debug(f"Session found for token {session_token[:10]}...")
                return session_data

            logger.debug(f"Session not found or expired for token {session_token[:10]}...")
            return None

        except Exception as e:
            logger.error(f"Error retrieving session: {e}")
            return None

    @staticmethod
    async def delete_session(session_token: str) -> bool:
        """
        Delete session from Redis (logout) - async

        Args:
            session_token: Session token to delete

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.SESSION_PREFIX}:{session_token}"

            deleted = await redis_client.delete(key)

            if deleted > 0:
                logger.info(f"Session deleted: {session_token[:10]}...")
                return True
            else:
                logger.warning(f"Session not found for deletion: {session_token[:10]}...")
                return False

        except Exception as e:
            logger.error(f"Error deleting session: {e}")
            return False

    @staticmethod
    async def create_reset_token(
        customer_id: str,
        reset_token: str,
        expires_at: datetime,
        customer_email: str
    ) -> bool:
        """
        Create password reset token in Redis (async)

        Args:
            customer_id: Customer ID
            reset_token: Unique reset token
            expires_at: Token expiration datetime
            customer_email: Customer email

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()

            # Calculate TTL (24 hours)
            from datetime import timezone
            ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl <= 0:
                logger.error(f"Invalid TTL for reset token: {ttl}")
                return False

            # Prepare token data
            token_data = {
                'customer_id': customer_id,
                'email': customer_email,
                'reset_token': reset_token,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': expires_at.isoformat()
            }

            # Store in Redis with TTL (async)
            key = f"{RedisSessionManager.RESET_TOKEN_PREFIX}:{reset_token}"
            serialized_data = RedisSessionManager._serialize(token_data)
            success = await redis_client.setex(key, ttl, serialized_data)

            if success:
                logger.info(f"Password reset token created for customer {customer_id} with TTL {ttl}s")
            else:
                logger.error(f"Failed to create reset token for customer {customer_id}")

            return bool(success)

        except Exception as e:
            logger.error(f"Error creating reset token: {e}")
            return False

    @staticmethod
    async def get_reset_token(reset_token: str) -> Optional[Dict]:
        """
        Get and validate password reset token from Redis (async)

        Args:
            reset_token: Reset token

        Returns:
            dict: Token data or None if not found/expired
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.RESET_TOKEN_PREFIX}:{reset_token}"

            token_data_raw = await redis_client.get(key)

            if token_data_raw:
                token_data = RedisSessionManager._deserialize(token_data_raw)
                logger.info(f"Reset token found for token {reset_token[:10]}...")
                return token_data

            logger.info(f"Reset token not found or expired for token {reset_token[:10]}...")
            return None

        except Exception as e:
            logger.error(f"Error retrieving reset token: {e}")
            return None

    @staticmethod
    async def delete_reset_token(reset_token: str) -> bool:
        """
        Delete password reset token (mark as used) - async

        Args:
            reset_token: Reset token to delete

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.RESET_TOKEN_PREFIX}:{reset_token}"

            deleted = await redis_client.delete(key)

            if deleted > 0:
                logger.info(f"Reset token deleted: {reset_token[:10]}...")
                return True
            else:
                logger.warning(f"Reset token not found for deletion: {reset_token[:10]}...")
                return False

        except Exception as e:
            logger.error(f"Error deleting reset token: {e}")
            return False

    @staticmethod
    async def create_verification_token(
        customer_id: str,
        verification_token: str,
        expires_at: datetime,
        customer_email: str
    ) -> bool:
        """
        Create email verification token in Redis (async)

        Args:
            customer_id: Customer ID
            verification_token: Unique verification token
            expires_at: Token expiration datetime
            customer_email: Customer email

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()

            # Calculate TTL (48 hours)
            from datetime import timezone
            ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
            if ttl <= 0:
                logger.error(f"Invalid TTL for verification token: {ttl}")
                return False

            # Prepare token data
            token_data = {
                'customer_id': customer_id,
                'email': customer_email,
                'verification_token': verification_token,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'expires_at': expires_at.isoformat()
            }

            # Store in Redis with TTL (async)
            key = f"{RedisSessionManager.VERIFY_TOKEN_PREFIX}:{verification_token}"
            serialized_data = RedisSessionManager._serialize(token_data)
            success = await redis_client.setex(key, ttl, serialized_data)

            if success:
                logger.info(f"Email verification token created for customer {customer_id} with TTL {ttl}s")
            else:
                logger.error(f"Failed to create verification token for customer {customer_id}")

            return bool(success)

        except Exception as e:
            logger.error(f"Error creating verification token: {e}")
            return False

    @staticmethod
    async def get_verification_token(verification_token: str) -> Optional[Dict]:
        """
        Get and validate email verification token from Redis (async)

        Args:
            verification_token: Verification token

        Returns:
            dict: Token data or None if not found/expired
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.VERIFY_TOKEN_PREFIX}:{verification_token}"

            token_data_raw = await redis_client.get(key)

            if token_data_raw:
                token_data = RedisSessionManager._deserialize(token_data_raw)
                logger.info(f"Verification token found for token {verification_token[:10]}...")
                return token_data

            logger.info(f"Verification token not found or expired for token {verification_token[:10]}...")
            return None

        except Exception as e:
            logger.error(f"Error retrieving verification token: {e}")
            return None

    @staticmethod
    async def delete_verification_token(verification_token: str) -> bool:
        """
        Delete email verification token (mark as used) - async

        Args:
            verification_token: Verification token to delete

        Returns:
            bool: Success status
        """
        try:
            redis_client = await RedisSessionManager._get_redis_client()
            key = f"{RedisSessionManager.VERIFY_TOKEN_PREFIX}:{verification_token}"

            deleted = await redis_client.delete(key)

            if deleted > 0:
                logger.info(f"Verification token deleted: {verification_token[:10]}...")
                return True
            else:
                logger.warning(f"Verification token not found for deletion: {verification_token[:10]}...")
                return False

        except Exception as e:
            logger.error(f"Error deleting verification token: {e}")
            return False
