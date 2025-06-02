"""
FastAPI Dependencies
Database connections and authentication dependencies
"""

from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Annotated
import logging

from app.utils.database import get_database_connection, CustomerDatabase
from app.utils.supabase_client import supabase_client

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
    Get current authenticated customer from JWT token
    
    Args:
        credentials: HTTP Authorization header with Bearer token
        
    Returns:
        dict: Customer information
        
    Raises:
        HTTPException: If token is invalid or customer not found
    """
    token = credentials.credentials
    
    try:
        # Verify token with Supabase if available
        if supabase_client.is_available():
            verification = await supabase_client.verify_token(token)
            if verification['success']:
                # Get customer from database using Supabase user ID
                customer = await CustomerDatabase.get_customer_by_id(verification['user_id'])
                if customer and customer['is_active']:
                    return {
                        'id': customer['id'],
                        'email': customer['email'],
                        'first_name': customer['first_name'],
                        'last_name': customer['last_name'],
                        'is_verified': customer['is_verified']
                    }
        
        # Fallback: Check local session token
        session = await CustomerDatabase.get_customer_session(token)
        if session and session['is_active']:
            return {
                'id': session['user_id'],
                'email': session['email'],
                'first_name': session['first_name'],
                'last_name': session['last_name'],
                'is_verified': True  # Local sessions are considered verified
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
        
        # Try Supabase verification first
        if supabase_client.is_available():
            verification = await supabase_client.verify_token(token)
            if verification['success']:
                customer = await CustomerDatabase.get_customer_by_id(verification['user_id'])
                if customer and customer['is_active']:
                    return {
                        'id': customer['id'],
                        'email': customer['email'],
                        'first_name': customer['first_name'],
                        'last_name': customer['last_name'],
                        'is_verified': customer['is_verified']
                    }
        
        # Fallback to local session
        session = await CustomerDatabase.get_customer_session(token)
        if session and session['is_active']:
            return {
                'id': session['user_id'],
                'email': session['email'],
                'first_name': session['first_name'],
                'last_name': session['last_name'],
                'is_verified': True
            }
            
    except Exception as e:
        logger.warning(f"Optional authentication failed: {e}")
    
    return None

# Type aliases for cleaner dependency injection
DatabaseDep = Annotated[object, Depends(get_database)]
CurrentCustomer = Annotated[dict, Depends(get_current_customer)]
ActiveCustomer = Annotated[dict, Depends(get_current_active_customer)]
OptionalCustomer = Annotated[Optional[dict], Depends(get_optional_customer)] 