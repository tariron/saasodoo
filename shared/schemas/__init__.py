"""
Shared data schemas for Odoo SaaS Kit

This package contains common data schemas used across all microservices.
"""

from .user import UserSchema, UserCreateSchema, UserUpdateSchema, UserResponseSchema
from .instance import InstanceSchema, InstanceCreateSchema, InstanceUpdateSchema, InstanceResponseSchema
from .billing import BillingSchema, PaymentSchema, SubscriptionSchema

__all__ = [
    "UserSchema",
    "UserCreateSchema", 
    "UserUpdateSchema",
    "UserResponseSchema",
    "InstanceSchema",
    "InstanceCreateSchema",
    "InstanceUpdateSchema", 
    "InstanceResponseSchema",
    "BillingSchema",
    "PaymentSchema",
    "SubscriptionSchema",
]

__version__ = "1.0.0" 