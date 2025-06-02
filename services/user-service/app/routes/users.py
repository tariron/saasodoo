"""
User Management Routes
Customer profile management, preferences, and account settings
"""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import Optional
import logging

# Import shared schemas
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../..'))
from shared.schemas.user import (
    UserUpdateSchema, UserResponseSchema, UserProfileSchema,
    UserPreferencesSchema, UserStatsSchema
)

from app.services.user_service import UserService
from app.utils.dependencies import DatabaseDep, CurrentCustomer, ActiveCustomer

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/profile", response_model=UserProfileSchema)
async def get_customer_profile(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get detailed customer profile
    
    Includes subscription status, instance count, and billing information
    """
    try:
        profile = await UserService.get_customer_profile(current_customer['id'])
        
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer profile not found"
            )
        
        return profile
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get customer profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer profile"
        )

@router.put("/profile", response_model=UserResponseSchema)
async def update_customer_profile(
    profile_data: UserUpdateSchema,
    current_customer: ActiveCustomer,
    db: DatabaseDep
):
    """
    Update customer profile information
    
    Allows customers to update their personal information
    """
    try:
        # Update customer profile
        updated_customer = await UserService.update_customer_profile(
            current_customer['id'],
            profile_data.dict(exclude_unset=True)
        )
        
        if not updated_customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        logger.info(f"Customer profile updated: {current_customer['email']}")
        
        return updated_customer
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update customer profile error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer profile"
        )

@router.get("/preferences", response_model=UserPreferencesSchema)
async def get_customer_preferences(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get customer preferences
    
    Returns customer's UI and notification preferences
    """
    try:
        preferences = await UserService.get_customer_preferences(current_customer['id'])
        
        if not preferences:
            # Return default preferences if none exist
            return UserPreferencesSchema()
        
        return preferences
        
    except Exception as e:
        logger.error(f"Get customer preferences error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer preferences"
        )

@router.put("/preferences", response_model=UserPreferencesSchema)
async def update_customer_preferences(
    preferences_data: UserPreferencesSchema,
    current_customer: ActiveCustomer,
    db: DatabaseDep
):
    """
    Update customer preferences
    
    Updates customer's UI and notification preferences
    """
    try:
        updated_preferences = await UserService.update_customer_preferences(
            current_customer['id'],
            preferences_data.dict(exclude_unset=True)
        )
        
        logger.info(f"Customer preferences updated: {current_customer['email']}")
        
        return updated_preferences
        
    except Exception as e:
        logger.error(f"Update customer preferences error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer preferences"
        )

@router.get("/stats", response_model=UserStatsSchema)
async def get_customer_stats(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get customer statistics
    
    Returns instance count, usage statistics, and account information
    """
    try:
        stats = await UserService.get_customer_stats(current_customer['id'])
        
        return stats
        
    except Exception as e:
        logger.error(f"Get customer stats error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer statistics"
        )

@router.delete("/account", response_model=dict)
async def delete_customer_account(
    current_customer: ActiveCustomer,
    db: DatabaseDep,
    confirmation: str = Query(None, description="Type 'DELETE' to confirm")
):
    """
    Delete customer account
    
    Permanently deletes customer account and all associated data
    Requires explicit confirmation
    """
    if confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account deletion requires confirmation. Please provide 'DELETE' as confirmation parameter."
        )
    
    try:
        # Delete customer account
        deletion_result = await UserService.delete_customer_account(current_customer['id'])
        
        if not deletion_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=deletion_result['error']
            )
        
        logger.info(f"Customer account deleted: {current_customer['email']}")
        
        return {
            "success": True,
            "message": "Account deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete customer account error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer account"
        )

@router.post("/deactivate", response_model=dict)
async def deactivate_customer_account(
    current_customer: ActiveCustomer,
    db: DatabaseDep
):
    """
    Deactivate customer account
    
    Temporarily deactivates account (can be reactivated)
    """
    try:
        # Deactivate customer account
        deactivation_result = await UserService.deactivate_customer_account(current_customer['id'])
        
        if not deactivation_result['success']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=deactivation_result['error']
            )
        
        logger.info(f"Customer account deactivated: {current_customer['email']}")
        
        return {
            "success": True,
            "message": "Account deactivated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Deactivate customer account error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate customer account"
        )

@router.get("/instances", response_model=dict)
async def get_customer_instances(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get customer's Odoo instances
    
    Returns list of customer's provisioned Odoo instances
    """
    try:
        instances = await UserService.get_customer_instances(current_customer['id'])
        
        return {
            "success": True,
            "instances": instances,
            "total_count": len(instances)
        }
        
    except Exception as e:
        logger.error(f"Get customer instances error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer instances"
        )

@router.get("/billing", response_model=dict)
async def get_customer_billing(
    current_customer: CurrentCustomer,
    db: DatabaseDep
):
    """
    Get customer billing information
    
    Returns subscription status and billing history
    """
    try:
        billing_info = await UserService.get_customer_billing(current_customer['id'])
        
        return {
            "success": True,
            "billing": billing_info
        }
        
    except Exception as e:
        logger.error(f"Get customer billing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer billing information"
        ) 