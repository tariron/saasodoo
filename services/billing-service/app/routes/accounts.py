"""
Billing Service - Accounts Routes
Handles KillBill account management
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional
import logging
from pydantic import BaseModel

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
