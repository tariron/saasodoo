# Docker Events-Based Status Synchronization Plan

## Executive Summary

This plan addresses the transition from bulk reconciliation-based status updates to real-time Docker events-driven status synchronization. The goal is to ensure `db_status` accurately reflects Docker service state in real-time, while maintaining proper transitional states (e.g., `starting`, `stopping`) during lifecycle operations.

### Key Implementation Details

1. **Service DNS over IP**: Uses Docker Swarm internal DNS (`http://service-name:8069`) for health checks instead of scraping task IPs
2. **Atomic Updates**: All status updates include `WHERE status IN (...)` conditions to prevent race conditions
3. **Task Filtering**: Uses `service.tasks(filters={'desired-state': 'running'})` to reduce API payload size
4. **Event Settling**: 2-second `countdown` delay before processing events to let Docker Swarm state stabilize
5. **Non-Blocking Health Checks**: Separate Celery task (`perform_odoo_health_check_and_update`) queued asynchronously

## Current State Analysis

### Existing Architecture
- **Docker Events Monitor**: `services/instance-service/app/tasks/monitoring.py`
  - Monitors Docker Swarm service events (`create`, `update`, `remove`)
  - Currently triggers bulk reconciliation on `update` events
  - Directly updates DB for `create` and `remove` events

- **Lifecycle Tasks**: `services/instance-service/app/tasks/lifecycle.py`
  - `start_instance_task`: Sets `starting` → waits for Docker → relies on reconciliation for `running`
  - `stop_instance_task`: Sets `stopping` → stops Docker → relies on reconciliation for `stopped`
  - `restart_instance_task`: Sets `restarting` → restarts Docker → relies on reconciliation

- **Reconciliation Task**: `reconcile_instance_statuses_task()`
  - Bulk checks all non-terminated instances
  - Compares DB status with Docker task states
  - Updates mismatches

### Problems with Current Approach
1. **Bulk reconciliation is heavy**: Checks ALL instances periodically, wasteful
2. **Status update lag**: Depends on reconciliation schedule (not real-time)
3. **Race conditions**: Lifecycle tasks and reconciliation can conflict
4. **Imprecise**: Can't distinguish scale events from restarts/failures
5. **No transitional state confirmation**: `starting`/`stopping` states depend on external reconciliation

### Production Considerations (Pre-Implementation)

1. **Database Connection Pooling**:
   - Risk: Mass-update events could spike DB connections (one per event)
   - Mitigation: Ensure PostgreSQL `max_connections` is adequate or implement connection pooling in Celery worker initialization

2. **Task State API Filtering**:
   - Use `service.tasks(filters={'desired-state': 'running'})` to reduce payload size
   - Avoid fetching full historical task data

3. **Event Deduplication Window**:
   - 5-second window may need tuning for rapidly flapping services
   - Consider adding 1-2 second `countdown` delay to task queuing for state settling

4. **Atomic Status Updates**:
   - Always include WHERE condition to prevent regressing state
   - Example: `WHERE id = $1 AND status IN ('starting', 'restarting')`

## Proposed Architecture

### Core Principle
**Docker events are the single source of truth for status transitions to `running` and `stopped` states.**

### Status Flow Design

#### Start Operation Flow (Non-Blocking)
```
User clicks "Start"
  → API sets DB status to `starting`
  → Celery task queued (start_instance_task)
  → Task performs Docker scale-up operation (scale to 1 replica)
  → Task waits for Odoo HTTP availability (internal check)
  → Task completes (DB still shows `starting`)
  → Docker event monitor detects service `update` event with running task
  → Event monitor verifies task state = `running`
  → Event monitor queues health check task (perform_odoo_health_check_and_update)
  → Event monitor returns immediately (non-blocking)
  → Health check task waits for Odoo HTTP (up to 60s, retries every 5s)
  → Health check task updates DB status to `running` after successful ping
```

#### Manual Start by DevOps Flow (Non-Blocking)
```
DevOps engineer manually scales service up in Docker
  → Docker event monitor detects service `update` event with running task
  → Event monitor checks current DB status = `stopped`
  → Event monitor sets DB status to `starting` first
  → Event monitor verifies task state = `running`
  → Event monitor queues health check task (perform_odoo_health_check_and_update)
  → Event monitor returns immediately (non-blocking)
  → Health check task waits for Odoo HTTP (up to 60s, retries every 5s)
  → Health check task updates DB status to `running` after successful ping
```

#### Stop Operation Flow
```
User clicks "Stop"
  → API sets DB status to `stopping`
  → Celery task queued (stop_instance_task)
  → Task performs Docker scale-down operation (scale to 0 replicas)
  → Task waits for all tasks to reach shutdown state
  → Task completes (DB still shows `stopping`)
  → Docker event monitor detects service `update` event with 0 running tasks
  → Event monitor verifies no running tasks
  → Event monitor updates DB status to `stopped`
```

#### Restart Operation Flow
```
User clicks "Restart"
  → API sets DB status to `restarting`
  → Celery task queued (restart_instance_task)
  → Task performs Docker force update operation
  → Task waits for new task to be running
  → Task waits for Odoo HTTP availability
  → Task completes (DB still shows `restarting`)
  → Docker event monitor detects service `update` event with running task
  → Event monitor verifies task state = `running`
  → Event monitor updates DB status to `running`
```

### Update/Restore Operations
- **Update**: Uses existing `update_instance_task` flow
  - Sets status to `updating` → performs update → sets to `running` on success
  - Docker events monitoring remains passive (no interference)

- **Restore**: Uses existing `restore_instance_task` flow
  - Sets status to `maintenance` → performs restore → sets to appropriate state
  - Docker events monitoring remains passive

**Key Point**: Update and restore operations maintain their own status management. Docker events only monitor start/stop/restart lifecycle operations.

## Implementation Plan

### Phase 1: Enhance Docker Event Monitor

#### 1.1 Improve Service Event Detection
**File**: `services/instance-service/app/tasks/monitoring.py`

**Changes to `_process_service_event()` method:**

```python
def _process_service_event(self, event: Dict[str, Any]):
    """Process Docker Swarm service event with enhanced task state checking"""

    # Extract event metadata
    event_type = event.get('Action', '').lower()
    service_name = event.get('Actor', {}).get('Attributes', {}).get('name', '')

    # Validate SaaS service
    service_info = self._is_saasodoo_service(service_name)
    if not service_info:
        return

    # Get full instance ID
    instance_id = self._get_instance_id_from_hex(service_info['instance_id_hex'])
    if not instance_id:
        return

    # Handle different event types
    if event_type == 'create':
        # Service creation → set to CREATING
        update_instance_status_from_event.delay(
            instance_id,
            InstanceStatus.CREATING.value,
            event_type,
            service_name,
            event.get('time', datetime.utcnow().isoformat())
        )

    elif event_type == 'remove':
        # Service removal → set to TERMINATED
        update_instance_status_from_event.delay(
            instance_id,
            InstanceStatus.TERMINATED.value,
            event_type,
            service_name,
            event.get('time', datetime.utcnow().isoformat())
        )

    elif event_type == 'update':
        # Service update → check task states to determine status
        # This is where we handle start/stop/restart operations
        # IMPORTANT: Non-blocking - queues a separate task with 2-second delay for state settling
        check_service_task_state_and_health.apply_async(
            args=[instance_id, service_name],
            countdown=2  # 2-second delay to let Docker Swarm state settle
        )
```

#### 1.2 Add New Task: `check_service_task_state_and_health`
**New Celery task** to inspect service task states and queue health check if needed.

```python
@celery_app.task(bind=True)
def check_service_task_state_and_health(self, instance_id: str, service_name: str):
    """
    Check Docker service task states and queue health check if needed

    This task is triggered by service 'update' events and determines
    whether the service is running, stopped, or in another state.

    IMPORTANT: This task does NOT block on health checks. Instead, it queues
    a separate health check task if the service is being scaled up.
    """
    try:
        result = asyncio.run(_check_service_task_state_and_health(instance_id, service_name))
        return result
    except Exception as e:
        logger.error("Failed to check service task state",
                    instance_id=instance_id,
                    service_name=service_name,
                    error=str(e))
        raise

async def _check_service_task_state_and_health(instance_id: str, service_name: str) -> Dict[str, Any]:
    """
    Analyze service task states and queue health check if upscale detected

    Rules:
    - If running tasks > 0 AND current_status in [starting, restarting, stopped] → queue health check task
    - If running tasks == 0 AND current_status == stopping → set to stopped immediately
    - If failed tasks > 0 AND no running tasks → set to error immediately
    - Otherwise → no change (avoid interfering with update/restore operations)

    IMPORTANT: Does NOT perform health check directly - queues separate task
    IMPORTANT: Handles manual DevOps operations (stopped → starting)
    """
    try:
        # Get current instance and network info from DB
        conn = await _get_db_connection()
        try:
            instance_row = await conn.fetchrow(
                "SELECT status, internal_url, database_name FROM instances WHERE id = $1",
                UUID(instance_id)
            )

            if not instance_row:
                logger.warning("Instance not found", instance_id=instance_id)
                return {"updated": False, "reason": "instance_not_found"}

            current_status = instance_row['status']
            internal_url = instance_row['internal_url']
            database_name = instance_row['database_name']

            # Skip if instance is terminated (final state)
            if current_status == 'terminated':
                return {"updated": False, "reason": "instance_terminated"}

            # Get Docker service and task states
            client = docker.from_env()
            service = client.services.get(service_name)

            # Filter for running tasks only to reduce payload size
            tasks = service.tasks(filters={'desired-state': 'running'})

            running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
            failed_tasks = [t for t in tasks if t['Status']['State'] == 'failed']

            # Also get all tasks to check for failures/shutdown
            all_tasks = service.tasks()
            all_failed_tasks = [t for t in all_tasks if t['Status']['State'] == 'failed']

            # Determine target status based on task states and current status
            target_status = None
            should_queue_health_check = False

            # Rule 1: Upscale detected from lifecycle operation (starting/restarting)
            if len(running_tasks) > 0 and current_status in ['starting', 'restarting']:
                # Don't update to RUNNING yet - queue health check task instead
                should_queue_health_check = True
                logger.info("Detected upscale from lifecycle operation - queueing health check",
                          instance_id=instance_id,
                          current_status=current_status,
                          running_tasks=len(running_tasks))

            # Rule 1b: Manual DevOps scale-up detected (stopped → starting)
            elif len(running_tasks) > 0 and current_status == 'stopped':
                # First transition to 'starting' to indicate manual operation detected
                logger.info("Manual DevOps scale-up detected",
                          instance_id=instance_id,
                          running_tasks=len(running_tasks))

                await conn.execute("""
                    UPDATE instances
                    SET status = $1, updated_at = $2
                    WHERE id = $3
                """, InstanceStatus.STARTING.value, datetime.utcnow(), UUID(instance_id))

                # Queue health check to transition from starting → running
                should_queue_health_check = True

            # Rule 2: Transition from stopping to stopped
            elif len(running_tasks) == 0 and current_status == 'stopping':
                target_status = InstanceStatus.STOPPED.value
                logger.info("Transitioning to STOPPED",
                          instance_id=instance_id,
                          current_status=current_status)

            # Rule 3: Detect failures
            elif len(all_failed_tasks) > 0 and len(running_tasks) == 0:
                target_status = InstanceStatus.ERROR.value
                error_msg = f"Service tasks failed: {len(all_failed_tasks)} failed tasks"
                logger.error("Service failure detected",
                           instance_id=instance_id,
                           failed_tasks=len(all_failed_tasks))

            # Rule 4: No change for other states (update, restore, maintenance, etc.)
            else:
                logger.debug("No status update needed",
                           instance_id=instance_id,
                           current_status=current_status,
                           running_tasks=len(running_tasks),
                           failed_tasks=len(failed_tasks))
                return {
                    "updated": False,
                    "reason": "no_transition_needed",
                    "current_status": current_status,
                    "running_tasks": len(running_tasks)
                }

            # Queue health check task if upscale detected
            if should_queue_health_check:
                # Use Docker Swarm internal DNS name (more reliable than IP scraping)
                # Format: service_name is already "odoo-{database_name}-{instance_id_hex}"
                # Docker's internal DNS resolver handles routing to the correct task
                internal_url = f'http://{service_name}:8069'

                logger.info("Using Docker Swarm DNS for health check",
                          instance_id=instance_id,
                          service_name=service_name,
                          internal_url=internal_url)

                # Queue health check task (non-blocking)
                logger.info("Queueing Odoo health check task",
                          instance_id=instance_id,
                          internal_url=internal_url)

                perform_odoo_health_check_and_update.delay(
                    instance_id,
                    internal_url,
                    current_status
                )

                return {
                    "updated": False,
                    "reason": "health_check_queued",
                    "current_status": current_status,
                    "internal_url": internal_url
                }

            # Update database with target status (atomic update with state validation)
            if target_status and target_status != current_status:
                # For STOPPED transitions: only if currently stopping
                # For ERROR transitions: allow from any non-terminated state
                if target_status == InstanceStatus.STOPPED.value:
                    valid_states = ['stopping']
                elif target_status == InstanceStatus.ERROR.value:
                    valid_states = ['starting', 'restarting', 'stopping', 'running', 'stopped']
                else:
                    valid_states = [current_status]  # Should not happen

                result = await conn.execute("""
                    UPDATE instances
                    SET status = $1, updated_at = $2, last_health_check = $3
                    WHERE id = $4 AND status = ANY($5)
                """, target_status, datetime.utcnow(), datetime.utcnow(), UUID(instance_id), valid_states)

                # Check if update actually occurred
                if result == 'UPDATE 0':
                    logger.warning("Status update blocked - instance state changed",
                                 instance_id=instance_id,
                                 expected_status=current_status,
                                 target_status=target_status)
                    return {
                        "updated": False,
                        "reason": "state_changed_race_condition",
                        "target_status": target_status
                    }

                logger.info("Instance status updated from Docker event",
                          instance_id=instance_id,
                          old_status=current_status,
                          new_status=target_status)

                return {
                    "updated": True,
                    "old_status": current_status,
                    "new_status": target_status,
                    "running_tasks": len(running_tasks)
                }

            return {
                "updated": False,
                "reason": "status_unchanged",
                "current_status": current_status
            }

        finally:
            await conn.close()

    except docker.errors.NotFound:
        logger.warning("Service not found", service_name=service_name)
        return {"updated": False, "reason": "service_not_found"}
    except Exception as e:
        logger.error("Error checking service task state", error=str(e))
        raise
```

#### 1.3 Add New Task: `perform_odoo_health_check_and_update`
**New Celery task** to perform Odoo HTTP health check and update status to RUNNING.

```python
@celery_app.task(bind=True)
def perform_odoo_health_check_and_update(self, instance_id: str, internal_url: str, expected_current_status: str):
    """
    Perform Odoo HTTP health check and update status to RUNNING if successful

    This task is queued when Docker event monitor detects service upscale.
    It runs asynchronously without blocking the event monitoring stream.

    Args:
        instance_id: Instance UUID
        internal_url: Odoo internal URL for health check
        expected_current_status: Expected current status (for validation)
    """
    try:
        logger.info("Starting Odoo health check task",
                   instance_id=instance_id,
                   internal_url=internal_url,
                   task_id=self.request.id)

        result = asyncio.run(_perform_odoo_health_check_and_update(
            instance_id,
            internal_url,
            expected_current_status
        ))

        logger.info("Odoo health check task completed",
                   instance_id=instance_id,
                   result=result,
                   task_id=self.request.id)

        return result

    except Exception as e:
        logger.error("Odoo health check task failed",
                    instance_id=instance_id,
                    error=str(e),
                    task_id=self.request.id)
        # Mark instance as error on health check failure
        asyncio.run(_update_instance_status_to_error(
            instance_id,
            f"Health check failed: {str(e)}"
        ))
        raise


async def _perform_odoo_health_check_and_update(
    instance_id: str,
    internal_url: str,
    expected_current_status: str
) -> Dict[str, Any]:
    """
    Perform HTTP health check and update instance status to RUNNING

    Waits up to 60 seconds for Odoo to respond with HTTP 200/302/303.
    Only updates status if current status matches expected (prevents race conditions).
    """
    import httpx

    logger.info("Performing Odoo health check",
               instance_id=instance_id,
               internal_url=internal_url,
               expected_status=expected_current_status)

    # Perform HTTP health check with retry
    timeout = 60  # 60 seconds total
    check_interval = 5  # Check every 5 seconds
    start_time = datetime.utcnow()
    health_check_passed = False

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(internal_url, timeout=10)
                if response.status_code in [200, 302, 303]:
                    health_check_passed = True
                    logger.info("Odoo health check passed",
                              instance_id=instance_id,
                              status_code=response.status_code,
                              elapsed_seconds=(datetime.utcnow() - start_time).seconds)
                    break
            except Exception as check_error:
                logger.debug("Health check attempt failed, will retry",
                           instance_id=instance_id,
                           error=str(check_error),
                           elapsed_seconds=(datetime.utcnow() - start_time).seconds)

            await asyncio.sleep(check_interval)

    if not health_check_passed:
        logger.error("Odoo health check failed - timeout",
                    instance_id=instance_id,
                    internal_url=internal_url,
                    timeout_seconds=timeout)
        # Update to ERROR status
        await _update_instance_status_to_error(
            instance_id,
            f"Odoo health check timeout after {timeout}s"
        )
        return {
            "success": False,
            "reason": "health_check_timeout",
            "timeout_seconds": timeout
        }

    # Health check passed - update status to RUNNING
    # But first verify current status hasn't changed unexpectedly
    conn = await _get_db_connection()
    try:
        current_status = await conn.fetchval(
            "SELECT status FROM instances WHERE id = $1",
            UUID(instance_id)
        )

        if not current_status:
            logger.warning("Instance not found during health check update",
                         instance_id=instance_id)
            return {"success": False, "reason": "instance_not_found"}

        # Only update if still in expected transitional state
        if current_status not in ['starting', 'restarting']:
            logger.warning("Instance status changed during health check, not updating",
                         instance_id=instance_id,
                         expected_status=expected_current_status,
                         actual_status=current_status)
            return {
                "success": False,
                "reason": "status_changed",
                "expected_status": expected_current_status,
                "actual_status": current_status
            }

        # Update to RUNNING (atomic - only if still in transitional state)
        result = await conn.execute("""
            UPDATE instances
            SET status = $1, updated_at = $2, last_health_check = $3
            WHERE id = $4 AND status IN ('starting', 'restarting')
        """, InstanceStatus.RUNNING.value, datetime.utcnow(), datetime.utcnow(), UUID(instance_id))

        # Check if update was blocked by race condition
        if result == 'UPDATE 0':
            # Re-check current status
            actual_status = await conn.fetchval(
                "SELECT status FROM instances WHERE id = $1",
                UUID(instance_id)
            )
            logger.warning("Health check status update blocked - state changed during check",
                         instance_id=instance_id,
                         expected_states=['starting', 'restarting'],
                         actual_status=actual_status)
            return {
                "success": False,
                "reason": "status_changed_race_condition",
                "actual_status": actual_status
            }

        logger.info("Instance status updated to RUNNING after health check",
                   instance_id=instance_id,
                   old_status=current_status)

        return {
            "success": True,
            "old_status": current_status,
            "new_status": InstanceStatus.RUNNING.value,
            "internal_url": internal_url
        }

    finally:
        await conn.close()


async def _update_instance_status_to_error(instance_id: str, error_message: str):
    """Update instance status to ERROR with error message"""
    conn = await _get_db_connection()
    try:
        await conn.execute("""
            UPDATE instances
            SET status = $1, error_message = $2, updated_at = $3
            WHERE id = $4
        """, InstanceStatus.ERROR.value, error_message, datetime.utcnow(), UUID(instance_id))

        logger.error("Instance status updated to ERROR",
                    instance_id=instance_id,
                    error_message=error_message)
    finally:
        await conn.close()


async def _get_db_connection():
    """
    Get database connection using existing patterns

    NOTE: For production with high event volume, consider implementing
    a connection pool at Celery worker initialization to reuse connections
    across tasks instead of opening/closing per task.

    Example with asyncpg.create_pool:
    # In celery worker init:
    # db_pool = await asyncpg.create_pool(...)
    # Then use: conn = await db_pool.acquire()
    """
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'instance'),
        'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
        'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
    }
    return await asyncpg.connect(**db_config)
```

### Phase 2: Modify Lifecycle Tasks

#### 2.1 Update `_start_instance_workflow`
**File**: `services/instance-service/app/tasks/lifecycle.py`

**Changes**:
1. Remove direct status update to `RUNNING` after Docker operation
2. Keep status as `STARTING` after Docker operation completes
3. Let Docker events monitor handle transition to `RUNNING`

```python
async def _start_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main start workflow with Docker operations"""

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    try:
        # Step 1: Update status to STARTING (transitional state)
        await _update_instance_status(instance_id, InstanceStatus.STARTING)

        # Step 2: Start Docker service (scale to 1)
        container_result = await _start_docker_container(instance)
        logger.info("Service start initiated", service_id=container_result.get('service_id'))

        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=300)
        logger.info("Odoo startup confirmed")

        # Step 4: Update network info
        await _update_instance_network_info(instance_id, container_result)

        # Step 5: Send notification email
        user_info = await _get_user_info(instance['customer_id'])
        if user_info:
            client = get_notification_client()
            await client.send_template_email(
                to_emails=[user_info['email']],
                template_name="instance_started",
                template_variables={
                    "first_name": user_info['first_name'],
                    "instance_name": instance['name'],
                    "instance_url": container_result['external_url']
                },
                tags=["instance", "lifecycle", "started"]
            )

        # CRITICAL: Do NOT update status to RUNNING here
        # Docker events monitor will detect running task and update to RUNNING
        logger.info("Start workflow completed, awaiting Docker events confirmation",
                   instance_id=instance_id)

        return {
            "status": "success",
            "service_id": container_result.get('service_id'),
            "external_url": container_result['external_url'],
            "message": "Instance start initiated - awaiting confirmation"
        }

    except Exception as e:
        logger.error("Start workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise
```

#### 2.2 Update `_stop_instance_workflow`
**File**: `services/instance-service/app/tasks/lifecycle.py`

**Changes**:
1. Remove direct status update to `STOPPED` after Docker operation
2. Keep status as `STOPPING` after Docker operation completes
3. Let Docker events monitor handle transition to `STOPPED`

```python
async def _stop_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main stop workflow with Docker operations"""

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    try:
        # Step 1: Update status to STOPPING (transitional state)
        await _update_instance_status(instance_id, InstanceStatus.STOPPING)

        # Step 2: Stop Docker service (scale to 0)
        await _stop_docker_container(instance)
        logger.info("Service stop initiated")

        # Step 3: Send notification email
        user_info = await _get_user_info(instance['customer_id'])
        if user_info:
            client = get_notification_client()
            await client.send_template_email(
                to_emails=[user_info['email']],
                template_name="instance_stopped",
                template_variables={
                    "first_name": user_info['first_name'],
                    "instance_name": instance['name'],
                    "reason": "Instance stopped by user request"
                },
                tags=["instance", "lifecycle", "stopped"]
            )

        # CRITICAL: Do NOT update status to STOPPED here
        # Docker events monitor will detect 0 running tasks and update to STOPPED
        logger.info("Stop workflow completed, awaiting Docker events confirmation",
                   instance_id=instance_id)

        return {
            "status": "success",
            "message": "Instance stop initiated - awaiting confirmation"
        }

    except Exception as e:
        logger.error("Stop workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise
```

#### 2.3 Update `_restart_instance_workflow`
**File**: `services/instance-service/app/tasks/lifecycle.py`

**Changes**:
1. Remove direct status update to `RUNNING` after Docker operation
2. Keep status as `RESTARTING` after Docker operation completes
3. Let Docker events monitor handle transition to `RUNNING`

```python
async def _restart_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main restart workflow with Docker operations"""

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    try:
        # Step 1: Update status to RESTARTING (transitional state)
        await _update_instance_status(instance_id, InstanceStatus.RESTARTING)

        # Step 2: Restart Docker service (force update)
        container_result = await _restart_docker_container(instance)
        logger.info("Service restart initiated", service_id=container_result.get('service_id'))

        # Step 3: Wait for Odoo to be accessible
        await _wait_for_odoo_startup(container_result, timeout=300)
        logger.info("Odoo startup confirmed")

        # Step 4: Update network info
        await _update_instance_network_info(instance_id, container_result)

        # CRITICAL: Do NOT update status to RUNNING here
        # Docker events monitor will detect running task and update to RUNNING
        logger.info("Restart workflow completed, awaiting Docker events confirmation",
                   instance_id=instance_id)

        return {
            "status": "success",
            "service_id": container_result.get('service_id'),
            "external_url": container_result['external_url'],
            "message": "Instance restart initiated - awaiting confirmation"
        }

    except Exception as e:
        logger.error("Restart workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise
```

### Phase 3: Update/Restore Operations (No Changes Required)

**Update Operation** (`services/instance-service/app/tasks/maintenance.py`):
- Currently sets status to `updating` → performs update → sets to `running`
- **No changes needed**: This flow is self-contained
- Docker events monitor will NOT interfere (no matching transition rules)

**Restore Operation** (`services/instance-service/app/tasks/maintenance.py`):
- Currently sets status to `maintenance` → performs restore → sets to appropriate state
- **No changes needed**: This flow is self-contained
- Docker events monitor will NOT interfere (no matching transition rules)

**Key Principle**: Docker events monitoring ONLY handles transitions from `starting`/`stopping`/`restarting` to `running`/`stopped`. All other status transitions are managed by their respective task workflows.

### Phase 4: Deprecate Bulk Reconciliation

#### 4.1 Remove Reconciliation Trigger from Events
**File**: `services/instance-service/app/tasks/monitoring.py`

**Current code** (line 250):
```python
elif event_type == 'update':
    logger.info("Service updated - triggering reconciliation", ...)
    reconcile_instance_statuses_task.delay()
```

**Remove this**. Replace with the new `check_service_task_state` call.

#### 4.2 Convert Reconciliation to Safety Net Only
Keep `reconcile_instance_statuses_task()` but:
- Run it ONLY as a scheduled periodic task (e.g., every 10 minutes)
- Use it as a safety net for edge cases (missed events, race conditions)
- Log warnings for any mismatches found (indicates missed events)

**Purpose**: Catch rare edge cases where events were missed, but NOT primary mechanism.

### Phase 5: Frontend Considerations

**No frontend changes required** for basic functionality, but consider:

1. **Status polling**: Frontend should poll instance status API to see transitions
   - `starting` → `running` (typically 10-60 seconds)
   - `stopping` → `stopped` (typically 2-10 seconds)
   - `restarting` → `running` (typically 30-90 seconds)

2. **User feedback**: Show transitional states clearly
   - "Starting instance... (this may take up to 60 seconds)"
   - "Stopping instance..."
   - "Restarting instance... (this may take up to 90 seconds)"

3. **Timeout handling**: If stuck in transitional state for too long, show error
   - Suggest user contact support or check service logs

## Testing Strategy

### Unit Tests
1. **Docker Event Monitor Tests**:
   - Test `_process_service_event()` with different event types
   - Test `check_service_task_state()` with various task state combinations
   - Verify status transitions only occur for valid current states

2. **Lifecycle Task Tests**:
   - Test that workflows set correct transitional states
   - Test that workflows do NOT set final states directly
   - Test error handling and rollback scenarios

### Integration Tests
1. **Start/Stop/Restart Cycles**:
   - Start instance → verify `starting` → verify `running`
   - Stop instance → verify `stopping` → verify `stopped`
   - Restart instance → verify `restarting` → verify `running`

2. **Update/Restore Operations**:
   - Verify update operation manages its own status
   - Verify restore operation manages its own status
   - Verify Docker events don't interfere with these operations

3. **Edge Cases**:
   - Service crash during start → should detect failure
   - Multiple rapid start/stop commands
   - Docker daemon restart scenarios
   - Missed event scenarios (verify safety net catches them)

### Load Testing
1. **Event Volume**: Test with many simultaneous instance operations
2. **Event Deduplication**: Verify duplicate events are properly filtered
3. **Database Concurrency**: Test concurrent status updates


## Success Metrics

1. **Status Accuracy**: 99.9%+ of instances reflect correct Docker state
2. **Update Latency**: Status updates occur within 2 seconds of Docker state change
3. **Safety Net Triggers**: <1% of status updates come from reconciliation (rest from events)
4. **Error Rate**: <0.1% of lifecycle operations result in stuck transitional states

## Risk Mitigation

### Risk 1: Missed Events
- **Mitigation**: Keep periodic reconciliation as safety net
- **Detection**: Log warnings when reconciliation finds mismatches
- **Recovery**: Reconciliation corrects missed events automatically

### Risk 2: Event Processing Failure
- **Mitigation**: Celery task retry mechanisms
- **Detection**: Monitor Celery worker logs for task failures
- **Recovery**: Failed tasks retry automatically, safety net catches gaps

### Risk 3: Race Conditions
- **Mitigation**:
  - Use database transactions for status updates
  - Event deduplication to prevent duplicate processing
  - Status transition rules prevent invalid transitions
- **Detection**: Log when status update is rejected due to current state
- **Recovery**: Safety net reconciliation corrects inconsistencies

### Risk 4: Docker Daemon Issues
- **Mitigation**:
  - Event stream automatically reconnects on failure
  - Monitor thread restarts on exceptions
- **Detection**: Monitor logs for "event monitoring failed" messages
- **Recovery**: Monitoring restarts automatically, safety net handles gaps

## Rollback Plan

If critical issues arise:

1. **Immediate**: Revert lifecycle tasks to directly set final states
2. **Short-term**: Re-enable bulk reconciliation trigger on `update` events
3. **Investigation**: Analyze logs to identify root cause
4. **Fix**: Address issues in development environment
5. **Re-deploy**: Repeat rollout plan with fixes

## Open Questions

1. **Event processing priority**: Should event processing use dedicated queue?
2. **Status history**: Should we log all status transitions for audit trail?
3. **Alerting**: What alerts should fire for stuck transitional states?
4. **Metrics**: What additional metrics should we collect?

## Appendix: File Modifications Summary

### Files to Modify

1. **`services/instance-service/app/tasks/monitoring.py`**
   - Modify `_process_service_event()` method to call new task
   - Add new `check_service_task_state_and_health()` Celery task
   - Add `_check_service_task_state_and_health()` async function
   - Add new `perform_odoo_health_check_and_update()` Celery task (non-blocking health check)
   - Add `_perform_odoo_health_check_and_update()` async function
   - Add `_update_instance_status_to_error()` helper function
   - Add `_get_db_connection()` helper function
   - Remove reconciliation trigger from `update` event handler

2. **`services/instance-service/app/tasks/lifecycle.py`**
   - Modify `_start_instance_workflow()` - remove final status update to RUNNING
   - Modify `_stop_instance_workflow()` - remove final status update to STOPPED
   - Modify `_restart_instance_workflow()` - remove final status update to RUNNING

3. **`services/instance-service/app/tasks/maintenance.py`**
   - **No changes required** (update/restore self-manage status)

### Files NOT Modified

- **Frontend code**: No changes required (polling handles async updates)
- **API routes**: No changes required
- **Database schema**: No changes required
- **Update/restore tasks**: No changes required

## Conclusion

This plan transitions from bulk reconciliation to event-driven status synchronization, ensuring real-time accuracy while maintaining proper transitional states. The architecture clearly separates concerns: lifecycle tasks manage Docker operations and set transitional states, while the Docker events monitor confirms final states based on actual container status.

### Key Benefits

1. **Real-time status updates** (2-5 seconds vs minutes)
2. **Reduced database load** (event-driven vs bulk scanning all instances)
3. **Clear responsibility separation** (tasks vs monitor)
4. **Safety net preserved** (reconciliation as backup for edge cases)
5. **No impact on update/restore** (self-contained workflows)
6. **Non-blocking architecture** (event monitor never blocks on health checks)
7. **DevOps-friendly** (detects manual Docker operations and syncs DB state)

### Critical Design Decisions

1. **Health Check is Asynchronous**:
   - Docker event monitor queues a separate Celery task for health checks
   - Event monitoring stream is never blocked
   - Health check task waits up to 60 seconds for Odoo HTTP response
   - Sets status to `running` only after successful ping

2. **Manual DevOps Operations Supported**:
   - If DevOps manually scales service up (stopped → running tasks detected)
   - System automatically sets DB to `starting` then queues health check
   - Final status transition to `running` happens after health verification

3. **Transitional States Enforced**:
   - Lifecycle tasks ONLY set transitional states (`starting`, `stopping`, `restarting`)
   - Docker events + health checks set final states (`running`, `stopped`)
   - Prevents race conditions and ensures Docker state = DB state

4. **Update/Restore Untouched**:
   - These operations continue to manage their own status
   - Docker event monitor ignores instances in `updating` or `maintenance` states
   - No interference with existing workflows
