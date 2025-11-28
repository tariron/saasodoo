"""
Billing Service - Webhooks Routes
Handles KillBill webhook events
"""

from fastapi import APIRouter, Request, HTTPException, Response
import logging
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from urllib.parse import parse_qs
from app.utils.instance_client import instance_client
from app.utils.killbill_client import KillBillClient
from app.utils.paynow_client import get_paynow_client
from app.utils.database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

# Module-level singleton KillBill client
def _get_killbill_client() -> KillBillClient:
    """Get or create singleton KillBill client instance"""
    if not hasattr(_get_killbill_client, '_instance'):
        _get_killbill_client._instance = KillBillClient(
            base_url=os.getenv('KILLBILL_URL', 'http://killbill:8080'),
            api_key=os.getenv('KILLBILL_API_KEY', 'test-key'),
            api_secret=os.getenv('KILLBILL_API_SECRET', 'test-secret'),
            username=os.getenv('KILLBILL_USERNAME', 'admin'),
            password=os.getenv('KILLBILL_PASSWORD', 'password')
        )
    return _get_killbill_client._instance

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
        if event_type == "INVOICE_PAYMENT_SUCCESS":
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
        elif event_type == "INVOICE_PAYMENT_FAILED":
            await handle_invoice_payment_failed(payload)
        # DISABLED: Upgrades are handled in INVOICE_PAYMENT_SUCCESS only (prevents premature resource application before payment)
        # elif event_type == "SUBSCRIPTION_CHANGE":
        #     await handle_subscription_change(payload)
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
        killbill = _get_killbill_client()
        
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
    """Handle subscription cancellation webhook - check actionType to determine when to terminate"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')
    metadata_str = payload.get('metaData')

    # Parse metadata to check actionType
    action_type = None
    if metadata_str:
        try:
            import json
            metadata = json.loads(metadata_str)
            action_type = metadata.get('actionType')
            logger.info(f"Subscription cancel actionType: {action_type} for {subscription_id}")
        except Exception as parse_error:
            logger.warning(f"Could not parse metaData for subscription {subscription_id}: {parse_error}")

    logger.info(f"Subscription cancellation: {subscription_id} for account: {account_id}, actionType: {action_type}")

    try:
        # Initialize KillBill client
        killbill = _get_killbill_client()

        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return

        if action_type == "REQUESTED":
            # Cancellation requested but not yet effective - send notification only
            logger.info(f"Subscription {subscription_id} cancellation REQUESTED for customer {customer_external_key}")

            # Send subscription cancellation confirmation email
            try:
                from ..utils.notification_client import send_subscription_cancelled_email

                # Get customer info and subscription details
                customer_info = await _get_customer_info_by_external_key(customer_external_key)
                subscription_info = await _get_subscription_info(subscription_id)

                if customer_info and subscription_info:
                    await send_subscription_cancelled_email(
                        email=customer_info.get('email', ''),
                        first_name=customer_info.get('first_name', ''),
                        subscription_name=subscription_info.get('planName', f'Subscription {subscription_id}'),
                        end_date=subscription_info.get('chargedThroughDate', 'end of current billing period')
                    )
                    logger.info(f"✅ Sent subscription cancellation email to {customer_info.get('email')}")
                else:
                    logger.warning(f"Could not send cancellation email - missing customer or subscription info")
            except Exception as email_error:
                logger.error(f"❌ Failed to send subscription cancellation email: {email_error}")

            logger.info(f"Processed subscription cancellation notification for {subscription_id}")

        elif action_type == "EFFECTIVE":
            # Cancellation is now effective - terminate the instance
            logger.info(f"Subscription {subscription_id} cancellation EFFECTIVE for customer {customer_external_key} - terminating instance")

            # Find instance by subscription_id
            instance = await instance_client.get_instance_by_subscription_id(subscription_id)
            if not instance:
                logger.warning(f"No instance found for subscription {subscription_id} during effective cancellation")
                return

            instance_id = instance.get("id")
            logger.info(f"Found instance {instance_id} for effective cancellation of subscription {subscription_id}")

            # Terminate the instance since billing period has ended
            try:
                await instance_client.terminate_instance(instance_id, "Subscription billing period ended")
                logger.info(f"Successfully terminated instance {instance_id} for subscription {subscription_id}")

                # Write off all unpaid invoices for this cancelled subscription (debt forgiven)
                unpaid_invoices = await killbill.get_unpaid_invoices_by_subscription(subscription_id)
                written_off_count = 0
                for invoice in unpaid_invoices:
                    invoice_id = invoice.get('invoiceId')
                    written_off = await killbill.write_off_invoice(invoice_id, "Subscription cancelled - debt forgiven")
                    if written_off:
                        written_off_count += 1
                        logger.info(f"Wrote off unpaid invoice {invoice_id} for cancelled subscription {subscription_id}")

                # Update instance billing_status to "paid" to indicate billing is resolved/settled
                # This enables the reactivation button in the frontend
                if written_off_count > 0:
                    await instance_client.provision_instance(
                        instance_id=instance_id,
                        subscription_id=subscription_id,
                        billing_status="paid",
                        provisioning_trigger="invoice_write_off_billing_resolved"
                    )
                    logger.info(f"Updated instance {instance_id} billing_status to 'paid' after writing off {written_off_count} invoice(s) - reactivation now enabled")

                logger.info(f"Instance {instance_id} terminated for customer {customer_external_key} - subscription {subscription_id} billing ended, {written_off_count} invoice(s) written off")

            except Exception as instance_error:
                logger.error(f"Failed to terminate instance {instance_id} for subscription {subscription_id}: {instance_error}")
                # Don't raise - we want to continue processing other webhooks

            # Send service termination notification email
            try:
                from ..utils.notification_client import send_service_terminated_email

                # Get customer info for the email
                customer_info = await _get_customer_info_by_external_key(customer_external_key)
                if customer_info:
                    await send_service_terminated_email(
                        email=customer_info.get('email', ''),
                        first_name=customer_info.get('first_name', ''),
                        service_name=f'Odoo Instance {instance_id}',
                        backup_info="Your data has been backed up and will be available for 30 days. Contact support to restore your data."
                    )
                    logger.info(f"✅ Sent service termination email to {customer_info.get('email')}")
                else:
                    logger.warning(f"Could not send termination email - customer info not found for {customer_external_key}")
            except Exception as email_error:
                logger.error(f"❌ Failed to send service termination email: {email_error}")

            logger.info(f"Processed effective subscription cancellation for {subscription_id}")
        else:
            # Unknown or missing actionType - log but don't terminate
            logger.warning(f"Subscription cancellation with unknown actionType '{action_type}' for {subscription_id}")

    except Exception as e:
        logger.error(f"Error handling subscription cancellation: {e}")

async def handle_entitlement_cancelled(payload: Dict[str, Any]):
    """Handle entitlement cancellation webhook - log event only, termination happens in SUBSCRIPTION_CANCEL with actionType=EFFECTIVE"""
    subscription_id = payload.get('objectId')
    account_id = payload.get('accountId')

    logger.info(f"Entitlement cancelled event received: {subscription_id} for account: {account_id}")
    logger.info(f"Instance termination will occur when SUBSCRIPTION_CANCEL webhook fires with actionType=EFFECTIVE")

    # NOTE: We no longer terminate instances here. With END_OF_TERM cancel policy,
    # ENTITLEMENT_CANCEL fires when cancellation is requested, but the instance should
    # remain active until the billing period ends. Termination now happens in
    # handle_subscription_cancelled when actionType == "EFFECTIVE"

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
        
        # Send invoice notification email to customer
        try:
            from ..utils.notification_client import send_invoice_created_email
            
            # Get customer info and invoice details
            customer_info = await _get_customer_info_by_external_key(customer_external_key)
            invoice_info = await _get_invoice_info(invoice_id)
            
            if customer_info and invoice_info:
                await send_invoice_created_email(
                    email=customer_info.get('email', ''),
                    first_name=customer_info.get('first_name', ''),
                    invoice_number=invoice_info.get('invoiceNumber', invoice_id),
                    amount_due=str(invoice_info.get('balance', 0)),
                    due_date=invoice_info.get('targetDate', 'upon receipt'),
                    payment_url=f"https://billing.saasodoo.local/invoices/{invoice_id}/pay"
                )
                logger.info(f"✅ Sent invoice notification email to {customer_info.get('email')}")
            else:
                logger.warning(f"Could not send invoice email - missing customer or invoice info")
        except Exception as email_error:
            logger.error(f"❌ Failed to send invoice notification email: {email_error}")
        
        # TODO: For overdue invoices, could trigger collection workflows
        
        logger.info(f"Processed invoice creation for customer {customer_external_key}")
        
    except Exception as e:
        logger.error(f"Error handling invoice creation: {e}")

async def handle_invoice_payment_failed(payload: Dict[str, Any]):
    """Handle invoice payment failure - suspend instances due to non-payment"""
    invoice_id = payload.get('objectId')
    account_id = payload.get('accountId')

    logger.warning(f"Invoice payment failed: {invoice_id} for account: {account_id}")

    try:
        # Get customer information from KillBill
        customer_external_key = await _get_customer_external_key_by_account_id(account_id)
        if not customer_external_key:
            logger.warning(f"Could not find customer for account {account_id}")
            return

        # Get invoice details to find associated subscriptions
        killbill = _get_killbill_client()

        invoice_details = await killbill.get_invoice_by_id(invoice_id)
        if not invoice_details or not invoice_details.get('items'):
            logger.warning(f"Could not get invoice details for failed payment invoice {invoice_id}")
            return

        # Extract subscription IDs from invoice items
        subscription_ids = set()
        for item in invoice_details.get('items', []):
            sub_id = item.get('subscriptionId')
            if sub_id:
                subscription_ids.add(sub_id)

        if not subscription_ids:
            logger.warning(f"No subscriptions found in failed payment invoice {invoice_id}")
            return

        logger.info(f"Found {len(subscription_ids)} subscriptions in failed payment invoice {invoice_id}: {subscription_ids}")

        # Suspend instances for each subscription
        for subscription_id in subscription_ids:
            try:
                # Find instance by subscription_id
                instance = await instance_client.get_instance_by_subscription_id(subscription_id)
                if not instance:
                    logger.warning(f"No instance found for subscription {subscription_id} with failed payment")
                    continue

                instance_id = instance.get("id")
                instance_status = instance.get("status")
                logger.info(f"Found instance {instance_id} (status: {instance_status}) for subscription {subscription_id} with failed payment")

                # Only suspend if instance is running
                ##if instance_status == "running":
                    # Suspend the instance
                await instance_client.suspend_instance(instance_id, f"Payment failed for invoice {invoice_id}")
                logger.info(f"Successfully suspended instance {instance_id} for subscription {subscription_id} due to payment failure")
                ##else:
                ##    logger.info(f"Instance {instance_id} not running (status: {instance_status}), skipping suspension")

            except Exception as instance_error:
                logger.error(f"Failed to suspend instance for subscription {subscription_id}: {instance_error}")
                continue

        # Send payment failure notification email
        try:
            from ..utils.notification_client import send_payment_failure_email

            # Get customer info and invoice details
            customer_info = await _get_customer_info_by_external_key(customer_external_key)

            if customer_info:
                await send_payment_failure_email(
                    email=customer_info.get('email', ''),
                    first_name=customer_info.get('first_name', ''),
                    amount_due=str(invoice_details.get('balance', 0)),
                    payment_method_url=f"https://billing.saasodoo.local/invoices/{invoice_id}/pay"
                )
                logger.info(f"✅ Sent payment failure email to {customer_info.get('email')}")
            else:
                logger.warning(f"Could not send payment failed email - customer info not found for {customer_external_key}")
        except Exception as email_error:
            logger.error(f"❌ Failed to send payment failed notification email: {email_error}")

        logger.info(f"Processed invoice payment failure for {len(subscription_ids)} subscriptions")

    except Exception as e:
        logger.error(f"Error handling invoice payment failure: {e}")

# DISABLED: This function caused premature resource upgrades before payment was received
# Upgrades are now handled exclusively in handle_invoice_payment_success() webhook
# Keeping this code commented for reference/audit purposes
#
# async def handle_subscription_change(payload: Dict[str, Any]):
#     """Handle subscription change webhook - upgrade/downgrade plans with live resource updates"""
#     subscription_id = payload.get('objectId')
#     account_id = payload.get('accountId')
#     metadata_str = payload.get('metaData')
#
#     # Parse metadata to check actionType
#     action_type = None
#     if metadata_str:
#         try:
#             import json
#             metadata = json.loads(metadata_str)
#             action_type = metadata.get('actionType')
#             logger.info(f"Subscription change actionType: {action_type} for {subscription_id}")
#         except Exception as parse_error:
#             logger.warning(f"Could not parse metaData for subscription {subscription_id}: {parse_error}")
#
#     # Only process EFFECTIVE changes (skip REQUESTED)
#     if action_type != "EFFECTIVE":
#         logger.info(f"Skipping subscription change with actionType '{action_type}' for {subscription_id} (waiting for EFFECTIVE)")
#         return
#
#     logger.info(f"Processing EFFECTIVE subscription change: {subscription_id} for account: {account_id}")
#
#     try:
#         # Get KillBill client
#         killbill = _get_killbill_client()
#
#         # Get subscription details to find new plan
#         subscription = await killbill.get_subscription_by_id(subscription_id)
#         if not subscription:
#             logger.warning(f"Could not get subscription details for {subscription_id}")
#             return
#
#         new_plan_name = subscription.get('planName')
#         logger.info(f"Subscription {subscription_id} changed to plan: {new_plan_name}")
#
#         # Get plan resources from database
#         from ..utils.database import get_plan_entitlements
#
#         entitlements = await get_plan_entitlements(new_plan_name)
#         if not entitlements:
#             logger.error(f"Plan entitlements not found for plan: {new_plan_name}")
#             return
#
#         cpu_limit = float(entitlements['cpu_limit'])
#         memory_limit = entitlements['memory_limit']
#         storage_limit = entitlements['storage_limit']
#
#         logger.info(f"New plan resources: {cpu_limit} CPU, {memory_limit} RAM, {storage_limit} storage")
#
#         # Find instance by subscription_id
#         instance = await instance_client.get_instance_by_subscription_id(subscription_id)
#         if not instance:
#             logger.warning(f"No instance found for subscription {subscription_id} during plan change")
#             return
#
#         instance_id = instance.get('id')
#         instance_status = instance.get('status')
#         old_cpu = instance.get('cpu_limit')
#         old_memory = instance.get('memory_limit')
#         old_storage = instance.get('storage_limit')
#
#         logger.info(f"Found instance {instance_id} (status: {instance_status}) for subscription {subscription_id}")
#         logger.info(f"Old resources: {old_cpu} CPU, {old_memory} RAM, {old_storage} storage")
#
#         # Update instance database record
#         await instance_client.update_instance_resources(instance_id, cpu_limit, memory_limit, storage_limit)
#         logger.info(f"Updated instance {instance_id} database record with new resource limits")
#
#         # Apply live resource updates to running container
#         if instance_status == 'running':
#             try:
#                 await instance_client.apply_resource_upgrade(instance_id)
#                 logger.info(f"Successfully applied live resource upgrade to instance {instance_id}")
#             except Exception as upgrade_error:
#                 logger.error(f"Failed to apply live resource upgrade to instance {instance_id}: {upgrade_error}")
#                 # Don't fail the whole operation - DB is updated, container can be restarted manually
#         else:
#             logger.info(f"Instance {instance_id} not running (status: {instance_status}), skipping live container update")
#
#         # Get customer information for notification
#         customer_external_key = await _get_customer_external_key_by_account_id(account_id)
#         if not customer_external_key:
#             logger.warning(f"Could not find customer for account {account_id}")
#             return
#
#         # Send upgrade notification email
#         try:
#             from ..utils.notification_client import get_notification_client
#
#             customer_info = await _get_customer_info_by_external_key(customer_external_key)
#             if customer_info:
#                 client = get_notification_client()
#                 await client.send_template_email(
#                     to_emails=[customer_info.get('email', '')],
#                     template_name="subscription_upgraded",
#                     template_variables={
#                         "first_name": customer_info.get('first_name', ''),
#                         "new_plan": new_plan_name,
#                         "cpu_limit": str(cpu_limit),
#                         "memory_limit": memory_limit,
#                         "storage_limit": storage_limit,
#                         "old_cpu": str(old_cpu),
#                         "old_memory": old_memory,
#                         "old_storage": old_storage
#                     },
#                     tags=["billing", "subscription", "upgrade"]
#                 )
#                 logger.info(f"✅ Sent subscription upgrade email to {customer_info.get('email')}")
#             else:
#                 logger.warning(f"Could not send upgrade email - customer info not found for {customer_external_key}")
#         except Exception as email_error:
#             logger.error(f"❌ Failed to send subscription upgrade email: {email_error}")
#
#         logger.info(f"Completed subscription change processing for {subscription_id}")
#
#     except Exception as e:
#         logger.error(f"Error handling subscription change for {subscription_id}: {e}")

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
        killbill = _get_killbill_client()
        
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

        # Extract all subscription IDs from invoice items
        subscription_ids = []
        for item in invoice_details.get('items', []):
            sub_id = item.get('subscriptionId')
            if sub_id and sub_id not in subscription_ids:
                subscription_ids.append(sub_id)
                logger.info(f"Found subscription {sub_id} (plan: {item.get('planName')}) in invoice {invoice_id}")

        if not subscription_ids:
            logger.warning(f"No subscription IDs found in invoice {invoice_id}")
            return

        logger.info(f"Processing invoice payment success for {len(subscription_ids)} subscriptions in invoice {invoice_id}")

        # Process each subscription in the invoice
        for subscription_id in subscription_ids:
            # Get the plan name for this subscription from the invoice items
            plan_name = next((item.get('planName', 'unknown') for item in invoice_details['items']
                            if item.get('subscriptionId') == subscription_id), 'unknown')

            logger.info(f"Processing invoice for subscription {subscription_id} (plan: {plan_name})")

            try:
                # Get subscription details
                subscription_details = await killbill.get_subscription_by_id(subscription_id)
                if not subscription_details:
                    logger.warning(f"Could not get subscription details for {subscription_id}")
                    continue


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

                    # Send invoice paid email for reactivation
                    try:
                        from ..utils.notification_client import get_notification_client

                        customer_info = await _get_customer_info_by_external_key(customer_external_key)
                        if customer_info:
                            from datetime import datetime
                            payment_date = datetime.utcnow().strftime("%B %d, %Y")

                            client = get_notification_client()
                            await client.send_template_email(
                                to_emails=[customer_info.get('email', '')],
                                template_name="invoice_paid",
                                template_variables={
                                    "first_name": customer_info.get('first_name', ''),
                                    "invoice_number": invoice_details.get('invoiceNumber', invoice_id),
                                    "amount_paid": str(invoice_details.get('amount', '0.00')),
                                    "payment_date": payment_date
                                },
                                tags=["billing", "invoice", "paid", "reactivation"]
                            )
                            logger.info(f"✅ Sent reactivation invoice paid email to {customer_info.get('email')}")
                    except Exception as email_error:
                        logger.error(f"❌ Failed to send reactivation invoice paid email: {email_error}")

                    # Continue to next subscription - reactivation handled
                    continue

                # SAFETY CHECK: Prevent duplicate instance creation for the same subscription
                # SKIP ENTIRELY for reactivations - they are handled above with restart_instance_with_new_subscription
                if is_reactivation:
                    logger.info(f"Skipping existing instance logic for reactivation subscription {subscription_id}")
                    continue

                existing_instance = await instance_client.get_instance_by_subscription_id(subscription_id)
                if existing_instance:
                    logger.warning(f"DUPLICATE PREVENTION: Instance {existing_instance.get('id')} already exists for subscription {subscription_id} - skipping creation to prevent duplication")

                    # UPGRADE DETECTION: Check if this payment is for an upgrade
                    instance_id = existing_instance.get('id')
                    current_cpu = existing_instance.get('cpu_limit')
                    current_memory = existing_instance.get('memory_limit')
                    current_storage = existing_instance.get('storage_limit')

                    logger.info(f"Checking for upgrade: current resources={current_cpu}CPU/{current_memory}/{current_storage}, invoice plan={plan_name}")

                    # Get new plan entitlements from database
                    from ..utils.database import get_plan_entitlements
                    new_entitlements = await get_plan_entitlements(plan_name)

                    if new_entitlements:
                        new_cpu = float(new_entitlements['cpu_limit'])
                        new_memory = new_entitlements['memory_limit']
                        new_storage = new_entitlements['storage_limit']

                        # Detect upgrade if resources changed from current instance resources
                        # We compare current instance DB resources with new plan entitlements
                        # If they're different, this is an upgrade payment
                        is_upgrade = (
                            new_cpu != current_cpu or
                            new_memory != current_memory or
                            new_storage != current_storage
                        )

                        if is_upgrade:
                            logger.info(
                                f"🚀 UPGRADE DETECTED for instance {instance_id}: "
                                f"New plan: {plan_name} | "
                                f"CPU: {current_cpu} → {new_cpu}, "
                                f"Memory: {current_memory} → {new_memory}, "
                                f"Storage: {current_storage} → {new_storage}"
                            )

                            # Update instance database with new resources
                            try:
                                await instance_client.update_instance_resources(
                                    instance_id=instance_id,
                                    cpu_limit=new_cpu,
                                    memory_limit=new_memory,
                                    storage_limit=new_storage
                                )
                                logger.info(f"✅ Updated instance {instance_id} database with new plan resources")
                            except Exception as db_error:
                                logger.error(f"❌ Failed to update instance DB for upgrade: {db_error}")

                            # Apply live resource upgrade if instance is running
                            instance_status = existing_instance.get('status')
                            if instance_status == 'running':
                                try:
                                    # Fixed: apply_resource_upgrade() only takes instance_id
                                    # It reads resource limits from the database (already updated above)
                                    await instance_client.apply_resource_upgrade(instance_id)
                                    logger.info(f"✅ Applied live resource upgrade to running instance {instance_id}")
                                except Exception as upgrade_error:
                                    logger.error(f"❌ Failed to apply live upgrade: {upgrade_error}")
                            else:
                                logger.info(f"Instance {instance_id} not running ({instance_status}) - resources will apply on next start")

                            # Send upgrade completion email
                            try:
                                from ..utils.notification_client import get_notification_client
                                customer_info = await _get_customer_info_by_external_key(customer_external_key)

                                if customer_info:
                                    from datetime import datetime
                                    upgrade_date = datetime.utcnow().strftime("%B %d, %Y")

                                    client = get_notification_client()
                                    await client.send_template_email(
                                        to_emails=[customer_info.get('email', '')],
                                        template_name="subscription_upgrade",
                                        template_variables={
                                            "first_name": customer_info.get('first_name', ''),
                                            "old_cpu": str(current_cpu),
                                            "old_memory": current_memory,
                                            "old_storage": current_storage,
                                            "new_plan": plan_name,
                                            "upgrade_date": upgrade_date,
                                            "cpu_limit": str(new_cpu),
                                            "memory_limit": new_memory,
                                            "storage_limit": new_storage
                                        },
                                        tags=["billing", "upgrade", "subscription"]
                                    )
                                    logger.info(f"✅ Sent upgrade completion email to {customer_info.get('email')}")
                            except Exception as email_error:
                                logger.error(f"❌ Failed to send upgrade email: {email_error}")

                            # Continue to next subscription - upgrade handled
                            continue

                    # ALWAYS update billing status to "paid" when payment succeeds
                    try:
                        await instance_client.provision_instance(
                            instance_id=existing_instance['id'],
                            subscription_id=subscription_id,
                            billing_status="paid",
                            provisioning_trigger="invoice_payment_success_billing_update"
                        )
                        logger.info(f"Updated billing status to 'paid' for instance {existing_instance['id']} after payment success")

                        # Start the instance after successful payment
                        await instance_client.start_instance(
                            instance_id=existing_instance['id'],
                            reason="Payment successful - starting instance"
                        )
                        logger.info(f"Started instance {existing_instance['id']} after payment success")
                    except Exception as e:
                        logger.error(f"Failed to update billing status or start instance {existing_instance['id']}: {e}")

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

                    # Continue to next subscription
                    continue

                # Create instance for this customer and subscription (only if no existing instance)
                await _create_instance_for_subscription(customer_external_key, subscription_id, plan_name, billing_status="paid")
                logger.info(f"Processed invoice payment success for subscription {subscription_id}")

            except Exception as sub_error:
                logger.error(f"Error processing subscription {subscription_id} from invoice {invoice_id}: {sub_error}")
                continue

        # Send single invoice paid email after processing all subscriptions
        logger.info(f"Completed processing invoice payment success for {len(subscription_ids)} subscriptions")
        
        # Send invoice paid notification email
        try:
            from ..utils.notification_client import get_notification_client
            
            # Get customer info for the email
            customer_info = await _get_customer_info_by_external_key(customer_external_key)
            if customer_info:
                # Format payment date
                from datetime import datetime
                payment_date = datetime.utcnow().strftime("%B %d, %Y")
                
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[customer_info.get('email', '')],
                    template_name="invoice_paid",
                    template_variables={
                        "first_name": customer_info.get('first_name', ''),
                        "invoice_number": invoice_details.get('invoiceNumber', invoice_id),
                        "amount_paid": str(invoice_details.get('amount', '0.00')),
                        "payment_date": payment_date
                    },
                    tags=["billing", "invoice", "paid"]
                )
                logger.info(f"✅ Sent invoice paid email to {customer_info.get('email')}")
            else:
                logger.warning(f"Could not send invoice paid email - customer info not found for {customer_external_key}")
        except Exception as email_error:
            logger.error(f"❌ Failed to send invoice paid email: {email_error}")
        
    except Exception as e:
        logger.error(f"Error handling invoice payment success: {e}")

async def _create_instance_for_subscription(customer_id: str, subscription_id: str, plan_name: str, billing_status: str = "paid"):
    """Create instance for customer when subscription is created or paid"""
    try:
        logger.info(f"WEBHOOK FLOW: Creating instance for customer {customer_id}, subscription {subscription_id}, plan {plan_name}, billing_status {billing_status}")
        
        # CRITICAL: This function should ONLY create an instance record, NOT a new subscription
        # The subscription (subscription_id) already exists and was just paid for
        
        # Get custom instance configuration from subscription metadata
        killbill = _get_killbill_client()
        
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
        required_fields = ["instance_name", "instance_admin_email", "instance_database_name"]
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
        import traceback
        logger.error(f"Error creating instance for subscription {subscription_id}: {e}",
                     traceback=traceback.format_exc())

        # Send failure email to customer
        try:
            from ..utils.notification_client import get_notification_client

            # Get customer email from subscription metadata
            admin_email = subscription_metadata.get("instance_admin_email")
            instance_name = subscription_metadata.get("instance_name", "your instance")

            if admin_email:
                client = get_notification_client()
                await client.send_template_email(
                    template_name="instance_creation_failed",
                    recipient_email=admin_email,
                    context={
                        "instance_name": instance_name,
                        "subscription_id": subscription_id,
                        "error_reason": str(e)[:200],  # Truncate long errors
                        "support_url": f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
                    }
                )
                logger.info(f"Sent instance creation failure email to {admin_email}")
            else:
                logger.warning(f"Could not send failure email - no admin email in subscription metadata")
        except Exception as email_error:
            logger.error(f"Failed to send instance creation failure email: {email_error}")


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
        killbill = _get_killbill_client()
        
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
                await instance_client.provision_instance(
                    instance_id=instance_id,
                    subscription_id=subscription_id,
                    billing_status="payment_required",
                    provisioning_trigger="trial_expired_billing_update"
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
        
        # Send subscription expiration notification email
        try:
            from ..utils.notification_client import get_notification_client
            
            # Get customer info and subscription details
            customer_info = await _get_customer_info_by_external_key(customer_external_key)
            subscription_info = await _get_subscription_info(subscription_id)
            
            if customer_info and subscription_info:
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[customer_info.get('email', '')],
                    template_name="subscription_expired",
                    template_variables={
                        "first_name": customer_info.get('first_name', ''),
                        "subscription_name": subscription_info.get('planName', f'Subscription {subscription_id}'),
                        "service_name": f'Odoo Instance {instance_id}'
                    },
                    tags=["billing", "subscription", "expiration"]
                )
                logger.info(f"✅ Sent subscription expiration email to {customer_info.get('email')}")
            else:
                logger.warning(f"Could not send expiration email - missing customer or subscription info")
        except Exception as email_error:
            logger.error(f"❌ Failed to send subscription expiration email: {email_error}")
        
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
        killbill = _get_killbill_client()
        
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
        
        # Send overdue payment notification email
        try:
            from ..utils.notification_client import get_notification_client
            
            # Get customer info and invoice details
            customer_info = await _get_customer_info_by_external_key(customer_external_key)
            invoice_info = await _get_invoice_info(invoice_id)
            
            if customer_info and invoice_info:
                # Calculate days overdue (simplified calculation)
                from datetime import datetime, timedelta
                target_date = invoice_info.get('targetDate')
                days_overdue = 7  # Default fallback
                
                if target_date:
                    try:
                        # Assume ISO format date string
                        target_dt = datetime.fromisoformat(target_date.replace('Z', '+00:00'))
                        days_overdue = max(0, (datetime.now() - target_dt).days)
                    except:
                        pass  # Use default
                
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[customer_info.get('email', '')],
                    template_name="overdue_payment",
                    template_variables={
                        "first_name": customer_info.get('first_name', ''),
                        "invoice_number": invoice_info.get('invoiceNumber', invoice_id),
                        "amount_due": str(invoice_info.get('balance', 0)),
                        "days_overdue": str(days_overdue),
                        "payment_url": f"https://billing.saasodoo.local/invoices/{invoice_id}/pay"
                    },
                    tags=["billing", "overdue", "urgent", "suspension"]
                )
                logger.info(f"✅ Sent overdue payment email to {customer_info.get('email')}")
            else:
                logger.warning(f"Could not send overdue payment email - missing customer or invoice info")
        except Exception as email_error:
            logger.error(f"❌ Failed to send overdue payment email: {email_error}")
        
        # TODO: Implement configurable grace period before suspension
        # TODO: Set up automatic retry for payment collection
        
    except Exception as e:
        logger.error(f"Error handling overdue invoice {invoice_id}: {e}")

async def _get_customer_external_key_by_account_id(account_id: str) -> Optional[str]:
    """Get customer external key from KillBill account ID"""
    try:
        # Initialize KillBill client with environment variables
        killbill = _get_killbill_client()
        
        # Get account details from KillBill
        account = await killbill.get_account_by_id(account_id)
        if account and account.get('externalKey'):
            return account['externalKey']
        
        logger.warning(f"No external key found for account {account_id}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting customer external key for account {account_id}: {e}")
        return None

async def _get_customer_info_by_external_key(external_key: str) -> Optional[Dict[str, Any]]:
    """Get customer information from user service by external key"""
    import httpx
    import os
    
    try:
        user_service_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8001')
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{user_service_url}/users/internal/{external_key}")
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"User not found for external key {external_key}: {response.status_code}")
                return None
    except Exception as e:
        logger.error(f"Error getting customer info for external key {external_key}: {e}")
        return None

async def _get_subscription_info(subscription_id: str) -> Optional[Dict[str, Any]]:
    """Get subscription information from KillBill"""
    try:
        killbill = _get_killbill_client()
        
        subscription = await killbill.get_subscription_by_id(subscription_id)
        return subscription
        
    except Exception as e:
        logger.error(f"Error getting subscription info for {subscription_id}: {e}")
        return None

async def _get_invoice_info(invoice_id: str) -> Optional[Dict[str, Any]]:
    """Get invoice information from KillBill"""
    try:
        killbill = _get_killbill_client()

        invoice = await killbill.get_invoice_by_id(invoice_id)
        return invoice

    except Exception as e:
        logger.error(f"Error getting invoice info for {invoice_id}: {e}")
        return None

@router.post("/paynow")
async def handle_paynow_webhook(request: Request, response: Response):
    """
    Handle webhook from Paynow

    Paynow sends status updates as URL-encoded POST:
    reference=X&paynowreference=Y&amount=Z&status=Paid&hash=...

    We validate hash, update payment record, and update KillBill if paid
    """
    response.headers["Connection"] = "close"

    try:
        # Get raw body
        body = await request.body()
        body_str = body.decode('utf-8')

        logger.info(f"Received Paynow webhook: {body_str}")

        # Parse URL-encoded payload
        payload_lists = parse_qs(body_str)

        # Convert lists to single values
        payload = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                  for k, v in payload_lists.items()}

        logger.info(f"Parsed Paynow payload: {payload}")

        # Validate hash
        paynow = get_paynow_client()
        if not paynow.validate_hash(payload):
            logger.error("Invalid hash in Paynow webhook")
            raise HTTPException(status_code=400, detail="Invalid hash")

        # Extract fields
        reference = payload.get('reference')  # Our reference
        paynow_reference = payload.get('paynowreference')
        amount = payload.get('amount')
        paynow_status = payload.get('status')
        poll_url = payload.get('pollurl')

        if not reference:
            logger.error("No reference in Paynow webhook")
            raise HTTPException(status_code=400, detail="Missing reference")

        logger.info(f"Paynow webhook: {reference} → {paynow_status}")

        # Find payment by our reference (gateway_transaction_id)
        pool = get_pool()
        async with pool.acquire() as conn:
            payment = await conn.fetchrow("""
                SELECT id, payment_status, amount as payment_amount, subscription_id
                FROM payments
                WHERE gateway_transaction_id = $1
            """, reference)

        if not payment:
            logger.warning(f"Payment not found for reference: {reference}")
            # Return 200 to prevent retries
            return {"success": True, "message": "Payment not found"}

        payment_id = payment['id']

        # Map Paynow status to our status
        from .payments import map_paynow_status
        new_status = map_paynow_status(paynow_status)

        # Update payment in database
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE payments
                SET payment_status = $1, paynow_status = $2, paynow_reference = $3,
                    webhook_received_at = $4, processed_at = $5
                WHERE id = $6
            """,
                new_status,
                paynow_status,
                paynow_reference,
                datetime.now(timezone.utc),
                datetime.now(timezone.utc) if new_status == 'paid' else None,
                payment_id
            )

        logger.info(f"Updated payment {payment_id}: {new_status}")

        # If payment successful, update KillBill
        if new_status == 'paid':
            logger.info(f"Payment successful, updating KillBill for payment {payment_id}")

            # Extract invoice_id from reference (format: INV_invoice_id_xxxxx)
            parts = reference.split('_')
            invoice_id = parts[1] if len(parts) > 1 else None

            if invoice_id:
                try:
                    # Get KillBill client
                    killbill = _get_killbill_client()

                    # Record payment in KillBill
                    invoice = await killbill.get_invoice_by_id(invoice_id)
                    if invoice:
                        account_id = invoice.get('accountId')

                        # Create payment in KillBill
                        payment_data = {
                            "accountId": account_id,
                            "targetInvoiceId": invoice_id,
                            "purchasedAmount": float(amount)
                        }

                        kb_payment = await killbill.create_payment(payment_data)
                        logger.info(f"Created KillBill payment for invoice {invoice_id}")

                        # Instance provisioning will be triggered by KillBill's
                        # INVOICE_PAYMENT_SUCCESS webhook

                    else:
                        logger.warning(f"Invoice {invoice_id} not found in KillBill")

                except Exception as kb_error:
                    logger.error(f"Failed to update KillBill: {kb_error}")
                    # Don't fail the webhook - payment is recorded locally
            else:
                logger.warning(f"Could not extract invoice_id from reference: {reference}")

        return {"success": True, "message": "Webhook processed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Paynow webhook: {e}")
        # Return 200 to prevent Paynow retries
        return {"success": False, "message": str(e)}
