"""
User Models
Database model definitions for customer entities
"""

from typing import Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

@dataclass
class Customer:
    """Customer database model"""
    id: str
    email: str
    password_hash: str
    first_name: str
    last_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

@dataclass  
class CustomerSession:
    """Customer session model"""
    id: str
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime
    
    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at 