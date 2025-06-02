"""
Supabase Client Configuration
Enhanced authentication features for customer management
"""

import os
from supabase import create_client, Client
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase client wrapper for authentication services"""
    
    def __init__(self):
        self.url: str = os.getenv("SUPABASE_URL", "")
        self.key: str = os.getenv("SUPABASE_ANON_KEY", "")
        self.service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")
        self.client: Optional[Client] = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.client = None
        else:
            logger.warning("Supabase credentials not found in environment")
    
    def get_client(self) -> Optional[Client]:
        """Get Supabase client instance"""
        return self.client
    
    def is_available(self) -> bool:
        """Check if Supabase is available and configured"""
        return self.client is not None
    
    async def sign_up_customer(self, email: str, password: str, metadata: dict = None) -> dict:
        """
        Sign up new customer with Supabase Auth
        
        Args:
            email: Customer email
            password: Customer password
            metadata: Additional customer metadata
            
        Returns:
            dict: Supabase auth response
        """
        if not self.client:
            raise Exception("Supabase client not available")
        
        try:
            response = self.client.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": metadata or {}
                }
            })
            
            if response.user:
                logger.info(f"Customer signed up successfully: {email}")
                return {
                    "success": True,
                    "user_id": response.user.id,
                    "email": response.user.email,
                    "email_confirmed": response.user.email_confirmed_at is not None
                }
            else:
                logger.error(f"Failed to sign up customer: {email}")
                return {
                    "success": False,
                    "error": "Failed to create account"
                }
                
        except Exception as e:
            logger.error(f"Supabase sign up error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def sign_in_customer(self, email: str, password: str) -> dict:
        """
        Sign in customer with Supabase Auth
        
        Args:
            email: Customer email
            password: Customer password
            
        Returns:
            dict: Supabase auth response with tokens
        """
        if not self.client:
            raise Exception("Supabase client not available")
        
        try:
            response = self.client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if response.user and response.session:
                logger.info(f"Customer signed in successfully: {email}")
                return {
                    "success": True,
                    "user_id": response.user.id,
                    "email": response.user.email,
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": response.session.expires_at
                }
            else:
                logger.error(f"Failed to sign in customer: {email}")
                return {
                    "success": False,
                    "error": "Invalid credentials"
                }
                
        except Exception as e:
            logger.error(f"Supabase sign in error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def reset_password(self, email: str) -> dict:
        """
        Send password reset email to customer
        
        Args:
            email: Customer email
            
        Returns:
            dict: Reset password response
        """
        if not self.client:
            raise Exception("Supabase client not available")
        
        try:
            response = self.client.auth.reset_password_email(email)
            logger.info(f"Password reset email sent to: {email}")
            return {
                "success": True,
                "message": "Password reset email sent"
            }
            
        except Exception as e:
            logger.error(f"Password reset error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def verify_token(self, token: str) -> dict:
        """
        Verify customer JWT token
        
        Args:
            token: JWT access token
            
        Returns:
            dict: Token verification response
        """
        if not self.client:
            raise Exception("Supabase client not available")
        
        try:
            response = self.client.auth.get_user(token)
            
            if response.user:
                return {
                    "success": True,
                    "user_id": response.user.id,
                    "email": response.user.email,
                    "metadata": response.user.user_metadata
                }
            else:
                return {
                    "success": False,
                    "error": "Invalid token"
                }
                
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def refresh_session(self, refresh_token: str) -> dict:
        """
        Refresh customer session using refresh token
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            dict: New session tokens
        """
        if not self.client:
            raise Exception("Supabase client not available")
        
        try:
            response = self.client.auth.refresh_session(refresh_token)
            
            if response.session:
                return {
                    "success": True,
                    "access_token": response.session.access_token,
                    "refresh_token": response.session.refresh_token,
                    "expires_at": response.session.expires_at
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to refresh session"
                }
                
        except Exception as e:
            logger.error(f"Session refresh error: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Global Supabase client instance
supabase_client = SupabaseClient() 