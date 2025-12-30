# Instance Service Production Readiness Plan

**Created:** 2025-12-29
**Status:** Draft
**Priority:** Critical
**Scope:** Software engineering principles, reliability, and production hardening

---

## Executive Summary

This plan addresses critical production-readiness issues identified in the `instance-service` and `instance-worker` components. These are **software engineering principle violations** that will cause failures in production:

| Category | Issues Found | Severity |
|----------|-------------|----------|
| Idempotency | 5 critical gaps | P0 - Ship Blocker |
| Silent Failures | 7 swallowed exceptions | P0 - Ship Blocker |
| State Machine | No transition validation | P0 - Ship Blocker |
| Transaction Boundaries | 4 multi-step operations without atomicity | P1 - High |
| Race Conditions | 4 concurrency bugs | P1 - High |
| Retry Logic | No exponential backoff | P2 - Medium |

---

## Table of Contents

1. [Phase 1: Distributed Locking & Idempotency](#phase-1-distributed-locking--idempotency)
2. [Phase 2: State Machine Implementation](#phase-2-state-machine-implementation)
3. [Phase 3: Transaction Boundaries & Atomicity](#phase-3-transaction-boundaries--atomicity)
4. [Phase 4: Error Handling & Silent Failure Elimination](#phase-4-error-handling--silent-failure-elimination)
5. [Phase 5: Celery Retry & Dead Letter Queue](#phase-5-celery-retry--dead-letter-queue)
6. [Phase 6: Input Validation & Security](#phase-6-input-validation--security)
7. [Phase 7: Observability & Correlation](#phase-7-observability--correlation)
8. [Implementation Priority Matrix](#implementation-priority-matrix)
9. [Testing Strategy](#testing-strategy)
10. [Rollout Plan](#rollout-plan)

---

## Phase 1: Distributed Locking & Idempotency

**Priority:** P0 - Ship Blocker
**Effort:** 2 days
**Impact:** Prevents duplicate resource creation, race conditions

### 1.1 Current Problems

```python
# PROBLEM 1: No idempotency check - retry creates duplicate resources
@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    # If task retries, creates duplicate K8s deployment!
    container_info = await _deploy_odoo_container(instance, db_info)

# PROBLEM 2: TOCTOU race in database uniqueness check
existing = await conn.fetchrow("SELECT id FROM instances WHERE database_name = $1", name)
if existing:
    raise ValueError("Already exists")
# ^^^ Another request can insert between check and insert below!
instance_id = await conn.fetchval("INSERT INTO instances ...")

# PROBLEM 3: Concurrent actions on same instance
# User clicks "Start" twice rapidly → 2 tasks queued → undefined behavior
job = start_instance_task.delay(str(instance_id))
```

### 1.2 Solution: Redis Distributed Locking

Based on [redis-py distributed lock patterns](https://github.com/redis/redis-py):

**File: `shared/utils/distributed_lock.py`**

```python
"""
Distributed Locking for SaaSOdoo

Based on redis-py lock patterns:
- Automatic release on context exit
- Lock extension for long operations
- Non-blocking acquisition option
"""

import asyncio
import functools
import logging
from typing import Optional, Callable, TypeVar
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import LockNotOwnedError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DistributedLockManager:
    """Redis-based distributed lock manager."""

    _redis: Optional[aioredis.Redis] = None

    # Lock key prefixes
    PREFIX_INSTANCE_ACTION = "lock:instance:action"
    PREFIX_INSTANCE_PROVISION = "lock:instance:provision"
    PREFIX_BACKUP = "lock:backup"

    @classmethod
    async def get_redis(cls) -> aioredis.Redis:
        """Get or create Redis connection."""
        if cls._redis is None:
            from shared.utils.redis_client import get_async_redis_client
            cls._redis = await get_async_redis_client()
        return cls._redis

    @classmethod
    @asynccontextmanager
    async def lock(
        cls,
        lock_name: str,
        timeout: int = 300,
        blocking: bool = True,
        blocking_timeout: float = 10.0
    ):
        """
        Acquire distributed lock with automatic release.

        Usage:
            async with DistributedLockManager.lock(f"instance:{id}:action"):
                # Critical section - only one worker can execute this
                await perform_action()

        Args:
            lock_name: Unique lock identifier
            timeout: Lock auto-expiry in seconds (prevents deadlocks)
            blocking: Wait for lock if unavailable
            blocking_timeout: Max time to wait for lock

        Raises:
            LockAcquisitionError: Could not acquire lock
        """
        redis = await cls.get_redis()
        lock = redis.lock(
            name=lock_name,
            timeout=timeout,
            blocking=blocking,
            blocking_timeout=blocking_timeout
        )

        acquired = await lock.acquire()
        if not acquired:
            raise LockAcquisitionError(f"Could not acquire lock: {lock_name}")

        logger.info("Lock acquired", lock_name=lock_name, timeout=timeout)

        try:
            yield lock
        finally:
            try:
                await lock.release()
                logger.info("Lock released", lock_name=lock_name)
            except LockNotOwnedError:
                logger.warning("Lock already released or expired", lock_name=lock_name)

    @classmethod
    async def extend_lock(cls, lock, additional_time: int):
        """Extend lock timeout for long-running operations."""
        await lock.extend(additional_time)
        logger.info("Lock extended", additional_time=additional_time)

    @classmethod
    async def is_locked(cls, lock_name: str) -> bool:
        """Check if a resource is currently locked."""
        redis = await cls.get_redis()
        return await redis.exists(lock_name) > 0


class LockAcquisitionError(Exception):
    """Raised when lock cannot be acquired."""
    pass


def with_instance_lock(timeout: int = 300):
    """
    Decorator to wrap instance operations with distributed lock.

    Usage:
        @with_instance_lock(timeout=600)
        async def provision_instance(instance_id: str, ...):
            # Only one worker can provision this instance at a time
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(instance_id: str, *args, **kwargs) -> T:
            lock_name = f"{DistributedLockManager.PREFIX_INSTANCE_ACTION}:{instance_id}"

            async with DistributedLockManager.lock(lock_name, timeout=timeout):
                return await func(instance_id, *args, **kwargs)

        return wrapper
    return decorator


# Idempotency key management
class IdempotencyManager:
    """
    Manages idempotency keys for preventing duplicate operations.

    Pattern: Check-and-set with Redis
    - Before operation: Check if idempotency key exists
    - If exists: Return cached result
    - If not: Execute operation, store result with TTL
    """

    PREFIX = "idempotency"
    DEFAULT_TTL = 3600  # 1 hour

    @classmethod
    async def check_and_set(
        cls,
        key: str,
        ttl: int = DEFAULT_TTL
    ) -> tuple[bool, Optional[str]]:
        """
        Check if operation was already performed.

        Returns:
            (is_duplicate, cached_result)
            - (True, result) if already executed
            - (False, None) if new operation
        """
        redis = await DistributedLockManager.get_redis()
        full_key = f"{cls.PREFIX}:{key}"

        # Try to get existing result
        cached = await redis.get(full_key)
        if cached:
            logger.info("Idempotency hit - returning cached result", key=key)
            return (True, cached.decode() if isinstance(cached, bytes) else cached)

        # Mark as in-progress (prevents concurrent duplicate)
        set_result = await redis.set(
            full_key,
            "in_progress",
            nx=True,  # Only set if not exists
            ex=ttl
        )

        if not set_result:
            # Another request just started this operation
            logger.info("Idempotency race - operation in progress", key=key)
            return (True, "in_progress")

        return (False, None)

    @classmethod
    async def store_result(cls, key: str, result: str, ttl: int = DEFAULT_TTL):
        """Store operation result for idempotency."""
        redis = await DistributedLockManager.get_redis()
        full_key = f"{cls.PREFIX}:{key}"
        await redis.set(full_key, result, ex=ttl)
        logger.info("Idempotency result stored", key=key)

    @classmethod
    async def clear(cls, key: str):
        """Clear idempotency key (for retryable failures)."""
        redis = await DistributedLockManager.get_redis()
        full_key = f"{cls.PREFIX}:{key}"
        await redis.delete(full_key)
```

### 1.3 Updated Task Patterns

```python
# BEFORE: No idempotency
@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    result = asyncio.run(_provision_instance_workflow(instance_id, db_info))
    return result

# AFTER: With idempotency and locking
from shared.utils.distributed_lock import (
    DistributedLockManager,
    IdempotencyManager,
    LockAcquisitionError
)

@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    """
    Idempotent instance provisioning with distributed locking.
    """
    # Generate idempotency key from task arguments
    idempotency_key = f"provision:{instance_id}"

    try:
        result = asyncio.run(
            _provision_instance_workflow_safe(instance_id, db_info, idempotency_key)
        )
        return result
    except LockAcquisitionError:
        logger.warning("Instance provisioning already in progress", instance_id=instance_id)
        return {"status": "already_in_progress", "instance_id": instance_id}


async def _provision_instance_workflow_safe(
    instance_id: str,
    db_info: Dict[str, str],
    idempotency_key: str
) -> Dict[str, Any]:
    """Provisioning workflow with idempotency and locking."""

    # Step 1: Check idempotency
    is_duplicate, cached_result = await IdempotencyManager.check_and_set(idempotency_key)
    if is_duplicate:
        if cached_result == "in_progress":
            raise LockAcquisitionError("Operation in progress")
        return {"status": "already_completed", "cached": True}

    # Step 2: Acquire distributed lock
    lock_name = f"lock:provision:{instance_id}"

    try:
        async with DistributedLockManager.lock(lock_name, timeout=900):  # 15 min
            # Step 3: Verify instance state before proceeding
            instance = await _get_instance_from_db(instance_id)
            if instance['status'] not in ['creating', 'error']:
                logger.info("Instance already provisioned or in wrong state",
                           instance_id=instance_id, status=instance['status'])
                return {"status": "skipped", "reason": f"Instance in {instance['status']} state"}

            # Step 4: Execute provisioning
            result = await _provision_instance_workflow(instance_id, db_info)

            # Step 5: Store result for idempotency
            await IdempotencyManager.store_result(
                idempotency_key,
                "completed",
                ttl=86400  # 24 hours
            )

            return result

    except Exception as e:
        # Clear idempotency key on failure (allow retry)
        await IdempotencyManager.clear(idempotency_key)
        raise
```

### 1.4 Route-Level Idempotency

```python
# routes/instances.py

from fastapi import HTTPException, Header
from shared.utils.distributed_lock import IdempotencyManager, DistributedLockManager

@router.post("/{instance_id}/actions", response_model=InstanceActionResponse)
async def perform_instance_action(
    instance_id: UUID,
    action_request: InstanceActionRequest,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    db: InstanceDatabase = Depends(get_database)
):
    """Perform action with idempotency support."""

    # Generate idempotency key if not provided
    if not idempotency_key:
        idempotency_key = f"{instance_id}:{action_request.action.value}:{datetime.utcnow().timestamp()}"

    # Check if action already in progress
    lock_key = f"lock:instance:{instance_id}:action"
    if await DistributedLockManager.is_locked(lock_key):
        raise HTTPException(
            status_code=409,
            detail="Another action is already in progress for this instance"
        )

    # Check idempotency
    is_duplicate, cached = await IdempotencyManager.check_and_set(
        f"action:{idempotency_key}",
        ttl=300
    )
    if is_duplicate:
        raise HTTPException(
            status_code=409,
            detail="Duplicate request - action already queued or completed"
        )

    # ... rest of action handling
```

---

## Phase 2: State Machine Implementation

**Priority:** P0 - Ship Blocker
**Effort:** 2 days
**Impact:** Prevents invalid state transitions, enforces business rules

### 2.1 Current Problems

```python
# PROBLEM: No state transition validation
async def _update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    # Can transition from ANY state to ANY state!
    await conn.execute("""
        UPDATE instances SET status = $1 WHERE id = $2
    """, status.value, instance_id)
```

### 2.2 Solution: Transitions Library State Machine

Based on [pytransitions/transitions](https://github.com/pytransitions/transitions):

**File: `shared/utils/state_machine.py`**

```python
"""
Instance State Machine

Based on transitions library patterns:
- Explicit state definitions with callbacks
- Guarded transitions with conditions
- Before/after hooks for logging and side effects

Valid State Transitions:
    CREATING → STARTING → RUNNING
                 ↓          ↓
               ERROR ← ← STOPPING → STOPPED
                 ↓          ↓
            MAINTENANCE ← ←┘
                 ↓
            TERMINATED
"""

from enum import Enum
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime
import logging

from transitions import Machine, State
from transitions.extensions import AsyncMachine

logger = logging.getLogger(__name__)


class InstanceState(str, Enum):
    """All valid instance states."""
    CREATING = "creating"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    RESTARTING = "restarting"
    MAINTENANCE = "maintenance"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"
    CONTAINER_MISSING = "container_missing"


# State definitions with callbacks
STATES = [
    State(name=InstanceState.CREATING.value, on_enter=['log_state_enter']),
    State(name=InstanceState.STARTING.value, on_enter=['log_state_enter']),
    State(name=InstanceState.RUNNING.value, on_enter=['log_state_enter', 'record_started_at']),
    State(name=InstanceState.STOPPING.value, on_enter=['log_state_enter']),
    State(name=InstanceState.STOPPED.value, on_enter=['log_state_enter', 'clear_started_at']),
    State(name=InstanceState.RESTARTING.value, on_enter=['log_state_enter']),
    State(name=InstanceState.MAINTENANCE.value, on_enter=['log_state_enter']),
    State(name=InstanceState.PAUSED.value, on_enter=['log_state_enter']),
    State(name=InstanceState.ERROR.value, on_enter=['log_state_enter', 'record_error']),
    State(name=InstanceState.TERMINATED.value, on_enter=['log_state_enter', 'cleanup_resources']),
    State(name=InstanceState.CONTAINER_MISSING.value, on_enter=['log_state_enter']),
]

# Valid transitions
TRANSITIONS = [
    # Provisioning flow
    {'trigger': 'start_provisioning', 'source': InstanceState.CREATING.value,
     'dest': InstanceState.STARTING.value},
    {'trigger': 'provisioning_complete', 'source': InstanceState.STARTING.value,
     'dest': InstanceState.RUNNING.value},
    {'trigger': 'provisioning_failed', 'source': [InstanceState.CREATING.value, InstanceState.STARTING.value],
     'dest': InstanceState.ERROR.value},

    # Lifecycle operations
    {'trigger': 'stop', 'source': InstanceState.RUNNING.value,
     'dest': InstanceState.STOPPING.value},
    {'trigger': 'stop_complete', 'source': InstanceState.STOPPING.value,
     'dest': InstanceState.STOPPED.value},
    {'trigger': 'start', 'source': [InstanceState.STOPPED.value, InstanceState.ERROR.value, InstanceState.CONTAINER_MISSING.value],
     'dest': InstanceState.STARTING.value},
    {'trigger': 'start_complete', 'source': InstanceState.STARTING.value,
     'dest': InstanceState.RUNNING.value},

    # Restart
    {'trigger': 'restart', 'source': InstanceState.RUNNING.value,
     'dest': InstanceState.RESTARTING.value},
    {'trigger': 'restart_complete', 'source': InstanceState.RESTARTING.value,
     'dest': InstanceState.RUNNING.value},

    # Maintenance
    {'trigger': 'enter_maintenance', 'source': [InstanceState.RUNNING.value, InstanceState.STOPPED.value],
     'dest': InstanceState.MAINTENANCE.value},
    {'trigger': 'exit_maintenance', 'source': InstanceState.MAINTENANCE.value,
     'dest': InstanceState.RUNNING.value, 'conditions': ['was_running_before']},
    {'trigger': 'exit_maintenance', 'source': InstanceState.MAINTENANCE.value,
     'dest': InstanceState.STOPPED.value, 'unless': ['was_running_before']},

    # Pause/Unpause
    {'trigger': 'pause', 'source': InstanceState.RUNNING.value,
     'dest': InstanceState.PAUSED.value},
    {'trigger': 'unpause', 'source': InstanceState.PAUSED.value,
     'dest': InstanceState.RUNNING.value},

    # Error recovery
    {'trigger': 'error', 'source': '*',
     'dest': InstanceState.ERROR.value, 'before': 'save_previous_state'},
    {'trigger': 'recover', 'source': InstanceState.ERROR.value,
     'dest': InstanceState.STOPPED.value},

    # Container issues
    {'trigger': 'container_lost', 'source': [InstanceState.RUNNING.value, InstanceState.STOPPING.value],
     'dest': InstanceState.CONTAINER_MISSING.value},

    # Termination (from most states)
    {'trigger': 'terminate', 'source': [
        InstanceState.STOPPED.value, InstanceState.ERROR.value,
        InstanceState.CONTAINER_MISSING.value, InstanceState.PAUSED.value
    ], 'dest': InstanceState.TERMINATED.value},
]


class InstanceStateMachine:
    """
    State machine for instance lifecycle management.

    Usage:
        instance_data = await get_instance(id)
        sm = InstanceStateMachine(instance_data)

        if sm.can_stop():
            sm.stop()
            await save_instance_state(id, sm.state, sm.error_message)
    """

    def __init__(self, instance_data: Dict[str, Any]):
        self.instance_id = str(instance_data.get('id'))
        self.instance_name = instance_data.get('name', 'unknown')
        self.error_message: Optional[str] = None
        self.previous_state: Optional[str] = None
        self.was_running: bool = False
        self.started_at: Optional[datetime] = instance_data.get('started_at')

        # Initialize state machine
        self.machine = Machine(
            model=self,
            states=STATES,
            transitions=TRANSITIONS,
            initial=instance_data.get('status', InstanceState.CREATING.value),
            auto_transitions=False,  # Disable automatic transitions
            send_event=True  # Pass event data to callbacks
        )

    # Callbacks
    def log_state_enter(self, event):
        """Log state transitions."""
        logger.info(
            "Instance state changed",
            instance_id=self.instance_id,
            instance_name=self.instance_name,
            from_state=event.transition.source,
            to_state=event.transition.dest,
            trigger=event.event.name
        )

    def record_started_at(self, event):
        """Record when instance started running."""
        self.started_at = datetime.utcnow()

    def clear_started_at(self, event):
        """Clear started_at when stopped."""
        self.started_at = None

    def record_error(self, event):
        """Record error message from event data."""
        if event.kwargs.get('error_message'):
            self.error_message = event.kwargs['error_message']

    def save_previous_state(self, event):
        """Save previous state before error transition."""
        self.previous_state = event.transition.source
        self.was_running = event.transition.source == InstanceState.RUNNING.value

    def cleanup_resources(self, event):
        """Placeholder for cleanup logic."""
        logger.info("Instance terminated - cleanup triggered", instance_id=self.instance_id)

    # Conditions
    def was_running_before(self, event) -> bool:
        """Check if instance was running before maintenance."""
        return self.was_running

    # Helper methods
    def get_valid_actions(self) -> List[str]:
        """Get list of valid actions from current state."""
        return [t.name for t in self.machine.get_triggers(self.state)]

    def can_transition_to(self, target_state: str) -> bool:
        """Check if transition to target state is valid."""
        for trigger in self.machine.get_triggers(self.state):
            for transition in self.machine.get_transitions(trigger):
                if transition.dest == target_state:
                    return True
        return False


# Validation function for status updates
async def validate_and_transition(
    instance_id: str,
    target_status: InstanceState,
    error_message: Optional[str] = None,
    get_instance_func: Callable = None
) -> tuple[bool, str]:
    """
    Validate and perform state transition.

    Returns:
        (success, message)
    """
    instance = await get_instance_func(instance_id)
    if not instance:
        return (False, "Instance not found")

    sm = InstanceStateMachine(instance)

    # Find the trigger that leads to target state
    trigger_map = {
        InstanceState.STARTING: 'start',
        InstanceState.RUNNING: 'start_complete',
        InstanceState.STOPPING: 'stop',
        InstanceState.STOPPED: 'stop_complete',
        InstanceState.ERROR: 'error',
        InstanceState.MAINTENANCE: 'enter_maintenance',
        InstanceState.TERMINATED: 'terminate',
    }

    trigger = trigger_map.get(target_status)
    if not trigger:
        return (False, f"No trigger defined for {target_status}")

    # Check if transition is valid
    can_method = getattr(sm, f'can_{trigger}', None)
    if can_method and not can_method():
        return (False, f"Cannot transition from {sm.state} to {target_status.value}")

    # Perform transition
    try:
        trigger_method = getattr(sm, trigger)
        trigger_method(error_message=error_message)
        return (True, sm.state)
    except Exception as e:
        return (False, str(e))
```

### 2.3 Updated Status Update Pattern

```python
# BEFORE: Direct status update without validation
async def _update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    await conn.execute("UPDATE instances SET status = $1 WHERE id = $2", status.value, instance_id)

# AFTER: Validated state transition
from shared.utils.state_machine import validate_and_transition, InstanceState

async def update_instance_status_safe(
    instance_id: str,
    target_status: InstanceState,
    error_message: Optional[str] = None
) -> bool:
    """Update instance status with state machine validation."""

    success, result = await validate_and_transition(
        instance_id=instance_id,
        target_status=target_status,
        error_message=error_message,
        get_instance_func=_get_instance_from_db
    )

    if not success:
        logger.error(
            "Invalid state transition attempted",
            instance_id=instance_id,
            target_status=target_status.value,
            reason=result
        )
        raise InvalidStateTransitionError(result)

    # Persist the validated state
    async with AsyncDatabasePool.acquire() as conn:
        await conn.execute("""
            UPDATE instances
            SET status = $1, error_message = $2, updated_at = $3
            WHERE id = $4
        """, result, error_message, datetime.utcnow(), UUID(instance_id))

    return True


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass
```

---

## Phase 3: Transaction Boundaries & Atomicity

**Priority:** P1 - High
**Effort:** 2 days
**Impact:** Prevents partial failures, ensures data consistency

### 3.1 Current Problems

```python
# PROBLEM: Multi-step operation without transaction
async def _provision_instance_workflow(instance_id: str, db_info: Dict[str, str]):
    # Step 1: Update status (DB write #1)
    await _update_instance_status(instance_id, InstanceStatus.STARTING)

    # Step 2: Deploy K8s resources (external call)
    container_info = await _deploy_odoo_container(instance, db_info)

    # Step 3: Wait for startup (can fail!)
    await _wait_for_odoo_startup(container_info, timeout=300)

    # Step 4: Update network info (DB write #2) - NEVER REACHED IF STEP 3 FAILS!
    await _update_instance_network_info(instance_id, container_info, db_info)

    # Result: K8s resources exist but DB has no record of them
```

### 3.2 Solution: Saga Pattern with Compensation

Based on [asyncpg transaction patterns](https://github.com/magicstack/asyncpg):

**File: `shared/utils/saga.py`**

```python
"""
Saga Pattern Implementation for Multi-Step Operations

Provides:
- Atomic multi-step operations with rollback
- Compensation actions for external systems
- Audit trail for debugging
"""

import asyncio
import logging
from typing import Callable, Any, List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass
class SagaStep:
    """Individual step in a saga."""
    name: str
    action: Callable  # async function to execute
    compensation: Optional[Callable] = None  # async function to rollback
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class SagaContext:
    """Shared context passed between saga steps."""
    instance_id: str
    data: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any):
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Saga:
    """
    Orchestrates multi-step operations with automatic rollback.

    Usage:
        saga = Saga("provision_instance", context)

        saga.add_step(
            name="create_pvc",
            action=create_pvc,
            compensation=delete_pvc
        )
        saga.add_step(
            name="create_deployment",
            action=create_deployment,
            compensation=delete_deployment
        )

        result = await saga.execute()
    """

    def __init__(self, name: str, context: SagaContext):
        self.name = name
        self.context = context
        self.steps: List[SagaStep] = []
        self.completed_steps: List[SagaStep] = []
        self.status = StepStatus.PENDING

    def add_step(
        self,
        name: str,
        action: Callable,
        compensation: Optional[Callable] = None
    ):
        """Add a step to the saga."""
        self.steps.append(SagaStep(
            name=name,
            action=action,
            compensation=compensation
        ))

    async def execute(self) -> Dict[str, Any]:
        """
        Execute all steps in order.
        On failure, compensate completed steps in reverse order.
        """
        logger.info(f"Starting saga: {self.name}", instance_id=self.context.instance_id)
        self.status = StepStatus.RUNNING

        try:
            for step in self.steps:
                await self._execute_step(step)
                self.completed_steps.append(step)

            self.status = StepStatus.COMPLETED
            logger.info(f"Saga completed: {self.name}", instance_id=self.context.instance_id)

            return {
                "status": "success",
                "steps_completed": len(self.completed_steps),
                "context": self.context.data
            }

        except Exception as e:
            self.status = StepStatus.FAILED
            logger.error(
                f"Saga failed: {self.name}",
                instance_id=self.context.instance_id,
                failed_step=step.name,
                error=str(e)
            )

            # Compensate in reverse order
            await self._compensate()

            raise SagaFailedError(
                saga_name=self.name,
                failed_step=step.name,
                error=str(e),
                compensated_steps=[s.name for s in self.completed_steps if s.status == StepStatus.COMPENSATED]
            )

    async def _execute_step(self, step: SagaStep):
        """Execute a single step."""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.utcnow()

        logger.info(f"Executing step: {step.name}", saga=self.name)

        try:
            step.result = await step.action(self.context)
            step.status = StepStatus.COMPLETED
            step.completed_at = datetime.utcnow()

            logger.info(f"Step completed: {step.name}", saga=self.name)

        except Exception as e:
            step.status = StepStatus.FAILED
            step.error = str(e)
            step.completed_at = datetime.utcnow()
            raise

    async def _compensate(self):
        """Run compensation for completed steps in reverse order."""
        logger.info(f"Starting compensation for saga: {self.name}")

        for step in reversed(self.completed_steps):
            if step.compensation is None:
                logger.warning(f"No compensation for step: {step.name}")
                continue

            try:
                logger.info(f"Compensating step: {step.name}")
                await step.compensation(self.context)
                step.status = StepStatus.COMPENSATED
                logger.info(f"Step compensated: {step.name}")

            except Exception as e:
                logger.error(
                    f"Compensation failed for step: {step.name}",
                    error=str(e)
                )
                # Continue compensating other steps


class SagaFailedError(Exception):
    """Raised when a saga fails."""

    def __init__(self, saga_name: str, failed_step: str, error: str, compensated_steps: List[str]):
        self.saga_name = saga_name
        self.failed_step = failed_step
        self.error = error
        self.compensated_steps = compensated_steps
        super().__init__(f"Saga '{saga_name}' failed at step '{failed_step}': {error}")
```

### 3.3 Updated Provisioning with Saga

```python
# provisioning.py - Using Saga pattern

from shared.utils.saga import Saga, SagaContext, SagaFailedError

async def _provision_instance_workflow(instance_id: str, db_info: Dict[str, str]) -> Dict[str, Any]:
    """Provisioning workflow with saga pattern for automatic rollback."""

    context = SagaContext(instance_id=instance_id)
    context.set('db_info', db_info)

    # Load instance data
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")
    context.set('instance', instance)

    # Build saga
    saga = Saga("provision_instance", context)

    saga.add_step(
        name="update_status_starting",
        action=_step_update_status_starting,
        compensation=_compensate_status_creating
    )

    saga.add_step(
        name="create_pvc",
        action=_step_create_pvc,
        compensation=_compensate_delete_pvc
    )

    saga.add_step(
        name="create_deployment",
        action=_step_create_deployment,
        compensation=_compensate_delete_deployment
    )

    saga.add_step(
        name="wait_for_startup",
        action=_step_wait_for_startup,
        compensation=None  # No compensation needed
    )

    saga.add_step(
        name="update_network_info",
        action=_step_update_network_info,
        compensation=None  # No compensation needed
    )

    saga.add_step(
        name="mark_running",
        action=_step_mark_running,
        compensation=_compensate_mark_error
    )

    try:
        result = await saga.execute()
        return result
    except SagaFailedError as e:
        # Saga already compensated, update final status
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


# Step implementations
async def _step_create_pvc(context: SagaContext) -> str:
    """Create PVC for instance storage."""
    instance = context.get('instance')
    client = KubernetesClient()

    pvc_name = f"odoo-instance-{instance['id'].hex}"
    storage_limit = instance.get('storage_limit', '10G') + 'i'

    client.create_instance_pvc(pvc_name, storage_limit)
    client.wait_for_pvc_bound(pvc_name, timeout=60)

    context.set('pvc_name', pvc_name)
    return pvc_name


async def _compensate_delete_pvc(context: SagaContext):
    """Delete PVC on failure."""
    pvc_name = context.get('pvc_name')
    if pvc_name:
        try:
            client = KubernetesClient()
            client.delete_pvc(pvc_name)
        except Exception as e:
            logger.warning(f"Failed to delete PVC during compensation: {e}")
```

### 3.4 Database Transaction Wrapper

```python
# For operations that are purely database
from shared.utils.async_db_pool import AsyncDatabasePool

async def create_instance_transactional(instance_data: InstanceCreate) -> Instance:
    """Create instance with all related records in a transaction."""

    async with AsyncDatabasePool.acquire() as conn:
        # Start transaction
        async with conn.transaction():
            # Check uniqueness (within transaction - prevents race)
            existing = await conn.fetchrow(
                "SELECT id FROM instances WHERE database_name = $1 FOR UPDATE",
                instance_data.database_name
            )
            if existing:
                raise ValueError(f"Database name already exists")

            # Insert instance
            instance_id = await conn.fetchval(
                "INSERT INTO instances (...) VALUES (...) RETURNING id",
                ...
            )

            # Insert related records
            await conn.execute(
                "INSERT INTO instance_audit_log (instance_id, action) VALUES ($1, 'created')",
                instance_id
            )

            # All or nothing - commits only if no exception
            return await _get_instance_by_id(conn, instance_id)
```

---

## Phase 4: Error Handling & Silent Failure Elimination

**Priority:** P0 - Ship Blocker
**Effort:** 1 day
**Impact:** Makes failures visible, enables proper error recovery

### 4.1 Current Problems

```python
# PROBLEM 1: Silent failure - email error swallowed
try:
    await send_instance_ready_email(...)
except Exception as e:
    logger.warning("Failed to send email", error=str(e))  # Swallowed!

# PROBLEM 2: Exception in loop swallowed
while (datetime.utcnow() - start_time).seconds < timeout:
    try:
        response = await client.get(url, timeout=10)
    except Exception:
        pass  # Completely silent!

# PROBLEM 3: Returns None on error instead of raising
except Exception as e:
    logger.error("Failed to get instance", error=str(e))
    return None  # Caller has no idea there was an error!
```

### 4.2 Solution: Explicit Error Handling Policy

**File: `shared/utils/errors.py`**

```python
"""
Error Handling Policy for SaaSOdoo

Rules:
1. NEVER swallow exceptions silently
2. Non-critical failures should be logged AND reported to monitoring
3. Critical failures must propagate
4. All errors should have correlation IDs
"""

import logging
import functools
from typing import Callable, TypeVar, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels."""
    CRITICAL = "critical"    # Must propagate, blocks operation
    HIGH = "high"            # Should propagate, may be recoverable
    MEDIUM = "medium"        # Log and continue, but track
    LOW = "low"              # Log only, non-essential feature


class OperationError(Exception):
    """Base exception with context."""

    def __init__(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.HIGH,
        correlation_id: Optional[str] = None,
        context: Optional[dict] = None
    ):
        self.message = message
        self.severity = severity
        self.correlation_id = correlation_id
        self.context = context or {}
        super().__init__(message)


class NonCriticalError(OperationError):
    """Error that should be logged but not propagated."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, severity=ErrorSeverity.MEDIUM, **kwargs)


def handle_non_critical(
    default_return: Any = None,
    error_message: str = "Non-critical operation failed"
):
    """
    Decorator for non-critical operations that should not block main flow.

    - Logs the error with full context
    - Reports to monitoring (future: Sentry/Datadog)
    - Returns default value instead of propagating

    Usage:
        @handle_non_critical(default_return=False, error_message="Email send failed")
        async def send_notification_email(email: str, ...):
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Full logging with context
                logger.error(
                    error_message,
                    error=str(e),
                    error_type=type(e).__name__,
                    function=func.__name__,
                    args_summary=str(args)[:200],
                    severity=ErrorSeverity.MEDIUM.value
                )

                # TODO: Report to monitoring service
                # await report_to_monitoring(e, context={...})

                return default_return

        return wrapper
    return decorator


def require_result(error_message: str = "Operation returned None"):
    """
    Decorator that raises if function returns None.
    Eliminates silent None returns on errors.

    Usage:
        @require_result("Instance not found")
        async def get_instance(id: str) -> Instance:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            result = await func(*args, **kwargs)
            if result is None:
                raise OperationError(
                    error_message,
                    severity=ErrorSeverity.HIGH,
                    context={"args": str(args)[:200]}
                )
            return result

        return wrapper
    return decorator
```

### 4.3 Updated Code Patterns

```python
# BEFORE: Silent email failure
try:
    await send_instance_ready_email(...)
except Exception as e:
    logger.warning("Failed to send email", error=str(e))

# AFTER: Explicit non-critical handling
from shared.utils.errors import handle_non_critical

@handle_non_critical(default_return=False, error_message="Failed to send instance ready email")
async def send_instance_ready_email_safe(
    email: str,
    first_name: str,
    instance_name: str,
    instance_url: str,
    admin_email: str,
    admin_password: str
) -> bool:
    """Send instance ready email with explicit error handling."""
    await send_instance_ready_email(
        email=email,
        first_name=first_name,
        instance_name=instance_name,
        instance_url=instance_url,
        admin_email=admin_email,
        admin_password=admin_password
    )
    return True

# Usage - no try/except needed, errors are handled
email_sent = await send_instance_ready_email_safe(...)
if not email_sent:
    logger.info("Continuing without email notification")


# BEFORE: Exception swallowed in health check
while ...:
    try:
        response = await client.get(url)
    except Exception:
        pass

# AFTER: Track failures, provide visibility
async def wait_for_odoo_startup_safe(
    container_info: Dict[str, Any],
    timeout: int = 300,
    check_interval: int = 10
) -> bool:
    """Wait for Odoo with failure tracking."""
    url = container_info['internal_url']
    start_time = datetime.utcnow()
    failures = []

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(url, timeout=10)
                if response.status_code in [200, 302, 303]:
                    logger.info("Odoo startup confirmed", url=url, attempts=len(failures) + 1)
                    return True

                failures.append(f"HTTP {response.status_code}")

            except httpx.TimeoutException:
                failures.append("timeout")
            except httpx.ConnectError as e:
                failures.append(f"connection_error: {e}")
            except Exception as e:
                failures.append(f"unexpected: {type(e).__name__}: {e}")

            # Log progress every 30 seconds
            if len(failures) % 3 == 0:
                logger.info(
                    "Waiting for Odoo startup",
                    url=url,
                    elapsed_seconds=(datetime.utcnow() - start_time).seconds,
                    failure_count=len(failures),
                    last_failures=failures[-3:]
                )

            await asyncio.sleep(check_interval)

    # Timeout - raise with full context
    raise TimeoutError(
        f"Odoo did not start within {timeout} seconds. "
        f"Total attempts: {len(failures)}. "
        f"Last errors: {failures[-5:]}"
    )
```

---

## Phase 5: Celery Retry & Dead Letter Queue

**Priority:** P2 - Medium
**Effort:** 1 day
**Impact:** Automatic recovery from transient failures

### 5.1 Current Problems

```python
# PROBLEM: No automatic retries
@celery_app.task(bind=True)  # max_retries defaults to 3 but no autoretry_for!
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    ...  # Fails once = permanent failure
```

### 5.2 Solution: Celery Retry with Exponential Backoff

Based on [Celery retry patterns](https://docs.celeryq.dev/en/stable/userguide/tasks.html):

**File: `services/instance-service/app/celery_config.py` (updated)**

```python
"""
Celery Configuration with Retry Policies

Based on Celery best practices:
- Exponential backoff with jitter
- Separate retry policies per task type
- Dead letter queue for permanent failures
"""

from celery import Celery, Task
from kombu import Queue, Exchange
import os

# Base task class with retry configuration
class BaseTaskWithRetry(Task):
    """Base task with sensible retry defaults."""

    # Retry on these exceptions
    autoretry_for = (
        ConnectionError,
        TimeoutError,
        OSError,
    )

    # Retry configuration
    max_retries = 3
    retry_backoff = True           # Enable exponential backoff
    retry_backoff_max = 600        # Max 10 minutes between retries
    retry_jitter = True            # Add randomness to prevent thundering herd

    # Don't retry on these
    dont_autoretry_for = (
        ValueError,
        KeyError,
        TypeError,
    )


class ProvisioningTask(BaseTaskWithRetry):
    """Task class for provisioning operations - longer timeouts."""
    max_retries = 5
    retry_backoff_max = 900  # 15 minutes max


class LifecycleTask(BaseTaskWithRetry):
    """Task class for lifecycle operations - quick retries."""
    max_retries = 3
    retry_backoff_max = 60  # 1 minute max


class MaintenanceTask(BaseTaskWithRetry):
    """Task class for maintenance operations - moderate retries."""
    max_retries = 3
    retry_backoff_max = 300  # 5 minutes max


# Dead letter queue configuration
CELERY_TASK_QUEUES = (
    Queue('instance_provisioning', Exchange('instance'), routing_key='instance.provision'),
    Queue('instance_operations', Exchange('instance'), routing_key='instance.operation'),
    Queue('instance_maintenance', Exchange('instance'), routing_key='instance.maintenance'),
    Queue('instance_monitoring', Exchange('instance'), routing_key='instance.monitor'),
    # Dead letter queue for failed tasks
    Queue('dead_letter', Exchange('dead_letter'), routing_key='dead_letter'),
)

# Task routing
CELERY_TASK_ROUTES = {
    'app.tasks.provisioning.*': {'queue': 'instance_provisioning'},
    'app.tasks.lifecycle.*': {'queue': 'instance_operations'},
    'app.tasks.maintenance.*': {'queue': 'instance_maintenance'},
    'app.tasks.monitoring.*': {'queue': 'instance_monitoring'},
}


def create_celery_app():
    app = Celery('instance_service')

    app.conf.update(
        broker_url=os.getenv('CELERY_BROKER_URL'),
        result_backend=os.getenv('CELERY_RESULT_BACKEND'),

        # Task execution settings
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,

        # Time limits
        task_time_limit=1800,      # 30 minutes hard limit
        task_soft_time_limit=1500, # 25 minutes soft limit

        # Retry settings (defaults, can be overridden per task)
        task_default_retry_delay=60,

        # Dead letter handling
        task_acks_on_failure_or_timeout=True,

        # Queues
        task_queues=CELERY_TASK_QUEUES,
        task_routes=CELERY_TASK_ROUTES,
    )

    return app


celery_app = create_celery_app()
```

### 5.3 Updated Task Definitions

```python
# provisioning.py

from app.celery_config import celery_app, ProvisioningTask
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@celery_app.task(
    bind=True,
    base=ProvisioningTask,
    name='instance.provision',
    queue='instance_provisioning',
    autoretry_for=(httpx.ConnectError, httpx.TimeoutException, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=900,
    max_retries=5
)
def provision_instance_task(self, instance_id: str, db_info: Dict[str, str]):
    """
    Provision instance with automatic retry on transient failures.

    Retry behavior:
    - Retries: 5 attempts
    - Backoff: 1s, 2s, 4s, 8s, 16s (capped at 15min)
    - Jitter: Yes (prevents thundering herd)
    """
    try:
        logger.info(
            "Starting provisioning",
            instance_id=instance_id,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries
        )

        result = asyncio.run(_provision_instance_workflow_safe(instance_id, db_info))
        return result

    except self.autoretry_for as e:
        logger.warning(
            "Transient error, will retry",
            instance_id=instance_id,
            error=str(e),
            attempt=self.request.retries + 1
        )
        raise  # Celery will auto-retry

    except Exception as e:
        logger.error(
            "Permanent failure, sending to dead letter",
            instance_id=instance_id,
            error=str(e)
        )
        # Update instance status
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))

        # Send to dead letter queue for manual review
        send_to_dead_letter.delay({
            'task': 'provision_instance',
            'instance_id': instance_id,
            'error': str(e),
            'retries': self.request.retries
        })

        raise


@celery_app.task(queue='dead_letter')
def send_to_dead_letter(payload: dict):
    """Store failed task for manual review."""
    logger.error("Task moved to dead letter queue", payload=payload)
    # TODO: Store in database, send alert
```

---

## Phase 6: Input Validation & Security

**Priority:** P1 - High
**Effort:** 1 day
**Impact:** Prevents injection attacks, ensures data integrity

### 6.1 Current Problems

```python
# PROBLEM 1: No validation of db_info keys
db_info = {
    'db_host': db_allocation.get('db_host'),  # Could be None!
    'db_password': db_allocation.get('db_password')
}
# Later used without checking:
'ODOO_DATABASE_HOST': db_info['db_host'],  # KeyError if missing

# PROBLEM 2: Hardcoded fallback password
db_info = {
    'db_password': instance.get('database_password', 'odoo_pass')  # SECURITY ISSUE!
}

# PROBLEM 3: No authorization check
@router.delete("/{instance_id}")
async def delete_instance(instance_id: UUID, ...):
    # Anyone can delete any instance!
    instance = await db.get_instance(instance_id)
```

### 6.2 Solution: Pydantic Validation & Authorization

```python
# shared/schemas/validation.py

from pydantic import BaseModel, Field, validator
from typing import Optional
from uuid import UUID


class DatabaseInfo(BaseModel):
    """Validated database connection info."""

    db_server_id: Optional[str] = None
    db_host: str = Field(..., min_length=1, description="Database host")
    db_port: int = Field(..., ge=1, le=65535, description="Database port")
    db_name: str = Field(..., min_length=1, max_length=63, regex=r'^[a-z][a-z0-9_]*$')
    db_user: str = Field(..., min_length=1, max_length=63)
    db_password: str = Field(..., min_length=8, description="Database password")

    @validator('db_password')
    def password_not_default(cls, v):
        forbidden = ['odoo_pass', 'password', 'changeme', '12345678']
        if v.lower() in forbidden:
            raise ValueError('Password cannot be a default/weak value')
        return v

    class Config:
        extra = 'forbid'  # Reject unknown fields


# Usage
def validate_db_info(raw_data: dict) -> DatabaseInfo:
    """Validate and parse database info."""
    try:
        return DatabaseInfo(**raw_data)
    except ValidationError as e:
        raise ValueError(f"Invalid database info: {e}")


# Authorization decorator
from functools import wraps
from fastapi import HTTPException

def require_instance_ownership(func):
    """Verify user owns the instance before allowing action."""

    @wraps(func)
    async def wrapper(
        instance_id: UUID,
        current_user: User = Depends(get_current_user),
        db: InstanceDatabase = Depends(get_database),
        *args,
        **kwargs
    ):
        instance = await db.get_instance(instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")

        if instance.customer_id != current_user.id:
            logger.warning(
                "Unauthorized access attempt",
                instance_id=str(instance_id),
                owner_id=str(instance.customer_id),
                requester_id=str(current_user.id)
            )
            raise HTTPException(status_code=403, detail="Not authorized to access this instance")

        return await func(instance_id, current_user, db, *args, **kwargs)

    return wrapper


# Updated route with authorization
@router.delete("/{instance_id}")
@require_instance_ownership
async def delete_instance(
    instance_id: UUID,
    current_user: User = Depends(get_current_user),
    db: InstanceDatabase = Depends(get_database)
):
    """Delete instance - requires ownership."""
    ...
```

---

## Phase 7: Observability & Correlation

**Priority:** P2 - Medium
**Effort:** 1 day
**Impact:** Enables debugging, performance monitoring

### 7.1 Solution: Correlation IDs & Structured Logging

```python
# shared/utils/correlation.py

import uuid
from contextvars import ContextVar
from typing import Optional

# Context variable for correlation ID
correlation_id_var: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one."""
    cid = correlation_id_var.get()
    if cid is None:
        cid = str(uuid.uuid4())[:8]
        correlation_id_var.set(cid)
    return cid


def set_correlation_id(cid: str):
    """Set correlation ID (e.g., from incoming request header)."""
    correlation_id_var.set(cid)


# FastAPI middleware
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        cid = request.headers.get('X-Correlation-ID') or str(uuid.uuid4())[:8]
        set_correlation_id(cid)

        # Add to response headers
        response = await call_next(request)
        response.headers['X-Correlation-ID'] = cid

        return response


# Celery task with correlation
@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str, db_info: dict, correlation_id: str = None):
    if correlation_id:
        set_correlation_id(correlation_id)

    logger.info("Starting task", correlation_id=get_correlation_id())
    ...


# Updated logger configuration
import structlog

def configure_logging():
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            add_correlation_id,  # Custom processor
            structlog.processors.JSONRenderer()
        ]
    )


def add_correlation_id(logger, method_name, event_dict):
    """Add correlation ID to all log entries."""
    event_dict['correlation_id'] = get_correlation_id()
    return event_dict
```

---

## Implementation Priority Matrix

| Phase | Priority | Effort | Dependencies | Ship Blocker? |
|-------|----------|--------|--------------|---------------|
| Phase 1: Distributed Locking | P0 | 2 days | Redis | Yes |
| Phase 2: State Machine | P0 | 2 days | None | Yes |
| Phase 4: Error Handling | P0 | 1 day | None | Yes |
| Phase 3: Transactions/Saga | P1 | 2 days | Phase 1 | No |
| Phase 6: Validation/Security | P1 | 1 day | None | No |
| Phase 5: Celery Retry | P2 | 1 day | None | No |
| Phase 7: Observability | P2 | 1 day | None | No |

**Total Estimated Effort:** 10 days

---

## Testing Strategy

### Unit Tests

```python
# tests/unit/test_state_machine.py
import pytest
from shared.utils.state_machine import InstanceStateMachine, InstanceState

def test_valid_transition_creating_to_starting():
    instance = {'id': 'test', 'status': 'creating'}
    sm = InstanceStateMachine(instance)

    assert sm.can_start_provisioning()
    sm.start_provisioning()
    assert sm.state == 'starting'

def test_invalid_transition_stopped_to_stopping():
    instance = {'id': 'test', 'status': 'stopped'}
    sm = InstanceStateMachine(instance)

    assert not sm.can_stop()


# tests/unit/test_distributed_lock.py
@pytest.mark.asyncio
async def test_lock_prevents_concurrent_access():
    async with DistributedLockManager.lock("test:resource"):
        # Should fail to acquire same lock
        with pytest.raises(LockAcquisitionError):
            async with DistributedLockManager.lock("test:resource", blocking_timeout=1):
                pass
```

### Integration Tests

```python
# tests/integration/test_idempotency.py
@pytest.mark.asyncio
async def test_duplicate_provision_request_returns_cached():
    # First request
    result1 = await provision_instance_workflow_safe(instance_id, db_info, "key1")
    assert result1['status'] == 'success'

    # Duplicate request with same idempotency key
    result2 = await provision_instance_workflow_safe(instance_id, db_info, "key1")
    assert result2['cached'] == True
```

---

## Rollout Plan

### Week 1: Ship Blockers (P0)
- Phase 1: Distributed Locking
- Phase 2: State Machine
- Phase 4: Error Handling

### Week 2: High Priority (P1)
- Phase 3: Transaction Boundaries
- Phase 6: Input Validation

### Week 3: Medium Priority (P2)
- Phase 5: Celery Retry
- Phase 7: Observability

---

## Appendix: Context7 Documentation References

### Redis Distributed Locking
- `r.lock('resource:lock', timeout=10)` - Auto-expiring locks
- Context manager pattern: `with r.lock(...) as lock:`
- Lock extension: `lock.extend(additional_time)`
- Non-blocking: `lock.acquire(blocking=False)`

### Celery Retry Patterns
- `autoretry_for=(Exception,)` - Auto-retry on exceptions
- `retry_backoff=True` - Exponential backoff (1s, 2s, 4s, ...)
- `retry_backoff_max=600` - Cap backoff at 10 minutes
- `retry_jitter=True` - Prevent thundering herd

### Transitions State Machine
- State callbacks: `on_enter`, `on_exit`
- Transition conditions: `conditions`, `unless`
- Callback order: prepare → conditions → before → state_change → after

### Asyncpg Transactions
- `async with conn.transaction():` - Auto commit/rollback
- Nested transactions use savepoints
- Manual: `tr.start()`, `tr.commit()`, `tr.rollback()`

### Tenacity Retry
- `@retry(stop=stop_after_attempt(3))`
- `wait=wait_exponential(multiplier=1, min=4, max=10)`
- `before_sleep=before_sleep_log(logger, logging.INFO)`

---

**Document Version:** 1.0
**Last Updated:** 2025-12-29
**Author:** Claude Code Analysis
