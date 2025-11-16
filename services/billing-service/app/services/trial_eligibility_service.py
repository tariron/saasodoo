"""
Trial Eligibility Service
Handles trial eligibility checking with Redis-based locking to prevent race conditions
"""

import logging
import os
from typing import Optional
from datetime import datetime, timedelta

from shared.schemas.billing import TrialEligibilityResponse, TrialEligibilityReason
from shared.utils.redis_client import RedisClient
from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)


class TrialLockTimeout(Exception):
    """Raised when unable to acquire trial creation lock"""
    pass


class TrialEligibilityService:
    """Service for checking trial eligibility and managing trial creation locks"""

    # Trial configuration constants
    DEFAULT_TRIAL_DAYS = 14
    LOCK_TIMEOUT_SECONDS = 10  # How long to wait for lock
    LOCK_TTL_SECONDS = 30  # How long lock is held

    def __init__(self, killbill_client: KillBillClient, redis_client: Optional[RedisClient] = None):
        """
        Initialize trial eligibility service

        Args:
            killbill_client: KillBill client for querying subscriptions
            redis_client: Redis client for distributed locking (optional)
        """
        self.killbill = killbill_client
        self.redis = redis_client or RedisClient()

        # Get configuration from environment
        self.trial_days = int(os.getenv("DEFAULT_TRIAL_DAYS", str(self.DEFAULT_TRIAL_DAYS)))
        self.fail_closed = os.getenv("TRIAL_ELIGIBILITY_FAIL_BEHAVIOR", "closed") == "closed"

    async def check_eligibility(self, customer_id: str) -> TrialEligibilityResponse:
        """
        Check if customer is eligible for a trial subscription

        This is the single source of truth for trial eligibility. Both frontend
        and backend should use this method to determine trial availability.

        Business Rules:
        - One trial per customer (lifetime)
        - Cannot have multiple active trials
        - Checks historical subscription data for any past trials
        - Customers with active paid subscriptions cannot get trials

        Args:
            customer_id: Customer UUID

        Returns:
            TrialEligibilityResponse with eligibility status and metadata
        """
        try:
            # Get customer's KillBill account
            account = await self.killbill.get_account_by_external_key(customer_id)

            if not account:
                logger.warning(f"No KillBill account found for customer {customer_id}")
                # New customer with no account yet - eligible for trial
                return TrialEligibilityResponse(
                    eligible=True,
                    can_show_trial_info=True,
                    trial_days=self.trial_days,
                    has_active_subscriptions=False,
                    subscription_count=0,
                    reason=TrialEligibilityReason.ELIGIBLE
                )

            account_id = account.get("accountId")

            # Get all subscriptions for this customer
            subscriptions = await self.killbill.get_account_subscriptions(account_id)

            # Check for ANY trial subscription (current or historical)
            has_trial = any(sub.get('phaseType') == 'TRIAL' for sub in subscriptions)

            # Count active subscriptions (not cancelled)
            active_subscriptions = [
                sub for sub in subscriptions
                if sub.get('state') == 'ACTIVE'
            ]

            # Check for active paid subscriptions (EVERGREEN phase = paid)
            active_paid_subscriptions = [
                sub for sub in active_subscriptions
                if sub.get('phaseType') == 'EVERGREEN'
            ]

            # Determine eligibility
            if has_trial:
                # Customer has had a trial before (active or historical)
                logger.info(f"Customer {customer_id} ineligible - has trial in subscription history")
                return TrialEligibilityResponse(
                    eligible=False,
                    can_show_trial_info=False,
                    trial_days=0,
                    has_active_subscriptions=len(active_subscriptions) > 0,
                    subscription_count=len(subscriptions),
                    reason=TrialEligibilityReason.HAS_HISTORICAL_TRIAL
                )

            if len(active_paid_subscriptions) > 0:
                # Customer has active paid subscription(s) - not eligible for trial
                logger.info(f"Customer {customer_id} ineligible - has {len(active_paid_subscriptions)} active paid subscription(s)")
                return TrialEligibilityResponse(
                    eligible=False,
                    can_show_trial_info=False,
                    trial_days=0,
                    has_active_subscriptions=True,
                    subscription_count=len(subscriptions),
                    reason=TrialEligibilityReason.HAS_ACTIVE_SUBSCRIPTION
                )

            # Customer is eligible - no trials in history and no active paid subscriptions
            logger.info(f"Customer {customer_id} eligible for trial")
            return TrialEligibilityResponse(
                eligible=True,
                can_show_trial_info=True,
                trial_days=self.trial_days,
                has_active_subscriptions=len(active_subscriptions) > 0,
                subscription_count=len(subscriptions),
                reason=TrialEligibilityReason.ELIGIBLE
            )

        except Exception as e:
            logger.error(f"Error checking trial eligibility for customer {customer_id}: {e}", exc_info=True)

            # Fail closed: deny trials on system errors
            if self.fail_closed:
                logger.warning(f"Failing closed - denying trial for customer {customer_id} due to system error")
                return TrialEligibilityResponse(
                    eligible=False,
                    can_show_trial_info=False,
                    trial_days=0,
                    has_active_subscriptions=False,
                    subscription_count=0,
                    reason=TrialEligibilityReason.SYSTEM_ERROR
                )
            else:
                # Fail open: allow trials on system errors (not recommended)
                logger.warning(f"Failing open - allowing trial for customer {customer_id} despite system error")
                return TrialEligibilityResponse(
                    eligible=True,
                    can_show_trial_info=True,
                    trial_days=self.trial_days,
                    has_active_subscriptions=False,
                    subscription_count=0,
                    reason=TrialEligibilityReason.SYSTEM_ERROR
                )

    def acquire_trial_creation_lock(self, customer_id: str) -> bool:
        """
        Acquire distributed lock for trial creation

        This prevents race conditions where two simultaneous requests could
        both check eligibility (both pass) and both create trials.

        Args:
            customer_id: Customer UUID

        Returns:
            True if lock acquired, False otherwise
        """
        lock_key = f"trial_creation_lock:{customer_id}"

        try:
            # Try to set lock with NX (only if not exists) and EX (expiration)
            # Using SET with NX and EX options is atomic in Redis
            result = self.redis.client.set(
                lock_key,
                datetime.utcnow().isoformat(),
                nx=True,  # Only set if doesn't exist
                ex=self.LOCK_TTL_SECONDS  # Expire after TTL
            )

            if result:
                logger.debug(f"Acquired trial creation lock for customer {customer_id}")
                return True
            else:
                logger.warning(f"Failed to acquire trial creation lock for customer {customer_id} - lock already held")
                return False

        except Exception as e:
            logger.error(f"Error acquiring trial creation lock for customer {customer_id}: {e}")
            # On Redis error, fail safe and don't block trial creation
            # The backend validation will still catch any issues
            return True

    def release_trial_creation_lock(self, customer_id: str) -> bool:
        """
        Release distributed lock for trial creation

        Args:
            customer_id: Customer UUID

        Returns:
            True if lock released, False otherwise
        """
        lock_key = f"trial_creation_lock:{customer_id}"

        try:
            result = self.redis.delete(lock_key)
            if result:
                logger.debug(f"Released trial creation lock for customer {customer_id}")
            return bool(result)
        except Exception as e:
            logger.error(f"Error releasing trial creation lock for customer {customer_id}: {e}")
            return False

    async def validate_trial_creation(self, customer_id: str) -> bool:
        """
        Validate that a customer can create a trial subscription

        This should be called immediately before creating a trial subscription
        to ensure eligibility is still valid.

        Args:
            customer_id: Customer UUID

        Returns:
            True if trial can be created, False otherwise

        Raises:
            TrialLockTimeout: If unable to acquire trial creation lock
        """
        # Check eligibility
        eligibility = await self.check_eligibility(customer_id)

        if not eligibility.eligible:
            logger.warning(f"Trial creation validation failed for customer {customer_id}: {eligibility.reason}")
            return False

        logger.info(f"Trial creation validation passed for customer {customer_id}")
        return True
