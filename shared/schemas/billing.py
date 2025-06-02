"""
Billing and Payment Schemas
Pydantic schemas for billing, payments, and subscription management
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, Enum):
    """Payment method enumeration"""
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    PAYPAL = "paypal"
    PAYNOW = "paynow"
    ECOCASH = "ecocash"
    ONEMONEY = "onemoney"
    CRYPTOCURRENCY = "cryptocurrency"


class SubscriptionStatus(str, Enum):
    """Subscription status enumeration"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class BillingCycle(str, Enum):
    """Billing cycle enumeration"""
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class Currency(str, Enum):
    """Supported currencies"""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    ZWL = "ZWL"
    ZAR = "ZAR"


class PaymentSchema(BaseModel):
    """Schema for payment information"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "pay_123456789",
                "customer_id": "cust_987654321",
                "subscription_id": "sub_456789123",
                "amount": "29.99",
                "currency": "USD",
                "payment_method": "credit_card",
                "status": "completed",
                "transaction_id": "txn_abc123def456",
                "reference_number": "REF-2024-001",
                "tax_amount": "2.70",
                "fee_amount": "0.87",
                "total_amount": "33.56",
                "created_at": "2024-01-01T10:00:00Z",
                "completed_at": "2024-01-01T10:00:05Z",
                "description": "Monthly subscription payment"
            }
        }
    )
    
    id: str = Field(..., description="Payment ID")
    customer_id: str = Field(..., description="Customer ID")
    subscription_id: Optional[str] = Field(None, description="Associated subscription ID")
    instance_id: Optional[str] = Field(None, description="Associated instance ID")
    amount: Decimal = Field(..., ge=0, description="Payment amount")
    currency: Currency = Field(default=Currency.USD, description="Payment currency")
    payment_method: PaymentMethod = Field(..., description="Payment method used")
    status: PaymentStatus = Field(..., description="Payment status")
    
    # Payment details
    transaction_id: Optional[str] = Field(None, description="External transaction ID")
    gateway_response: Optional[Dict[str, Any]] = Field(None, description="Gateway response data")
    reference_number: Optional[str] = Field(None, description="Reference number")
    
    # Billing information
    billing_address: Optional[Dict[str, str]] = Field(None, description="Billing address")
    tax_amount: Optional[Decimal] = Field(None, ge=0, description="Tax amount")
    fee_amount: Optional[Decimal] = Field(None, ge=0, description="Processing fee")
    total_amount: Decimal = Field(..., ge=0, description="Total amount charged")
    
    # Timestamps
    created_at: datetime = Field(..., description="Payment creation timestamp")
    processed_at: Optional[datetime] = Field(None, description="Payment processing timestamp")
    completed_at: Optional[datetime] = Field(None, description="Payment completion timestamp")
    
    # Metadata
    description: Optional[str] = Field(None, description="Payment description")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class SubscriptionSchema(BaseModel):
    """Schema for subscription information"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "sub_123456789",
                "customer_id": "cust_987654321",
                "instance_id": "inst_456789123",
                "plan_id": "plan_basic_monthly",
                "plan_name": "Basic Monthly Plan",
                "status": "active",
                "billing_cycle": "monthly",
                "currency": "USD",
                "base_price": "29.99",
                "discount_amount": "5.00",
                "tax_rate": "0.09",
                "total_price": "26.99",
                "start_date": "2024-01-01",
                "next_billing_date": "2024-02-01",
                "trial_end_date": "2024-01-14",
                "usage_limits": {
                    "instances": 3,
                    "storage_gb": 50,
                    "users": 10
                },
                "current_usage": {
                    "instances": 1,
                    "storage_gb": 15.5,
                    "users": 3
                },
                "created_at": "2024-01-01T10:00:00Z",
                "updated_at": "2024-01-15T14:30:00Z"
            }
        }
    )
    
    id: str = Field(..., description="Subscription ID")
    customer_id: str = Field(..., description="Customer ID")
    instance_id: Optional[str] = Field(None, description="Associated instance ID")
    plan_id: str = Field(..., description="Subscription plan ID")
    plan_name: str = Field(..., description="Subscription plan name")
    
    # Subscription details
    status: SubscriptionStatus = Field(..., description="Subscription status")
    billing_cycle: BillingCycle = Field(..., description="Billing cycle")
    currency: Currency = Field(default=Currency.USD, description="Billing currency")
    
    # Pricing
    base_price: Decimal = Field(..., ge=0, description="Base subscription price")
    discount_amount: Optional[Decimal] = Field(None, ge=0, description="Discount amount")
    tax_rate: Optional[Decimal] = Field(None, ge=0, le=1, description="Tax rate (0-1)")
    total_price: Decimal = Field(..., ge=0, description="Total subscription price")
    
    # Billing dates
    start_date: date = Field(..., description="Subscription start date")
    end_date: Optional[date] = Field(None, description="Subscription end date")
    next_billing_date: Optional[date] = Field(None, description="Next billing date")
    trial_end_date: Optional[date] = Field(None, description="Trial period end date")
    
    # Usage and limits
    usage_limits: Optional[Dict[str, Any]] = Field(None, description="Usage limits")
    current_usage: Optional[Dict[str, Any]] = Field(None, description="Current usage")
    
    # Timestamps
    created_at: datetime = Field(..., description="Subscription creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    cancelled_at: Optional[datetime] = Field(None, description="Cancellation timestamp")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class BillingSchema(BaseModel):
    """Schema for billing information and invoices"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "bill_123456789",
                "customer_id": "cust_987654321",
                "subscription_id": "sub_456789123",
                "invoice_number": "INV-2024-001",
                "billing_period_start": "2024-01-01",
                "billing_period_end": "2024-01-31",
                "due_date": "2024-02-01",
                "subtotal": "29.99",
                "tax_amount": "2.70",
                "discount_amount": "0.00",
                "total_amount": "32.69",
                "paid_amount": "32.69",
                "balance_due": "0.00",
                "status": "completed",
                "currency": "USD",
                "payment_method": "credit_card",
                "line_items": [
                    {
                        "description": "Basic Monthly Plan",
                        "quantity": 1,
                        "unit_price": "29.99",
                        "total": "29.99"
                    }
                ],
                "issued_at": "2024-01-01T00:00:00Z",
                "paid_at": "2024-01-01T10:00:00Z",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T10:00:00Z"
            }
        }
    )
    
    id: str = Field(..., description="Billing record ID")
    customer_id: str = Field(..., description="Customer ID")
    subscription_id: Optional[str] = Field(None, description="Associated subscription ID")
    invoice_number: str = Field(..., description="Invoice number")
    
    # Billing period
    billing_period_start: date = Field(..., description="Billing period start date")
    billing_period_end: date = Field(..., description="Billing period end date")
    due_date: date = Field(..., description="Payment due date")
    
    # Amounts
    subtotal: Decimal = Field(..., ge=0, description="Subtotal amount")
    tax_amount: Decimal = Field(default=0, ge=0, description="Tax amount")
    discount_amount: Decimal = Field(default=0, ge=0, description="Discount amount")
    total_amount: Decimal = Field(..., ge=0, description="Total amount due")
    paid_amount: Decimal = Field(default=0, ge=0, description="Amount paid")
    balance_due: Decimal = Field(..., description="Remaining balance")
    
    # Status and details
    status: PaymentStatus = Field(..., description="Billing status")
    currency: Currency = Field(default=Currency.USD, description="Billing currency")
    payment_method: Optional[PaymentMethod] = Field(None, description="Payment method")
    
    # Line items
    line_items: List[Dict[str, Any]] = Field(default=[], description="Billing line items")
    
    # Timestamps
    issued_at: datetime = Field(..., description="Invoice issue timestamp")
    paid_at: Optional[datetime] = Field(None, description="Payment timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Billing address
    billing_address: Optional[Dict[str, str]] = Field(None, description="Billing address")
    
    # Metadata
    notes: Optional[str] = Field(None, description="Billing notes")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class PaymentMethodSchema(BaseModel):
    """Schema for stored payment methods"""
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "pm_123456789",
                "customer_id": "cust_987654321",
                "type": "credit_card",
                "is_default": True,
                "last_four": "4242",
                "brand": "Visa",
                "exp_month": 12,
                "exp_year": 2025,
                "is_verified": True,
                "is_active": True,
                "created_at": "2024-01-01T10:00:00Z",
                "updated_at": "2024-01-01T10:00:00Z",
                "last_used_at": "2024-01-15T14:30:00Z"
            }
        }
    )
    
    id: str = Field(..., description="Payment method ID")
    customer_id: str = Field(..., description="Customer ID")
    type: PaymentMethod = Field(..., description="Payment method type")
    is_default: bool = Field(default=False, description="Is default payment method")
    
    # Card details (masked)
    last_four: Optional[str] = Field(None, description="Last four digits")
    brand: Optional[str] = Field(None, description="Card brand")
    exp_month: Optional[int] = Field(None, ge=1, le=12, description="Expiration month")
    exp_year: Optional[int] = Field(None, description="Expiration year")
    
    # Bank details (masked)
    bank_name: Optional[str] = Field(None, description="Bank name")
    account_type: Optional[str] = Field(None, description="Account type")
    
    # Mobile money details
    phone_number: Optional[str] = Field(None, description="Phone number (masked)")
    provider: Optional[str] = Field(None, description="Mobile money provider")
    
    # Status
    is_verified: bool = Field(default=False, description="Is payment method verified")
    is_active: bool = Field(default=True, description="Is payment method active")
    
    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")


class BillingStatsSchema(BaseModel):
    """Schema for billing statistics"""
    model_config = ConfigDict(from_attributes=True)
    
    customer_id: str = Field(..., description="Customer ID")
    
    # Revenue metrics
    total_revenue: Decimal = Field(default=0, description="Total revenue")
    monthly_revenue: Decimal = Field(default=0, description="Monthly revenue")
    yearly_revenue: Decimal = Field(default=0, description="Yearly revenue")
    
    # Payment metrics
    total_payments: int = Field(default=0, description="Total number of payments")
    successful_payments: int = Field(default=0, description="Successful payments")
    failed_payments: int = Field(default=0, description="Failed payments")
    
    # Subscription metrics
    active_subscriptions: int = Field(default=0, description="Active subscriptions")
    cancelled_subscriptions: int = Field(default=0, description="Cancelled subscriptions")
    trial_subscriptions: int = Field(default=0, description="Trial subscriptions")
    
    # Usage metrics
    average_monthly_spend: Decimal = Field(default=0, description="Average monthly spend")
    lifetime_value: Decimal = Field(default=0, description="Customer lifetime value")
    
    # Dates
    first_payment_date: Optional[date] = Field(None, description="First payment date")
    last_payment_date: Optional[date] = Field(None, description="Last payment date")
    
    last_updated: datetime = Field(..., description="Statistics last updated") 