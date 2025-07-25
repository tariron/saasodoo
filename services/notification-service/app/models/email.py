"""
Email Models
Pydantic models for email operations
"""

from pydantic import BaseModel, EmailStr, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class EmailPriority(str, Enum):
    """Email priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

class EmailStatus(str, Enum):
    """Email status types"""
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"

class EmailRequest(BaseModel):
    """Request model for sending emails"""
    
    # Recipients
    to_emails: List[EmailStr]
    cc_emails: Optional[List[EmailStr]] = None
    bcc_emails: Optional[List[EmailStr]] = None
    
    # Content
    subject: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    
    # Sender info
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None
    reply_to: Optional[EmailStr] = None
    
    # Metadata
    priority: EmailPriority = EmailPriority.NORMAL
    headers: Optional[Dict[str, str]] = None
    tags: Optional[List[str]] = None
    
    # Tracking
    track_opens: bool = False
    track_clicks: bool = False
    
    @validator('to_emails')
    def validate_recipients(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one recipient email is required')
        if len(v) > 50:  # Reasonable limit
            raise ValueError('Maximum 50 recipients per email')
        return v
    
    @validator('subject')
    def validate_subject(cls, v):
        if not v or not v.strip():
            raise ValueError('Subject is required')
        if len(v) > 200:
            raise ValueError('Subject too long (max 200 characters)')
        return v.strip()
    
    @validator('html_content', 'text_content')
    def validate_content(cls, v, values):
        # At least one content type is required
        if not values.get('html_content') and not v:
            raise ValueError('Either HTML or text content is required')
        return v

class TemplateEmailRequest(BaseModel):
    """Request model for sending template-based emails"""
    
    # Recipients
    to_emails: List[EmailStr]
    
    # Template
    template_name: str
    template_variables: Optional[Dict[str, Any]] = None
    
    # Override template defaults
    subject_override: Optional[str] = None
    from_email_override: Optional[EmailStr] = None
    from_name_override: Optional[str] = None
    
    # Metadata
    priority: EmailPriority = EmailPriority.NORMAL
    tags: Optional[List[str]] = None
    
    @validator('template_name')
    def validate_template_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Template name is required')
        return v.strip()
    
    @validator('template_variables')
    def validate_template_variables(cls, v):
        if v is None:
            return {}
        return v

class EmailResponse(BaseModel):
    """Response model for email operations"""
    
    success: bool
    message: str
    email_id: Optional[str] = None
    message_id: Optional[str] = None
    recipients: List[str]
    sent_at: Optional[datetime] = None
    attempts: Optional[int] = None

class EmailHistoryRecord(BaseModel):
    """Email history record"""
    
    id: str
    to_emails: List[str]
    subject: str
    status: EmailStatus
    priority: EmailPriority
    from_email: str
    from_name: Optional[str] = None
    
    # Timestamps
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    
    # Metadata
    template_name: Optional[str] = None
    tags: Optional[List[str]] = None
    attempts: int = 0
    error_message: Optional[str] = None
    
    # Tracking
    opens: int = 0
    clicks: int = 0
    last_opened_at: Optional[datetime] = None
    last_clicked_at: Optional[datetime] = None

class EmailHistoryResponse(BaseModel):
    """Response model for email history"""
    
    emails: List[EmailHistoryRecord]
    total: int
    page: int
    per_page: int
    pages: int

class BulkEmailRequest(BaseModel):
    """Request model for bulk email sending"""
    
    # Template and content
    template_name: Optional[str] = None
    subject: Optional[str] = None
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    
    # Recipients with personalization
    recipients: List[Dict[str, Any]]  # [{"email": "user@example.com", "variables": {"name": "John"}}]
    
    # Sender info
    from_email: Optional[EmailStr] = None
    from_name: Optional[str] = None
    
    # Metadata
    priority: EmailPriority = EmailPriority.NORMAL
    tags: Optional[List[str]] = None
    
    # Batch settings
    batch_size: int = 10
    delay_between_batches: float = 1.0  # seconds
    
    @validator('recipients')
    def validate_recipients(cls, v):
        if not v or len(v) == 0:
            raise ValueError('At least one recipient is required')
        if len(v) > 1000:  # Reasonable limit for bulk
            raise ValueError('Maximum 1000 recipients per bulk email')
        
        for i, recipient in enumerate(v):
            if not isinstance(recipient, dict):
                raise ValueError(f'Recipient {i} must be a dictionary')
            if 'email' not in recipient:
                raise ValueError(f'Recipient {i} must have an email field')
        
        return v
    
    @validator('batch_size')
    def validate_batch_size(cls, v):
        if v < 1 or v > 100:
            raise ValueError('Batch size must be between 1 and 100')
        return v

class BulkEmailResponse(BaseModel):
    """Response model for bulk email operations"""
    
    success: bool
    message: str
    total_recipients: int
    successful_sends: int
    failed_sends: int
    batch_id: str
    started_at: datetime
    estimated_completion: Optional[datetime] = None