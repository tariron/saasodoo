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
                params={"customer_id": customer_id},
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
    """Create a new KillBill account for a customer"""
    try:
        # Check if account already exists
        existing_account = await killbill.get_account_by_external_key(account_data.customer_id)
        if existing_account:
            return CreateAccountResponse(
                success=True,
                killbill_account_id=existing_account.get("accountId"),
                customer_id=account_data.customer_id,
                message="Account already exists"
            )
        
        # Create new account
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
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        logger.info(f"Getting billing overview for customer {customer_id}, account {account_id}")
        
        # Get subscriptions with instance metadata
        subscriptions = await killbill.get_account_subscriptions(account_id)
        
        # Get customer instances for linking with subscriptions
        customer_instances = await get_customer_instances(customer_id)
        
        # Get account balance from KillBill
        account_balance = 0.0
        try:
            balance_info = await killbill.get_account_balance(account_id)
            account_balance = balance_info.get('accountBalance', 0.0) if balance_info else 0.0
        except Exception as e:
            logger.warning(f"Failed to get account balance for {account_id}: {e}")
        
        # Process subscriptions and extract trial info with per-instance linking
        active_subscriptions = []
        trial_info = None
        next_billing_date = None
        next_billing_amount = 0.0
        
        # Create instance lookup for faster matching
        instance_lookup = {instance['id']: instance for instance in customer_instances}
        
        for sub in subscriptions:
            if sub.get('state') == 'ACTIVE':
                # Get subscription metadata to find linked instance
                subscription_metadata = {}
                try:
                    subscription_metadata = await killbill.get_subscription_metadata(sub.get('subscriptionId', ''))
                except Exception as e:
                    logger.warning(f"Failed to get metadata for subscription {sub.get('subscriptionId')}: {e}")
                
                # Find linked instance
                instance_id = subscription_metadata.get('instance_id')
                linked_instance = None
                if instance_id and instance_id in instance_lookup:
                    linked_instance = instance_lookup[instance_id]
                
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
                    'billing_end_date': sub.get('billingEndDate'),
                    'trial_start_date': sub.get('trialStartDate'),
                    'trial_end_date': sub.get('trialEndDate'),
                    'metadata': subscription_metadata,
                    'created_at': sub.get('createdDate'),
                    'updated_at': sub.get('updatedDate'),
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
        
        # Get all invoices for the account using direct approach
        recent_invoices = []
        
        try:
            # Fetch all invoices for the account directly
            all_invoices = await killbill.get_account_invoices(account_id, limit=20)
            logger.info(f"Retrieved {len(all_invoices)} invoices for account {account_id}")
            
            for invoice in all_invoices:
                invoice_id = invoice.get('id')
                
                # Get subscription ID from invoice
                subscription_id = None
                try:
                    subscription_id = await killbill.get_subscription_id_from_invoice(invoice_id)
                    logger.info(f"DEBUG - Invoice {invoice_id} extracted subscription_id: {subscription_id}")
                except Exception as e:
                    logger.warning(f"Failed to get subscription ID for invoice {invoice_id}: {e}")
                
                # Find linked instance if subscription exists
                instance_id = None
                for sub in active_subscriptions:
                    logger.info(f"DEBUG - Checking subscription {sub.get('id')} == {subscription_id}")
                    if sub.get('id') == subscription_id:
                        instance_id = sub.get('instance_id')
                        logger.info(f"DEBUG - Found matching subscription, instance_id: {instance_id}")
                        break
                
                # Get payment data for this invoice
                payments = []
                try:
                    payments = await killbill.get_invoice_payments(invoice_id)
                    logger.info(f"Found {len(payments)} payments for invoice {invoice_id}")
                except Exception as e:
                    logger.warning(f"Failed to get payments for invoice {invoice_id}: {e}")
                
                # Determine payment status
                payment_status = 'no_payments'
                if any(p.get('status') == 'SUCCESS' for p in payments):
                    payment_status = 'paid'
                elif payments:
                    payment_status = 'unpaid'
                
                # Add subscription_id and payment data to invoice
                invoice_with_data = invoice.copy()
                invoice_with_data['subscription_id'] = subscription_id
                invoice_with_data['payments'] = payments
                invoice_with_data['payment_status'] = payment_status
                invoice_with_data['instance_id'] = instance_id
                recent_invoices.append(invoice_with_data)
            
            # Sort invoices by date (most recent first)
            recent_invoices.sort(key=lambda x: x.get('invoice_date', ''), reverse=True)
            logger.info(f"Built {len(recent_invoices)} invoices with direct fetching")
            
            # DEBUG: Log all invoice data being returned
            logger.info("DEBUG - Final invoice data:")
            for invoice in recent_invoices:
                logger.info(f"  Invoice {invoice.get('id')} - Amount: {invoice.get('amount')}, Subscription: {invoice.get('subscription_id')}, Instance: {invoice.get('instance_id')}, Payment Status: {invoice.get('payment_status')}")
                
        except Exception as e:
            logger.warning(f"Failed to get invoices for account {account_id}: {e}")
        
        # Get payment methods from KillBill
        payment_methods = []
        try:
            payment_methods = await killbill.get_account_payment_methods(account_id)
        except Exception as e:
            logger.warning(f"Failed to get payment methods for {account_id}: {e}")
        
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
        
        # Build comprehensive billing overview with per-instance data
        billing_overview = {
            'account': billing_account,
            'active_subscriptions': active_subscriptions,
            'recent_invoices': recent_invoices,
            'next_billing_date': next_billing_date.isoformat() if next_billing_date else None,
            'next_billing_amount': next_billing_amount if next_billing_amount > 0 else None,
            'payment_methods': payment_methods,
            'account_balance': account_balance,
            'trial_info': trial_info,
            'customer_instances': customer_instances
        }
        
        return {
            "success": True,
            "data": billing_overview
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get billing overview for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing overview: {str(e)}")
