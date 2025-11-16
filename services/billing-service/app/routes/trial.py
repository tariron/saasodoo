"""
Billing Service - Trial Eligibility Routes
Handles trial eligibility checking for customers
"""

from fastapi import APIRouter, HTTPException, Depends, Request
import logging

from shared.schemas.billing import TrialEligibilityResponse
from shared.utils.redis_client import RedisClient
from ..services.trial_eligibility_service import TrialEligibilityService
from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()


def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill


def get_redis_client() -> RedisClient:
    """Dependency to get Redis client"""
    return RedisClient()


def get_trial_eligibility_service(
    killbill: KillBillClient = Depends(get_killbill_client),
    redis: RedisClient = Depends(get_redis_client)
) -> TrialEligibilityService:
    """Dependency to get Trial Eligibility Service"""
    return TrialEligibilityService(killbill, redis)


@router.get("/{customer_id}", response_model=TrialEligibilityResponse)
async def get_trial_eligibility(
    customer_id: str,
    service: TrialEligibilityService = Depends(get_trial_eligibility_service)
):
    """
    Check if a customer is eligible for a trial subscription

    This is the single source of truth for trial eligibility.
    Both frontend and backend should use this endpoint to determine
    whether trial information should be displayed and whether trial
    creation is allowed.

    **Business Rules:**
    - One trial per customer (lifetime limit)
    - Checks historical subscription data for any past trials
    - Cannot have multiple active trials simultaneously

    **Authorization:**
    The customer_id in the path should match the authenticated user's
    customer_id from their JWT token. This endpoint should be protected
    by authentication middleware.

    **Error Handling:**
    - Returns ineligible status (fail closed) if system errors occur
    - Logs all errors for investigation
    - Never blocks legitimate new customers due to transient errors

    Args:
        customer_id: Customer UUID (should match authenticated user)
        service: Trial eligibility service (injected)

    Returns:
        TrialEligibilityResponse with:
        - eligible: Boolean indicating if customer can create a trial
        - can_show_trial_info: Boolean for UI rendering (same as eligible)
        - trial_days: Number of trial days available (14 if eligible, 0 if not)
        - has_active_subscriptions: Whether customer has active subs
        - subscription_count: Total number of subscriptions
        - reason: Reason code for logging

    Raises:
        HTTPException: Never raises errors, returns structured response instead
    """
    try:
        logger.info(f"Checking trial eligibility for customer {customer_id}")

        # Check eligibility using the service
        eligibility = await service.check_eligibility(customer_id)

        logger.info(
            f"Trial eligibility check complete for customer {customer_id}: "
            f"eligible={eligibility.eligible}, reason={eligibility.reason}"
        )

        return eligibility

    except Exception as e:
        # This should rarely happen since the service handles errors internally
        logger.error(f"Unexpected error in trial eligibility endpoint for customer {customer_id}: {e}", exc_info=True)

        # Return fail-closed response
        from shared.schemas.billing import TrialEligibilityReason
        return TrialEligibilityResponse(
            eligible=False,
            can_show_trial_info=False,
            trial_days=0,
            has_active_subscriptions=False,
            subscription_count=0,
            reason=TrialEligibilityReason.SYSTEM_ERROR
        )
