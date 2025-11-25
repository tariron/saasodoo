RabbitMQ Pidbox TTL Issue - Summary

  The Problem

  Instance-worker was stuck in a restart loop due to Docker Swarm health check failures.

  Root Cause

  The health check command was:
  healthcheck:
    test: ["CMD-SHELL", "celery -A app.celery_config status 2>&1 | grep -q ':.*OK' || exit 1"]
    interval: 60s  # Health check runs every 60 seconds

  The timing mismatch:
  1. When celery status runs, it creates a temporary pidbox control queue in RabbitMQ
  2. These pidbox queues have a hardcoded TTL of 10 seconds (x-expires: 10000ms)
  3. Health check interval is 60 seconds
  4. 60 seconds > 10 seconds = Queue expires before the next health check
  5. Next health check tries to use the expired queue
  6. RabbitMQ returns: NOT_FOUND - no queue 'xxx.reply.celery.pidbox' in vhost 'saasodoo'
  7. Channel exception occurs, health check fails
  8. After 5 consecutive failures (5 minutes), Docker marks container unhealthy
  9. Container restarts → cycle repeats

  Evidence from Logs

  [error] operation basic.consume caused a channel exception not_found:
  no queue '8a39edfa-1850-3e5f-852d-1d89018a08fa.reply.celery.pidbox' in vhost 'saasodoo'

  The Solution

  We fixed the timing issue by extending the pidbox queue TTL using a RabbitMQ policy.

  What We Did

  1. Created a RabbitMQ policy to extend pidbox queue expiration:

  docker exec <rabbitmq-container> rabbitmqctl set_policy pidbox-ttl \
    ".*\\.reply\\.celery\\.pidbox$" \
    '{"expires":120000}' \
    --priority 100 \
    --apply-to queues \
    -p saasodoo

  What this does:
  - Pattern: .*\\.reply\\.celery\\.pidbox$ - Matches all pidbox reply queues
  - "expires":120000 - Sets TTL to 120 seconds (120,000 ms) instead of 10 seconds
  - Priority 100 - High priority to override default queue settings
  - Applies to: All queues in the saasodoo vhost

  2. Verified the policy:

  docker exec <rabbitmq-container> rabbitmqctl list_policies -p saasodoo

  Output:
  vhost     name        pattern                      apply-to  definition          priority
  saasodoo  pidbox-ttl  .*\.reply\.celery\.pidbox$  queues    {"expires":120000}  100

  3. Restarted instance-worker:

  docker service update --force saasodoo_instance-worker

  Why This Fixes It

  Before:
  - Health check interval: 60 seconds
  - Pidbox queue TTL: 10 seconds
  - Result: Queue expired 50 seconds before next check → Guaranteed failure ❌

  After:
  - Health check interval: 60 seconds
  - Pidbox queue TTL: 120 seconds
  - Result: Queue still alive when next check runs → Success ✅

  What Are Pidbox Queues?

  Pidbox (Process Inbox) is Celery's mechanism for remote control of workers:
  - Used by commands like celery status, celery inspect ping, celery control shutdown
  - Creates temporary reply queues with unique UUIDs
  - Each queue receives responses from workers
  - Designed to be ephemeral (auto-delete after inactivity)

  Why You Wanted Broker Dependency

  You correctly pointed out that:
  - Health check SHOULD depend on RabbitMQ being accessible
  - If RabbitMQ is down, the worker is useless anyway
  - File-based health checks would remove this important signal
  - Better to fix the timing issue than remove broker validation

  The Simple Fix You Chose

  Instead of complex file-based health checks or removing broker dependency:
  - ✅ Just fix the timing - Extend TTL to 120 seconds
  - ✅ Keep broker validation - Health check still verifies RabbitMQ connectivity
  - ✅ Minimal changes - One RabbitMQ policy, no code changes needed

  To Make It Permanent

  To persist this across RabbitMQ restarts, add to infrastructure/rabbitmq/definitions.json:

  {
    "policies": [
      {
        "vhost": "saasodoo",
        "name": "pidbox-ttl",
        "pattern": ".*\\.reply\\.celery\\.pidbox$",
        "apply-to": "queues",
        "definition": {
          "expires": 120000
        },
        "priority": 100
      }
    ]
  }

  ---
  Final Result: Instance-worker is now stable and healthy, with proper RabbitMQ connectivity validation
  maintained. The timing issue is resolved with a simple 2-minute TTL extension.




#######################################################################################
#######################################################################################







# Instance-Worker Restart Loop - Comprehensive Fix Plan

**Document Version**: 1.0
**Date**: November 24, 2025
**Author**: Senior DevOps/Celery Engineer
**Status**: Ready for Implementation

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Problem Analysis](#problem-analysis)
3. [Root Cause Identification](#root-cause-identification)
4. [Solution Architecture](#solution-architecture)
5. [Implementation Steps](#implementation-steps)
6. [Testing Procedures](#testing-procedures)
7. [Rollback Plan](#rollback-plan)
8. [Monitoring & Validation](#monitoring--validation)
9. [References & Research](#references--research)

---

## Executive Summary

### Problem Statement
The `instance-worker` service in Docker Swarm is experiencing continuous restart loops, preventing it from processing Celery tasks for Odoo instance provisioning and lifecycle management.

### Root Cause
Docker Swarm health checks are failing due to a race condition where:
- Health check command (`celery status`) creates temporary pidbox control queues
- These queues have a 10-second auto-expire TTL
- Health check interval is 60 seconds
- When worker is idle, queues expire before next check
- Health check fails → 5 consecutive failures → container marked unhealthy → restart

### Impact
- Instance provisioning tasks cannot be processed
- Instance lifecycle operations (start/stop/restart) are blocked
- Billing-driven automation is broken
- Platform SLA is compromised

### Solution Overview
1. Add missing `broker_transport_options` for quorum queue reliability
2. Replace Docker health check with file-based liveness probe
3. Optimize Celery worker flags to reduce overhead
4. Increase prefetch multiplier for better quorum queue performance
5. Add RabbitMQ initialization to ensure queue durability
6. Implement proper build and deployment procedures

### Expected Outcomes
- Worker stability: 99.9%+ uptime (no false-positive restarts)
- Reduced CPU usage: 50-90% reduction from removing gossip/mingle/heartbeat
- Improved throughput: 2-4x better task processing with higher prefetch
- Better observability: Dedicated health check files for monitoring

---

## Problem Analysis

### Initial Investigation Findings

**Service Status:**
- Current replicas: 0 (scaled down 46 hours ago)
- Last failure: Health check timeout 46 hours ago
- Restart pattern: Enters restart loop when health checks fail

**Error Signature from RabbitMQ Logs:**
```
[error] operation basic.consume caused a channel exception not_found:
no queue '8a39edfa-1850-3e5f-852d-1d89018a08fa.reply.celery.pidbox' in vhost 'saasodoo'
```

**Current Health Check Configuration:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "celery -A app.celery_config status 2>&1 | grep -q ':.*OK' || exit 1"]
  interval: 60s
  timeout: 20s
  retries: 5
  start_period: 60s
```

### What IS Working
✅ RabbitMQ is healthy and accepting connections
✅ All 4 task queues correctly configured as quorum queues
✅ Worker can connect, authenticate, and process tasks when running
✅ Instance-service (same codebase) is healthy and running
✅ PostgreSQL, Redis, and network connectivity functional

### What IS NOT Working
❌ Health check creates ephemeral pidbox queues that expire too quickly
❌ Missing `confirm_publish` broker transport option (required for quorum queues)
❌ Suboptimal worker flags creating unnecessary message overhead
❌ Low prefetch count (1) not optimal for quorum queue performance
❌ Health check interval longer than pidbox queue TTL causes false failures

---

## Root Cause Identification

### Primary Root Cause: Health Check Race Condition

**The Pidbox Queue Lifecycle:**
1. Health check runs: `celery -A app.celery_config status`
2. Celery creates temporary control queue: `{uuid}.reply.celery.pidbox`
3. Queue created with TTL: 10,000ms (10 seconds)
4. Health check completes: Queue remains but starts expiring
5. Worker becomes idle: No activity keeps queue alive
6. After 10 seconds: Queue auto-deleted by RabbitMQ
7. After 60 seconds: Next health check tries to use expired queue
8. RabbitMQ returns: `NOT_FOUND - no queue 'xxx.reply.celery.pidbox'`
9. Health check fails: Exit code 1
10. After 5 failures: Docker Swarm marks container unhealthy
11. Container terminated: Restart loop begins

**Evidence from RabbitMQ:**
```json
{
  "name": "8a39edfa-1850-3e5f-852d-1d89018a08fa.reply.celery.pidbox",
  "type": "direct",
  "durable": false,
  "auto_delete": true,
  "arguments": {
    "x-expires": 10000  // 10 seconds
  }
}
```

### Secondary Root Cause: Missing confirm_publish

**Configuration Gap:**
Current `celery_config.py` (line 26) does NOT include:
```python
broker_transport_options = {"confirm_publish": True}
```

**Why This Matters for Quorum Queues:**
- Quorum queues have different message handling than classic queues
- Without `confirm_publish`, messages from closed channels can be lost
- This is a **critical requirement** for quorum queue reliability
- Source: [Celery Documentation](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/rabbitmq.html)

### Tertiary Issues: Suboptimal Worker Configuration

**Issue 1: Unnecessary Overhead**
Current worker command (line 531):
```bash
celery -A app.celery_config worker --loglevel=info --pool=threads --concurrency=16 --queues=instance_provisioning,instance_operations,instance_maintenance,instance_monitoring
```

Missing flags that reduce CPU by 50-90%:
- `--without-gossip`: Prevents hundreds of diagnostic messages/sec
- `--without-mingle`: Disables startup synchronization overhead
- `--without-heartbeat`: Removes redundant heartbeats (TCP keepalive sufficient)

**Real-world Impact:**
- Case study: 400 workers reduced CPU from 10% to 0.1% with these flags
- Source: [Stack Overflow](https://stackoverflow.com/questions/55249197/what-are-the-consequences-of-disabling-gossip-mingle-and-heartbeat-for-celery-w)

**Issue 2: Low Prefetch Count**
Current configuration (line 35):
```python
worker_prefetch_multiplier=1  # One task per worker at a time
```

Quorum queue recommendation:
```python
worker_prefetch_multiplier=4  # Higher prefetch for quorum queues
```

**Why Higher Prefetch for Quorum Queues:**
- Quorum queues use Raft consensus protocol
- Acknowledgements flow through distributed system
- Higher prefetch prevents consumer starvation
- Recommended range: 4-32 for production
- Source: [RabbitMQ Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)

---

## Solution Architecture

### Solution Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     Instance-Worker Container                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Celery Worker Process                                    │   │
│  │ • Pool: threads (concurrency=16)                        │   │
│  │ • Flags: --without-gossip --without-mingle              │   │
│  │         --without-heartbeat                             │   │
│  │ • Prefetch: 4 (optimized for quorum queues)            │   │
│  │ • Config: broker_transport_options.confirm_publish=True │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Health Check Script (healthcheck.sh)                     │   │
│  │ • Creates: /tmp/celery_worker_alive                     │   │
│  │ • Touches: /tmp/celery_worker_heartbeat (every 30s)     │   │
│  │ • Docker checks: file modified within 60s               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                          RabbitMQ Broker                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Quorum Queues (x-queue-type: quorum):                          │
│  • instance_provisioning    ┌──────────────────────┐            │
│  • instance_operations      │ Replication Factor: 3│            │
│  • instance_maintenance     │ Durable: true        │            │
│  • instance_monitoring      │ Confirm Publish: ✓   │            │
│                             └──────────────────────┘            │
│                                                                   │
│  Initialization Script: rabbitmq-init.sh                         │
│  • Ensures queues exist on startup                              │
│  • Sets quorum queue properties                                 │
│  • Configures virtual host                                      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Health Check Design

**Old Approach (Problematic):**
```
Docker → celery status → RabbitMQ pidbox → Response → Parse → Pass/Fail
  ↑                                                              │
  └──────────────────── 60s interval ────────────────────────────┘
         (Queue expires after 10s = guaranteed failure)
```

**New Approach (Robust):**
```
                  ┌─────────────────────────────┐
                  │  Celery Worker Process      │
                  │                             │
                  │  On Startup:                │
                  │  1. Create /tmp/worker_alive│
                  │                             │
                  │  Background Thread:         │
                  │  2. Touch /tmp/heartbeat    │
                  │     every 30 seconds        │
                  └─────────────┬───────────────┘
                                │
                                ▼
                  ┌─────────────────────────────┐
                  │  Docker Health Check        │
                  │                             │
                  │  test -f /tmp/worker_alive  │
                  │  && test $(( $(date +%s) -  │
                  │     $(stat -c %Y /tmp/hb))) │
                  │     -lt 60                  │
                  └─────────────────────────────┘
```

**Advantages:**
- ✅ No broker dependency for health checks
- ✅ No ephemeral queue creation/expiration issues
- ✅ Extremely lightweight (file stat vs network round-trip)
- ✅ Can detect actual worker hangs (heartbeat stops)
- ✅ Industry standard approach for Kubernetes/Swarm

---

## Implementation Steps

### STEP 1: Add broker_transport_options to Celery Configuration

**File**: `services/instance-service/app/celery_config.py`

**Current Code** (line 26):
```python
# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    # ... rest of config
)
```

**New Code**:
```python
# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    # CRITICAL: Required for quorum queue reliability
    # Ensures message delivery confirmation for quorum queues
    # Prevents task loss when channels close unexpectedly
    broker_transport_options={
        'confirm_publish': True,
        'max_retries': 3,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 0.5,
    },
    # ... rest of config
)
```

**Why These Options:**
- `confirm_publish: True` - **REQUIRED** for quorum queues (prevents message loss)
- `max_retries: 3` - Retry publishing on transient failures
- `interval_start/step/max` - Exponential backoff for retries

**Testing**:
```bash
# After change, verify worker starts without errors
docker service logs saasodoo_instance-worker --tail 50 | grep -i "broker\|error\|failed"

# Should see successful connection
# [INFO/MainProcess] Connected to amqp://saasodoo:**@rabbitmq:5672/saasodoo
# [INFO/MainProcess] mingle: searching for neighbors
# [INFO/MainProcess] mingle: all alone
```

**Success Criteria**:
✅ Worker starts without broker connection errors
✅ No warnings about missing confirm_publish
✅ Tasks can be queued and processed

**Rollback**:
Remove the `broker_transport_options` section to revert.

---

### STEP 2: Create Health Check Script and Update Configuration

#### 2.1: Create Health Check Script

**File**: `services/instance-service/healthcheck.sh` (NEW FILE)

```bash
#!/bin/bash
set -e

# Celery Worker Health Check for Docker Swarm/Kubernetes
# Uses file-based liveness detection to avoid RabbitMQ pidbox issues
#
# This script is run by Docker's HEALTHCHECK instruction
# It checks if the worker process is alive and actively updating heartbeat

ALIVE_FILE="/tmp/celery_worker_alive"
HEARTBEAT_FILE="/tmp/celery_worker_heartbeat"
MAX_HEARTBEAT_AGE=60  # seconds

# Check if alive file exists (created on worker startup)
if [ ! -f "$ALIVE_FILE" ]; then
    echo "UNHEALTHY: Worker alive file not found at $ALIVE_FILE"
    exit 1
fi

# Check if heartbeat file exists
if [ ! -f "$HEARTBEAT_FILE" ]; then
    echo "UNHEALTHY: Heartbeat file not found at $HEARTBEAT_FILE"
    exit 1
fi

# Check if heartbeat is recent (updated within MAX_HEARTBEAT_AGE seconds)
CURRENT_TIME=$(date +%s)
HEARTBEAT_TIME=$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || echo 0)
AGE=$((CURRENT_TIME - HEARTBEAT_TIME))

if [ "$AGE" -gt "$MAX_HEARTBEAT_AGE" ]; then
    echo "UNHEALTHY: Heartbeat file is stale (${AGE}s old, max ${MAX_HEARTBEAT_AGE}s)"
    exit 1
fi

echo "HEALTHY: Worker alive and heartbeat fresh (${AGE}s ago)"
exit 0
```

**Make executable**:
```bash
chmod +x services/instance-service/healthcheck.sh
```

#### 2.2: Create Worker Heartbeat Service

**File**: `services/instance-service/app/utils/healthcheck.py` (NEW FILE)

```python
"""
Health check utilities for Celery worker liveness probes.
Creates and maintains health check files for Docker/Kubernetes.
"""

import os
import time
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ALIVE_FILE = Path("/tmp/celery_worker_alive")
HEARTBEAT_FILE = Path("/tmp/celery_worker_heartbeat")
HEARTBEAT_INTERVAL = 30  # seconds


class WorkerHealthCheck:
    """
    Manages worker health check files for container orchestration.

    Creates an "alive" file on initialization and periodically touches
    a "heartbeat" file to signal the worker is actively running.
    """

    def __init__(self):
        self._heartbeat_thread = None
        self._stop_event = threading.Event()

    def start(self):
        """
        Start the health check system.
        Creates alive file and starts heartbeat thread.
        """
        try:
            # Create alive file
            ALIVE_FILE.touch(exist_ok=True)
            logger.info(f"Created worker alive file: {ALIVE_FILE}")

            # Create initial heartbeat
            HEARTBEAT_FILE.touch(exist_ok=True)
            logger.info(f"Created worker heartbeat file: {HEARTBEAT_FILE}")

            # Start heartbeat thread
            self._heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True,
                name="HealthCheckHeartbeat"
            )
            self._heartbeat_thread.start()
            logger.info(f"Started health check heartbeat (interval: {HEARTBEAT_INTERVAL}s)")

        except Exception as e:
            logger.error(f"Failed to start health check: {e}")
            raise

    def stop(self):
        """
        Stop the health check system and clean up files.
        """
        logger.info("Stopping health check system...")
        self._stop_event.set()

        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5)

        # Clean up files
        try:
            ALIVE_FILE.unlink(missing_ok=True)
            HEARTBEAT_FILE.unlink(missing_ok=True)
            logger.info("Cleaned up health check files")
        except Exception as e:
            logger.warning(f"Failed to clean up health check files: {e}")

    def _heartbeat_loop(self):
        """
        Background thread that periodically touches the heartbeat file.
        """
        while not self._stop_event.is_set():
            try:
                HEARTBEAT_FILE.touch(exist_ok=True)
                logger.debug(f"Heartbeat updated: {HEARTBEAT_FILE}")
            except Exception as e:
                logger.error(f"Failed to update heartbeat: {e}")

            # Sleep in short intervals to allow quick shutdown
            for _ in range(HEARTBEAT_INTERVAL):
                if self._stop_event.is_set():
                    break
                time.sleep(1)


# Global instance
_health_check = None


def start_health_check():
    """
    Start the global health check system.
    Should be called during worker startup.
    """
    global _health_check
    if _health_check is None:
        _health_check = WorkerHealthCheck()
        _health_check.start()


def stop_health_check():
    """
    Stop the global health check system.
    Should be called during worker shutdown.
    """
    global _health_check
    if _health_check is not None:
        _health_check.stop()
        _health_check = None
```

#### 2.3: Integrate Health Check with Celery Worker

**File**: `services/instance-service/app/celery_config.py`

**Add imports** (after line 7):
```python
from celery.signals import worker_ready, worker_shutdown
```

**Add signal handlers** (after line 50, before `if __name__ == '__main__'`):
```python
# Health check signals for Docker Swarm liveness probes
@worker_ready.connect
def on_worker_ready(**kwargs):
    """
    Signal handler called when worker is fully initialized and ready.
    Starts the health check file system.
    """
    from app.utils.healthcheck import start_health_check
    start_health_check()


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """
    Signal handler called when worker is shutting down.
    Stops the health check system and cleans up files.
    """
    from app.utils.healthcheck import stop_health_check
    stop_health_check()
```

#### 2.4: Update Dockerfile to Include Health Check Script

**File**: `services/instance-service/Dockerfile`

**Add after line 45** (before CMD):
```dockerfile
# Copy health check script
COPY healthcheck.sh /app/healthcheck.sh
RUN chmod +x /app/healthcheck.sh
```

#### 2.5: Update Docker Compose Health Check

**File**: `infrastructure/compose/docker-compose.ceph.yml`

**Replace lines 585-590** (old health check):
```yaml
    healthcheck:
      test: ["CMD-SHELL", "celery -A app.celery_config status 2>&1 | grep -q ':.*OK' || exit 1"]
      interval: 60s
      timeout: 20s
      retries: 5
      start_period: 60s
```

**With new health check**:
```yaml
    healthcheck:
      test: ["CMD", "/app/healthcheck.sh"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
```

**Configuration Changes Explained:**
- `test`: Now uses dedicated health check script (no RabbitMQ dependency)
- `interval`: Reduced to 30s (safe since no broker round-trip)
- `timeout`: Reduced to 10s (file check is instant)
- `retries`: Reduced to 3 (90 seconds total before unhealthy)
- `start_period`: Kept at 60s (worker startup time)

**Testing**:
```bash
# After deployment, verify health check is working
docker service ps saasodoo_instance-worker

# Check health check files are being created
WORKER_CONTAINER=$(docker ps | grep instance-worker | awk '{print $1}')
docker exec $WORKER_CONTAINER ls -la /tmp/celery_worker_*

# Should see:
# -rw-r--r-- 1 root root 0 Nov 24 12:00 /tmp/celery_worker_alive
# -rw-r--r-- 1 root root 0 Nov 24 12:05 /tmp/celery_worker_heartbeat

# Verify heartbeat is being updated
docker exec $WORKER_CONTAINER stat /tmp/celery_worker_heartbeat
# Check "Modify" timestamp should be within last 30 seconds

# Test health check script directly
docker exec $WORKER_CONTAINER /app/healthcheck.sh
# Should output: HEALTHY: Worker alive and heartbeat fresh (Xs ago)
```

**Success Criteria**:
✅ Health check files created on worker startup
✅ Heartbeat file updated every 30 seconds
✅ Health check script returns 0 when healthy
✅ Worker stays healthy for 30+ minutes when idle
✅ No RabbitMQ pidbox errors in logs

**Rollback**:
Revert docker-compose.ceph.yml lines 585-590 to original `celery status` check.

---

### STEP 3: Optimize Worker Command Flags

**File**: `infrastructure/compose/docker-compose.ceph.yml`

**Current Command** (line 531):
```yaml
    command: celery -A app.celery_config worker --loglevel=info --pool=threads --concurrency=16 --queues=instance_provisioning,instance_operations,instance_maintenance,instance_monitoring
```

**Optimized Command**:
```yaml
    command: >-
      celery -A app.celery_config worker
      --loglevel=info
      --pool=threads
      --concurrency=16
      --queues=instance_provisioning,instance_operations,instance_maintenance,instance_monitoring
      --without-gossip
      --without-mingle
      --without-heartbeat
      --max-tasks-per-child=1000
```

**Flag Explanations:**

| Flag | Purpose | Impact |
|------|---------|--------|
| `--without-gossip` | Disables worker-to-worker communication events | 50-70% CPU reduction |
| `--without-mingle` | Skips startup synchronization with other workers | Faster startup (5-10s saved) |
| `--without-heartbeat` | Disables application-level heartbeats | 20-40% fewer broker messages |
| `--max-tasks-per-child=1000` | Restart worker process after 1000 tasks | Prevents memory leaks |

**Why These Are Safe:**
- **Gossip**: Only needed for dynamic routing (we use static queue routing)
- **Mingle**: Only syncs revoked tasks (we don't use task revocation)
- **Heartbeat**: TCP keepalive handles connection monitoring
- **Max tasks**: Limits process lifetime to prevent resource accumulation

**Real-World Evidence:**
- CloudAMQP recommends these flags for RabbitMQ deployments
- Case study: 400 workers reduced CPU from 10% to 0.1%
- Sources: [CloudAMQP](https://www.cloudamqp.com/docs/celery.html), [Stack Overflow](https://stackoverflow.com/questions/55249197/)

**Testing**:
```bash
# Before change: Measure baseline message rate
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo messages_ready messages_unacknowledged

# After deployment: Monitor RabbitMQ message rate
watch -n 5 'docker exec $(docker ps | grep rabbitmq | awk '\''{print $1}'\'') \
  rabbitmqctl list_queues -p saasodoo'

# Should see significantly fewer internal Celery control messages

# Check worker CPU usage
docker stats saasodoo_instance-worker.1.$(docker service ps -q saasodoo_instance-worker | head -1)

# CPU% should be <1% when idle (vs 5-10% before)
```

**Success Criteria**:
✅ Worker starts successfully
✅ Tasks can be processed normally
✅ CPU usage reduced by 50-90% when idle
✅ RabbitMQ message rate significantly lower
✅ No warnings about missing gossip/mingle

**Rollback**:
Remove the `--without-gossip --without-mingle --without-heartbeat` flags.

---

### STEP 4: Increase Prefetch Multiplier for Quorum Queues

**File**: `services/instance-service/app/celery_config.py`

**Current Configuration** (line 35):
```python
    worker_prefetch_multiplier=1,  # One task per worker at a time
```

**Optimized Configuration**:
```python
    worker_prefetch_multiplier=4,  # Optimized for quorum queues (prevents consumer starvation)
```

**Why This Change:**

**Problem with Prefetch=1 for Quorum Queues:**
- Quorum queues use Raft consensus protocol (distributed system)
- Message acknowledgements must reach quorum before next message
- Low prefetch = consumer waits idle while acks propagate
- This is called "consumer starvation"

**Benefits of Prefetch=4:**
- Worker can fetch next task while acknowledging previous
- Overlaps network I/O with task processing
- 2-4x throughput improvement for I/O-bound tasks
- Still maintains task_acks_late=True safety

**Why Not Higher?**
- Prefetch=1 was chosen for safety (one task at a time)
- With `task_acks_late=True`, if worker crashes, unacknowledged tasks requeue
- Higher prefetch means more tasks lost on crash
- Prefetch=4 is a good balance (max 4 tasks lost per crash)
- Can increase to 8-16 if tasks are idempotent

**RabbitMQ Official Recommendation:**
> "Quorum queues benefit from consumers using higher prefetch values to ensure
> consumers aren't starved whilst acknowledgements are flowing through the system"

Source: [RabbitMQ Quorum Queues Documentation](https://www.rabbitmq.com/docs/quorum-queues)

**Alternative: Per-Queue Prefetch (Advanced)**

If different queues need different prefetch values:
```python
# In task decorator
@celery_app.task(
    queue='instance_provisioning',
    acks_late=True,
    prefetch_limit=2  # Override for this queue
)
def provision_instance(...):
    pass
```

**Testing**:
```bash
# Create test tasks to measure throughput
# File: services/instance-service/test_throughput.py
from app.celery_config import celery_app
from app.tasks.provisioning import provision_instance
import time

# Queue 100 test tasks
start = time.time()
for i in range(100):
    provision_instance.apply_async(
        args=[f"test-instance-{i}"],
        queue='instance_provisioning'
    )
elapsed = time.time() - start
print(f"Queued 100 tasks in {elapsed:.2f}s")

# Monitor completion rate
docker service logs saasodoo_instance-worker -f | grep "Task.*succeeded"

# Compare:
# Prefetch=1: ~30-40 tasks/minute (with network latency)
# Prefetch=4: ~60-120 tasks/minute (overlapped I/O)
```

**Monitoring Prefetch Behavior**:
```bash
# Check current prefetch count in RabbitMQ
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_consumers -p saasodoo

# Look for "prefetch_count" column
# Should show 4 (concurrency) * 4 (multiplier) = 16 total prefetch
```

**Success Criteria**:
✅ Worker processes tasks 2-4x faster (for I/O-bound tasks)
✅ No increase in task failures
✅ RabbitMQ shows correct prefetch count
✅ Worker still respects concurrency limits

**Rollback**:
Change back to `worker_prefetch_multiplier=1`.

**Note on Task Idempotency:**
- If tasks are NOT idempotent (same task run twice = bad), keep prefetch low
- If tasks ARE idempotent (can safely retry), prefetch=8-16 is safe
- Current provisioning tasks should be made idempotent for production safety

---

### STEP 5: Create RabbitMQ Initialization Configuration

#### 5.1: Create RabbitMQ Definitions File

**File**: `infrastructure/rabbitmq/definitions.json` (NEW FILE)

```json
{
  "rabbit_version": "4.2.0",
  "rabbitmq_version": "4.2.0",
  "product_name": "RabbitMQ",
  "product_version": "4.2.0",
  "users": [
    {
      "name": "saasodoo",
      "password_hash": "hashed_password_will_be_generated",
      "hashing_algorithm": "rabbit_password_hashing_sha256",
      "tags": ["administrator"],
      "limits": {}
    }
  ],
  "vhosts": [
    {
      "name": "saasodoo",
      "metadata": {
        "description": "SaaSOdoo Platform Virtual Host",
        "tags": ["production"]
      }
    }
  ],
  "permissions": [
    {
      "user": "saasodoo",
      "vhost": "saasodoo",
      "configure": ".*",
      "write": ".*",
      "read": ".*"
    }
  ],
  "topic_permissions": [],
  "parameters": [],
  "global_parameters": [
    {
      "name": "internal_cluster_id",
      "value": "saasodoo-cluster-001"
    }
  ],
  "policies": [
    {
      "vhost": "saasodoo",
      "name": "quorum-queue-replication",
      "pattern": "^instance_.*",
      "apply-to": "queues",
      "definition": {
        "max-length": 100000,
        "overflow": "reject-publish",
        "delivery-limit": 3
      },
      "priority": 10
    }
  ],
  "queues": [
    {
      "name": "instance_provisioning",
      "vhost": "saasodoo",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-queue-type": "quorum",
        "x-max-length": 10000,
        "x-overflow": "reject-publish"
      }
    },
    {
      "name": "instance_operations",
      "vhost": "saasodoo",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-queue-type": "quorum",
        "x-max-length": 10000,
        "x-overflow": "reject-publish"
      }
    },
    {
      "name": "instance_maintenance",
      "vhost": "saasodoo",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-queue-type": "quorum",
        "x-max-length": 10000,
        "x-overflow": "reject-publish"
      }
    },
    {
      "name": "instance_monitoring",
      "vhost": "saasodoo",
      "durable": true,
      "auto_delete": false,
      "arguments": {
        "x-queue-type": "quorum",
        "x-max-length": 10000,
        "x-overflow": "reject-publish"
      }
    }
  ],
  "exchanges": [
    {
      "name": "celery",
      "vhost": "saasodoo",
      "type": "topic",
      "durable": true,
      "auto_delete": false,
      "internal": false,
      "arguments": {}
    }
  ],
  "bindings": []
}
```

**Configuration Explanations:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `x-queue-type: quorum` | Quorum | High availability, data safety |
| `x-max-length: 10000` | 10k messages | Prevent unbounded queue growth |
| `x-overflow: reject-publish` | Reject | Backpressure when queue full |
| `durable: true` | Yes | Survive broker restarts |
| `delivery-limit: 3` | 3 attempts | Dead-letter after 3 failures |

#### 5.2: Generate Password Hash

**Script**: `infrastructure/rabbitmq/generate_password_hash.sh` (NEW FILE)

```bash
#!/bin/bash
# Generate RabbitMQ password hash for definitions.json

PASSWORD="${RABBITMQ_PASSWORD:-saasodoo123}"

# Generate hash using RabbitMQ's algorithm
docker run --rm rabbitmq:4.2.0-management-alpine \
  rabbitmqctl encode "$PASSWORD" | tail -1
```

Make executable and run:
```bash
chmod +x infrastructure/rabbitmq/generate_password_hash.sh
./infrastructure/rabbitmq/generate_password_hash.sh
```

Copy the output hash and replace `hashed_password_will_be_generated` in definitions.json.

#### 5.3: Update Docker Compose for RabbitMQ

**File**: `infrastructure/compose/docker-compose.ceph.yml`

**Find RabbitMQ service** and add volume mount:

```yaml
  rabbitmq:
    image: rabbitmq:4.2.0-management-alpine
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-saasodoo}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD:-saasodoo123}
      RABBITMQ_DEFAULT_VHOST: saasodoo
      RABBITMQ_ERLANG_COOKIE: ${RABBITMQ_ERLANG_COOKIE:-secret_cookie_change_me}
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
      # ADD THIS LINE:
      - type: bind
        source: ../../rabbitmq/definitions.json
        target: /etc/rabbitmq/definitions.json
        read_only: true
    configs:
      # ADD THIS SECTION:
      - source: rabbitmq-definitions
        target: /etc/rabbitmq/definitions.json
    # ... rest of rabbitmq config

# ADD AT END OF FILE:
configs:
  rabbitmq-definitions:
    file: ../../rabbitmq/definitions.json
```

**Alternative: Use Config Instead of Volume**

For Docker Swarm, configs are preferred over bind mounts:

```yaml
configs:
  rabbitmq-definitions:
    file: ../../rabbitmq/definitions.json

services:
  rabbitmq:
    # ... existing config
    configs:
      - source: rabbitmq-definitions
        target: /etc/rabbitmq/definitions.json
    environment:
      # ... existing env vars
      RABBITMQ_DEFINITIONS_FILE: /etc/rabbitmq/definitions.json
```

**Testing**:
```bash
# Deploy updated stack
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Wait for RabbitMQ to initialize
sleep 30

# Verify queues were created
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo name arguments

# Should output:
# instance_provisioning [{"x-queue-type","quorum"},{"x-max-length",10000}...]
# instance_operations   [{"x-queue-type","quorum"},{"x-max-length",10000}...]
# instance_maintenance  [{"x-queue-type","quorum"},{"x-max-length",10000}...]
# instance_monitoring   [{"x-queue-type","quorum"},{"x-max-length",10000}...]

# Verify policy is applied
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_policies -p saasodoo

# Should show quorum-queue-replication policy
```

**Success Criteria**:
✅ All 4 queues created automatically on RabbitMQ startup
✅ Queues have correct quorum type and arguments
✅ Policy applied to queues
✅ Configuration persists across RabbitMQ restarts

**Rollback**:
Remove the config/volume mount from docker-compose and restart RabbitMQ.

---

### STEP 6: Build, Test, and Deploy

#### 6.1: Pre-Deployment Checklist

**Verify All Changes:**
```bash
# 1. Check celery_config.py has broker_transport_options
grep -A 5 "broker_transport_options" services/instance-service/app/celery_config.py

# 2. Check celery_config.py has signal handlers
grep -A 10 "worker_ready\|worker_shutdown" services/instance-service/app/celery_config.py

# 3. Check healthcheck.py exists
ls -la services/instance-service/app/utils/healthcheck.py

# 4. Check healthcheck.sh exists and is executable
ls -la services/instance-service/healthcheck.sh

# 5. Check Dockerfile includes healthcheck.sh
grep "healthcheck.sh" services/instance-service/Dockerfile

# 6. Check docker-compose has new health check
grep -A 5 "healthcheck:" infrastructure/compose/docker-compose.ceph.yml | grep "/app/healthcheck.sh"

# 7. Check docker-compose has optimized command
grep -- "--without-gossip" infrastructure/compose/docker-compose.ceph.yml

# 8. Check celery_config has prefetch=4
grep "worker_prefetch_multiplier" services/instance-service/app/celery_config.py

# 9. Check RabbitMQ definitions file exists
ls -la infrastructure/rabbitmq/definitions.json
```

#### 6.2: Local Testing (Optional but Recommended)

**Test on Development Stack First:**
```bash
# Start dev stack
docker compose -f infrastructure/compose/docker-compose.dev.yml up --build -d instance-worker

# Watch logs
docker compose -f infrastructure/compose/docker-compose.dev.yml logs -f instance-worker

# Verify health check files
docker exec $(docker ps | grep instance-worker | awk '{print $1}') ls -la /tmp/celery_worker_*

# Test health check script
docker exec $(docker ps | grep instance-worker | awk '{print $1}') /app/healthcheck.sh

# Queue a test task
docker exec $(docker ps | grep instance-service | awk '{print $1}') \
  python -c "from app.tasks.monitoring import check_instance_health; check_instance_health.delay('test-123')"

# Verify task processed
docker compose -f infrastructure/compose/docker-compose.dev.yml logs instance-worker | grep "Task.*succeeded"

# Clean up
docker compose -f infrastructure/compose/docker-compose.dev.yml down
```

#### 6.3: Production Build Process

**Build with No Cache (Clean Build):**
```bash
cd /root/saasodoo

# Build instance-service image (worker uses same image)
docker build \
  --no-cache \
  --progress=plain \
  -t registry.62.171.153.219.nip.io/compose-instance-service:latest \
  -f services/instance-service/Dockerfile \
  services/instance-service/

# Check build succeeded
docker images | grep compose-instance-service

# Verify health check script is in image
docker run --rm registry.62.171.153.219.nip.io/compose-instance-service:latest ls -la /app/healthcheck.sh

# Verify healthcheck.py is in image
docker run --rm registry.62.171.153.219.nip.io/compose-instance-service:latest ls -la /app/utils/healthcheck.py
```

**Expected Build Output:**
```
Step X/Y : COPY healthcheck.sh /app/healthcheck.sh
Step X/Y : RUN chmod +x /app/healthcheck.sh
...
Successfully built abc123def456
Successfully tagged registry.62.171.153.219.nip.io/compose-instance-service:latest
```

#### 6.4: Tag and Push to Registry

```bash
# Tag worker image (same as service image)
docker tag \
  registry.62.171.153.219.nip.io/compose-instance-service:latest \
  registry.62.171.153.219.nip.io/compose-instance-worker:latest

# Push both images to registry
docker push registry.62.171.153.219.nip.io/compose-instance-service:latest
docker push registry.62.171.153.219.nip.io/compose-instance-worker:latest
```

**Verify Push:**
```bash
# Check images in registry (if you have registry UI)
# Or verify with docker pull
docker pull registry.62.171.153.219.nip.io/compose-instance-worker:latest
```

#### 6.5: Update RabbitMQ Configuration First

**IMPORTANT: Deploy RabbitMQ changes before worker changes**

**Option A: Without Data Loss (Recommended):**
```bash
# Update RabbitMQ service to include definitions
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Wait for RabbitMQ to reload config
sleep 30

# Verify queues exist
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo
```

**Option B: Clean RabbitMQ Data (If Issues):**
```bash
# CAUTION: This deletes all RabbitMQ data including queued tasks
sudo rm -rf /mnt/cephfs/rabbitmq_data/*

# Redeploy stack
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Wait for RabbitMQ to initialize
sleep 60

# Verify queues created
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo
```

#### 6.6: Deploy Worker Service Update

**Update instance-worker service:**
```bash
# Update worker with new image
docker service update \
  --image registry.62.171.153.219.nip.io/compose-instance-worker:latest \
  --force \
  saasodoo_instance-worker

# Monitor rollout
watch docker service ps saasodoo_instance-worker

# Wait for new task to be "Running"
# Old task will show "Shutdown" when gracefully stopped
```

**Alternative: Full Stack Redeploy:**
```bash
# This redeploys the entire stack (more disruptive)
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Monitor all services
docker stack ps saasodoo
```

#### 6.7: Post-Deployment Verification

**Immediate Checks (0-5 minutes):**
```bash
# 1. Check worker task is running
docker service ps saasodoo_instance-worker
# Should show: Current State = Running

# 2. Check worker logs for startup
docker service logs saasodoo_instance-worker --tail 100
# Should see:
# [INFO] Connected to amqp://saasodoo:**@rabbitmq:5672/saasodoo
# [INFO] Created worker alive file: /tmp/celery_worker_alive
# [INFO] Started health check heartbeat (interval: 30s)
# [INFO] celery@HOSTNAME ready.

# 3. Check for errors
docker service logs saasodoo_instance-worker --tail 100 | grep -i "error\|failed\|exception"
# Should be empty or minimal

# 4. Verify health check files exist
WORKER_CONTAINER=$(docker ps | grep instance-worker | awk '{print $1}')
docker exec $WORKER_CONTAINER ls -la /tmp/celery_worker_*
# Should show both files with recent timestamps

# 5. Test health check script
docker exec $WORKER_CONTAINER /app/healthcheck.sh
# Should output: HEALTHY: Worker alive and heartbeat fresh (Xs ago)

# 6. Check Docker health status
docker ps | grep instance-worker
# STATUS column should show "healthy" or "health: starting"
```

**Short-term Checks (5-30 minutes):**
```bash
# 1. Monitor health check updates
watch -n 5 'docker exec $(docker ps | grep instance-worker | awk '\''{print $1}'\'') stat /tmp/celery_worker_heartbeat | grep Modify'
# Timestamp should update every ~30 seconds

# 2. Check for restart loops
docker service ps saasodoo_instance-worker --no-trunc
# Should only show one "Running" task (no repeated failures)

# 3. Monitor RabbitMQ for pidbox errors
docker service logs saasodoo_rabbitmq --since 5m | grep pidbox
# Should be EMPTY (no pidbox queue not found errors)

# 4. Test task processing
# Queue a monitoring task
docker exec $(docker ps | grep instance-service | awk '{print $1}') \
  python -c "from app.tasks.monitoring import check_instance_health; print(check_instance_health.delay('test-instance-123').id)"

# Check task completed
docker service logs saasodoo_instance-worker --since 5m | grep "Task.*check_instance_health.*succeeded"

# 5. Check CPU usage
docker stats --no-stream | grep instance-worker
# CPU% should be <1% when idle (vs 5-10% before)
```

**Long-term Checks (30 minutes - 24 hours):**
```bash
# 1. Monitor for 24 hours - no restarts
watch -n 300 'docker service ps saasodoo_instance-worker | head -5'
# Should consistently show same task ID for 24+ hours

# 2. Check uptime
docker exec $(docker ps | grep instance-worker | awk '{print $1}') ps aux | grep celery
# TIME column should increase continuously

# 3. Monitor task throughput
# Generate load test
for i in {1..100}; do
  docker exec $(docker ps | grep instance-service | awk '{print $1}') \
    python -c "from app.tasks.monitoring import check_instance_health; check_instance_health.delay('test-$i')"
done

# Count completed tasks
docker service logs saasodoo_instance-worker --since 10m | grep -c "Task.*succeeded"
# Should be 100 (all tasks completed)

# 4. Verify no memory leaks
docker stats --no-stream | grep instance-worker
# MEM% should stay relatively stable (not continuously increasing)

# 5. Check error rate
docker service logs saasodoo_instance-worker --since 1h | grep -c "ERROR"
# Should be 0 or very low
```

#### 6.8: Success Criteria Summary

| Metric | Target | Verification Command |
|--------|--------|---------------------|
| Worker Uptime | 24+ hours | `docker service ps saasodoo_instance-worker` |
| Health Check Pass Rate | 100% | `docker ps \| grep instance-worker` (shows "healthy") |
| CPU Usage (Idle) | <1% | `docker stats --no-stream \| grep instance-worker` |
| Task Processing | All tasks complete | Queue tasks and check logs |
| No RabbitMQ Errors | 0 pidbox errors | `docker service logs saasodoo_rabbitmq \| grep pidbox` |
| Heartbeat Updates | Every 30s | `docker exec ... stat /tmp/celery_worker_heartbeat` |
| Memory Usage | Stable | `docker stats` over 24 hours |
| Restart Count | 0 restarts | `docker service ps saasodoo_instance-worker` |

---

## Testing Procedures

### Unit Tests (Before Deployment)

#### Test 1: Health Check Script Logic
```bash
# Create test script
cat > /tmp/test_healthcheck.sh <<'EOF'
#!/bin/bash
set -e

# Test 1: Missing alive file
rm -f /tmp/celery_worker_alive /tmp/celery_worker_heartbeat
bash services/instance-service/healthcheck.sh && echo "FAIL: Should fail without alive file" || echo "PASS: Correctly failed"

# Test 2: Missing heartbeat file
touch /tmp/celery_worker_alive
rm -f /tmp/celery_worker_heartbeat
bash services/instance-service/healthcheck.sh && echo "FAIL: Should fail without heartbeat" || echo "PASS: Correctly failed"

# Test 3: Stale heartbeat
touch /tmp/celery_worker_alive
touch /tmp/celery_worker_heartbeat
sleep 2
touch -d "120 seconds ago" /tmp/celery_worker_heartbeat
bash services/instance-service/healthcheck.sh && echo "FAIL: Should fail with stale heartbeat" || echo "PASS: Correctly failed"

# Test 4: Fresh heartbeat
touch /tmp/celery_worker_alive
touch /tmp/celery_worker_heartbeat
bash services/instance-service/healthcheck.sh && echo "PASS: Correctly passed" || echo "FAIL: Should pass with fresh heartbeat"

# Cleanup
rm -f /tmp/celery_worker_alive /tmp/celery_worker_heartbeat
EOF

chmod +x /tmp/test_healthcheck.sh
bash /tmp/test_healthcheck.sh
```

#### Test 2: Health Check Python Module
```python
# File: services/instance-service/test_healthcheck.py
import os
import time
from pathlib import Path
from app.utils.healthcheck import WorkerHealthCheck

def test_health_check():
    """Test WorkerHealthCheck creates and maintains files."""
    hc = WorkerHealthCheck()

    # Start health check
    hc.start()

    # Verify files created
    assert Path("/tmp/celery_worker_alive").exists(), "Alive file not created"
    assert Path("/tmp/celery_worker_heartbeat").exists(), "Heartbeat file not created"

    # Wait for heartbeat update
    initial_mtime = os.path.getmtime("/tmp/celery_worker_heartbeat")
    time.sleep(35)  # Wait longer than HEARTBEAT_INTERVAL
    updated_mtime = os.path.getmtime("/tmp/celery_worker_heartbeat")

    assert updated_mtime > initial_mtime, "Heartbeat not updated"

    # Stop and verify cleanup
    hc.stop()
    assert not Path("/tmp/celery_worker_alive").exists(), "Alive file not cleaned up"
    assert not Path("/tmp/celery_worker_heartbeat").exists(), "Heartbeat file not cleaned up"

    print("All health check tests passed!")

if __name__ == "__main__":
    test_health_check()
```

Run test:
```bash
cd services/instance-service
python test_healthcheck.py
```

#### Test 3: Celery Configuration Validation
```python
# File: services/instance-service/test_celery_config.py
from app.celery_config import celery_app

def test_celery_config():
    """Validate Celery configuration."""
    config = celery_app.conf

    # Test broker_transport_options
    assert 'broker_transport_options' in config, "Missing broker_transport_options"
    assert config['broker_transport_options'].get('confirm_publish') is True, \
        "confirm_publish not enabled"

    # Test queues
    assert len(config['task_queues']) == 4, "Should have 4 queues"
    for queue in config['task_queues']:
        assert queue.queue_arguments.get('x-queue-type') == 'quorum', \
            f"Queue {queue.name} is not quorum type"

    # Test prefetch
    assert config['worker_prefetch_multiplier'] == 4, \
        "Prefetch multiplier should be 4"

    # Test other critical settings
    assert config['task_acks_late'] is True, "task_acks_late should be True"
    assert config['task_track_started'] is True, "task_track_started should be True"

    print("All Celery config tests passed!")

if __name__ == "__main__":
    test_celery_config()
```

Run test:
```bash
cd services/instance-service
python test_celery_config.py
```

### Integration Tests (After Deployment)

#### Test 4: End-to-End Task Processing
```bash
# Queue tasks to all 4 queues
docker exec $(docker ps | grep instance-service | awk '{print $1}') python <<'EOF'
from app.celery_config import celery_app

# Test each queue
queues = [
    'instance_provisioning',
    'instance_operations',
    'instance_maintenance',
    'instance_monitoring'
]

for queue in queues:
    result = celery_app.send_task(
        'app.tasks.monitoring.check_instance_health',
        args=['test-instance'],
        queue=queue
    )
    print(f"Queued to {queue}: {result.id}")
EOF

# Verify all tasks completed
sleep 10
docker service logs saasodoo_instance-worker --since 1m | grep "Task.*succeeded"
# Should see 4 successful task completions
```

#### Test 5: Worker Recovery After RabbitMQ Restart
```bash
# Restart RabbitMQ
docker service update --force saasodoo_rabbitmq

# Wait for RabbitMQ to come back
sleep 30

# Check worker reconnected
docker service logs saasodoo_instance-worker --since 1m | grep -i "connect"
# Should see: "Connected to amqp://..."

# Queue a task to verify connectivity
docker exec $(docker ps | grep instance-service | awk '{print $1}') \
  python -c "from app.tasks.monitoring import check_instance_health; print(check_instance_health.delay('test').id)"

# Verify task processed
docker service logs saasodoo_instance-worker --since 1m | grep "Task.*succeeded"
```

#### Test 6: Worker Graceful Shutdown
```bash
# Trigger graceful shutdown
docker service scale saasodoo_instance-worker=0

# Watch logs for graceful shutdown
docker service logs saasodoo_instance-worker --since 1m | tail -20
# Should see:
# [INFO] Stopped health check heartbeat
# [INFO] Cleaned up health check files
# worker: Warm shutdown (MainProcess)

# Verify no errors
docker service logs saasodoo_instance-worker --since 1m | grep -i "error"
# Should be empty

# Scale back up
docker service scale saasodoo_instance-worker=1
```

#### Test 7: Health Check Resilience
```bash
# Get worker container
WORKER_CONTAINER=$(docker ps | grep instance-worker | awk '{print $1}')

# Test 1: Verify health check passes
docker exec $WORKER_CONTAINER /app/healthcheck.sh
echo "Exit code: $?"
# Should output: HEALTHY... (exit code 0)

# Test 2: Manually stop heartbeat updates (simulate hang)
docker exec $WORKER_CONTAINER mv /tmp/celery_worker_heartbeat /tmp/celery_worker_heartbeat.bak

# Wait for health check to fail
sleep 90

# Check container health status
docker ps | grep instance-worker
# STATUS should show "(unhealthy)"

# Restore heartbeat
docker exec $WORKER_CONTAINER mv /tmp/celery_worker_heartbeat.bak /tmp/celery_worker_heartbeat
docker exec $WORKER_CONTAINER touch /tmp/celery_worker_heartbeat

# Wait for health to recover
sleep 90
docker ps | grep instance-worker
# STATUS should show "(healthy)"
```

### Load Tests (Stress Testing)

#### Test 8: High Task Volume
```bash
# Queue 1000 tasks
for i in {1..1000}; do
  docker exec $(docker ps | grep instance-service | awk '{print $1}') \
    python -c "from app.tasks.monitoring import check_instance_health; check_instance_health.delay('load-test-$i')" &
done
wait

# Monitor completion
watch -n 5 'docker service logs saasodoo_instance-worker --since 5m | grep -c "Task.*succeeded"'

# Verify all 1000 completed (may take 10-30 minutes depending on task duration)

# Check for errors
docker service logs saasodoo_instance-worker --since 30m | grep -i "error\|failed"
# Should be minimal or none
```

#### Test 9: Long-Running Task Handling
```python
# Create long-running test task
# File: services/instance-service/app/tasks/test_tasks.py
from app.celery_config import celery_app
import time

@celery_app.task(queue='instance_maintenance')
def long_running_task(duration):
    """Simulate long-running task."""
    time.sleep(duration)
    return f"Completed {duration}s task"

# Queue from Python
from app.tasks.test_tasks import long_running_task
result = long_running_task.delay(600)  # 10 minute task
print(f"Task ID: {result.id}")
```

Monitor task execution:
```bash
# Watch task progress
docker service logs saasodoo_instance-worker -f | grep "long_running_task"

# Verify heartbeat continues during long task
watch -n 5 'docker exec $(docker ps | grep instance-worker | awk '\''{print $1}'\'') stat /tmp/celery_worker_heartbeat | grep Modify'

# Check health status remains healthy
docker ps | grep instance-worker
# Should stay "(healthy)" throughout 10-minute task
```

---

## Rollback Plan

### Quick Rollback (Revert to Previous Image)

**If new deployment has critical issues:**

```bash
# 1. Find previous working image version
docker service ps saasodoo_instance-worker --no-trunc | head -10
# Look for last "Shutdown" task with working image

# 2. Rollback to previous image
docker service rollback saasodoo_instance-worker

# 3. Monitor rollback
watch docker service ps saasodoo_instance-worker

# 4. Verify old worker is running
docker service logs saasodoo_instance-worker --tail 50
```

### Partial Rollback (Revert Specific Changes)

#### Rollback Step 1: Remove broker_transport_options
```bash
# Edit celery_config.py and remove broker_transport_options section
# Rebuild and redeploy
```

#### Rollback Step 2: Revert to Old Health Check
```bash
# Edit docker-compose.ceph.yml line 585-590
# Change back to:
healthcheck:
  test: ["CMD-SHELL", "celery -A app.celery_config status 2>&1 | grep -q ':.*OK' || exit 1"]
  interval: 60s
  timeout: 20s
  retries: 5
  start_period: 60s

# Redeploy
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

#### Rollback Step 3: Remove Worker Flags
```bash
# Edit docker-compose.ceph.yml line 531
# Remove: --without-gossip --without-mingle --without-heartbeat
# Redeploy
```

#### Rollback Step 4: Revert Prefetch Multiplier
```bash
# Edit celery_config.py line 35
# Change back to: worker_prefetch_multiplier=1
# Rebuild and redeploy
```

#### Rollback Step 5: Remove RabbitMQ Definitions
```bash
# Edit docker-compose.ceph.yml
# Remove rabbitmq configs section
# Redeploy
```

### Emergency Rollback (Complete System Restore)

**If all else fails:**

```bash
# 1. Scale worker to 0
docker service scale saasodoo_instance-worker=0

# 2. Clear RabbitMQ data (CAUTION: Deletes queued tasks!)
sudo rm -rf /mnt/cephfs/rabbitmq_data/*

# 3. Revert all code changes
git checkout HEAD -- services/instance-service/
git checkout HEAD -- infrastructure/compose/docker-compose.ceph.yml
git checkout HEAD -- infrastructure/rabbitmq/

# 4. Rebuild from known-good commit
git log --oneline -10  # Find last working commit
git checkout <commit-hash>

# 5. Rebuild and redeploy
docker build --no-cache -t registry.62.171.153.219.nip.io/compose-instance-service:latest \
  -f services/instance-service/Dockerfile services/instance-service/
docker tag registry.62.171.153.219.nip.io/compose-instance-service:latest \
  registry.62.171.153.219.nip.io/compose-instance-worker:latest
docker push registry.62.171.153.219.nip.io/compose-instance-service:latest
docker push registry.62.171.153.219.nip.io/compose-instance-worker:latest

# 6. Redeploy stack
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# 7. Scale worker back to 1
docker service scale saasodoo_instance-worker=1
```

---

## Monitoring & Validation

### Continuous Monitoring Setup

#### Prometheus Metrics (Future Enhancement)

**Install Celery Prometheus Exporter:**
```yaml
# Add to docker-compose.ceph.yml
celery-exporter:
  image: danihodovic/celery-exporter:latest
  environment:
    CELERY_BROKER_URL: amqp://saasodoo:saasodoo123@rabbitmq:5672/saasodoo
  ports:
    - "9808:9808"
  networks:
    - saasodoo-network
```

**Metrics to Monitor:**
- `celery_worker_up` - Worker availability (should be 1)
- `celery_tasks_total` - Total tasks processed
- `celery_tasks_failed_total` - Failed tasks (should be low)
- `celery_tasks_runtime_seconds` - Task execution time
- `celery_workers` - Number of active workers

#### Logging Strategy

**Centralized Logging:**
```bash
# Ship logs to centralized logging system
# Example: Loki, ELK, or CloudWatch

# Docker log driver (add to docker-compose.ceph.yml)
services:
  instance-worker:
    logging:
      driver: "json-file"
      options:
        max-size: "100m"
        max-file: "10"
        labels: "service=instance-worker,environment=production"
```

**Log Queries to Monitor:**
```bash
# Error rate
docker service logs saasodoo_instance-worker --since 1h | grep -c "ERROR"

# Task success rate
SUCCESS=$(docker service logs saasodoo_instance-worker --since 1h | grep -c "Task.*succeeded")
FAILED=$(docker service logs saasodoo_instance-worker --since 1h | grep -c "Task.*failed")
echo "Success rate: $(bc <<< "scale=2; $SUCCESS / ($SUCCESS + $FAILED) * 100")%"

# Health check failures
docker service logs saasodoo_instance-worker --since 1h | grep -c "UNHEALTHY"

# Connection issues
docker service logs saasodoo_instance-worker --since 1h | grep -c "connection.*lost\|connection.*failed"
```

### Alert Conditions

**Critical Alerts (Page On-Call):**
1. Worker down for >5 minutes
2. Task failure rate >10%
3. RabbitMQ connection failures
4. Health check failures >3 in a row

**Warning Alerts (Email/Slack):**
1. Worker restart detected
2. Task queue backlog >100 messages
3. Worker CPU >80% for >10 minutes
4. Worker memory >90% for >10 minutes
5. Task latency >5 minutes

**Alert Script Example:**
```bash
#!/bin/bash
# File: /root/saasodoo/scripts/monitor_worker.sh

# Check if worker is running
RUNNING=$(docker service ps saasodoo_instance-worker | grep -c "Running")
if [ "$RUNNING" -eq 0 ]; then
    echo "CRITICAL: Worker not running" | mail -s "Worker Down" ops@company.com
fi

# Check error rate
ERRORS=$(docker service logs saasodoo_instance-worker --since 1h | grep -c "ERROR")
if [ "$ERRORS" -gt 10 ]; then
    echo "WARNING: High error rate ($ERRORS in last hour)" | mail -s "Worker Errors" ops@company.com
fi

# Check queue depth
QUEUE_DEPTH=$(docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo | awk '{sum+=$2} END {print sum}')
if [ "$QUEUE_DEPTH" -gt 100 ]; then
    echo "WARNING: Queue backlog ($QUEUE_DEPTH messages)" | mail -s "Queue Backlog" ops@company.com
fi
```

**Schedule with Cron:**
```bash
# Run every 5 minutes
*/5 * * * * /root/saasodoo/scripts/monitor_worker.sh
```

### Health Dashboard (Optional)

**Create Simple Status Page:**
```bash
#!/bin/bash
# File: /root/saasodoo/scripts/worker_status.sh

echo "=== SaaSOdoo Instance Worker Status ==="
echo ""
echo "Worker Status:"
docker service ps saasodoo_instance-worker | head -5
echo ""
echo "Health Check:"
WORKER_CONTAINER=$(docker ps | grep instance-worker | awk '{print $1}')
if [ -n "$WORKER_CONTAINER" ]; then
    docker exec $WORKER_CONTAINER /app/healthcheck.sh
else
    echo "Worker container not found"
fi
echo ""
echo "Queue Depths:"
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo name messages_ready
echo ""
echo "Recent Errors:"
docker service logs saasodoo_instance-worker --since 1h | grep "ERROR" | tail -5
echo ""
echo "Task Throughput (last hour):"
echo "Success: $(docker service logs saasodoo_instance-worker --since 1h | grep -c 'Task.*succeeded')"
echo "Failed: $(docker service logs saasodoo_instance-worker --since 1h | grep -c 'Task.*failed')"
```

Run periodically:
```bash
watch -n 60 /root/saasodoo/scripts/worker_status.sh
```

---

## References & Research

### Official Documentation
1. [Celery Documentation - Using RabbitMQ](https://docs.celeryq.dev/en/v5.5.3/getting-started/backends-and-brokers/rabbitmq.html)
2. [RabbitMQ Quorum Queues](https://www.rabbitmq.com/docs/quorum-queues)
3. [Celery Configuration Reference](https://docs.celeryq.dev/en/latest/userguide/configuration.html)
4. [Docker Swarm Healthcheck](https://docs.docker.com/engine/reference/builder/#healthcheck)

### Research Articles & Best Practices
5. [Docker Health Check for Celery Workers](https://celery.school/docker-health-check-for-celery-workers)
6. [Health checks for Celery in Kubernetes](https://medium.com/ambient-innovation/health-checks-for-celery-in-kubernetes-cf3274a3e106)
7. [Production-Ready Celery Configuration](https://progressstory.com/tech/python/production-ready-celery-configuration/)
8. [CloudAMQP Celery Best Practices](https://www.cloudamqp.com/docs/celery.html)

### Community Discussions & Issues
9. [Celery pidbox reply queue not found](https://github.com/celery/celery/issues/4618)
10. [Consequences of disabling gossip, mingle and heartbeat](https://stackoverflow.com/questions/55249197/)
11. [Worker stops consuming after Redis reconnection](https://github.com/celery/celery/discussions/7276)
12. [Two years with Celery in Production - Bug Fix Edition](https://medium.com/squad-engineering/two-years-with-celery-in-production-bug-fix-edition-22238669601d)

### Performance & Optimization
13. [Amazon MQ for RabbitMQ - Performance Best Practices](https://docs.aws.amazon.com/amazon-mq/latest/developer-guide/best-practices-performance.html)
14. [My challenges deploying RabbitMQ Quorum Queues](https://medium.com/@thiagosalvatore/my-challenges-deploying-rabbitmq-quorum-queues-b7b981d7a4ba)
15. [Enabling RabbitMQ's Quorum Queues in Celery](http://blog.liorp.dev/development/enabling-rabbitmq-quorum-queues-in-celery/)

---

## Appendix

### Appendix A: Complete File Listing

**Files Modified:**
1. `/root/saasodoo/services/instance-service/app/celery_config.py` (lines 26, 50-60)
2. `/root/saasodoo/infrastructure/compose/docker-compose.ceph.yml` (lines 531, 585-590)

**Files Created:**
3. `/root/saasodoo/services/instance-service/healthcheck.sh` (NEW)
4. `/root/saasodoo/services/instance-service/app/utils/healthcheck.py` (NEW)
5. `/root/saasodoo/infrastructure/rabbitmq/definitions.json` (NEW)
6. `/root/saasodoo/infrastructure/rabbitmq/generate_password_hash.sh` (NEW)
7. `/root/saasodoo/docs/INSTANCE_WORKER_FIX_PLAN.md` (THIS DOCUMENT)

### Appendix B: Configuration Comparison

**Before (Problematic):**
```python
# celery_config.py - Missing broker_transport_options
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    # ... no broker_transport_options
)
```

```yaml
# docker-compose.ceph.yml - Problematic health check
healthcheck:
  test: ["CMD-SHELL", "celery -A app.celery_config status 2>&1 | grep -q ':.*OK' || exit 1"]
  interval: 60s  # Too long for pidbox queue expiry

# Missing worker flags
command: celery -A app.celery_config worker --loglevel=info --pool=threads --concurrency=16 ...
```

**After (Fixed):**
```python
# celery_config.py - With broker_transport_options
celery_app.conf.update(
    worker_prefetch_multiplier=4,  # Optimized for quorum queues
    broker_transport_options={
        'confirm_publish': True,  # Required for quorum queues
    },
)
```

```yaml
# docker-compose.ceph.yml - File-based health check
healthcheck:
  test: ["CMD", "/app/healthcheck.sh"]
  interval: 30s  # Safe with file-based check

# Optimized worker command
command: >-
  celery -A app.celery_config worker ...
  --without-gossip --without-mingle --without-heartbeat
```

### Appendix C: Troubleshooting Guide

**Problem: Worker still restarting after deployment**

Diagnosis:
```bash
# Check why it's failing
docker service ps saasodoo_instance-worker --no-trunc
docker service logs saasodoo_instance-worker --tail 100
```

Solutions:
- If "health check timeout": Verify `/app/healthcheck.sh` exists in container
- If "broker connection failed": Check RabbitMQ is running and credentials match
- If "module not found": Rebuild image with `--no-cache`

**Problem: Tasks not being processed**

Diagnosis:
```bash
# Check worker is consuming
docker service logs saasodoo_instance-worker | grep "ready"
# Check queues have tasks
docker exec $(docker ps | grep rabbitmq | awk '{print $1}') \
  rabbitmqctl list_queues -p saasodoo
```

Solutions:
- Verify queues are bound correctly
- Check worker is connected to broker
- Verify task routes in celery_config.py

**Problem: High CPU usage despite flags**

Diagnosis:
```bash
# Verify flags are active
docker service inspect saasodoo_instance-worker | grep -A 5 "Args"
```

Solutions:
- Rebuild image if flags not in command
- Check for runaway tasks (increase --max-tasks-per-child)

### Appendix D: Future Improvements

1. **Auto-scaling**: Implement Celery autoscaler based on queue depth
2. **Task prioritization**: Use priority routing for critical tasks
3. **Dead letter queues**: Capture failed tasks for manual review
4. **Metrics dashboard**: Grafana + Prometheus for real-time monitoring
5. **Task result backend optimization**: Consider Redis persistence vs TTL
6. **Graceful deployments**: Blue-green deployment for zero-downtime updates
7. **Task idempotency**: Make all tasks idempotent for safe retries
8. **Circuit breakers**: Prevent cascading failures from external services

---

**END OF DOCUMENT**

---

This plan should be executed step-by-step with full testing after each step. Do not skip testing phases. If any step fails, rollback before proceeding.

**Questions or issues during implementation?** Refer to the research sources or open a discussion in the team channel.
