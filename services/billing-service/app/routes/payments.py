"""
Billing Service - Payment Management Routes
Handles payment methods and payment processing
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel

from ..utils.killbill_client import KillBillClient

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

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

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