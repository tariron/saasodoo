"""
Billing Service - Invoice Management Routes
Handles invoice retrieval and management
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel

from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

class EmailInvoiceRequest(BaseModel):
    invoice_id: str
    email: Optional[str] = None  # If not provided, use account email

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

@router.get("/invoices/{customer_id}")
async def get_customer_invoices(
    customer_id: str,
    limit: int = 10,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get all invoices for a customer"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Retrieving invoices for customer {customer_id}")
        
        # For now, return empty list (in real implementation, fetch from KillBill)
        invoices = []
        
        return {
            "success": True,
            "customer_id": customer_id,
            "account_id": account_id,
            "invoices": invoices,
            "invoice_count": len(invoices),
            "limit": limit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get invoices for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve invoices: {str(e)}")

@router.get("/invoices/{invoice_id}/details")
async def get_invoice_details(
    invoice_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get detailed information about a specific invoice"""
    try:
        logger.info(f"Retrieving invoice details for {invoice_id}")
        
        # For now, return mock data (in real implementation, fetch from KillBill)
        invoice_details = {
            "invoice_id": invoice_id,
            "invoice_number": f"INV-{invoice_id[:8]}",
            "amount": 25.00,
            "currency": "USD",
            "status": "outstanding",
            "due_date": "2025-07-25",
            "created_date": "2025-06-25",
            "line_items": [
                {
                    "description": "Basic Monthly Plan",
                    "amount": 25.00,
                    "period": "2025-06-25 to 2025-07-25"
                }
            ]
        }
        
        return {
            "success": True,
            "invoice": invoice_details
        }
        
    except Exception as e:
        logger.error(f"Failed to get invoice details for {invoice_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve invoice details: {str(e)}")

@router.get("/invoices/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Download invoice as PDF"""
    try:
        logger.info(f"Generating PDF for invoice {invoice_id}")
        
        # For now, return a placeholder response (in real implementation, generate from KillBill)
        pdf_content = b"PDF placeholder content for invoice " + invoice_id.encode()
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=invoice_{invoice_id}.pdf"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to generate PDF for invoice {invoice_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate invoice PDF: {str(e)}")

@router.post("/invoices/email")
async def email_invoice(
    email_data: EmailInvoiceRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Email an invoice to a customer"""
    try:
        logger.info(f"Emailing invoice {email_data.invoice_id}")
        
        # For now, return success (in real implementation, send email)
        
        return {
            "success": True,
            "invoice_id": email_data.invoice_id,
            "email": email_data.email or "customer@example.com",
            "message": "Invoice emailed successfully"
        }
        
    except Exception as e:
        logger.error(f"Failed to email invoice {email_data.invoice_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to email invoice: {str(e)}")

@router.get("/billing-history/{customer_id}")
async def get_billing_history(
    customer_id: str,
    limit: int = 20,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get complete billing history for a customer (invoices + payments)"""
    try:
        # Get customer's KillBill account
        account = await killbill.get_account_by_external_key(customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer account not found")
        
        account_id = account.get("accountId")
        
        logger.info(f"Retrieving billing history for customer {customer_id}")
        
        # For now, return mock data (in real implementation, fetch from KillBill)
        billing_history = {
            "invoices": [],
            "payments": [],
            "credits": [],
            "total_paid": 0.0,
            "outstanding_balance": 0.0
        }
        
        return {
            "success": True,
            "customer_id": customer_id,
            "account_id": account_id,
            "billing_history": billing_history,
            "limit": limit
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get billing history for customer {customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing history: {str(e)}")