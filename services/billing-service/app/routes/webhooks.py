"""
Billing Service - Webhooks Routes
Handles KillBill webhook events
"""

from fastapi import APIRouter, Request, HTTPException, Response
import logging
import json
import os
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
        elif event_type == "INVOICE_PAYMENT_SUCCESS":
            await handle_invoice_payment_success(payload)
        elif event_type == "SUBSCRIPTION_CREATION":
            await handle_subscription_created(payload)
        elif event_type == "SUBSCRIPTION_CANCELLATION":
            await handle_subscription_cancelled(payload)
        elif event_type == "SUBSCRIPTION_CANCEL":
            await handle_subscription_cancelled(payload)
        elif event_type == "ENTITLEMENT_CANCEL":
            await handle_entitlement_cancelled(payload)
        elif event_type == "SUBSCRIPTION_PHASE":
            await handle_subscription_phase_change(payload)
        elif event_type == "SUBSCRIPTION_EXPIRED":
            await handle_subscription_expired(payload)
        elif event_type == "INVOICE_OVERDUE":
            await handle_invoice_overdue(payload)
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
    """Handle successful payment webhook - trigger instance provisioning for paid instances"""
    payment_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Payment successful: {payment_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get payment details to find associated subscription
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        # First, handle provisioning of pending paid instances
        # NOTE: Payment webhooks don't directly provide subscription_id, they provide payment_id
        # For now, keeping bulk approach since payment->invoice->subscription mapping is complex
        # TODO: Could be improved by fetching payment details to get invoice/subscription info
        pending_instances = await instance_client.get_instances_by_customer_and_status(
            customer_external_key, "pending"
        )
        
        provisioned_count = 0
        for instance in pending_instances:
            instance_id = instance.get('id')
            billing_status = instance.get('billing_status')
            
            # Only provision paid instances here (not trial instances)
            if billing_status == 'payment_required':
                logger.info(f"Provisioning paid instance {instance_id} for customer {customer_external_key}")
                
                # Update instance billing status and trigger provisioning
                await instance_client.provision_instance(
                    instance_id=instance_id,
                    subscription_id=None,  # Will be updated when we get subscription details
                    billing_status="paid",
                    provisioning_trigger="payment_success"
                )
                
                provisioned_count += 1
                logger.info(f"Paid instance {instance_id} provisioning triggered")
        
        # Second, handle unsuspending existing instances due to payment
        instances = await instance_client.get_instances_by_customer(customer_external_key)
        unsuspended_count = 0
        
        for instance in instances:
            if instance.get('status') == 'suspended' or instance.get('billing_status') == 'payment_required':
                try:
                    result = await instance_client.unsuspend_instance(instance['id'], "Payment received")
                    if result.get('status') == 'success':
                        unsuspended_count += 1
                        logger.info(f"Unsuspended instance {instance['id']} for customer {customer_external_key}")
                    else:
                        logger.error(f"Failed to unsuspend instance {instance['id']}: {result}")
                except Exception as e:
                    logger.error(f"Error unsuspending instance {instance['id']}: {e}")
        
        logger.info(f"Payment success processed for customer {customer_external_key}: "
                   f"provisioned {provisioned_count} instances, unsuspended {unsuspended_count} instances")
        
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
    """Handle subscription creation webhook - create instances for trial subscriptions"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Subscription created: {subscription_id} for account: {account_id}")
    
    try:
        # Check if this is an EFFECTIVE subscription creation (avoid duplicates from REQUESTED)
        metadata = payload.get('metaData')
        if metadata:
            import json
            try:
                meta_dict = json.loads(metadata)
                action_type = meta_dict.get('actionType')
                
                # Only process EFFECTIVE subscriptions to avoid duplicates
                if action_type != 'EFFECTIVE':
                    logger.info(f"Skipping subscription {subscription_id} with action type '{action_type}' (waiting for EFFECTIVE)")
                    return
                
                logger.info(f"Processing EFFECTIVE subscription {subscription_id}")
            except json.JSONDecodeError:
                logger.warning(f"Could not parse metadata for subscription {subscription_id}, proceeding anyway")
        
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        logger.info(f"Subscription {subscription_id} created for customer {customer_external_key}")
        
        # Get subscription details from KillBill
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        subscription_details = await killbill.get_subscription_by_id(subscription_id)
        if not subscription_details:
            logger.warning(f"Could not get subscription details for {subscription_id}")
            return
        
        plan_name = subscription_details.get('planName', 'unknown')
        phase_type = subscription_details.get('phaseType', 'UNKNOWN')
        
        # Get subscription metadata to check for reactivation
        subscription_metadata = await killbill.get_subscription_metadata(subscription_id)
        target_instance_id = subscription_metadata.get("target_instance_id")
        is_reactivation = subscription_metadata.get("reactivation") == "true"
        
        # Handle reactivation subscriptions
        if is_reactivation and target_instance_id:
            logger.info(f"Reactivation subscription {subscription_id} created for instance {target_instance_id}")
            
            # Call restart function to update billing status - skip status change to keep TERMINATED
            try:
                result = await instance_client.restart_instance_with_new_subscription(
                    instance_id=target_instance_id,
                    subscription_id=subscription_id,
                    billing_status="payment_required",
                    skip_status_change=True
                )
                logger.info(f"Updated instance {target_instance_id} billing status for reactivation - remains TERMINATED until payment")
                
            except Exception as e:
                logger.error(f"Failed to update instance billing status for reactivation: {e}")
            
            return  # Exit early - reactivation subscription recorded, waiting for payment
        
        # Check if this is a trial subscription
        is_trial = phase_type == 'TRIAL'
        
        if not is_trial:
            logger.info(f"Subscription {subscription_id} is not a trial or reactivation ({plan_name}, {phase_type}). Skipping instance creation.")
            return
        
        logger.info(f"Processing trial subscription {subscription_id} (plan: {plan_name}, phase: {phase_type})")
        
        # Trial eligibility is now checked upfront in the API endpoint before subscription creation
        # All trial subscriptions reaching this webhook are pre-validated and eligible
        logger.info(f"Creating instance for pre-validated trial subscription {subscription_id}")
        
        # Create instance for trial subscription
        await _create_instance_for_subscription(
            customer_id=customer_external_key,
            subscription_id=subscription_id,
            plan_name=plan_name,
            billing_status="trial"
        )
        
        logger.info(f"Processed trial subscription creation for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling subscription creation: {e}")

async def handle_subscription_cancelled(payload: Dict[str, Any]):
    """Handle subscription cancellation webhook - database updates and notifications only"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Subscription cancellation scheduled: {subscription_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        logger.info(f"Subscription {subscription_id} scheduled for cancellation for customer {customer_external_key}")
        
        # TODO: Update subscription status in our database if we have one
        # TODO: Log cancellation event for analytics
        # TODO: Send cancellation confirmation email to customer
        # TODO: Update billing dashboard/UI status
        
        # NOTE: We DO NOT terminate instances here - that happens in ENTITLEMENT_CANCEL webhook
        # at the end of the billing period when the user's access actually ends
        
        logger.info(f"Processed subscription cancellation notification for {subscription_id}")
        
    except Exception as e:
        logger.error(f"Error handling subscription cancellation: {e}")

async def handle_entitlement_cancelled(payload: Dict[str, Any]):
    """Handle entitlement cancellation webhook - terminate instance when access ends"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Entitlement cancelled: {subscription_id} for account: {account_id}")
    
    try:
        # Find instance by subscription_id using our database lookup
        instance = await instance_client.get_instance_by_subscription_id(subscription_id)
        if not instance:
            logger.warning(f"No instance found for subscription {subscription_id} during entitlement cancellation")
            return
        
        instance_id = instance.get("id")
        logger.info(f"Found instance {instance_id} for cancelled entitlement {subscription_id}")
        
        # Terminate the instance since entitlement has ended
        try:
            await instance_client.terminate_instance(instance_id, "Subscription entitlement ended")
            logger.info(f"Successfully terminated instance {instance_id} for subscription {subscription_id}")
            
            # Get customer information for logging
            customer_external_key = await _get_customer_external_key_by_account_id(account_id)
            logger.info(f"Instance {instance_id} terminated for customer {customer_external_key} - subscription {subscription_id} entitlement ended")
            
        except Exception as instance_error:
            logger.error(f"Failed to terminate instance {instance_id} for subscription {subscription_id}: {instance_error}")
            # Don't raise - we want to continue processing other webhooks
        
        # TODO: Send service termination notification email
        # TODO: Trigger data backup before final cleanup
        # TODO: Clean up any additional resources
        
    except Exception as e:
        logger.error(f"Error handling entitlement cancellation for subscription {subscription_id}: {e}")

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

async def handle_invoice_payment_success(payload: Dict[str, Any]):
    """Handle invoice payment success - create instances for paid subscriptions"""
    invoice_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Invoice payment success for invoice: {invoice_id}, account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get subscription details from the invoice
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        invoice_details = await killbill.get_invoice_by_id(invoice_id)
        logger.info(f"Fetched invoice details for {invoice_id}: {invoice_details}")
        if not invoice_details or not invoice_details.get('items'):
            logger.warning(f"Could not get invoice details or no items found for invoice {invoice_id}")
            return
        # Log the invoice balance and amount for debugging
        logger.info(f"Invoice {invoice_id} amount: {invoice_details.get('amount')}, balance: {invoice_details.get('balance')}")
        logger.info(f"Invoice items: {invoice_details.get('items')}")
        import json
        logger.info(f"Full invoice details: {json.dumps(invoice_details, indent=2)}")
        # Ensure invoice is fully paid before proceeding
        if float(invoice_details.get('balance', 1)) != 0.0:
            logger.info(f"Invoice {invoice_id} is not fully paid (balance: {invoice_details.get('balance')}). Skipping instance creation.")
            return
            
        # Extract subscription ID from the first invoice item
        first_item = invoice_details['items'][0]
        subscription_id = first_item.get('subscriptionId')
        plan_name = first_item.get('planName', 'unknown')
        
        if not subscription_id:
            logger.warning(f"No subscription ID found in invoice {invoice_id}")
            return
            
        logger.info(f"Processing invoice for subscription {subscription_id} (plan: {plan_name})")
        
        # Get subscription details
        subscription_details = await killbill.get_subscription_by_id(subscription_id)
        if not subscription_details:
            logger.warning(f"Could not get subscription details for {subscription_id}")
            return
        
        # Only create instances for non-trial subscriptions
        if 'trial' in plan_name.lower():
            logger.info(f"Subscription {subscription_id} is trial - not creating instance on payment")
            return

        # Check if this is a reactivation subscription
        subscription_metadata = await killbill.get_subscription_metadata(subscription_id)
        target_instance_id = subscription_metadata.get("target_instance_id")
        is_reactivation = subscription_metadata.get("reactivation") == "true"
        
        # Handle reactivation payment
        if is_reactivation and target_instance_id:
            logger.info(f"Payment received for reactivation subscription {subscription_id}, restarting instance {target_instance_id}")
            
            try:
                result = await instance_client.restart_instance_with_new_subscription(
                    instance_id=target_instance_id,
                    subscription_id=subscription_id,
                    billing_status="paid"
                )
                
                if result.get("status") == "success":
                    logger.info(f"Successfully reactivated instance {target_instance_id} after payment for subscription {subscription_id}")
                else:
                    logger.error(f"Failed to reactivate instance {target_instance_id}: {result}")
                    
            except Exception as e:
                logger.error(f"Error reactivating instance {target_instance_id}: {e}")
                
            # ALWAYS return for reactivations - don't continue to existing_instance logic
            return  # Exit early - reactivation handled regardless of success/failure
        
        # SAFETY CHECK: Prevent duplicate instance creation for the same subscription
        # Skip this check for reactivations as they're handled above
        existing_instance = await instance_client.get_instance_by_subscription_id(subscription_id)
        if existing_instance and not is_reactivation:
            logger.warning(f"DUPLICATE PREVENTION: Instance {existing_instance.get('id')} already exists for subscription {subscription_id} - skipping creation to prevent duplication")
            
            # ALWAYS update billing status to "paid" when payment succeeds
            try:
                await instance_client.provision_instance(
                    instance_id=existing_instance['id'],
                    subscription_id=subscription_id,
                    billing_status="paid",
                    provisioning_trigger="invoice_payment_success_billing_update"
                )
                logger.info(f"Updated billing status to 'paid' for instance {existing_instance['id']} after payment success")
            except Exception as e:
                logger.error(f"Failed to update billing status to 'paid' for instance {existing_instance['id']}: {e}")
            
            # Additional provisioning if needed
            if existing_instance.get('provisioning_status') in ['pending']:
                logger.info(f"Triggering additional provisioning for existing instance {existing_instance.get('id')}")
                try:
                    await instance_client.provision_instance(
                        instance_id=existing_instance['id'],
                        subscription_id=subscription_id,
                        billing_status="paid",
                        provisioning_trigger="invoice_payment_success_provision"
                    )
                except Exception as e:
                    logger.error(f"Failed to trigger additional provisioning: {e}")
            else:
                logger.info(f"Existing instance {existing_instance.get('id')} is in status {existing_instance.get('provisioning_status')} - billing status updated, no additional provisioning needed")
            return
        
        # Create instance for this customer and subscription
        await _create_instance_for_subscription(customer_external_key, subscription_id, plan_name, billing_status="paid")
        
        logger.info(f"Processed invoice payment success for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling invoice payment success: {e}")

async def _create_instance_for_subscription(customer_id: str, subscription_id: str, plan_name: str, billing_status: str = "paid"):
    """Create instance for customer when subscription is created or paid"""
    try:
        logger.info(f"WEBHOOK FLOW: Creating instance for customer {customer_id}, subscription {subscription_id}, plan {plan_name}, billing_status {billing_status}")
        
        # CRITICAL: This function should ONLY create an instance record, NOT a new subscription
        # The subscription (subscription_id) already exists and was just paid for
        
        # Get custom instance configuration from subscription metadata
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        # Extract instance configuration from subscription custom fields
        subscription_metadata = await killbill.get_subscription_metadata(subscription_id)
        logger.info(f"Retrieved subscription metadata for {subscription_id}: {subscription_metadata}")
        
        # Check if this is for reactivating an existing instance
        target_instance_id = subscription_metadata.get("target_instance_id")
        if target_instance_id:
            logger.info(f"INSTANCE REACTIVATION: Found target_instance_id {target_instance_id} for subscription {subscription_id}")
            
            # Restart the existing instance with new subscription
            result = await instance_client.restart_instance_with_new_subscription(
                instance_id=target_instance_id,
                subscription_id=subscription_id,
                billing_status=billing_status
            )
            
            if result.get("status") == "success":
                logger.info(f"INSTANCE REACTIVATION: Successfully restarted instance {target_instance_id} with subscription {subscription_id}")
            else:
                logger.error(f"INSTANCE REACTIVATION: Failed to restart instance {target_instance_id}: {result}")
                
            return  # Exit early - we restarted existing instance
        
        logger.info(f"NEW INSTANCE CREATION: No target_instance_id found, creating new instance for subscription {subscription_id}")
        
        # Validate required metadata exists for new instance creation
        required_fields = ["instance_name", "instance_admin_email", "instance_admin_password", "instance_database_name"]
        missing_fields = [field for field in required_fields if not subscription_metadata.get(field)]
        
        if missing_fields:
            logger.error(f"Missing required metadata fields for subscription {subscription_id}: {missing_fields}")
            raise Exception(f"Cannot create instance - missing required configuration: {', '.join(missing_fields)}")
        
        # Create instance data with custom parameters from subscription metadata
        instance_data = {
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "name": subscription_metadata["instance_name"],
            "description": subscription_metadata.get("instance_description", f"Instance created for subscription {subscription_id}"),
            "admin_email": subscription_metadata["instance_admin_email"],
            "admin_password": subscription_metadata["instance_admin_password"],
            "database_name": subscription_metadata["instance_database_name"],
            "subdomain": subscription_metadata.get("instance_subdomain") or None,
            "odoo_version": subscription_metadata.get("instance_odoo_version", "17.0"),
            "instance_type": subscription_metadata.get("instance_type", "production"),
            "demo_data": subscription_metadata.get("instance_demo_data", "false").lower() == "true",
            "cpu_limit": float(subscription_metadata.get("instance_cpu_limit", "1.0")),
            "memory_limit": subscription_metadata.get("instance_memory_limit", "1G"),
            "storage_limit": subscription_metadata.get("instance_storage_limit", "10G"),
            "custom_addons": subscription_metadata.get("instance_custom_addons", "").split(",") if subscription_metadata.get("instance_custom_addons") else [],
            "billing_status": billing_status,
            "provisioning_status": "pending"
        }
        
        # Remove empty subdomain if not provided
        if not instance_data["subdomain"]:
            instance_data["subdomain"] = None
            
        logger.info(f"WEBHOOK FLOW: Using custom instance configuration for subscription {subscription_id}: {instance_data}")
        
        # CRITICAL: Call instance service to create instance record ONLY
        # This should NOT trigger any new subscription creation since subscription_id is provided
        logger.info(f"WEBHOOK FLOW: Calling instance service to create instance with existing subscription {subscription_id}")
        created_instance = await instance_client.create_instance_with_subscription(instance_data)
        
        if created_instance and created_instance.get('id'):
            instance_id = created_instance['id']
            logger.info(f"Created instance {instance_id} for customer {customer_id}")
            
            # Trigger instance provisioning
            provisioning_trigger = "invoice_payment_success" if billing_status == "paid" else "subscription_created"
            await instance_client.provision_instance(
                instance_id=instance_id,
                subscription_id=subscription_id,
                billing_status=billing_status,
                provisioning_trigger=provisioning_trigger
            )
            
            logger.info(f"Triggered provisioning for instance {instance_id}")
        else:
            logger.error(f"Failed to create instance for customer {customer_id}")
            
    except Exception as e:
        logger.error(f"Error creating instance for subscription {subscription_id}: {e}")


async def handle_subscription_phase_change(payload: Dict[str, Any]):
    """Handle subscription phase change webhook - manage trial-to-paid transitions"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Subscription phase change: {subscription_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get subscription details to understand the phase change
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        subscription_details = await killbill.get_subscription_by_id(subscription_id)
        if not subscription_details:
            logger.warning(f"Could not get subscription details for {subscription_id}")
            return
        
        current_phase = subscription_details.get('phaseType', 'UNKNOWN')
        plan_name = subscription_details.get('planName', 'unknown')
        
        logger.info(f"Subscription {subscription_id} phase changed to: {current_phase} (plan: {plan_name})")
        
        # Handle trial-to-paid transition
        if current_phase == 'EVERGREEN':
            # Find existing trial instance for this subscription
            instance = await instance_client.get_instance_by_subscription_id(subscription_id)
            if not instance:
                logger.warning(f"No instance found for subscription {subscription_id} during phase change")
                return
            
            instance_id = instance.get('id')
            current_billing_status = instance.get('billing_status')
            
            logger.info(f"Found instance {instance_id} with billing status '{current_billing_status}' for subscription {subscription_id}")
            
            # Update instance billing status from trial to pending payment
            if current_billing_status == 'trial':
                logger.info(f"Updating instance {instance_id} billing status from 'trial' to 'payment_required'")
                
                # Update instance billing status to indicate payment is expected
                await instance_client.update_instance_billing_status(
                    instance_id=instance_id,
                    billing_status="payment_required",
                    reason="Trial expired - transitioning to paid plan"
                )
                
                logger.info(f"Updated instance {instance_id} to payment_required status for customer {customer_external_key}")
            else:
                logger.info(f"Instance {instance_id} already has billing status '{current_billing_status}' - no update needed")
        
        # Log phase change for analytics
        logger.info(f"Processed phase change for subscription {subscription_id}: customer {customer_external_key}, phase {current_phase}")
        
    except Exception as e:
        logger.error(f"Error handling subscription phase change for {subscription_id}: {e}")

async def handle_subscription_expired(payload: Dict[str, Any]):
    """Handle subscription expiration webhook - terminate instances when subscription expires"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.info(f"Subscription expired: {subscription_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Find instance associated with expired subscription
        instance = await instance_client.get_instance_by_subscription_id(subscription_id)
        if not instance:
            logger.warning(f"No instance found for expired subscription {subscription_id}")
            return
        
        instance_id = instance.get('id')
        current_status = instance.get('status')
        billing_status = instance.get('billing_status')
        
        logger.info(f"Found instance {instance_id} (status: {current_status}, billing: {billing_status}) for expired subscription {subscription_id}")
        
        # Terminate instance since subscription has expired
        if current_status not in ['terminated', 'terminating']:
            logger.info(f"Terminating instance {instance_id} due to subscription expiration")
            
            await instance_client.terminate_instance(
                instance_id=instance_id,
                reason="Subscription expired - no payment received"
            )
            
            logger.info(f"Terminated instance {instance_id} for customer {customer_external_key} - subscription {subscription_id} expired")
        else:
            logger.info(f"Instance {instance_id} already in terminal state ({current_status}) - no action needed")
        
        # TODO: Send expiration notification email to customer
        # TODO: Log expiration event for analytics and retention analysis
        
        logger.info(f"Processed subscription expiration for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling subscription expiration for {subscription_id}: {e}")

async def handle_invoice_overdue(payload: Dict[str, Any]):
    """Handle overdue invoice webhook - suspend instances with grace period"""
    invoice_id = payload.get('objectId')
    account_id = payload.get('accountId')
    
    logger.warning(f"Invoice overdue: {invoice_id} for account: {account_id}")
    
    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return
        
        # Get invoice details to find associated subscription
        killbill = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
        
        invoice_details = await killbill.get_invoice_by_id(invoice_id)
        if not invoice_details or not invoice_details.get('items'):
            logger.warning(f"Could not get invoice details for overdue invoice {invoice_id}")
            return
        
        # Extract subscription ID from invoice items
        subscription_ids = set()
        for item in invoice_details.get('items', []):
            if item.get('subscriptionId'):
                subscription_ids.add(item['subscriptionId'])
        
        if not subscription_ids:
            logger.warning(f"No subscription IDs found in overdue invoice {invoice_id}")
            return
        
        logger.warning(f"Processing overdue invoice {invoice_id} affecting subscriptions: {list(subscription_ids)}")
        
        # Suspend instances associated with overdue subscriptions
        suspended_count = 0
        for subscription_id in subscription_ids:
            try:
                instance = await instance_client.get_instance_by_subscription_id(subscription_id)
                if not instance:
                    logger.warning(f"No instance found for subscription {subscription_id} in overdue invoice")
                    continue
                
                instance_id = instance.get('id')
                current_status = instance.get('status')
                
                # Only suspend running instances
                if current_status in ['running', 'stopped', 'starting', 'stopping']:
                    logger.warning(f"Suspending instance {instance_id} due to overdue invoice {invoice_id}")
                    
                    result = await instance_client.suspend_instance(
                        instance_id=instance_id,
                        reason=f"Invoice {invoice_id} is overdue - payment required"
                    )
                    
                    if result.get('status') == 'success':
                        suspended_count += 1
                        logger.warning(f"Suspended instance {instance_id} for overdue payment")
                    else:
                        logger.error(f"Failed to suspend instance {instance_id}: {result}")
                else:
                    logger.info(f"Instance {instance_id} status is {current_status} - no suspension needed")
                    
            except Exception as instance_error:
                logger.error(f"Error processing subscription {subscription_id} for overdue invoice: {instance_error}")
        
        logger.warning(f"Processed overdue invoice {invoice_id} for customer {customer_external_key}: suspended {suspended_count} instances")
        
        # TODO: Send overdue payment notification email
        # TODO: Implement configurable grace period before suspension
        # TODO: Set up automatic retry for payment collection
        
    except Exception as e:
        logger.error(f"Error handling overdue invoice {invoice_id}: {e}")

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
