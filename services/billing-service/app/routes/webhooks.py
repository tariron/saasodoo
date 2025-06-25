"""
Billing Service - Webhooks Routes
Handles KillBill webhook events
"""

from fastapi import APIRouter, Request, HTTPException, Response
import logging
import json
from typing import Dict, Any, Optional
from app.utils.instance_client import instance_client
from app.utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/killbill")
async def handle_killbill_webhook(request: Request, response: Response):
    """Handle webhook events from KillBill"""
    
    # Set response headers to prevent HTTP/2 upgrade attempts
    response.headers["Connection"] = "close"
    response.headers["Upgrade"] = ""
    try:
        # Log all relevant headers for debugging
        headers = dict(request.headers)
        logger.info(f"KillBill webhook headers: {headers}")
        
        # Get raw body with enhanced handling
        body = await request.body()
        logger.info(f"Received KillBill webhook - Raw body length: {len(body)}")
        logger.info(f"Raw body content: {body}")
        
        # Try alternative body reading if empty
        if not body:
            # Check if there's a content-length header
            content_length = request.headers.get('content-length', '0')
            logger.info(f"Content-Length header: {content_length}")
            
            # Check for HTTP/2 upgrade attempt
            connection_header = request.headers.get('connection', '')
            upgrade_header = request.headers.get('upgrade', '')
            
            if 'upgrade' in connection_header.lower() and 'h2c' in upgrade_header.lower():
                logger.warning("Detected HTTP/2 upgrade attempt - body lost due to protocol upgrade")
                logger.info("KillBill is attempting HTTP/2 upgrade - will parse from logs if needed")
                
                # Since we lost the body due to HTTP/2 upgrade, check if this is a retry
                # KillBill logs the payload in our logs, we can see the pattern
                # For now, return success to prevent endless retries but log the issue
                logger.warning(f"HTTP/2 upgrade caused body loss - Content-Length was {content_length}")
                logger.info("Webhook data lost due to HTTP/2 upgrade - check KillBill logs for payload details")
                
                return {
                    "success": True, 
                    "message": "Webhook received but body lost due to HTTP/2 upgrade",
                    "note": "Consider configuring KillBill to use HTTP/1.1 for webhooks"
                }
            
            # Try reading from request.stream() if body is empty but content-length > 0
            if int(content_length) > 0:
                logger.info("Attempting to read from request.stream()")
                try:
                    chunks = []
                    async for chunk in request.stream():
                        chunks.append(chunk)
                    body = b''.join(chunks)
                    logger.info(f"Stream read body length: {len(body)}, content: {body}")
                except Exception as e:
                    logger.error(f"Failed to read from request.stream(): {e}")
        
        # Handle different content types
        content_type = request.headers.get('content-type', '').lower()
        
        if 'application/json' in content_type:
            # Try to parse as JSON
            if body:
                try:
                    payload = json.loads(body)
                    logger.info(f"Parsed JSON payload: {payload}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in webhook payload: {e}")
                    logger.error(f"Raw body was: {body}")
                    raise HTTPException(status_code=400, detail="Invalid JSON payload")
            else:
                # Empty JSON body - treat as ping/health check
                logger.info("Received empty JSON webhook - treating as ping/health check")
                payload = {
                    "eventType": "PING",
                    "message": "Empty webhook received"
                }
        else:
            # Handle other content types (e.g., form data, plain text)
            body_str = body.decode('utf-8') if body else ""
            logger.info(f"Non-JSON payload received: {body_str}")
            
            # For now, create a simple payload structure
            payload = {
                "eventType": "UNKNOWN",
                "rawPayload": body_str,
                "contentType": content_type
            }
        
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
        elif event_type == "PING":
            logger.info("Processed KillBill ping/health check webhook")
        elif event_type == "UNKNOWN":
            logger.info(f"Received webhook with unknown format - investigating: {payload}")
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
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Subscription created: {subscription_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        logger.info(f"Subscription {subscription_id} created for customer {customer_external_key}")
        
        # TODO: Trigger instance provisioning if needed
        # This could integrate with the instance service to automatically provision
        # an Odoo instance when a subscription is created
        
        # TODO: Send welcome email to customer
        # This would integrate with an email service to send onboarding emails
        
        logger.info(f"Processed subscription creation for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling subscription creation: {e}")

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
    invoice_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Invoice created: {invoice_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        logger.info(f"Invoice {invoice_id} created for customer {customer_external_key}")
        
        # TODO: Store invoice metadata in our database if needed
        # This could include custom fields, instance associations, etc.
        
        # TODO: Send invoice notification email to customer
        # This would integrate with an email service to notify customers
        # about new invoices with links to view/pay
        
        # TODO: For overdue invoices, could trigger collection workflows
        
        logger.info(f"Processed invoice creation for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling invoice creation: {e}")


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
