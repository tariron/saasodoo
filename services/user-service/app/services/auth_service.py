"""
Authentication Service
Customer authentication business logic
"""

import asyncio
import bcrypt
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

# Import shared schemas
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../..'))
from shared.schemas.user import UserCreateSchema

from app.utils.database import CustomerDatabase
from app.utils.redis_session import RedisSessionManager
from app.utils.billing_client import billing_client
from app.services.user_service import UserService

logger = logging.getLogger(__name__)

class AuthService:
    """Customer authentication service"""

    @staticmethod
    def _sync_hash_password(password: str) -> str:
        """Synchronous bcrypt hash (CPU-bound)"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    async def hash_password(password: str) -> str:
        """Hash password using bcrypt in thread pool to avoid blocking"""
        return await asyncio.to_thread(AuthService._sync_hash_password, password)

    @staticmethod
    def _sync_verify_password(password: str, hashed_password: str) -> bool:
        """Synchronous bcrypt verify (CPU-bound)"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

    @staticmethod
    async def verify_password(password: str, hashed_password: str) -> bool:
        """Verify password against hash in thread pool to avoid blocking"""
        return await asyncio.to_thread(AuthService._sync_verify_password, password, hashed_password)

    @staticmethod
    def generate_session_token() -> str:
        """Generate secure session token"""
        return secrets.token_urlsafe(32)

    @staticmethod
    async def register_customer(customer_data: UserCreateSchema) -> Dict:
        """
        Register new customer

        Args:
            customer_data: Customer registration data

        Returns:
            dict: Registration result with customer info
        """
        try:
            # Hash password
            password_hash = await AuthService.hash_password(customer_data.password)

            # Prepare customer data for database
            db_customer_data = {
                'email': customer_data.email,
                'password_hash': password_hash,
                'first_name': customer_data.first_name,
                'last_name': customer_data.last_name,
                'is_active': True,
                'is_verified': False  # Require email verification
            }

            # Create customer in local database
            customer_id = await CustomerDatabase.create_customer(db_customer_data)

            # Generate email verification token
            verification_token = await AuthService.generate_verification_token(customer_id)

            # Get created customer
            customer = await CustomerDatabase.get_customer_by_id(customer_id)

            # Create KillBill account for the new customer (no subscription yet)
            billing_result = None
            billing_account_id = None
            try:
                full_name = f"{customer['first_name']} {customer['last_name']}"
                billing_result = await billing_client.create_customer_account(
                    customer_id=customer['id'],
                    email=customer['email'],
                    name=full_name,
                    company=None  # Can be added later via profile update
                )

                if billing_result and billing_result.get('success'):
                    billing_account_id = billing_result.get('killbill_account_id')
                    if billing_account_id:
                        logger.info(f"KillBill account created for customer {customer['id']}: {billing_account_id}")
                    else:
                        logger.error(f"KillBill account creation returned success but no account ID for customer {customer['id']}")
                        raise Exception("Billing account creation returned success but no account ID")
                else:
                    error_msg = billing_result.get('message', 'Unknown error') if billing_result else 'No response from billing service'
                    logger.error(f"Failed to create KillBill account for customer {customer['id']}: {error_msg}")
                    raise Exception(f"Billing account creation failed: {error_msg}")

            except Exception as e:
                logger.error(f"KillBill account creation failed for customer {customer['id']}: {e}")
                # Billing account creation is required - fail registration if it fails
                # Clean up the PostgreSQL customer account
                try:
                    customer_id_str = str(customer['id'])  # Ensure string type
                    logger.info(f"Attempting to clean up customer account {customer_id_str} due to KillBill failure")
                    cleanup_result = await UserService.delete_customer_account(customer_id_str)

                    if cleanup_result and cleanup_result.get('success'):
                        logger.info(f"Successfully cleaned up customer account {customer_id_str} from PostgreSQL")
                    else:
                        error_msg = cleanup_result.get('error', 'Unknown error') if cleanup_result else 'No result returned'
                        logger.error(f"Failed to clean up customer account {customer_id_str}: {error_msg}")
                        # Note: We still raise the original exception but log the cleanup failure
                except Exception as cleanup_error:
                    logger.error(f"Exception during customer cleanup for {customer['id']}: {cleanup_error}", exc_info=True)
                    # Continue to raise the original registration failure

                raise Exception(f"Customer registration failed: Unable to create billing account - {str(e)}")

            return {
                'success': True,
                'customer': {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                },
                'billing_account': billing_result,
                'billing_account_id': billing_account_id,
                'verification_token': verification_token
            }

        except Exception as e:
            logger.error(f"Customer registration failed: {e}")
            return {
                'success': False,
                'error': f"Registration failed: {str(e)}"
            }

    @staticmethod
    async def authenticate_customer(email: str, password: str, remember_me: bool = False) -> Dict:
        """
        Authenticate customer

        Args:
            email: Customer email
            password: Customer password
            remember_me: Extended session flag

        Returns:
            dict: Authentication result with tokens
        """
        try:
            # Get customer from database
            customer = await CustomerDatabase.get_customer_by_email(email)
            if not customer:
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }

            # Verify password
            if not await AuthService.verify_password(password, customer['password_hash']):
                return {
                    'success': False,
                    'error': 'Invalid email or password'
                }

            # Check if customer is active
            if not customer['is_active']:
                return {
                    'success': False,
                    'error': 'Account is deactivated'
                }

            # Check if customer email is verified
            if not customer['is_verified']:
                return {
                    'success': False,
                    'error': 'Email verification required. Please check your email and verify your account, or request a new verification email.',
                    'verification_required': True
                }

            # Create Redis session
            session_token = AuthService.generate_session_token()
            from datetime import timezone
            expires_at = datetime.now(timezone.utc) + timedelta(
                days=30 if remember_me else 7
            )

            # Store session in Redis with customer data
            customer_data = {
                'email': customer['email'],
                'first_name': customer['first_name'],
                'last_name': customer['last_name'],
                'is_active': customer['is_active']
            }

            success = await RedisSessionManager.create_session(
                str(customer['id']),
                session_token,
                expires_at,
                customer_data
            )

            if not success:
                logger.error(f"Failed to create Redis session for customer: {email}")
                return {
                    'success': False,
                    'error': 'Failed to create session'
                }

            tokens = {
                'access_token': session_token,
                'expires_at': expires_at.isoformat(),
                'token_type': 'redis'
            }

            logger.info(f"Customer authenticated with Redis session: {email}")

            return {
                'success': True,
                'customer': {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                },
                'tokens': tokens
            }

        except Exception as e:
            logger.error(f"Customer authentication failed: {e}")
            return {
                'success': False,
                'error': 'Authentication failed'
            }

    @staticmethod
    async def logout_customer(customer_id: str, session_token: str = None) -> Dict:
        """
        Logout customer and invalidate session

        Args:
            customer_id: Customer ID
            session_token: Session token to invalidate (optional)

        Returns:
            dict: Logout result
        """
        try:
            # Invalidate Redis session token if provided
            if session_token:
                success = await RedisSessionManager.delete_session(session_token)
                if success:
                    logger.info(f"Redis session invalidated for customer: {customer_id}")
                else:
                    logger.warning(f"Failed to invalidate session for customer: {customer_id}")
                    return {
                        'success': False,
                        'error': 'Failed to invalidate session'
                    }

            logger.info(f"Customer logged out: {customer_id}")
            return {
                'success': True,
                'message': 'Logged out successfully'
            }

        except Exception as e:
            logger.error(f"Customer logout failed: {e}")
            return {
                'success': False,
                'error': 'Logout failed'
            }

    @staticmethod
    async def request_password_reset(email: str) -> Dict:
        """
        Request password reset

        Args:
            email: Customer email

        Returns:
            dict: Password reset result
        """
        try:
            # Check if customer exists
            customer = await CustomerDatabase.get_customer_by_email(email)
            if not customer:
                return {
                    'success': False,
                    'error': 'Customer not found'
                }

            # Generate reset token
            reset_token = secrets.token_urlsafe(32)

            # Set expiration time (24 hours from now)
            from datetime import timezone
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

            # Store token in Redis
            success = await RedisSessionManager.create_reset_token(
                customer['id'],
                reset_token,
                expires_at,
                customer['email']
            )

            if not success:
                logger.error(f"Failed to create password reset token for: {email}")
                return {
                    'success': False,
                    'error': 'Failed to generate reset token'
                }

            return {
                'success': True,
                'reset_token': reset_token,
                'message': 'Password reset token generated and stored in Redis'
            }

        except Exception as e:
            logger.error(f"Password reset request failed: {e}")
            return {
                'success': False,
                'error': 'Password reset request failed'
            }

    @staticmethod
    async def change_password(customer_id: str, current_password: str, new_password: str) -> Dict:
        """
        Change customer password

        Args:
            customer_id: Customer ID
            current_password: Current password
            new_password: New password

        Returns:
            dict: Password change result
        """
        try:
            # Get customer
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            if not customer:
                return {
                    'success': False,
                    'error': 'Customer not found'
                }

            # Verify current password
            if not await AuthService.verify_password(current_password, customer['password_hash']):
                return {
                    'success': False,
                    'error': 'Current password is incorrect'
                }

            # Hash new password
            new_password_hash = await AuthService.hash_password(new_password)

            # Update password in database
            success = await CustomerDatabase.update_customer(
                customer_id,
                {'password_hash': new_password_hash}
            )

            if success:
                logger.info(f"Password changed for customer: {customer_id}")
                return {
                    'success': True,
                    'message': 'Password changed successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to update password'
                }

        except Exception as e:
            logger.error(f"Password change failed: {e}")
            return {
                'success': False,
                'error': 'Password change failed'
            }

    @staticmethod
    async def verify_email(verification_token: str) -> Dict:
        """
        Verify customer email

        Args:
            verification_token: Email verification token

        Returns:
            dict: Verification result
        """
        try:
            # Get and validate verification token from Redis
            token_data = await RedisSessionManager.get_verification_token(verification_token)
            if not token_data:
                return {
                    'success': False,
                    'error': 'Invalid or expired verification token'
                }

            customer_id = str(token_data['customer_id'])

            # Mark email as verified in users table
            verification_success = await CustomerDatabase.verify_customer_email(customer_id)
            if not verification_success:
                return {
                    'success': False,
                    'error': 'Failed to verify email'
                }

            # Delete verification token from Redis (mark as used)
            await RedisSessionManager.delete_verification_token(verification_token)

            # Get updated customer data
            customer = await CustomerDatabase.get_customer_by_id(customer_id)

            logger.info(f"Email verified successfully for customer: {customer_id}")

            return {
                'success': True,
                'customer_id': customer_id,
                'customer': {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                }
            }

        except Exception as e:
            logger.error(f"Email verification failed: {e}")
            return {
                'success': False,
                'error': 'Email verification failed'
            }

    @staticmethod
    async def refresh_token(refresh_token: str) -> Dict:
        """
        Refresh access token (not supported for Redis sessions)

        Args:
            refresh_token: Refresh token

        Returns:
            dict: Error - not supported
        """
        return {
            'success': False,
            'error': 'Token refresh not supported for Redis sessions. Please login again.'
        }

    @staticmethod
    async def send_welcome_email(email: str, first_name: str):
        """
        Send welcome email to new customer

        Args:
            email: Customer email
            first_name: Customer first name
        """
        try:
            from app.utils.notification_client import send_welcome_email
            result = await send_welcome_email(email, first_name)
            logger.info(f"✅ Welcome email sent to: {email} ({first_name}) - ID: {result.get('email_id')}")
        except Exception as e:
            logger.error(f"❌ Failed to send welcome email to {email}: {e}")
            # Don't raise the exception to avoid blocking user registration

    @staticmethod
    async def send_password_reset_email(email: str, reset_token: str):
        """
        Send password reset email

        Args:
            email: Customer email
            reset_token: Password reset token
        """
        try:
            from app.utils.notification_client import send_password_reset_email
            # We need to get the user's first name for the email
            # For now, we'll extract it from the email or use a default
            first_name = email.split('@')[0].title()  # Simple fallback

            result = await send_password_reset_email(email, first_name, reset_token)
            logger.info(f"✅ Password reset email sent to: {email} - ID: {result.get('email_id')}")
        except Exception as e:
            logger.error(f"❌ Failed to send password reset email to {email}: {e}")
            # Don't raise the exception to avoid blocking password reset process

    @staticmethod
    async def generate_verification_token(customer_id: str) -> str:
        """
        Generate email verification token for customer

        Args:
            customer_id: Customer ID

        Returns:
            str: Verification token
        """
        try:
            # Get customer data
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            if not customer:
                raise Exception("Customer not found")

            # Generate secure verification token
            verification_token = secrets.token_urlsafe(32)

            # Set expiration time (48 hours from now)
            from datetime import timezone
            expires_at = datetime.now(timezone.utc) + timedelta(hours=48)

            # Store token in Redis
            success = await RedisSessionManager.create_verification_token(
                customer_id,
                verification_token,
                expires_at,
                customer['email']
            )

            if not success:
                raise Exception("Failed to store verification token in Redis")

            logger.info(f"Verification token generated for customer: {customer_id}")
            return verification_token

        except Exception as e:
            logger.error(f"Failed to generate verification token: {e}")
            raise

    @staticmethod
    async def send_verification_email(email: str, first_name: str, verification_token: str):
        """
        Send email verification email

        Args:
            email: Customer email
            first_name: Customer first name
            verification_token: Email verification token
        """
        try:
            from app.utils.notification_client import send_verification_email
            result = await send_verification_email(email, first_name, verification_token)
            logger.info(f"✅ Verification email sent to: {email} ({first_name}) - ID: {result.get('email_id')}")
        except Exception as e:
            logger.error(f"❌ Failed to send verification email to {email}: {e}")
            # Don't raise the exception to avoid blocking user registration

    @staticmethod
    async def reset_password_with_token(reset_token: str, new_password: str) -> Dict:
        """
        Reset password using reset token

        Args:
            reset_token: Password reset token
            new_password: New password to set

        Returns:
            dict: Reset result
        """
        try:
            logger.info(f"🔍 Password reset attempt with token: {reset_token[:10]}...")

            # 1. Validate the reset token from Redis
            token_data = await RedisSessionManager.get_reset_token(reset_token)
            if not token_data:
                return {
                    'success': False,
                    'error': 'Invalid or expired password reset token'
                }

            customer_id = str(token_data['customer_id'])

            # 2. Hash the new password
            new_password_hash = await AuthService.hash_password(new_password)

            # 3. Update the customer's password
            success = await CustomerDatabase.update_customer(
                customer_id,
                {'password_hash': new_password_hash}
            )

            if not success:
                return {
                    'success': False,
                    'error': 'Failed to update password'
                }

            # 4. Delete the reset token from Redis (mark as used)
            await RedisSessionManager.delete_reset_token(reset_token)

            logger.info(f"Password reset successful for customer: {customer_id}")

            return {
                'success': True,
                'message': 'Password has been reset successfully'
            }

        except Exception as e:
            logger.error(f"Password reset with token failed: {e}")
            return {
                'success': False,
                'error': 'Password reset failed'
            }
