"""
User data schemas for Odoo SaaS Kit

Pydantic models for user data validation and serialization.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum


class UserRole(str, Enum):
    """User role enumeration"""
    ADMIN = "admin"
    USER = "user"
    SUPPORT = "support"


class UserStatus(str, Enum):
    """User status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class UserSchema(BaseModel):
    """Base user schema"""
    id: Optional[str] = None
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING
    phone: Optional[str] = Field(None, regex=r'^\+?[1-9]\d{1,14}$')
    company: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=50)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

    @validator('email')
    def validate_email(cls, v):
        """Validate email format"""
        if not v or '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower()

    @validator('phone')
    def validate_phone(cls, v):
        """Validate phone number"""
        if v and len(v.replace('+', '').replace('-', '').replace(' ', '')) < 7:
            raise ValueError('Phone number too short')
        return v

    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone"""
        if v:
            import pytz
            try:
                pytz.timezone(v)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError('Invalid timezone')
        return v


class UserCreateSchema(BaseModel):
    """Schema for creating a new user"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    phone: Optional[str] = Field(None, regex=r'^\+?[1-9]\d{1,14}$')
    company: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=50)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    accept_terms: bool = Field(..., description="User must accept terms and conditions")
    marketing_consent: Optional[bool] = False

    @validator('email')
    def validate_email(cls, v):
        """Validate email format"""
        return v.lower()

    @validator('password')
    def validate_password(cls, v):
        """Validate password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for at least one uppercase, lowercase, digit, and special character
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v)
        
        if not all([has_upper, has_lower, has_digit, has_special]):
            raise ValueError('Password must contain uppercase, lowercase, digit, and special character')
        
        return v

    @validator('accept_terms')
    def validate_terms(cls, v):
        """Validate terms acceptance"""
        if not v:
            raise ValueError('Terms and conditions must be accepted')
        return v


class UserUpdateSchema(BaseModel):
    """Schema for updating user information"""
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, regex=r'^\+?[1-9]\d{1,14}$')
    company: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=50)
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    avatar_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone"""
        if v:
            import pytz
            try:
                pytz.timezone(v)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError('Invalid timezone')
        return v


class UserResponseSchema(BaseModel):
    """Schema for user API responses"""
    id: str
    email: str
    first_name: str
    last_name: str
    role: UserRole
    status: UserStatus
    phone: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    instance_count: Optional[int] = 0
    subscription_status: Optional[str] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class UserLoginSchema(BaseModel):
    """Schema for user login"""
    email: EmailStr
    password: str = Field(..., min_length=1)
    remember_me: Optional[bool] = False

    @validator('email')
    def validate_email(cls, v):
        """Validate email format"""
        return v.lower()


class UserPasswordResetSchema(BaseModel):
    """Schema for password reset request"""
    email: EmailStr

    @validator('email')
    def validate_email(cls, v):
        """Validate email format"""
        return v.lower()


class UserPasswordChangeSchema(BaseModel):
    """Schema for password change"""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @validator('new_password')
    def validate_new_password(cls, v):
        """Validate new password strength"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for at least one uppercase, lowercase, digit, and special character
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in v)
        
        if not all([has_upper, has_lower, has_digit, has_special]):
            raise ValueError('Password must contain uppercase, lowercase, digit, and special character')
        
        return v

    @validator('confirm_password')
    def validate_password_match(cls, v, values):
        """Validate password confirmation"""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('Passwords do not match')
        return v


class UserEmailVerificationSchema(BaseModel):
    """Schema for email verification"""
    token: str = Field(..., min_length=1)


class UserProfileSchema(BaseModel):
    """Schema for user profile information"""
    id: str
    email: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    company: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    instance_count: int = 0
    subscription_plan: Optional[str] = None
    subscription_status: Optional[str] = None
    billing_info: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class UserPreferencesSchema(BaseModel):
    """Schema for user preferences"""
    timezone: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    email_notifications: Optional[bool] = True
    sms_notifications: Optional[bool] = False
    marketing_emails: Optional[bool] = False
    theme: Optional[str] = Field(None, regex=r'^(light|dark|auto)$')
    date_format: Optional[str] = Field(None, regex=r'^(DD/MM/YYYY|MM/DD/YYYY|YYYY-MM-DD)$')
    time_format: Optional[str] = Field(None, regex=r'^(12|24)$')
    currency: Optional[str] = Field(None, max_length=3)

    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone"""
        if v:
            import pytz
            try:
                pytz.timezone(v)
            except pytz.exceptions.UnknownTimeZoneError:
                raise ValueError('Invalid timezone')
        return v


class UserStatsSchema(BaseModel):
    """Schema for user statistics"""
    total_instances: int = 0
    active_instances: int = 0
    total_storage_used: float = 0.0  # in GB
    total_bandwidth_used: float = 0.0  # in GB
    last_login: Optional[datetime] = None
    account_age_days: int = 0
    subscription_days_remaining: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class UserListSchema(BaseModel):
    """Schema for user list responses"""
    users: List[UserResponseSchema]
    total: int
    page: int
    per_page: int
    pages: int

    class Config:
        from_attributes = True 