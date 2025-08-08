"""
Authentication Routes
Customer registration, login, password reset, and email verification
"""

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import bcrypt
import secrets
from datetime import datetime, timedelta
import logging

# Import shared schemas
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))
from shared.schemas.user import (
    UserCreateSchema, UserLoginSchema, UserPasswordResetSchema,
    UserPasswordChangeSchema, UserPasswordResetCompleteSchema, UserEmailVerificationSchema, UserResponseSchema,
    UserProfileSchema, UserResendVerificationSchema
)

from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.dependencies import DatabaseDep, CurrentCustomer, ActiveCustomer
from app.utils.supabase_client import supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Security scheme for JWT tokens
security = HTTPBearer()

@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_customer(
    customer_data: UserCreateSchema,
    background_tasks: BackgroundTasks,
    db: DatabaseDep
):
    """
    Register new customer
    
    Creates customer account with email verification
    Integrates with Supabase for enhanced authentication
    """
    try:
        # Check if customer already exists
        existing_customer = await UserService.get_customer_by_email(customer_data.email)
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer with this email already exists"
            )
        
        # Create customer account
        customer_result = await AuthService.register_customer(customer_data)
        
        if not customer_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=customer_result['error']
            )
        
        # Send welcome email (background task)
        background_tasks.add_task(
            AuthService.send_welcome_email,
            customer_result['customer']['email'],
            customer_result['customer']['first_name']
        )
        
        # Send verification email (background task)
        background_tasks.add_task(
            AuthService.send_verification_email,
            customer_result['customer']['email'],
            customer_result['customer']['first_name'],
            customer_result['verification_token']
        )
        
        logger.info(f"Customer registered successfully: {customer_data.email}")
        
        return {
            "success": True,
            "message": "Customer registered successfully",
            "customer": {
                "id": customer_result['customer']['id'],
                "email": customer_result['customer']['email'],
                "first_name": customer_result['customer']['first_name'],
                "last_name": customer_result['customer']['last_name'],
                "requires_verification": not customer_result['customer']['is_verified']
            },
            "supabase_user": customer_result.get('supabase_user')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Customer registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/login", response_model=dict)
async def login_customer(
    login_data: UserLoginSchema,
    db: DatabaseDep
):
    """
    Customer login
    
    Authenticates customer and returns access tokens
    Supports both Supabase and local authentication
    """
    try:
        # Authenticate customer
        auth_result = await AuthService.authenticate_customer(
            login_data.email,
            login_data.password,
            login_data.remember_me
        )
        
        if not auth_result['success']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=auth_result['error']
            )
        
        logger.info(f"Customer logged in successfully: {login_data.email}")
        
        return {
            "success": True,
            "message": "Login successful",
            "customer": auth_result['customer'],
            "tokens": auth_result['tokens']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Customer login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.post("/logout", response_model=dict)
async def logout_customer(
    current_customer: CurrentCustomer,
    db: DatabaseDep,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Customer logout
    
    Invalidates current session and tokens
    """
    try:
        # Extract session token for invalidation
        session_token = credentials.credentials
        
        # Logout customer with token invalidation
        logout_result = await AuthService.logout_customer(
            current_customer['id'], 
            session_token
        )
        
        if not logout_result['success']:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=logout_result.get('error', 'Logout failed')
            )
        
        logger.info(f"Customer logged out: {current_customer['email']}")
        
        return {
            "success": True,
            "message": "Logout successful"
        }
        
    except Exception as e:
        logger.error(f"Customer logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.post("/password-reset", response_model=dict)
async def request_password_reset(
    reset_data: UserPasswordResetSchema,
    background_tasks: BackgroundTasks,
    db: DatabaseDep
):
    """
    Request password reset
    
    Sends password reset email to customer
    """
    try:
        # Check if customer exists
        customer = await UserService.get_customer_by_email(reset_data.email)
        if not customer:
            # Don't reveal if email exists for security
            return {
                "success": True,
                "message": "If the email exists, a password reset link has been sent"
            }
        
        # Generate and send password reset
        reset_result = await AuthService.request_password_reset(reset_data.email)
        
        if reset_result['success']:
            # Send reset email (background task)
            background_tasks.add_task(
                AuthService.send_password_reset_email,
                reset_data.email,
                reset_result['reset_token']
            )
        
        logger.info(f"Password reset requested for: {reset_data.email}")
        
        return {
            "success": True,
            "message": "If the email exists, a password reset link has been sent"
        }
        
    except Exception as e:
        logger.error(f"Password reset request error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset request failed"
        )

@router.post("/password-reset-complete", response_model=dict)
async def complete_password_reset(
    reset_data: UserPasswordResetCompleteSchema,
    db: DatabaseDep
):
    """
    Complete password reset with token
    
    Sets new password using reset token
    """
    try:
        # For now, we need to implement token-based password reset in AuthService
        # This is a simplified implementation - in production you'd want proper token validation
        
        # Since the current backend doesn't have token-based reset logic,
        # we'll add this functionality to AuthService.reset_password_with_token()
        from app.services.auth_service import AuthService
        
        # This method doesn't exist yet - we'll need to implement it
        reset_result = await AuthService.reset_password_with_token(
            reset_data.token,
            reset_data.new_password
        )
        
        if not reset_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=reset_result['error']
            )
        
        logger.info(f"Password reset completed with token")
        
        return {
            "success": True,
            "message": "Password has been reset successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset completion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed"
        )

@router.post("/password-change", response_model=dict)
async def change_password(
    password_data: UserPasswordChangeSchema,
    current_customer: ActiveCustomer,
    db: DatabaseDep
):
    """
    Change customer password
    
    Requires current password verification
    """
    try:
        # Change password
        change_result = await AuthService.change_password(
            current_customer['id'],
            password_data.current_password,
            password_data.new_password
        )
        
        if not change_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=change_result['error']
            )
        
        logger.info(f"Password changed for customer: {current_customer['email']}")
        
        return {
            "success": True,
            "message": "Password changed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password change failed"
        )

@router.post("/verify-email", response_model=dict)
async def verify_email(
    verification_data: UserEmailVerificationSchema,
    db: DatabaseDep
):
    """
    Verify customer email address
    
    Activates customer account
    """
    try:
        # Verify email
        verify_result = await AuthService.verify_email(verification_data.token)
        
        if not verify_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=verify_result['error']
            )
        
        logger.info(f"Email verified for customer: {verify_result['customer_id']}")
        
        return {
            "success": True,
            "message": "Email verified successfully",
            "customer": verify_result['customer']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email verification failed"
        )

@router.post("/resend-verification", response_model=dict)
async def resend_verification_email(
    verification_data: UserResendVerificationSchema,
    background_tasks: BackgroundTasks,
    db: DatabaseDep
):
    """
    Resend email verification email
    
    Generates a new verification token and sends verification email
    """
    try:
        # Check if customer exists
        customer = await UserService.get_customer_by_email(verification_data.email)
        if not customer:
            # Don't reveal if email exists for security
            return {
                "success": True,
                "message": "If the email exists and is unverified, a verification email has been sent"
            }
        
        # Check if customer is already verified
        if customer['is_verified']:
            return {
                "success": True,
                "message": "Email is already verified"
            }
        
        # Generate new verification token
        verification_token = await AuthService.generate_verification_token(customer['id'])
        
        # Send verification email (background task)
        background_tasks.add_task(
            AuthService.send_verification_email,
            customer['email'],
            customer['first_name'],
            verification_token
        )
        
        logger.info(f"Verification email resent for: {verification_data.email}")
        
        return {
            "success": True,
            "message": "If the email exists and is unverified, a verification email has been sent"
        }
        
    except Exception as e:
        logger.error(f"Resend verification email error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email"
        )

@router.post("/refresh-token", response_model=dict)
async def refresh_token(
    refresh_token: str,
    db: DatabaseDep
):
    """
    Refresh access token
    
    Uses refresh token to get new access token
    """
    try:
        # Refresh token
        refresh_result = await AuthService.refresh_token(refresh_token)
        
        if not refresh_result['success']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=refresh_result['error']
            )
        
        return {
            "success": True,
            "tokens": refresh_result['tokens']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token refresh failed"
        )

@router.get("/me", response_model=UserProfileSchema)
async def get_current_customer_info(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get current customer information
    
    Returns detailed customer profile
    """
    try:
        # Get full customer details
        customer_details = await UserService.get_customer_profile(current_customer['id'])
        
        if not customer_details:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        return customer_details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get customer info error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer information"
        ) 