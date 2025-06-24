"""
Tenant data models and schemas
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID, uuid4
from enum import Enum

from pydantic import BaseModel, Field, validator


class TenantStatus(str, Enum):
    """Tenant status enumeration"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    PROVISIONING = "provisioning"
    ERROR = "error"


class TenantPlan(str, Enum):
    """Tenant subscription plan enumeration"""
    STARTER = "starter"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


# Base tenant model
class TenantBase(BaseModel):
    """Base tenant model with common fields"""
    name: str = Field(..., min_length=1, max_length=100, description="Tenant display name")
    plan: TenantPlan = Field(default=TenantPlan.STARTER, description="Subscription plan")
    max_instances: int = Field(default=1, ge=0, le=10, description="Maximum allowed instances")
    max_users: int = Field(default=5, ge=1, le=1000, description="Maximum users per instance")
    custom_domain: Optional[str] = Field(None, description="Custom domain if any")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    @validator('custom_domain')
    def validate_custom_domain(cls, v):
        """Validate custom domain format if provided"""
        if v is not None:
            # Basic domain validation
            if not v or '.' not in v:
                raise ValueError('Invalid domain format')
        return v


# Create tenant schema (for API requests)
class TenantCreate(TenantBase):
    """Schema for creating a new tenant"""
    customer_id: UUID = Field(..., description="Customer ID who owns this tenant")


# Update tenant schema (for API requests)
class TenantUpdate(BaseModel):
    """Schema for updating tenant information"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    plan: Optional[TenantPlan] = None
    max_instances: Optional[int] = Field(None, ge=0, le=10)
    max_users: Optional[int] = Field(None, ge=1, le=1000)
    custom_domain: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    status: Optional[TenantStatus] = None

    @validator('custom_domain')
    def validate_custom_domain(cls, v):
        """Validate custom domain format if provided"""
        if v is not None and v != "":
            if '.' not in v:
                raise ValueError('Invalid domain format')
        return v


# Full tenant model (database representation)
class Tenant(TenantBase):
    """Full tenant model with all database fields"""
    id: UUID = Field(default_factory=uuid4, description="Unique tenant ID")
    customer_id: UUID = Field(..., description="Customer ID who owns this tenant")
    status: TenantStatus = Field(default=TenantStatus.PROVISIONING, description="Current tenant status")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Response schema (for API responses)
class TenantResponse(BaseModel):
    """Schema for tenant API responses"""
    id: str = Field(..., description="Tenant ID")
    customer_id: str = Field(..., description="Customer ID")
    name: str = Field(..., description="Tenant name")
    plan: TenantPlan = Field(..., description="Subscription plan")
    status: TenantStatus = Field(..., description="Current status")
    max_instances: int = Field(..., description="Maximum allowed instances")
    max_users: int = Field(..., description="Maximum users per instance")
    custom_domain: Optional[str] = Field(None, description="Custom domain")
    instance_count: int = Field(default=0, description="Current number of instances")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic configuration"""
        from_attributes = True


# Tenant list response
class TenantListResponse(BaseModel):
    """Schema for tenant list API response"""
    tenants: list[TenantResponse] = Field(..., description="List of tenants")
    total: int = Field(..., description="Total number of tenants")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")

    class Config:
        """Pydantic configuration"""
        from_attributes = True 