"""
Instance data models and schemas for Odoo instances
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4
from enum import Enum

from pydantic import BaseModel, Field, validator


class InstanceStatus(str, Enum):
    """Instance status enumeration"""
    CREATING = "creating"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    UPDATING = "updating"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    TERMINATED = "terminated"
    PAUSED = "paused"


class BillingStatus(str, Enum):
    """Billing status enumeration"""
    PAYMENT_REQUIRED = "payment_required"  # Instance requires payment to activate/continue
    TRIAL = "trial"                        # Instance is in trial period
    PAID = "paid"                         # Instance is paid and active


class ProvisioningStatus(str, Enum):
    """Provisioning status enumeration"""
    PENDING = "pending"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    FAILED = "failed"


class OdooVersion(str, Enum):
    """Supported Odoo versions"""
    V16 = "16.0"
    V17 = "17.0"
    V18 = "18.0"
    # Add more versions as needed


class InstanceType(str, Enum):
    """Instance deployment type"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# Base instance model
class InstanceBase(BaseModel):
    """Base instance model with common fields"""
    name: str = Field(..., min_length=1, max_length=100, description="Instance display name")
    odoo_version: OdooVersion = Field(default=OdooVersion.V17, description="Odoo version")
    instance_type: InstanceType = Field(default=InstanceType.DEVELOPMENT, description="Instance type")
    description: Optional[str] = Field(None, max_length=500, description="Instance description")
    
    # Resource allocation
    cpu_limit: float = Field(default=1.0, ge=0.1, le=8.0, description="CPU limit in cores")
    memory_limit: str = Field(default="1G", description="Memory limit (e.g., 512M, 1G, 2G)")
    storage_limit: str = Field(default="10G", description="Storage limit (e.g., 5G, 10G, 20G)")
    
    # Odoo configuration
    admin_email: str = Field(..., description="Odoo admin email")
    admin_password: str = Field(..., min_length=8, description="Odoo admin password")
    database_name: str = Field(..., min_length=1, max_length=50, description="Odoo database name")
    subdomain: Optional[str] = Field(None, min_length=3, max_length=50, description="Custom subdomain (defaults to database_name if not provided)")
    demo_data: bool = Field(default=False, description="Install demo data")
    
    # Addons and modules
    custom_addons: List[str] = Field(default_factory=list, description="List of custom addon names")
    disabled_modules: List[str] = Field(default_factory=list, description="List of disabled module names")
    
    # Environment variables
    environment_vars: Dict[str, str] = Field(default_factory=dict, description="Custom environment variables")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    @validator('memory_limit')
    def validate_memory_limit(cls, v):
        """Validate memory limit format"""
        if not v or not v[-1].upper() in ['M', 'G']:
            raise ValueError('Memory limit must end with M or G (e.g., 512M, 1G)')
        try:
            int(v[:-1])
        except ValueError:
            raise ValueError('Memory limit must be a number followed by M or G')
        return v.upper()

    @validator('storage_limit')
    def validate_storage_limit(cls, v):
        """Validate storage limit format"""
        if not v or not v[-1].upper() in ['M', 'G']:
            raise ValueError('Storage limit must end with M or G (e.g., 5G, 10G)')
        try:
            int(v[:-1])
        except ValueError:
            raise ValueError('Storage limit must be a number followed by M or G')
        return v.upper()

    @validator('database_name')
    def validate_database_name(cls, v):
        """Validate database name format"""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Database name must contain only alphanumeric characters, underscores, and hyphens')
        return v.lower()

    @validator('subdomain')
    def validate_subdomain(cls, v):
        """Validate subdomain format"""
        if v is not None:
            if not v.replace('-', '').isalnum():
                raise ValueError('Subdomain must contain only alphanumeric characters and hyphens')
            if v.startswith('-') or v.endswith('-'):
                raise ValueError('Subdomain cannot start or end with a hyphen')
        return v.lower() if v else None

    @validator('admin_password')
    def validate_admin_password(cls, v):
        """Validate admin password strength according to Odoo requirements"""
        if len(v) < 8:
            raise ValueError('Admin password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Admin password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Admin password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Admin password must contain at least one digit')
        return v


# Create instance schema (for API requests)
class InstanceCreate(InstanceBase):
    """Schema for creating a new instance"""
    customer_id: UUID = Field(..., description="Customer ID that owns this instance")
    subscription_id: Optional[UUID] = Field(None, description="Pre-existing billing subscription ID")
    billing_status: BillingStatus = Field(default=BillingStatus.PAYMENT_REQUIRED, description="Billing status provided by the billing service")
    provisioning_status: ProvisioningStatus = Field(default=ProvisioningStatus.PENDING, description="Provisioning status provided by the billing service")


# Update instance schema (for API requests)
class InstanceUpdate(BaseModel):
    """Schema for updating instance information"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    instance_type: Optional[InstanceType] = None
    cpu_limit: Optional[float] = Field(None, ge=0.1, le=8.0)
    memory_limit: Optional[str] = None
    storage_limit: Optional[str] = None
    admin_email: Optional[str] = None
    demo_data: Optional[bool] = None
    custom_addons: Optional[List[str]] = None
    disabled_modules: Optional[List[str]] = None
    environment_vars: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, Any]] = None

    @validator('memory_limit')
    def validate_memory_limit(cls, v):
        """Validate memory limit format"""
        if v is not None:
            if not v or not v[-1].upper() in ['M', 'G']:
                raise ValueError('Memory limit must end with M or G (e.g., 512M, 1G)')
            try:
                int(v[:-1])
            except ValueError:
                raise ValueError('Memory limit must be a number followed by M or G')
        return v.upper() if v else None

    @validator('storage_limit')
    def validate_storage_limit(cls, v):
        """Validate storage limit format"""
        if v is not None:
            if not v or not v[-1].upper() in ['M', 'G']:
                raise ValueError('Storage limit must end with M or G (e.g., 5G, 10G)')
            try:
                int(v[:-1])
            except ValueError:
                raise ValueError('Storage limit must be a number followed by M or G')
        return v.upper() if v else None


# Full instance model (database representation)
class Instance(InstanceBase):
    """Full instance model with all database fields"""
    id: UUID = Field(default_factory=uuid4, description="Unique instance ID")
    customer_id: UUID = Field(..., description="Customer ID that owns this instance")
    subscription_id: Optional[UUID] = Field(None, description="Associated billing subscription ID")
    status: InstanceStatus = Field(default=InstanceStatus.CREATING, description="Current instance status")
    
    # Billing and provisioning status
    billing_status: BillingStatus = Field(default=BillingStatus.PAYMENT_REQUIRED, description="Billing status")
    provisioning_status: ProvisioningStatus = Field(default=ProvisioningStatus.PENDING, description="Provisioning status")
    
    # Container information
    container_id: Optional[str] = Field(None, description="Docker container ID")
    container_name: Optional[str] = Field(None, description="Docker container name")
    
    # Network information
    internal_port: int = Field(default=8069, description="Internal Odoo port")
    external_port: Optional[int] = Field(None, description="External mapped port")
    internal_url: Optional[str] = Field(None, description="Internal access URL")
    external_url: Optional[str] = Field(None, description="External access URL")
    
    # Database information
    db_host: Optional[str] = Field(None, description="Database host")
    db_port: int = Field(default=5432, description="Database port")
    db_user: Optional[str] = Field(None, description="Database user")
    
    # Status information
    last_health_check: Optional[datetime] = Field(None, description="Last health check timestamp")
    error_message: Optional[str] = Field(None, description="Error message if status is ERROR")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")
    started_at: Optional[datetime] = Field(None, description="Last start timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


# Response schema (for API responses)
class InstanceResponse(BaseModel):
    """Schema for instance API responses"""
    id: str = Field(..., description="Instance ID")
    customer_id: str = Field(..., description="Customer ID")
    subscription_id: Optional[str] = Field(None, description="Associated billing subscription ID")
    name: str = Field(..., description="Instance name")
    description: Optional[str] = Field(None, description="Instance description")
    odoo_version: OdooVersion = Field(..., description="Odoo version")
    instance_type: InstanceType = Field(..., description="Instance type")
    status: InstanceStatus = Field(..., description="Current status")
    
    # Billing and provisioning status
    billing_status: BillingStatus = Field(..., description="Billing status")
    provisioning_status: ProvisioningStatus = Field(..., description="Provisioning status")
    
    # Resource allocation
    cpu_limit: float = Field(..., description="CPU limit in cores")
    memory_limit: str = Field(..., description="Memory limit")
    storage_limit: str = Field(..., description="Storage limit")
    
    # Access information
    external_url: Optional[str] = Field(None, description="External access URL")
    internal_url: Optional[str] = Field(None, description="Internal access URL")
    admin_email: str = Field(..., description="Admin email")
    admin_password: Optional[str] = Field(None, description="Admin password")
    subdomain: Optional[str] = Field(None, description="Custom subdomain")
    
    # Status information
    error_message: Optional[str] = Field(None, description="Error message if any")
    last_health_check: Optional[str] = Field(None, description="Last health check")
    
    # Timestamps
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    started_at: Optional[str] = Field(None, description="Last start timestamp")
    
    # Configuration
    demo_data: bool = Field(..., description="Has demo data")
    database_name: str = Field(..., description="Database name")
    custom_addons: List[str] = Field(..., description="Custom addons")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        """Pydantic configuration"""
        from_attributes = True


# Instance list response
class InstanceListResponse(BaseModel):
    """Schema for instance list API response"""
    instances: List[InstanceResponse] = Field(..., description="List of instances")
    total: int = Field(..., description="Total number of instances")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")

    class Config:
        """Pydantic configuration"""
        from_attributes = True


# Instance action schemas
class InstanceAction(str, Enum):
    """Available instance actions"""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    UPDATE = "update"
    BACKUP = "backup"
    RESTORE = "restore"
    SUSPEND = "suspend"
    UNSUSPEND = "unsuspend"
    UNPAUSE = "unpause"
    TERMINATE = "terminate"


class InstanceActionRequest(BaseModel):
    """Schema for instance action requests"""
    action: InstanceAction = Field(..., description="Action to perform")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Action parameters")


class InstanceActionResponse(BaseModel):
    """Schema for instance action responses"""
    instance_id: str = Field(..., description="Instance ID")
    action: InstanceAction = Field(..., description="Action performed")
    status: str = Field(..., description="Action status")
    message: str = Field(..., description="Action result message")
    timestamp: str = Field(..., description="Action timestamp")
    job_id: Optional[str] = Field(None, description="Celery job ID for tracking") 