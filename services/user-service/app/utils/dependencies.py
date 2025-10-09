"""
FastAPI Dependencies
Database connections and authentication dependencies
"""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Annotated
import logging

from app.utils.database import get_database_connection, CustomerDatabase
from app.utils.redis_session import RedisSessionManager

logger = logging.getLogger(__name__)

# Security scheme for JWT tokens
security = HTTPBearer()

async def get_database():
    """Database connection dependency"""
    async with get_database_connection() as db:
        yield db

async def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Get current authenticated customer from session token

    Args:
        credentials: HTTP Authorization header with Bearer token

    Returns:
        dict: Customer information

    Raises:
        HTTPException: If token is invalid or customer not found
    """
    token = credentials.credentials

    try:
        # Get session from Redis
        session = await RedisSessionManager.get_session(token)
        if session and session.get('is_active'):
            # Get full customer data from database to ensure up-to-date info
            customer = await CustomerDatabase.get_customer_by_id(session['customer_id'])
            if customer and customer['is_active']:
                return {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                }

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_active_customer(
    current_customer: dict = Depends(get_current_customer)
) -> dict:
    """
    Get current active customer (must be verified)

    Args:
        current_customer: Customer from get_current_customer

    Returns:
        dict: Active customer information

    Raises:
        HTTPException: If customer is inactive or unverified
    """
    if not current_customer.get('is_verified'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required"
        )

    return current_customer

async def get_optional_customer(
    authorization: Optional[str] = Header(None)
) -> Optional[dict]:
    """
    Get optional customer (for endpoints that work with or without auth)

    Args:
        authorization: Optional Authorization header

    Returns:
        dict or None: Customer information if authenticated, None otherwise
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    try:
        token = authorization.split(" ")[1]

        # Get session from Redis
        session = await RedisSessionManager.get_session(token)
        if session and session.get('is_active'):
            # Get full customer data from database
            customer = await CustomerDatabase.get_customer_by_id(session['customer_id'])
            if customer and customer['is_active']:
                return {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                }

    except Exception as e:
        logger.warning(f"Optional authentication failed: {e}")

    return None

# Type aliases for cleaner dependency injection
DatabaseDep = Annotated[object, Depends(get_database)]
CurrentCustomer = Annotated[dict, Depends(get_current_customer)]
ActiveCustomer = Annotated[dict, Depends(get_current_active_customer)]
OptionalCustomer = Annotated[Optional[dict], Depends(get_optional_customer)]
