"""
Billing Service - Plans Routes
Handles KillBill catalog plans and pricing
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, List
import logging
from pydantic import BaseModel

from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

class Plan(BaseModel):
    """Plan information model"""
    name: str
    product: str
    type: str
    description: str
    billing_period: str
    trial_length: int
    trial_time_unit: str
    price: float | None
    currency: str
    available: bool
    fallback: bool = False

class PlansResponse(BaseModel):
    """Response for plans listing"""
    success: bool
    plans: List[Plan]
    total: int
    message: str

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

@router.get("/", response_model=PlansResponse)
async def get_available_plans(
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get all available billing plans from KillBill catalog"""
    try:
        logger.info("Fetching available plans from KillBill catalog")
        
        # Get plans from KillBill catalog
        plans_data = await killbill.get_catalog_plans()
        
        # Convert to response models
        plans = []
        for plan_data in plans_data:
            try:
                plan = Plan(
                    name=plan_data.get("name", ""),
                    product=plan_data.get("product", ""),
                    type=plan_data.get("type", "BASE"),
                    description=plan_data.get("description", ""),
                    billing_period=plan_data.get("billing_period", "MONTHLY"),
                    trial_length=plan_data.get("trial_length", 0),
                    trial_time_unit=plan_data.get("trial_time_unit", "DAYS"),
                    price=plan_data.get("price"),
                    currency=plan_data.get("currency", "USD"),
                    available=plan_data.get("available", True),
                    fallback=plan_data.get("fallback", False)
                )
                plans.append(plan)
            except Exception as plan_error:
                logger.warning(f"Failed to parse plan data {plan_data}: {plan_error}")
                continue
        
        # Sort plans: trial plans first, then by price
        plans.sort(key=lambda p: (p.trial_length == 0, p.price or 0))
        
        response = PlansResponse(
            success=True,
            plans=plans,
            total=len(plans),
            message=f"Retrieved {len(plans)} available plans"
        )
        
        logger.info(f"Successfully retrieved {len(plans)} plans")
        return response
        
    except Exception as e:
        logger.error(f"Failed to get available plans: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve plans: {str(e)}")

@router.get("/{plan_name}")
async def get_plan_details(
    plan_name: str,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Get detailed information about a specific plan"""
    try:
        logger.info(f"Fetching details for plan: {plan_name}")
        
        # Get all plans and find the requested one
        plans_data = await killbill.get_catalog_plans()
        
        plan_details = None
        for plan_data in plans_data:
            if plan_data.get("name") == plan_name:
                plan_details = plan_data
                break
        
        if not plan_details:
            raise HTTPException(status_code=404, detail=f"Plan '{plan_name}' not found")
        
        return {
            "success": True,
            "plan": plan_details,
            "message": f"Plan details for {plan_name}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get plan details for {plan_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get plan details: {str(e)}")