"""
Instance Management Schemas
Pydantic schemas for Odoo instance creation, management, and responses
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class InstanceStatus(str, Enum):
    """Instance status enumeration"""
    PENDING = "pending"
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    FAILED = "failed"
    DELETING = "deleting"
    DELETED = "deleted"


class InstanceType(str, Enum):
    """Instance type enumeration"""
    COMMUNITY = "community"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class InstanceCreateSchema(BaseModel):
    """Schema for creating a new Odoo instance"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "name": "My Company Odoo",
                "subdomain": "mycompany",
                "odoo_version": "17.0",
                "instance_type": "community",
                "admin_email": "admin@mycompany.com",
                "admin_password": "SecurePass123!",
                "timezone": "America/New_York",
                "language": "en_US",
                "country_code": "US",
                "modules": ["sale", "purchase", "inventory"],
                "ssl_enabled": True,
                "backup_enabled": True
            }
        }
    )
    
    name: str = Field(..., min_length=3, max_length=50, description="Instance name")
    subdomain: str = Field(..., min_length=3, max_length=30, pattern=r'^[a-z0-9-]+$', description="Subdomain for the instance")
    odoo_version: str = Field(default="17.0", description="Odoo version to deploy")
    instance_type: InstanceType = Field(default=InstanceType.COMMUNITY, description="Type of Odoo instance")
    database_name: Optional[str] = Field(None, description="Custom database name")
    admin_email: str = Field(..., description="Administrator email for the instance")
    admin_password: str = Field(..., min_length=8, description="Administrator password")
    timezone: str = Field(default="UTC", description="Instance timezone")
    language: str = Field(default="en_US", description="Default language")
    country_code: str = Field(default="US", description="Country code")
    modules: Optional[List[str]] = Field(default=[], description="Additional modules to install")
    custom_domain: Optional[str] = Field(None, description="Custom domain for the instance")
    ssl_enabled: bool = Field(default=True, description="Enable SSL/TLS")
    backup_enabled: bool = Field(default=True, description="Enable automatic backups")


class InstanceUpdateSchema(BaseModel):
    """Schema for updating an existing Odoo instance"""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "name": "Updated Company Name",
                "status": "running",
                "admin_email": "newadmin@company.com",
                "timezone": "Europe/London",
                "ssl_enabled": True,
                "backup_enabled": True,
                "cpu_limit": 2.0,
                "memory_limit": 4096,
                "storage_limit": 50
            }
        }
    )
    
    name: Optional[str] = Field(None, min_length=3, max_length=50, description="Instance name")
    status: Optional[InstanceStatus] = Field(None, description="Instance status")
    admin_email: Optional[str] = Field(None, description="Administrator email")
    timezone: Optional[str] = Field(None, description="Instance timezone")
    language: Optional[str] = Field(None, description="Default language")
    custom_domain: Optional[str] = Field(None, description="Custom domain")
    ssl_enabled: Optional[bool] = Field(None, description="Enable SSL/TLS")
    backup_enabled: Optional[bool] = Field(None, description="Enable automatic backups")
    modules: Optional[List[str]] = Field(None, description="Installed modules")
    cpu_limit: Optional[float] = Field(None, ge=0.1, le=8.0, description="CPU limit in cores")
    memory_limit: Optional[int] = Field(None, ge=512, le=16384, description="Memory limit in MB")
    storage_limit: Optional[int] = Field(None, ge=1, le=500, description="Storage limit in GB")


class InstanceSchema(BaseModel):
    """Base instance schema"""
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(..., description="Instance ID")
    name: str = Field(..., description="Instance name")
    subdomain: str = Field(..., description="Instance subdomain")
    customer_id: str = Field(..., description="Owner customer ID")
    odoo_version: str = Field(..., description="Odoo version")
    instance_type: InstanceType = Field(..., description="Instance type")
    status: InstanceStatus = Field(..., description="Current status")
    database_name: str = Field(..., description="Database name")
    admin_email: str = Field(..., description="Administrator email")
    timezone: str = Field(..., description="Instance timezone")
    language: str = Field(..., description="Default language")
    country_code: str = Field(..., description="Country code")
    url: str = Field(..., description="Instance URL")
    custom_domain: Optional[str] = Field(None, description="Custom domain")
    ssl_enabled: bool = Field(..., description="SSL/TLS enabled")
    backup_enabled: bool = Field(..., description="Automatic backups enabled")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")


class InstanceResponseSchema(BaseModel):
    """Schema for instance API responses"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "inst_123456789",
                "name": "My Company Odoo",
                "subdomain": "mycompany",
                "customer_id": "cust_987654321",
                "odoo_version": "17.0",
                "instance_type": "community",
                "status": "running",
                "url": "http://mycompany.saasodoo.com",
                "custom_domain": "erp.mycompany.com",
                "ssl_enabled": True,
                "backup_enabled": True,
                "modules": ["sale", "purchase", "inventory", "accounting"],
                "cpu_usage": 45.2,
                "memory_usage": 1024,
                "storage_usage": 15,
                "cpu_limit": 2.0,
                "memory_limit": 4096,
                "storage_limit": 50,
                "created_at": "2024-01-01T10:00:00Z",
                "updated_at": "2024-01-15T14:30:00Z",
                "last_accessed": "2024-01-15T16:45:00Z",
                "health_status": "healthy",
                "uptime": 1296000,
                "monthly_cost": 29.99,
                "billing_cycle": "monthly"
            }
        }
    )
    
    id: str = Field(..., description="Instance ID")
    name: str = Field(..., description="Instance name")
    subdomain: str = Field(..., description="Instance subdomain")
    customer_id: str = Field(..., description="Owner customer ID")
    odoo_version: str = Field(..., description="Odoo version")
    instance_type: InstanceType = Field(..., description="Instance type")
    status: InstanceStatus = Field(..., description="Current status")
    url: str = Field(..., description="Instance URL")
    custom_domain: Optional[str] = Field(None, description="Custom domain")
    ssl_enabled: bool = Field(..., description="SSL/TLS enabled")
    backup_enabled: bool = Field(..., description="Automatic backups enabled")
    modules: List[str] = Field(default=[], description="Installed modules")
    
    # Resource usage information
    cpu_usage: Optional[float] = Field(None, description="Current CPU usage percentage")
    memory_usage: Optional[int] = Field(None, description="Current memory usage in MB")
    storage_usage: Optional[int] = Field(None, description="Current storage usage in GB")
    
    # Limits
    cpu_limit: Optional[float] = Field(None, description="CPU limit in cores")
    memory_limit: Optional[int] = Field(None, description="Memory limit in MB")
    storage_limit: Optional[int] = Field(None, description="Storage limit in GB")
    
    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")
    
    # Instance health
    health_status: Optional[str] = Field(None, description="Health check status")
    uptime: Optional[int] = Field(None, description="Uptime in seconds")
    
    # Billing information
    monthly_cost: Optional[float] = Field(None, description="Monthly cost in USD")
    billing_cycle: Optional[str] = Field(None, description="Billing cycle")


class InstanceStatsSchema(BaseModel):
    """Schema for instance statistics"""
    model_config = ConfigDict(from_attributes=True)
    
    instance_id: str = Field(..., description="Instance ID")
    total_users: int = Field(default=0, description="Total users in the instance")
    active_users: int = Field(default=0, description="Active users in the last 30 days")
    total_records: int = Field(default=0, description="Total records in database")
    database_size: float = Field(default=0.0, description="Database size in MB")
    file_storage_size: float = Field(default=0.0, description="File storage size in MB")
    
    # Usage metrics
    api_calls_today: int = Field(default=0, description="API calls today")
    api_calls_month: int = Field(default=0, description="API calls this month")
    page_views_today: int = Field(default=0, description="Page views today")
    page_views_month: int = Field(default=0, description="Page views this month")
    
    # Performance metrics
    avg_response_time: Optional[float] = Field(None, description="Average response time in ms")
    error_rate: Optional[float] = Field(None, description="Error rate percentage")
    
    last_updated: datetime = Field(..., description="Statistics last updated") 