"""
Billing Service - Webhooks Routes
Handles KillBill webhook events
"""

from fastapi import APIRouter, Request, HTTPException
import logging
import json
from typing import Dict, Any, Optional
from app.utils.instance_client import instance_client
from app.utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/killbill")
async def handle_killbill_webhook(request: Request):
    """Handle webhook events from KillBill"""
    try:
        # Get raw body
        body = await request.body()
        
        # Parse JSON payload
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
        # Extract event type
        event_type = payload.get("eventType")
        if not event_type:
            logger.error("No event type in webhook payload")
            raise HTTPException(status_code=400, detail="Missing event type")
        
        logger.info(f"Received KillBill webhook: {event_type}")
        
        # Handle different event types
        if event_type == "PAYMENT_SUCCESS":
            await handle_payment_success(payload)
        elif event_type == "PAYMENT_FAILED":
            await handle_payment_failed(payload)
        elif event_type == "SUBSCRIPTION_CREATION":
            await handle_subscription_created(payload)
        elif event_type == "SUBSCRIPTION_CANCELLATION":
            await handle_subscription_cancelled(payload)
        elif event_type == "INVOICE_CREATION":
            await handle_invoice_created(payload)
        else:
            logger.info(f"Unhandled webhook event type: {event_type}")
        
        return {"success": True, "message": "Webhook processed"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to process webhook: {e}")
        raise HTTPException(status_code=500, detail="Failed to process webhook")

async def handle_payment_success(payload: Dict[str, Any]):
    """Handle successful payment webhook"""
    payment_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Payment successful: {payment_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get all suspended instances for this customer and unsuspend them
        logger.info(f"Payment successful for customer {customer_external_key} - unsuspending instances")
        
        instances = await instance_client.get_instances_by_customer(customer_external_key)
        suspended_count = 0
        
        for instance in instances:
            if instance.get('status') == 'suspended':
                try:
                    result = await instance_client.unsuspend_instance(instance['id'], "Payment received")
                    if result.get('status') == 'success':
                        suspended_count += 1
                        logger.info(f"Unsuspended instance {instance['id']} for customer {customer_external_key}")
                    else:
                        logger.error(f"Failed to unsuspend instance {instance['id']}: {result}")
                except Exception as e:
                    logger.error(f"Error unsuspending instance {instance['id']}: {e}")
        
        logger.info(f"Unsuspended {suspended_count} instances for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling payment success: {e}")

async def handle_payment_failed(payload: Dict[str, Any]):
    """Handle failed payment webhook"""
    payment_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.warning(f"Payment failed: {payment_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get all instances for this customer and suspend them
        logger.warning(f"Payment failed for customer {customer_external_key} - suspending all instances")
        
        instances = await instance_client.get_instances_by_customer(customer_external_key)
        suspended_count = 0
        
        for instance in instances:
            if instance.get('status') in ['running', 'stopped', 'starting', 'stopping']:
                try:
                    result = await instance_client.suspend_instance(instance['id'], "Payment failed")
                    if result.get('status') == 'success':
                        suspended_count += 1
                        logger.warning(f"Suspended instance {instance['id']} for customer {customer_external_key}")
                    else:
                        logger.error(f"Failed to suspend instance {instance['id']}: {result}")
                except Exception as e:
                    logger.error(f"Error suspending instance {instance['id']}: {e}")
        
        logger.warning(f"Suspended {suspended_count} instances for customer {customer_external_key}")
        
        # TODO: Send notification email to customer about failed payment
        
    except Exception as e:
        logger.error(f"Error handling payment failure: {e}")

async def handle_subscription_created(payload: Dict[str, Any]):
    """Handle subscription creation webhook"""
    logger.info(f"Subscription created: {payload.get('objectId')}")
    # TODO: Update subscription status in our database
    # TODO: Trigger instance provisioning
    # TODO: Send welcome email

async def handle_subscription_cancelled(payload: Dict[str, Any]):
    """Handle subscription cancellation webhook"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.warning(f"Subscription cancelled: {subscription_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Suspend all instances for this customer due to subscription cancellation
        logger.warning(f"Subscription cancelled for customer {customer_external_key} - suspending all instances")
        
        instances = await instance_client.get_instances_by_customer(customer_external_key)
        suspended_count = 0
        
        for instance in instances:
            if instance.get('status') in ['running', 'stopped', 'starting', 'stopping']:
                try:
                    result = await instance_client.suspend_instance(instance['id'], "Subscription cancelled")
                    if result.get('status') == 'success':
                        suspended_count += 1
                        logger.warning(f"Suspended instance {instance['id']} for customer {customer_external_key}")
                    else:
                        logger.error(f"Failed to suspend instance {instance['id']}: {result}")
                except Exception as e:
                    logger.error(f"Error suspending instance {instance['id']}: {e}")
        
        logger.warning(f"Suspended {suspended_count} instances for customer {customer_external_key}")
        
        # TODO: Send cancellation confirmation email
        
    except Exception as e:
        logger.error(f"Error handling subscription cancellation: {e}")

async def handle_invoice_created(payload: Dict[str, Any]):
    """Handle invoice creation webhook"""
    logger.info(f"Invoice created: {payload.get('objectId')}")
    # TODO: Store invoice details in our database
    # TODO: Send invoice to customer


async def _get_customer_external_key_by_account_id(account_id: str) -> Optional[str]:
    """Get customer external key from KillBill account ID"""
    import os
    
    try:
        # Initialize KillBill client with environment variables
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        # Get account details from KillBill
        account = await killbill.get_account_by_id(account_id)
        if account and account.get('externalKey'):
            return account['externalKey']
        
        logger.warning(f"No external key found for account {account_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting customer external key for account {account_id}: {e}")
        return None
