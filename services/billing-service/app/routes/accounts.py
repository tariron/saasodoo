"""
Billing Service - Accounts Routes
Handles KillBill account management
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel
from datetime import datetime
import httpx
import os

from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateAccountRequest(BaseModel):
    customer_id: str
    email: str
    name: str
    company: Optional[str] = None
    currency: str = "USD"

class CreateAccountResponse(BaseModel):
    success: bool
    killbill_account_id: Optional[str] = None
    customer_id: str
    message: str

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

async def get_customer_instances(customer_id: str) -> List[Dict[str, Any]]:
    """Get instances for a customer from instance service"""
    try:
        instance_service_url = os.getenv("INSTANCE_SERVICE_URL", "http://instance-service:8003")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{instance_service_url}/api/v1/instances/",
                params={"customer_id": customer_id, "page_size": 25},
                timeout=10.0
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("instances", [])
            else:
                logger.warning(f"Failed to get instances for customer {customer_id}: {response.status_code}")
                return []
    except Exception as e:
        logger.warning(f"Failed to connect to instance service for customer {customer_id}: {e}")
        return []

@router.post("/", response_model=CreateAccountResponse)
async def create_account(
    account_data: CreateAccountRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Create a new KillBill account for a customer.

    Uses optimistic creation - tries to create first, handles duplicates on conflict.
    This is more efficient for high concurrency since most requests are new accounts.
    """
    try:
        # Optimistic approach: try to create first (saves a GET for 99% of cases)
        account = await killbill.create_account(
            customer_id=account_data.customer_id,
            email=account_data.email,
            name=account_data.name,
            company=account_data.company,
            currency=account_data.currency
        )

        return CreateAccountResponse(
            success=True,
            killbill_account_id=account.get("accountId"),
            customer_id=account_data.customer_id,
            message="Account created successfully"
        )

    except Exception as e:
        error_msg = str(e)
        # Handle duplicate account (HTTP 409 Conflict from KillBill)
        if "409" in error_msg or "already exists" in error_msg.lower() or "duplicate" in error_msg.lower():
            try:
                existing_account = await killbill.get_account_by_external_key(account_data.customer_id)
                if existing_account:
                    return CreateAccountResponse(
                        success=True,
                        killbill_account_id=existing_account.get("accountId"),
                        customer_id=account_data.customer_id,
                        message="Account already exists"
                    )
            except Exception as lookup_err:
                logger.error(f"Failed to lookup existing account for {account_data.customer_id}: {lookup_err}")

        logger.error(f"Failed to create account for customer {account_data.customer_id}: {e}")
        return CreateAccountResponse(
            success=False,
            customer_id=account_data.customer_id,
            message=f"Failed to create account: {str(e)}"
        )

@router.get("/{customer_id}")
async def get_account(
    customer_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get account information by customer ID"""
    try:
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {
            "success": True,
            "account": account
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get account for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve account")

@router.get("/overview/{customer_id}")
async def get_billing_overview(
    customer_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get comprehensive billing overview for a customer with per-instance information"""
    try:
        import time
        start_time = time.time()
        
        # PERFORMANCE DEBUG: Log the start of the request
        logger.error(f"🔥 BILLING OVERVIEW START for customer {customer_id} at {start_time}")
        
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            logger.error(f"❌ Customer account not found for {customer_id}")
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        logger.info(f"Getting billing overview for customer {customer_id}, account {account_id}")
        
        # Fetch all independent data in parallel
        import asyncio
        parallel_start = time.time()
        logger.info(f"Starting parallel data fetch for account {account_id}")
        
        # Execute independent API calls in parallel (removed invoice processing for performance)
        logger.info("Creating parallel tasks...")
        subscriptions_task = killbill.get_account_subscriptions(account_id)
        instances_task = get_customer_instances(customer_id)
        payment_methods_task = killbill.get_account_payment_methods(account_id)
        
        # Balance call can fail, so handle separately
        balance_task = asyncio.create_task(killbill.get_account_balance(account_id))
        
        logger.info("Waiting for parallel tasks to complete...")
        # Wait for all parallel calls to complete
        subscriptions, customer_instances, payment_methods = await asyncio.gather(
            subscriptions_task, 
            instances_task, 
            payment_methods_task,
            return_exceptions=True
        )
        logger.info("Parallel tasks completed")
        
        # Handle balance separately to avoid failing the entire operation
        account_balance = 0.0
        try:
            balance_info = await balance_task
            account_balance = balance_info.get('accountBalance', 0.0) if balance_info else 0.0
        except Exception as e:
            logger.warning(f"Failed to get account balance for {account_id}: {e}")
        
        # Handle exceptions from parallel calls
        if isinstance(subscriptions, Exception):
            logger.error(f"Failed to get subscriptions: {subscriptions}")
            subscriptions = []
        if isinstance(customer_instances, Exception):
            logger.error(f"Failed to get customer instances: {customer_instances}")
            customer_instances = []
        if isinstance(payment_methods, Exception):
            logger.error(f"Failed to get payment methods: {payment_methods}")
            payment_methods = []
        
        parallel_time = time.time() - parallel_start
        logger.info(f"Parallel data fetch completed in {parallel_time:.2f} seconds")
        
        # Process subscriptions and extract trial info with per-instance linking
        active_subscriptions = []
        trial_info = None
        next_billing_date = None
        next_billing_amount = 0.0

        # Create instance lookup by subscription_id (the correct way - instances have subscription_id foreign key)
        instance_by_subscription = {instance['subscription_id']: instance for instance in customer_instances if instance.get('subscription_id')}
        logger.info(f"Created instance lookup with {len(instance_by_subscription)} subscription mappings")

        # Separate processing for all subscription states
        pending_subscriptions = []
        outstanding_invoices = []
        total_outstanding = 0.0
        provisioning_blocked_instances = []

        for sub in subscriptions:
            if sub.get('state') == 'ACTIVE':
                # Find linked instance using subscription_id (instances have subscription_id field)
                subscription_id = sub.get('subscriptionId')
                linked_instance = instance_by_subscription.get(subscription_id)
                instance_id = linked_instance.get('id') if linked_instance else None
                
                # Extract cancellation information
                cancelled_date = sub.get('cancelledDate')
                billing_end_date = sub.get('billingEndDate')
                is_scheduled_for_cancellation = bool(cancelled_date) and sub.get('state') == 'ACTIVE'
                
                # Determine cancellation reason from events if available
                cancellation_reason = "User requested cancellation"  # Default reason
                events = sub.get('events', [])
                for event in events:
                    if event.get('eventType') in ['STOP_ENTITLEMENT', 'STOP_BILLING']:
                        # Could extract reason from audit logs if available
                        break

                subscription_data = {
                    'id': sub.get('subscriptionId'),
                    'account_id': account_id,
                    'plan_name': sub.get('planName'),
                    'product_name': sub.get('productName', sub.get('planName')),
                    'product_category': sub.get('productCategory', 'SAAS'),
                    'billing_period': sub.get('billingPeriod', 'MONTHLY'),
                    'state': sub.get('state'),
                    'start_date': sub.get('startDate'),
                    'charged_through_date': sub.get('chargedThroughDate'),
                    'billing_start_date': sub.get('billingStartDate'),
                    'billing_end_date': billing_end_date,
                    'trial_start_date': sub.get('trialStartDate'),
                    'trial_end_date': sub.get('trialEndDate'),
                    'created_at': sub.get('createdDate'),
                    'updated_at': sub.get('updatedDate'),
                    # Cancellation information
                    'cancelled_date': cancelled_date,
                    'is_scheduled_for_cancellation': is_scheduled_for_cancellation,
                    'cancellation_reason': cancellation_reason if is_scheduled_for_cancellation else None,
                    # Per-instance information
                    'instance_id': instance_id,
                    'instance_name': linked_instance.get('name') if linked_instance else None,
                    'instance_status': linked_instance.get('status') if linked_instance else None,
                    'instance_billing_status': linked_instance.get('billing_status') if linked_instance else None
                }
                
                active_subscriptions.append(subscription_data)
                
                # Check for trial phase
                phase_type = sub.get('phaseType')
                if phase_type == 'TRIAL' and sub.get('trialEndDate'):
                    trial_end_date = sub.get('trialEndDate')
                    try:
                        trial_end = datetime.fromisoformat(trial_end_date.replace('Z', '+00:00'))
                        now = datetime.now(trial_end.tzinfo)
                        days_remaining = max(0, (trial_end - now).days)
                        
                        trial_info = {
                            'is_trial': True,
                            'trial_end_date': trial_end_date,
                            'days_remaining': days_remaining
                        }
                    except Exception as e:
                        logger.warning(f"Failed to parse trial date {trial_end_date}: {e}")
                
                # Calculate next billing
                if sub.get('chargedThroughDate') and not phase_type == 'TRIAL':
                    try:
                        charged_through = datetime.fromisoformat(sub.get('chargedThroughDate').replace('Z', '+00:00'))
                        if not next_billing_date or charged_through < next_billing_date:
                            next_billing_date = charged_through
                            # Estimate billing amount (in real implementation, get from KillBill plan)
                            next_billing_amount += 25.0  # Default amount
                    except Exception as e:
                        logger.warning(f"Failed to parse charged through date: {e}")
            
            # Handle non-ACTIVE subscriptions (pending payment states)
            elif sub.get('state') in ['COMMITTED']:  # Subscriptions created but not fully activated
                # Find linked instance using subscription_id (instances have subscription_id field)
                subscription_id = sub.get('subscriptionId')
                linked_instance = instance_by_subscription.get(subscription_id)
                instance_id = linked_instance.get('id') if linked_instance else None

                # Track instances blocked by pending payment
                if linked_instance and linked_instance.get('billing_status') == 'payment_required':
                    provisioning_blocked_instances.append({
                        'instance_id': instance_id,
                        'instance_name': linked_instance.get('name'),
                        'subscription_id': subscription_id,
                        'plan_name': sub.get('planName'),
                        'created_at': sub.get('createdDate')
                    })

                pending_subscription_data = {
                    'id': subscription_id,
                    'account_id': account_id,
                    'plan_name': sub.get('planName'),
                    'product_name': sub.get('productName', sub.get('planName')),
                    'billing_period': sub.get('billingPeriod', 'MONTHLY'),
                    'state': sub.get('state'),
                    'start_date': sub.get('startDate'),
                    'created_at': sub.get('createdDate'),
                    'instance_id': instance_id,
                    'instance_name': linked_instance.get('name') if linked_instance else None,
                    'instance_status': linked_instance.get('status') if linked_instance else None,
                    'awaiting_payment': True
                }

                pending_subscriptions.append(pending_subscription_data)
        
        # Get outstanding invoices (invoices with balance > 0)
        try:
            invoices = await killbill.get_account_invoices(account_id, limit=50)
            for invoice in invoices:
                balance = float(invoice.get('balance', 0))
                if balance > 0:  # Invoice has outstanding balance
                    outstanding_invoices.append({
                        'id': invoice.get('id'),
                        'invoice_number': invoice.get('invoice_number'),
                        'invoice_date': invoice.get('invoice_date'),
                        'amount': float(invoice.get('amount', 0)),
                        'balance': balance,
                        'currency': invoice.get('currency', 'USD'),
                        'status': invoice.get('status')
                    })
                    total_outstanding += balance
        except Exception as e:
            logger.warning(f"Failed to fetch outstanding invoices for {customer_id}: {e}")
        
        # Invoice processing removed for performance optimization
        # Detailed invoice information is now available in dedicated instance billing pages
        # This eliminates expensive parallel processing and improves dashboard load times
        
        # Format account info
        billing_account = {
            'id': account_id,
            'customer_id': customer_id,
            'external_key': customer_id,
            'name': account.get('name', ''),
            'email': account.get('email', ''),
            'currency': account.get('currency', 'USD'),
            'company': account.get('company'),
            'created_at': account.get('createdDate'),
            'updated_at': account.get('updatedDate')
        }
        
        # Build comprehensive billing overview with payment visibility
        billing_overview = {
            'account': billing_account,
            'active_subscriptions': active_subscriptions,
            'pending_subscriptions': pending_subscriptions,
            'outstanding_invoices': outstanding_invoices,
            'total_outstanding': total_outstanding,
            'provisioning_blocked_instances': provisioning_blocked_instances,
            'next_billing_date': next_billing_date.isoformat() if next_billing_date else None,
            'next_billing_amount': next_billing_amount if next_billing_amount > 0 else None,
            'payment_methods': payment_methods,
            'account_balance': account_balance,
            'trial_info': trial_info,
            'customer_instances': customer_instances
        }
        
        total_time = time.time() - start_time
        logger.error(f"🔥 BILLING OVERVIEW COMPLETED in {total_time:.2f} seconds for customer {customer_id}")
        
        return {
            "success": True,
            "data": billing_overview
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get billing overview for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing overview: {str(e)}")
