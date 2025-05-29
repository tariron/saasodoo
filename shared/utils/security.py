"""
Security utilities for Odoo SaaS Kit

Provides password hashing, JWT tokens, encryption, and other security utilities.
"""

import os
import secrets
import hashlib
import hmac
import base64
import logging
from typing import Optional, Dict, Any, Union
from datetime import datetime, timedelta
import bcrypt
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class SecurityUtils:
    """Security utilities class"""
    
    def __init__(self):
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "your_super_secret_jwt_key_change_me")
        self.jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        self.encryption_key = os.getenv("ENCRYPTION_KEY", "your_32_character_encryption_key")
        self.password_salt = os.getenv("PASSWORD_SALT", "your_password_salt_change_me")
        
        # Initialize Fernet encryption
        self._init_encryption()
    
    def _init_encryption(self):
        """Initialize Fernet encryption"""
        try:
            # Derive key from encryption key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self.password_salt.encode(),
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self.encryption_key.encode()))
            self.fernet = Fernet(key)
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            # Fallback to a default key (not secure for production)
            self.fernet = Fernet(Fernet.generate_key())
    
    def hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password
        """
        try:
            # Generate salt and hash password
            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to hash password: {e}")
            raise
    
    def verify_password(self, password: str, hashed_password: str) -> bool:
        """
        Verify password against hash
        
        Args:
            password: Plain text password
            hashed_password: Hashed password
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to verify password: {e}")
            return False
    
    def generate_token(
        self,
        payload: Dict[str, Any],
        expires_in: Optional[int] = None
    ) -> str:
        """
        Generate JWT token
        
        Args:
            payload: Token payload
            expires_in: Expiration time in minutes
            
        Returns:
            JWT token string
        """
        try:
            # Set default expiration
            if expires_in is None:
                expires_in = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
            
            # Add expiration to payload
            payload_copy = payload.copy()
            payload_copy["exp"] = datetime.utcnow() + timedelta(minutes=expires_in)
            payload_copy["iat"] = datetime.utcnow()
            
            # Generate token
            token = jwt.encode(payload_copy, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            logger.error(f"Failed to generate token: {e}")
            raise
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded payload or None if invalid
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to verify token: {e}")
            return None
    
    def generate_refresh_token(self, user_id: str) -> str:
        """
        Generate refresh token
        
        Args:
            user_id: User ID
            
        Returns:
            Refresh token string
        """
        expires_days = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))
        payload = {
            "user_id": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=expires_days),
            "iat": datetime.utcnow()
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def encrypt_data(self, data: Union[str, bytes]) -> str:
        """
        Encrypt data using Fernet
        
        Args:
            data: Data to encrypt
            
        Returns:
            Base64 encoded encrypted data
        """
        try:
            if isinstance(data, str):
                data = data.encode('utf-8')
            
            encrypted = self.fernet.encrypt(data)
            return base64.urlsafe_b64encode(encrypted).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encrypt data: {e}")
            raise
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decrypt data using Fernet
        
        Args:
            encrypted_data: Base64 encoded encrypted data
            
        Returns:
            Decrypted data as string
        """
        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode('utf-8'))
            decrypted = self.fernet.decrypt(encrypted_bytes)
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise
    
    def generate_api_key(self, length: int = 32) -> str:
        """
        Generate secure API key
        
        Args:
            length: Key length
            
        Returns:
            Random API key
        """
        return secrets.token_urlsafe(length)
    
    def generate_secure_random(self, length: int = 16) -> str:
        """
        Generate secure random string
        
        Args:
            length: String length
            
        Returns:
            Random string
        """
        return secrets.token_hex(length)
    
    def hash_api_key(self, api_key: str) -> str:
        """
        Hash API key for storage
        
        Args:
            api_key: API key to hash
            
        Returns:
            Hashed API key
        """
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    def verify_api_key(self, api_key: str, hashed_key: str) -> bool:
        """
        Verify API key against hash
        
        Args:
            api_key: API key to verify
            hashed_key: Stored hash
            
        Returns:
            True if key matches, False otherwise
        """
        return hmac.compare_digest(self.hash_api_key(api_key), hashed_key)
    
    def generate_otp(self, length: int = 6) -> str:
        """
        Generate numeric OTP
        
        Args:
            length: OTP length
            
        Returns:
            Numeric OTP string
        """
        return ''.join([str(secrets.randbelow(10)) for _ in range(length)])
    
    def generate_csrf_token(self) -> str:
        """
        Generate CSRF token
        
        Returns:
            CSRF token
        """
        return secrets.token_urlsafe(32)
    
    def verify_csrf_token(self, token: str, stored_token: str) -> bool:
        """
        Verify CSRF token
        
        Args:
            token: Token to verify
            stored_token: Stored token
            
        Returns:
            True if tokens match, False otherwise
        """
        return hmac.compare_digest(token, stored_token)
    
    def sanitize_input(self, input_string: str) -> str:
        """
        Sanitize user input
        
        Args:
            input_string: Input to sanitize
            
        Returns:
            Sanitized string
        """
        # Remove null bytes and control characters
        sanitized = ''.join(char for char in input_string if ord(char) >= 32 or char in '\t\n\r')
        
        # Limit length
        max_length = 10000
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized.strip()
    
    def validate_email(self, email: str) -> bool:
        """
        Validate email format
        
        Args:
            email: Email to validate
            
        Returns:
            True if valid, False otherwise
        """
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    def validate_password_strength(self, password: str) -> Dict[str, Any]:
        """
        Validate password strength
        
        Args:
            password: Password to validate
            
        Returns:
            Dictionary with validation results
        """
        result = {
            "valid": True,
            "errors": [],
            "score": 0
        }
        
        # Check length
        if len(password) < 8:
            result["errors"].append("Password must be at least 8 characters long")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Check for uppercase
        if not any(c.isupper() for c in password):
            result["errors"].append("Password must contain at least one uppercase letter")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Check for lowercase
        if not any(c.islower() for c in password):
            result["errors"].append("Password must contain at least one lowercase letter")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Check for digits
        if not any(c.isdigit() for c in password):
            result["errors"].append("Password must contain at least one digit")
            result["valid"] = False
        else:
            result["score"] += 1
        
        # Check for special characters
        special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
        if not any(c in special_chars for c in password):
            result["errors"].append("Password must contain at least one special character")
            result["valid"] = False
        else:
            result["score"] += 1
        
        return result
    
    def rate_limit_key(self, identifier: str, action: str) -> str:
        """
        Generate rate limit key
        
        Args:
            identifier: User identifier (IP, user ID, etc.)
            action: Action being rate limited
            
        Returns:
            Rate limit key
        """
        return f"rate_limit:{action}:{identifier}"
    
    def generate_session_id(self) -> str:
        """
        Generate secure session ID
        
        Returns:
            Session ID
        """
        return secrets.token_urlsafe(32)


# Global security utils instance
_security_utils: Optional[SecurityUtils] = None


def get_security_utils() -> SecurityUtils:
    """
    Get global security utils instance
    
    Returns:
        SecurityUtils instance
    """
    global _security_utils
    if _security_utils is None:
        _security_utils = SecurityUtils()
    return _security_utils


# Convenience functions
def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    return get_security_utils().hash_password(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return get_security_utils().verify_password(password, hashed_password)


def generate_token(payload: Dict[str, Any], expires_in: Optional[int] = None) -> str:
    """Generate JWT token"""
    return get_security_utils().generate_token(payload, expires_in)


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode JWT token"""
    return get_security_utils().verify_token(token)


def encrypt_data(data: Union[str, bytes]) -> str:
    """Encrypt data"""
    return get_security_utils().encrypt_data(data)


def decrypt_data(encrypted_data: str) -> str:
    """Decrypt data"""
    return get_security_utils().decrypt_data(encrypted_data)


def generate_api_key(length: int = 32) -> str:
    """Generate secure API key"""
    return get_security_utils().generate_api_key(length)


def generate_otp(length: int = 6) -> str:
    """Generate numeric OTP"""
    return get_security_utils().generate_otp(length)


def sanitize_input(input_string: str) -> str:
    """Sanitize user input"""
    return get_security_utils().sanitize_input(input_string)


def validate_email(email: str) -> bool:
    """Validate email format"""
    return get_security_utils().validate_email(email)


def validate_password_strength(password: str) -> Dict[str, Any]:
    """Validate password strength"""
    return get_security_utils().validate_password_strength(password) 