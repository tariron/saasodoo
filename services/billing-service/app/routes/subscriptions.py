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
    """Create a subscription for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(subscription_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Creating subscription for customer {subscription_data.customer_id}, plan {subscription_data.plan_name}")
        
        # Check trial eligibility - get existing subscriptions
        existing_subscriptions = await killbill.get_account_subscriptions(account_id)
        
        # Count existing trial subscriptions
        trial_count = 0
        for sub in existing_subscriptions:
            sub_phase = sub.get('phaseType', '')
            if sub.get('phaseType') == 'TRIAL':
                trial_count += 1
        
        if sub.get('phaseType') == 'TRIAL' and trial_count > 0: #this is my fix i made
            logger.warning(f"Trial eligibility check failed - customer {subscription_data.customer_id} has {trial_count} existing trial subscriptions")
            logger.warning(f"Trial eligibility check failed - customer has {sub_phase} existing trial subscriptions")
            raise HTTPException(
                status_code=400, 
                detail=f"Trial limit exceeded. You already have {trial_count} active trial subscription(s). Only one trial per customer is allowed."
            )
        
        logger.info(f"Trial eligibility check passed - customer {subscription_data.customer_id} has {trial_count} existing trials")
        
        # Create actual KillBill subscription with instance metadata
        killbill_subscription = await killbill.create_subscription(
            account_id=account_id,
            plan_name=subscription_data.plan_name,
            billing_period=subscription_data.billing_period,
            instance_id=subscription_data.instance_id
        )
        
        # Format response with both KillBill data and our metadata
        subscription_info = {
            "subscription_id": killbill_subscription.get("subscriptionId"),
            "killbill_subscription_id": killbill_subscription.get("subscriptionId"),
            "customer_id": subscription_data.customer_id,
            "instance_id": subscription_data.instance_id,
            "plan_name": subscription_data.plan_name,
            "billing_period": subscription_data.billing_period,
            "status": "active",  # KillBill will have its own status
            "account_id": account_id,
            "killbill_data": killbill_subscription
        }
        
        return {
            "success": True,
            "subscription": subscription_info,
            "message": f"Subscription created successfully for plan {subscription_data.plan_name}"
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
        
        # Start trial with a basic plan (default to basic-monthly for trials)
        plan_name = "basic-monthly"  # Default trial plan
        trial_subscription = await killbill.start_trial(
            account_id=account_id,
            plan_name=plan_name,
            trial_days=trial_data.trial_days
        )
        
        return {
            "success": True,
            "trial_subscription": trial_subscription,
            "trial_days": trial_data.trial_days,
            "plan_name": plan_name,
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
        
        # Get subscriptions from KillBill
        subscriptions = await killbill.get_account_subscriptions(account_id)
        
        return {
            "success": True,
            "customer_id": customer_id,
            "account_id": account_id,
            "subscriptions": subscriptions,
            "subscription_count": len(subscriptions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get subscriptions for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve subscriptions: {str(e)}")

@router.get("/subscription/{subscription_id}")
async def get_subscription_details(
    subscription_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get individual subscription details by subscription ID"""
    try:
        # Get subscription details from KillBill
        subscription = await killbill.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        # Get subscription metadata (instance info, etc.)
        metadata = await killbill.get_subscription_metadata(subscription_id)
        
        logger.info(f"Retrieved subscription {subscription_id} with metadata")
        
        return {
            "success": True,
            "subscription": subscription,
            "metadata": metadata,
            "subscription_id": subscription_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve subscription: {str(e)}")

@router.get("/subscription/{subscription_id}/invoices")
async def get_subscription_invoices(
    subscription_id: str,
    page: int = 1,
    limit: int = 10,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get invoices for a specific subscription"""
    try:
        # Get subscription details to find the account
        subscription = await killbill.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        account_id = subscription.get("accountId")
        if not account_id:
            raise HTTPException(status_code=400, detail="No account found for subscription")
        
        # Get all account invoices and filter by subscription
        # Note: This is a simplified approach. In a production system, you'd want more efficient filtering
        account_response = await killbill._make_request("GET", f"/1.0/kb/accounts/{account_id}/invoices")
        all_invoices = account_response if isinstance(account_response, list) else []
        
        # Filter invoices for this specific subscription and get complete invoice data
        import asyncio
        subscription_invoice_ids = []
        
        # First pass: find which invoices belong to this subscription
        for invoice in all_invoices:
            invoice_id = invoice.get("invoiceId")
            if invoice_id:
                # Check if invoice belongs to this subscription
                invoice_subscription_id = await killbill.get_subscription_id_from_invoice(invoice_id)
                if invoice_subscription_id == subscription_id:
                    subscription_invoice_ids.append(invoice_id)
        
        # Second pass: get complete invoice data for subscription invoices only
        subscription_invoices = []
        if subscription_invoice_ids:
            # Fetch complete invoice details in parallel
            complete_invoice_tasks = [killbill.get_invoice_by_id(invoice_id) for invoice_id in subscription_invoice_ids]
            complete_invoices = await asyncio.gather(*complete_invoice_tasks, return_exceptions=True)
            
            # Build subscription invoices with complete data
            for i, complete_invoice in enumerate(complete_invoices):
                if not isinstance(complete_invoice, Exception) and complete_invoice:
                    # Use complete invoice data with correct amounts and field names for frontend
                    invoice_data = {
                        'invoiceId': complete_invoice.get('invoiceId'),
                        'account_id': account_id,
                        'invoice_number': complete_invoice.get('invoiceNumber'),
                        'invoiceDate': complete_invoice.get('invoiceDate'),
                        'target_date': complete_invoice.get('targetDate'),
                        'amount': float(complete_invoice.get('amount', 0)),
                        'currency': complete_invoice.get('currency', 'USD'),
                        'status': complete_invoice.get('status', 'DRAFT'),
                        'balance': float(complete_invoice.get('balance', 0)),
                        'credit_adj': float(complete_invoice.get('creditAdj', 0)),
                        'refund_adj': float(complete_invoice.get('refundAdj', 0)),
                        'created_at': complete_invoice.get('createdDate'),
                        'updated_at': complete_invoice.get('updatedDate'),
                        'items': complete_invoice.get('items', [])
                    }
                    subscription_invoices.append(invoice_data)
                else:
                    if isinstance(complete_invoices[i], Exception):
                        logger.warning(f"Failed to get complete data for invoice {subscription_invoice_ids[i]}: {complete_invoices[i]}")
        
        # Sort by invoice date (most recent first)
        subscription_invoices.sort(key=lambda x: x.get('invoiceDate', ''), reverse=True)
        
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_invoices = subscription_invoices[start_idx:end_idx]
        
        logger.info(f"Found {len(subscription_invoices)} invoices for subscription {subscription_id}")
        
        return {
            "success": True,
            "invoices": paginated_invoices,
            "total": len(subscription_invoices),
            "page": page,
            "limit": limit,
            "subscription_id": subscription_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get invoices for subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve invoices: {str(e)}")

@router.post("/subscription/{subscription_id}/pause")
async def pause_subscription_and_instance(
    subscription_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Pause subscription billing and suspend associated instance"""
    try:
        # Get subscription metadata to find instance ID
        metadata = await killbill.get_subscription_metadata(subscription_id)
        instance_id = metadata.get("instance_id")
        
        if not instance_id:
            logger.warning(f"No instance_id found in subscription {subscription_id} metadata")
        
        # TODO: Implement actual KillBill subscription pause
        # For now, we'll use the suspend instance action which should handle billing status
        
        # Import instance client to suspend the instance
        from ..utils.instance_client import InstanceServiceClient
        instance_client = InstanceServiceClient()
        
        if instance_id:
            try:
                # Suspend the instance (this will also update billing status)
                await instance_client.suspend_instance(instance_id)
                logger.info(f"Successfully suspended instance {instance_id} for subscription {subscription_id}")
            except Exception as instance_error:
                logger.error(f"Failed to suspend instance {instance_id}: {instance_error}")
                # Continue with subscription pause even if instance suspension fails
        
        logger.info(f"Paused subscription {subscription_id}")
        
        return {
            "success": True,
            "message": "Subscription paused and instance suspended",
            "subscription_id": subscription_id,
            "instance_id": instance_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to pause subscription: {str(e)}")

@router.post("/subscription/{subscription_id}/resume")
async def resume_subscription_and_instance(
    subscription_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Resume subscription billing and unsuspend associated instance"""
    try:
        # Get subscription metadata to find instance ID
        metadata = await killbill.get_subscription_metadata(subscription_id)
        instance_id = metadata.get("instance_id")
        
        if not instance_id:
            logger.warning(f"No instance_id found in subscription {subscription_id} metadata")
        
        # TODO: Implement actual KillBill subscription resume
        # For now, we'll use the unsuspend instance action
        
        # Import instance client to unsuspend the instance
        from ..utils.instance_client import InstanceServiceClient
        instance_client = InstanceServiceClient()
        
        if instance_id:
            try:
                # Unsuspend the instance (this will also update billing status)
                await instance_client.unsuspend_instance(instance_id)
                logger.info(f"Successfully unsuspended instance {instance_id} for subscription {subscription_id}")
            except Exception as instance_error:
                logger.error(f"Failed to unsuspend instance {instance_id}: {instance_error}")
        
        logger.info(f"Resumed subscription {subscription_id}")
        
        return {
            "success": True,
            "message": "Subscription resumed and instance unsuspended",
            "subscription_id": subscription_id,
            "instance_id": instance_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resume subscription: {str(e)}")

@router.delete("/subscription/{subscription_id}")
async def cancel_subscription(
    subscription_id: str,
    reason: str = "User requested cancellation",
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Schedule subscription cancellation at end of billing period"""
    try:
        # Get subscription details to determine cancellation date
        subscription = await killbill.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        # Schedule end-of-term cancellation in KillBill
        await killbill.cancel_subscription(subscription_id, reason)
        logger.info(f"Scheduled end-of-term cancellation for subscription {subscription_id}")
        
        # Extract cancellation information
        charged_through_date = subscription.get("chargedThroughDate")
        plan_name = subscription.get("planName", "Unknown")
        
        return {
            "success": True,
            "message": "Subscription scheduled for cancellation at end of billing period",
            "subscription_id": subscription_id,
            "plan_name": plan_name,
            "cancellation_date": charged_through_date,
            "reason": reason,
            "note": "You will continue to have access to your service until the end of your current billing period."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to schedule cancellation for subscription {subscription_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule subscription cancellation: {str(e)}")
