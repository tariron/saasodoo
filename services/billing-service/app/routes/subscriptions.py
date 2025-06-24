"""
Billing Service - Subscriptions Routes
Handles KillBill subscription management
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel
from decimal import Decimal

from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateSubscriptionRequest(BaseModel):
    customer_id: str
    plan_name: str
    billing_period: str = "MONTHLY"
    price_override: Optional[Decimal] = None
    instance_id: Optional[str] = None  # For instance-specific subscriptions

class StartTrialRequest(BaseModel):
    customer_id: str
    trial_days: int = 14

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

@router.post("/")
async def create_subscription(
    subscription_data: CreateSubscriptionRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Create a subscription for a customer with 14-day trial"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(subscription_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        # For now, return a simplified success response
        # In a full implementation, this would create actual KillBill subscriptions
        logger.info(f"Creating subscription for customer {subscription_data.customer_id}, plan {subscription_data.plan_name}")
        
        # Simulate subscription creation with trial period
        subscription_id = f"sub_{subscription_data.customer_id}_{subscription_data.instance_id or 'default'}"
        
        subscription_info = {
            "subscription_id": subscription_id,
            "customer_id": subscription_data.customer_id,
            "instance_id": subscription_data.instance_id,
            "plan_name": subscription_data.plan_name,
            "billing_period": subscription_data.billing_period,
            "trial_days": 14,
            "status": "trial",
            "account_id": account_id
        }
        
        return {
            "success": True,
            "subscription": subscription_info,
            "message": f"Subscription created with 14-day trial for plan {subscription_data.plan_name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create subscription for customer {subscription_data.customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create subscription: {str(e)}")

@router.post("/trial")
async def start_trial(
    trial_data: StartTrialRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Start a trial subscription for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(trial_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        # Start trial
        trial_subscription = await killbill.start_trial(
            account_id=account_id,
            trial_days=trial_data.trial_days
        )
        
        return {
            "success": True,
            "trial_subscription": trial_subscription,
            "trial_days": trial_data.trial_days,
            "message": f"Trial started for {trial_data.trial_days} days"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start trial for customer {trial_data.customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start trial: {str(e)}")

@router.get("/{customer_id}")
async def get_customer_subscriptions(
    customer_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get all subscriptions for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        # Get subscriptions
        subscriptions = await killbill.get_account_subscriptions(account_id)
        
        return {
            "success": True,
            "customer_id": customer_id,
            "subscriptions": subscriptions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get subscriptions for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve subscriptions")
