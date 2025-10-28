"""
Billing Service - Payment Management Routes
Handles payment methods and payment processing
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List, Literal
import logging
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

from ..utils.killbill_client import KillBillClient
from ..utils.paynow_client import get_paynow_client
from ..utils.database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

class AddPaymentMethodRequest(BaseModel):
    customer_id: str
    card_number: str
    expiry_month: int
    expiry_year: int
    cvv: str
    cardholder_name: str
    billing_address: Optional[Dict[str, str]] = None

class RetryPaymentRequest(BaseModel):
    customer_id: str
    invoice_id: Optional[str] = None
    amount: Optional[float] = None

class PaynowInitiateRequest(BaseModel):
    invoice_id: str
    payment_method: Literal["ecocash", "onemoney", "card"]
    phone: Optional[str] = None  # Required for ecocash/onemoney
    return_url: Optional[str] = None  # Required for card
    customer_email: str  # Required for all


class PaynowPaymentResponse(BaseModel):
    payment_id: str
    reference: str
    payment_type: Literal["mobile", "redirect"]
    status: str
    poll_url: str
    redirect_url: Optional[str] = None
    message: str

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

def map_paynow_status(paynow_status: str) -> str:
    """Map Paynow status to our payment_status"""
    status_map = {
        "Paid": "paid",
        "Awaiting Delivery": "paid",
        "Delivered": "paid",
        "Created": "pending",
        "Sent": "pending",
        "Cancelled": "cancelled",
        "Failed": "failed",
        "Disputed": "disputed",
        "Refunded": "refunded"
    }
    return status_map.get(paynow_status, "pending")

@router.post("/payment-methods/")
async def add_payment_method(
    payment_data: AddPaymentMethodRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Add a payment method for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(payment_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Adding payment method for customer {payment_data.customer_id}")
        
        # For now, return a success response (in real implementation, integrate with payment processor)
        payment_method_info = {
            "payment_method_id": f"pm_{payment_data.customer_id}_{len(payment_data.card_number[-4:])}",
            "customer_id": payment_data.customer_id,
            "account_id": account_id,
            "type": "credit_card",
            "last_four": payment_data.card_number[-4:],
            "cardholder_name": payment_data.cardholder_name,
            "expiry_month": payment_data.expiry_month,
            "expiry_year": payment_data.expiry_year,
            "is_default": True,
            "status": "active"
        }
        
        return {
            "success": True,
            "payment_method": payment_method_info,
            "message": "Payment method added successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add payment method for customer {payment_data.customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add payment method: {str(e)}")

@router.get("/payment-methods/{customer_id}")
async def get_payment_methods(
    customer_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get all payment methods for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Retrieving payment methods for customer {customer_id}")
        
        # Get real payment methods from KillBill
        payment_methods = await killbill.get_account_payment_methods(account_id)
        
        return {
            "success": True,
            "customer_id": customer_id,
            "account_id": account_id,
            "payment_methods": payment_methods,
            "method_count": len(payment_methods)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get payment methods for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve payment methods: {str(e)}")

@router.delete("/payment-methods/{payment_method_id}")
async def remove_payment_method(
    payment_method_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Remove a payment method"""
    try:
        logger.info(f"Removing payment method {payment_method_id}")
        
        # For now, return success (in real implementation, remove from KillBill)
        
        return {
            "success": True,
            "payment_method_id": payment_method_id,
            "message": "Payment method removed successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to remove payment method {payment_method_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove payment method: {str(e)}")

@router.post("/retry-payment/")
async def retry_payment(
    retry_data: RetryPaymentRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Retry a failed payment"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(retry_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Retrying payment for customer {retry_data.customer_id}")
        
        # For now, return success (in real implementation, trigger payment retry in KillBill)
        payment_result = {
            "payment_id": f"pay_{retry_data.customer_id}_{account_id[:8]}",
            "customer_id": retry_data.customer_id,
            "account_id": account_id,
            "amount": retry_data.amount or 0.0,
            "status": "pending",
            "retry_attempt": 1
        }
        
        return {
            "success": True,
            "payment": payment_result,
            "message": "Payment retry initiated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry payment for customer {retry_data.customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retry payment: {str(e)}")

@router.post("/paynow/initiate", response_model=PaynowPaymentResponse)
async def initiate_paynow_payment(
    request: PaynowInitiateRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """
    Initiate Paynow payment (mobile money or card)

    Mobile Money Flow (EcoCash/OneMoney):
    - Sends USSD push to customer's phone
    - Customer approves on phone
    - Frontend polls status endpoint

    Card Flow:
    - Returns redirect URL
    - Customer redirects to Paynow
    - Customer pays on Paynow page
    - Paynow redirects back to return_url
    """
    try:
        # Validate request
        if request.payment_method in ["ecocash", "onemoney"] and not request.phone:
            raise HTTPException(status_code=400, detail="Phone number required for mobile money payments")

        if request.payment_method == "card" and not request.return_url:
            raise HTTPException(status_code=400, detail="Return URL required for card payments")

        # Get invoice from KillBill
        invoice = await killbill.get_invoice_by_id(request.invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        amount = float(invoice.get('balance', 0))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Invoice already paid or has zero balance")

        # Generate unique reference
        payment_id = str(uuid.uuid4())
        reference = f"INV_{request.invoice_id}_{payment_id[:8]}"

        # Initialize Paynow client
        paynow = get_paynow_client()

        # Initiate payment based on method
        if request.payment_method in ["ecocash", "onemoney"]:
            # Mobile money - USSD push
            paynow_response = await paynow.initiate_mobile_transaction(
                reference=reference,
                amount=amount,
                phone=request.phone,
                method=request.payment_method,
                auth_email=request.customer_email,
                additional_info=f"Invoice {request.invoice_id}"
            )
            payment_type = "mobile"

        else:
            # Card - redirect flow
            # Replace PLACEHOLDER in return_url with actual payment_id
            return_url = request.return_url
            if return_url and 'PLACEHOLDER' in return_url:
                return_url = return_url.replace('PLACEHOLDER', payment_id)

            paynow_response = await paynow.initiate_transaction(
                reference=reference,
                amount=amount,
                return_url=return_url,
                auth_email=request.customer_email,
                additional_info=f"Invoice {request.invoice_id}"
            )
            payment_type = "redirect"

        # Check Paynow response
        if paynow_response.get('status') == 'Error':
            error_msg = paynow_response.get('error', 'Unknown error')
            logger.error(f"Paynow initiation failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Payment initiation failed: {error_msg}")

        # Store payment in database
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO payments (
                    id, subscription_id, amount, currency, payment_method, payment_status,
                    gateway_transaction_id, paynow_poll_url, paynow_browser_url,
                    return_url, phone, paynow_status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                payment_id,
                None,  # subscription_id - link if available
                amount,
                'USD',
                request.payment_method,
                'pending',
                reference,  # Our reference
                paynow_response.get('pollurl'),
                paynow_response.get('browserurl'),
                request.return_url,
                request.phone,
                paynow_response.get('status'),
                datetime.now(timezone.utc)
            )

        logger.info(f"Payment initiated: {payment_id} ({request.payment_method})")

        # Build response
        response_data = {
            "payment_id": payment_id,
            "reference": reference,
            "payment_type": payment_type,
            "status": "pending",
            "poll_url": f"/api/billing/payments/paynow/status/{payment_id}"
        }

        if payment_type == "redirect":
            response_data["redirect_url"] = paynow_response.get('browserurl')
            response_data["message"] = "Redirect customer to payment page"
        else:
            response_data["message"] = f"Payment request sent to {request.phone}. Please check your phone."

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating Paynow payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/paynow/status/{payment_id}")
async def get_paynow_payment_status(payment_id: str):
    """
    Get current payment status - Frontend polls this endpoint

    Returns current status from database.
    If status is still pending after 30 seconds, polls Paynow for update.
    """
    try:
        pool = get_pool()

        # Get payment from database
        async with pool.acquire() as conn:
            payment = await conn.fetchrow("""
                SELECT id, gateway_transaction_id, amount, payment_method, payment_status,
                       paynow_reference, paynow_poll_url, paynow_status, phone,
                       created_at, webhook_received_at
                FROM payments
                WHERE id = $1
            """, payment_id)

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # Check if we should poll Paynow for update
        should_poll = (
            payment['payment_status'] == 'pending' and
            payment['paynow_poll_url'] and
            (datetime.now(timezone.utc) - payment['created_at']).total_seconds() > 30
        )

        if should_poll:
            # Poll Paynow for latest status
            paynow = get_paynow_client()
            paynow_status = await paynow.poll_transaction_status(payment['paynow_poll_url'])

            if paynow_status.get('status') not in ['Error']:
                # Update database with latest status
                new_status = paynow_status.get('status', 'pending')
                mapped_status = map_paynow_status(new_status)

                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE payments
                        SET payment_status = $1, paynow_status = $2, paynow_reference = $3
                        WHERE id = $4
                    """,
                        mapped_status,
                        new_status,
                        paynow_status.get('paynowreference'),
                        payment_id
                    )

                # If payment just became paid, record in KillBill
                if mapped_status == 'paid':
                    logger.info(f"Payment {payment_id} status changed to 'paid', recording in KillBill")

                    # Extract invoice_id from reference (format: INV_invoice_id_xxxxx)
                    reference = payment['gateway_transaction_id']
                    parts = reference.split('_')
                    invoice_id = parts[1] if len(parts) > 1 else None

                    if invoice_id:
                        try:
                            # Get KillBill client
                            from ..routes.webhooks import _get_killbill_client
                            killbill = _get_killbill_client()

                            # Get invoice to find account_id
                            invoice = await killbill.get_invoice_by_id(invoice_id)
                            if invoice:
                                account_id = invoice.get('accountId')
                                amount_to_pay = float(paynow_status.get('amount', payment['amount']))

                                # Record payment in KillBill
                                payment_data = {
                                    "accountId": account_id,
                                    "targetInvoiceId": invoice_id,
                                    "purchasedAmount": amount_to_pay
                                }

                                kb_payment = await killbill.create_payment(payment_data)
                                logger.info(f"✅ Recorded payment in KillBill for invoice {invoice_id} (amount: {amount_to_pay})")
                                logger.info(f"KillBill will trigger INVOICE_PAYMENT_SUCCESS webhook to provision instances")
                            else:
                                logger.warning(f"Invoice {invoice_id} not found in KillBill")
                        except Exception as kb_error:
                            logger.error(f"Failed to record payment in KillBill for invoice {invoice_id}: {kb_error}")
                            # Don't fail the endpoint - payment is recorded locally
                    else:
                        logger.warning(f"Could not extract invoice_id from reference: {reference}")

                # Reload payment
                async with pool.acquire() as conn:
                    payment = await conn.fetchrow("""
                        SELECT id, gateway_transaction_id, amount, payment_method, payment_status,
                               paynow_reference, paynow_status, phone,
                               created_at, webhook_received_at
                        FROM payments
                        WHERE id = $1
                    """, payment_id)

        # Return current status
        return {
            "payment_id": str(payment['id']),
            "reference": payment['gateway_transaction_id'],
            "status": payment['payment_status'],
            "paynow_status": payment['paynow_status'],
            "amount": float(payment['amount']),
            "payment_method": payment['payment_method'],
            "phone": payment['phone'],
            "created_at": payment['created_at'].isoformat() if payment['created_at'] else None,
            "webhook_received": payment['webhook_received_at'] is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting payment status: {e}")
        raise HTTPException(status_code=500, detail=str(e))