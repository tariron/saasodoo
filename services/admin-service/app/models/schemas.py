from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


# Auth Schemas
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "AdminUserResponse"


class AdminUserResponse(BaseModel):
    id: str
    email: str
    full_name: str  # Changed from 'name' to match DB
    role: str
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Platform Metrics Schema
class SystemStatus(BaseModel):
    user_service: str
    billing_service: str
    instance_service: str
    database_service: str


class PlatformMetrics(BaseModel):
    total_customers: int
    active_instances: int
    total_instances: int
    revenue_mrr: float
    system_status: SystemStatus


# Customer Schema
class Customer(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    status: str
    created_at: str
    total_instances: int
