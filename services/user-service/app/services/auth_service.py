"""
Authentication Service
Customer authentication business logic
"""

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
from app.utils.supabase_client import supabase_client

logger = logging.getLogger(__name__)

class AuthService:
    """Customer authentication service"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    
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
            dict: Registration result with customer info and Supabase response
        """
        try:
            # Hash password
            password_hash = AuthService.hash_password(customer_data.password)
            
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
            
            # Try to create customer in Supabase for enhanced features
            supabase_result = None
            if supabase_client.is_available():
                try:
                    supabase_result = await supabase_client.sign_up_customer(
                        customer_data.email,
                        customer_data.password,
                        metadata={
                            'first_name': customer_data.first_name,
                            'last_name': customer_data.last_name,
                            'local_customer_id': customer_id
                        }
                    )
                    
                    if supabase_result['success']:
                        logger.info(f"Customer created in Supabase: {customer_data.email}")
                except Exception as e:
                    logger.warning(f"Supabase registration failed, using local auth only: {e}")
            
            # Get created customer
            customer = await CustomerDatabase.get_customer_by_id(customer_id)
            
            return {
                'success': True,
                'customer': {
                    'id': customer['id'],
                    'email': customer['email'],
                    'first_name': customer['first_name'],
                    'last_name': customer['last_name'],
                    'is_verified': customer['is_verified']
                },
                'supabase_user': supabase_result
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
            if not AuthService.verify_password(password, customer['password_hash']):
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
            
            # Try Supabase authentication first
            tokens = {}
            if supabase_client.is_available():
                try:
                    supabase_result = await supabase_client.sign_in_customer(email, password)
                    if supabase_result['success']:
                        tokens = {
                            'access_token': supabase_result['access_token'],
                            'refresh_token': supabase_result['refresh_token'],
                            'expires_at': supabase_result['expires_at'],
                            'token_type': 'supabase'
                        }
                        logger.info(f"Customer authenticated with Supabase: {email}")
                except Exception as e:
                    logger.warning(f"Supabase authentication failed, using local session: {e}")
            
            # Fallback to local session token
            if not tokens:
                session_token = AuthService.generate_session_token()
                expires_at = datetime.utcnow() + timedelta(
                    days=30 if remember_me else 7
                )
                
                # Create session in database
                await CustomerDatabase.create_customer_session(
                    customer['id'], session_token, expires_at
                )
                
                tokens = {
                    'access_token': session_token,
                    'expires_at': expires_at.isoformat(),
                    'token_type': 'local'
                }
                
                logger.info(f"Customer authenticated with local session: {email}")
            
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
            # Invalidate the local session token if provided
            if session_token:
                success = await CustomerDatabase.invalidate_customer_session(session_token)
                if success:
                    logger.info(f"Local session invalidated for customer: {customer_id}")
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
            
            # Try Supabase password reset first
            if supabase_client.is_available():
                try:
                    supabase_result = await supabase_client.reset_password(email)
                    if supabase_result['success']:
                        return {
                            'success': True,
                            'message': 'Password reset email sent via Supabase'
                        }
                except Exception as e:
                    logger.warning(f"Supabase password reset failed: {e}")
            
            # Generate local reset token
            reset_token = secrets.token_urlsafe(32)
            
            # For now, just return the token
            # In production, store this in password_resets table and send email
            
            return {
                'success': True,
                'reset_token': reset_token,
                'message': 'Password reset token generated'
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
            if not AuthService.verify_password(current_password, customer['password_hash']):
                return {
                    'success': False,
                    'error': 'Current password is incorrect'
                }
            
            # Hash new password
            new_password_hash = AuthService.hash_password(new_password)
            
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
            # For now, just mark email as verified
            # In production, you would validate the token against stored verification tokens
            
            # This is a simplified implementation
            # You would need to implement proper token validation
            
            return {
                'success': True,
                'customer_id': 'placeholder',
                'customer': 'placeholder'
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
        Refresh access token
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            dict: New tokens
        """
        try:
            # Try Supabase token refresh
            if supabase_client.is_available():
                try:
                    supabase_result = await supabase_client.refresh_session(refresh_token)
                    if supabase_result['success']:
                        return {
                            'success': True,
                            'tokens': {
                                'access_token': supabase_result['access_token'],
                                'refresh_token': supabase_result['refresh_token'],
                                'expires_at': supabase_result['expires_at']
                            }
                        }
                except Exception as e:
                    logger.warning(f"Supabase token refresh failed: {e}")
            
            # For local tokens, you would validate and issue new ones
            return {
                'success': False,
                'error': 'Token refresh not supported for local sessions'
            }
            
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            return {
                'success': False,
                'error': 'Token refresh failed'
            }
    
    @staticmethod
    async def send_welcome_email(email: str, first_name: str):
        """
        Send welcome email to new customer
        
        Args:
            email: Customer email
            first_name: Customer first name
        """
        # This would integrate with the notification service
        # For now, just log the action
        logger.info(f"Welcome email sent to: {email} ({first_name})")
    
    @staticmethod
    async def send_password_reset_email(email: str, reset_token: str):
        """
        Send password reset email
        
        Args:
            email: Customer email
            reset_token: Password reset token
        """
        # This would integrate with the notification service
        # For now, just log the action
        logger.info(f"Password reset email sent to: {email} (token: {reset_token[:8]}...)") 