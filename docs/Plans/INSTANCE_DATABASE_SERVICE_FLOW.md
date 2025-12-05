# Instance-Service ↔ Database-Service Flow Explanation

**Date**: 2025-12-05
**Purpose**: Detailed explanation of async operations, Celery tasks, and queues between instance-service and database-service

---

## 🎯 Overview

When an instance is created, there are **two possible flows** depending on whether a database pool is already available:

1. **Fast Path**: Pool exists → Database allocated immediately (~1-2 seconds)
2. **Slow Path**: No pool → Pool must be provisioned first (~3-5 minutes)

---

## 📊 Complete Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          BILLING SERVICE                                 │
│  KillBill Webhook Handler (SUBSCRIPTION_CREATION)                       │
│  ────────────────────────────────────────────────────────────────       │
│  1. Get plan_name from KillBill subscription                            │
│  2. Look up app.state.plan_entitlements[plan_name]                      │
│  3. Extract: db_type, cpu_limit, memory_limit, storage_limit            │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ HTTP POST /api/instances
                          │ {
                          │   customer_id: "...",
                          │   subscription_id: "...",
                          │   plan_name: "basic-monthly",
                          │   db_type: "shared",  ← from plan_entitlements
                          │   cpu_limit: 1.0,
                          │   memory_limit: "2G",
                          │   storage_limit: "10G"
                          │ }
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        INSTANCE SERVICE (FastAPI)                        │
│  Route: POST /api/instances                                              │
│  ────────────────────────────────────────────────────────────────       │
│  STEP 1: Create instance record in database                             │
│          status = "creating"                                             │
│          db_type = request.db_type (from billing)                        │
│                                                                          │
│  STEP 2: Call database-service to allocate database                     │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ HTTP POST /api/database/allocate
                          │ {
                          │   instance_id: "abc-123...",
                          │   customer_id: "xyz-456...",
                          │   db_type: "shared"
                          │ }
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      DATABASE SERVICE (FastAPI)                          │
│  Route: POST /api/database/allocate                                      │
│  File: app/routes/allocation.py:allocate_database()                     │
│  ────────────────────────────────────────────────────────────────       │
│  STEP 1: Check db_type                                                   │
│          IF db_type == "dedicated":                                      │
│             → Return status="provisioning" (not implemented yet)         │
│                                                                          │
│  STEP 2: IF db_type == "shared":                                         │
│          → Call allocation_service.allocate_database_for_instance()      │
│          → Look for available shared pool in database:                   │
│             SELECT * FROM db_servers                                     │
│             WHERE server_type = 'shared'                                 │
│               AND status = 'active'                                      │
│               AND health_status IN ('healthy', 'unknown')                │
│               AND current_instances < max_instances                      │
│             ORDER BY priority ASC, current_instances ASC                 │
│             LIMIT 1                                                      │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                ┌─────────┴─────────┐
                │                   │
         Pool exists?        Pool doesn't exist?
                │                   │
        ┌───────▼──────┐    ┌──────▼────────┐
        │  FAST PATH   │    │   SLOW PATH   │
        │ (~1-2 sec)   │    │  (~3-5 min)   │
        └───────┬──────┘    └──────┬────────┘
                │                   │
                │                   │
┌───────────────▼───────────────────▼──────────────────────────────────────┐
│                       ALLOCATION SERVICE                                 │
│  File: app/services/db_allocation_service.py                            │
└──────────────────────────────────────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════════════
                            🚀 FAST PATH
════════════════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────────────┐
│  ALLOCATION SERVICE (continued)                                          │
│  ────────────────────────────────────────────────────────────────────   │
│  Pool found! Let's allocate database immediately.                        │
│                                                                          │
│  STEP 3: Generate database name                                          │
│          db_name = f"odoo_{customer_id[:16]}_{instance_id[:8]}"          │
│          Example: "odoo_a1b2c3d4e5f6g7h8_abc12345"                       │
│                                                                          │
│  STEP 4: Create PostgreSQL database on pool server                       │
│          ┌────────────────────────────────────────────┐                 │
│          │ Connect to postgres-pool-1:5432            │                 │
│          │ CREATE DATABASE odoo_a1b2c3d4e5f6g7h8_...  │                 │
│          │ CREATE USER odoo_..._user WITH PASSWORD... │                 │
│          │ GRANT ALL PRIVILEGES ON DATABASE ...       │                 │
│          └────────────────────────────────────────────┘                 │
│                                                                          │
│  STEP 5: Increment instance count                                        │
│          UPDATE db_servers                                               │
│          SET current_instances = current_instances + 1                   │
│          WHERE id = pool_id                                              │
│                                                                          │
│  STEP 6: Return allocation result                                        │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Returns to database-service FastAPI route:
                          │ {
                          │   "status": "allocated",
                          │   "db_server_id": "pool-uuid",
                          │   "db_host": "postgres-pool-1",
                          │   "db_port": 5432,
                          │   "db_name": "odoo_a1b2..._abc123",
                          │   "db_user": "odoo_a1b2..._abc123_user",
                          │   "db_password": "generated_password"
                          │ }
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DATABASE SERVICE FastAPI Route (returns to instance-service)           │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ HTTP 200 Response with db_config
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INSTANCE SERVICE Route (receives response)                              │
│  ────────────────────────────────────────────────────────────────────   │
│  STEP 3: Update instance record with database config                     │
│          UPDATE instances                                                │
│          SET db_server_id = $1,                                          │
│              db_host = $2,                                               │
│              db_port = $3,                                               │
│              db_name = $4,                                               │
│              status = 'provisioning'                                     │
│                                                                          │
│  STEP 4: Queue Celery task for Odoo container provisioning              │
│          provision_instance_task.delay(                                  │
│              instance_id=instance_id,                                    │
│              db_config=db_config                                         │
│          )                                                               │
│                                                                          │
│  STEP 5: Return HTTP 201 response to billing-service                     │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Queues task to RabbitMQ
                          │ Queue: instance_provisioning
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         RABBITMQ                                         │
│  Queue: instance_provisioning (quorum queue)                            │
│  ────────────────────────────────────────────────────────────────────   │
│  Task: provision_instance_task                                           │
│  Args: {instance_id, db_config}                                          │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Worker picks up task
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                    INSTANCE WORKER (Celery)                              │
│  Task: provision_instance_task                                           │
│  File: app/tasks/provisioning.py                                        │
│  Queue: instance_provisioning                                            │
│  ────────────────────────────────────────────────────────────────────   │
│  STEP 1: Create CephFS directory for instance data                       │
│          mkdir -p /mnt/cephfs/odoo_instances/odoo_data_{db_name}        │
│                                                                          │
│  STEP 2: Create Docker service for Odoo                                  │
│          docker service create \                                         │
│            --name odoo_{instance_id[:8]} \                               │
│            --env DB_HOST=postgres-pool-1 \                               │
│            --env DB_PORT=5432 \                                          │
│            --env DB_NAME=odoo_a1b2..._abc123 \                           │
│            --env DB_USER=odoo_..._user \                                 │
│            --env DB_PASSWORD=... \                                       │
│            --mount type=bind,src=/mnt/cephfs/...,dst=/var/lib/odoo      │
│            odoo:16.0                                                     │
│                                                                          │
│  STEP 3: Wait for Odoo to become healthy (health checks)                 │
│                                                                          │
│  STEP 4: Update instance status to 'running'                             │
│          UPDATE instances SET status = 'running' WHERE id = ...          │
│                                                                          │
│  STEP 5: Task completes, result stored in Redis                          │
└──────────────────────────────────────────────────────────────────────────┘

✅ FAST PATH COMPLETE: Instance is RUNNING (~1-2 minutes total)


════════════════════════════════════════════════════════════════════════════
                            🐢 SLOW PATH
════════════════════════════════════════════════════════════════════════════

┌──────────────────────────────────────────────────────────────────────────┐
│  ALLOCATION SERVICE (when no pool exists)                                │
│  ────────────────────────────────────────────────────────────────────   │
│  No pool found! Return None to trigger provisioning.                     │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Returns None
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DATABASE SERVICE FastAPI Route                                          │
│  File: app/routes/allocation.py:allocate_database()                     │
│  ────────────────────────────────────────────────────────────────────   │
│  result = await allocation_service.allocate_database_for_instance(...)   │
│  if result is None:                                                      │
│      # No pool available - need to provision                             │
│      return AllocationResponse(                                          │
│          status="provisioning",                                          │
│          message="No database pool available. Provisioning new pool...", │
│          retry_after=30  # seconds                                       │
│      )                                                                   │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ HTTP 200 Response (status=provisioning)
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INSTANCE SERVICE Route (receives "provisioning" status)                 │
│  ────────────────────────────────────────────────────────────────────   │
│  elif db_allocation.get("status") == "provisioning":                     │
│      # Database provisioning in progress                                 │
│      await db.update_instance_status(str(instance.id),                   │
│                                      "waiting_for_database")             │
│                                                                          │
│      # Queue polling task to retry allocation                            │
│      wait_for_database_and_provision.delay(                              │
│          instance_id=str(instance.id),                                   │
│          customer_id=str(instance_data.customer_id),                     │
│          db_type=instance_data.db_type                                   │
│      )                                                                   │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Queues polling task to RabbitMQ
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         RABBITMQ                                         │
│  Queue: instance_provisioning                                            │
│  ────────────────────────────────────────────────────────────────────   │
│  Task: wait_for_database_and_provision                                   │
│  Args: {instance_id, customer_id, db_type}                               │
│  Max retries: 30 (30 × 10 seconds = 5 minutes timeout)                   │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Worker picks up task
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INSTANCE WORKER (Celery) - Polling Task                                │
│  Task: wait_for_database_and_provision                                   │
│  File: app/tasks/provisioning.py (needs to be created)                  │
│  Queue: instance_provisioning                                            │
│  ────────────────────────────────────────────────────────────────────   │
│  ATTEMPT 1 (t=0s):                                                       │
│    Call database-service again: POST /api/database/allocate             │
│    Response: status="provisioning" (pool not ready yet)                  │
│    → Retry in 10 seconds                                                 │
│                                                                          │
│  ATTEMPT 2 (t=10s):                                                      │
│    Call database-service again: POST /api/database/allocate             │
│    Response: status="provisioning" (pool still not ready)                │
│    → Retry in 10 seconds                                                 │
│                                                                          │
│  ATTEMPT 3 (t=20s):                                                      │
│    Call database-service again: POST /api/database/allocate             │
│    Response: status="provisioning" (pool still provisioning...)          │
│    → Retry in 10 seconds                                                 │
│                                                                          │
│  ... continues polling every 10 seconds ...                              │
│                                                                          │
│  ATTEMPT 18 (t=180s = 3 minutes):                                        │
│    Call database-service again: POST /api/database/allocate             │
│    Response: status="allocated" + db_config ✅                           │
│                                                                          │
│  SUCCESS! Database now available.                                        │
│  → Update instance with db_config                                        │
│  → Queue provision_instance_task.delay()                                 │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Queues provisioning task
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  INSTANCE WORKER - Provisioning Task                                     │
│  Task: provision_instance_task                                           │
│  ────────────────────────────────────────────────────────────────────   │
│  Same as Fast Path from here:                                            │
│  1. Create CephFS directory                                              │
│  2. Create Docker service                                                │
│  3. Wait for health checks                                               │
│  4. Update status to 'running'                                           │
└──────────────────────────────────────────────────────────────────────────┘

✅ SLOW PATH COMPLETE: Instance is RUNNING (~4-6 minutes total)


════════════════════════════════════════════════════════════════════════════
      ❓ BUT WHO PROVISIONS THE POOL? (background explanation)
════════════════════════════════════════════════════════════════════════════

When the first allocation request comes in and no pool exists, WHO actually
creates the pool? The answer: database-service ADMIN or AUTO-PROVISIONING.

Option A: Manual Admin Provisioning (Current Implementation)
────────────────────────────────────────────────────────────────────────────
Admin calls: POST /api/database/admin/provision-pool {"max_instances": 50}

┌──────────────────────────────────────────────────────────────────────────┐
│  DATABASE SERVICE Admin Route                                            │
│  POST /api/database/admin/provision-pool                                 │
│  ────────────────────────────────────────────────────────────────────   │
│  Queues Celery task: provision_shared_pool.delay(max_instances=50)       │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Queues task to RabbitMQ
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         RABBITMQ                                         │
│  Queue: database_provisioning (quorum queue)                            │
│  ────────────────────────────────────────────────────────────────────   │
│  Task: provision_shared_pool                                             │
│  Args: {max_instances: 50}                                               │
└─────────────────────────┬────────────────────────────────────────────────┘
                          │
                          │ Worker picks up task
                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  DATABASE WORKER (Celery)                                                │
│  Task: provision_shared_pool                                             │
│  File: app/tasks/provisioning.py                                        │
│  Queue: database_provisioning                                            │
│  ────────────────────────────────────────────────────────────────────   │
│  STEP 1: Generate pool name (postgres-pool-N)                            │
│                                                                          │
│  STEP 2: Create Docker Swarm service                                     │
│          docker service create \                                         │
│            --name postgres-pool-1 \                                      │
│            --env POSTGRES_PASSWORD=... \                                 │
│            --mount type=bind,src=/mnt/cephfs/postgres_pools/pool-1      │
│            postgres:15-alpine                                            │
│                                                                          │
│  STEP 3: Wait for PostgreSQL to become healthy (~30 seconds)             │
│          while ! pg_isready -h postgres-pool-1; do sleep 2; done         │
│                                                                          │
│  STEP 4: Insert record into db_servers table                             │
│          INSERT INTO db_servers (                                        │
│              name, host, port, server_type, status,                      │
│              max_instances, current_instances, health_status             │
│          ) VALUES (                                                      │
│              'postgres-pool-1', 'postgres-pool-1', 5432,                 │
│              'shared', 'active', 50, 0, 'healthy'                        │
│          )                                                               │
│                                                                          │
│  STEP 5: Task completes                                                  │
└──────────────────────────────────────────────────────────────────────────┘

Now the polling task (wait_for_database_and_provision) will succeed!


Option B: Auto-Provisioning (Future Enhancement - Not Implemented Yet)
────────────────────────────────────────────────────────────────────────────
Modify allocation.py to automatically queue provisioning when no pool exists:

if result is None:
    # No pool available - auto-provision
    from app.tasks.provisioning import provision_shared_pool
    provision_shared_pool.delay(max_instances=50)

    return AllocationResponse(
        status="provisioning",
        message="Auto-provisioning new pool...",
        retry_after=30
    )


════════════════════════════════════════════════════════════════════════════
                      🔄 SUMMARY: Async & Queues
════════════════════════════════════════════════════════════════════════════

SERVICES:
─────────
1. instance-service (FastAPI)     - HTTP API, handles requests synchronously
2. instance-worker (Celery)       - Background tasks (provisioning, operations)
3. database-service (FastAPI)     - HTTP API, handles allocation synchronously
4. database-worker (Celery)       - Background tasks (pool provisioning, health checks)
5. database-beat (Celery Beat)    - Scheduler for periodic tasks

RABBITMQ QUEUES:
────────────────
1. instance_provisioning   - Odoo container creation, database polling
2. instance_operations     - Start/stop/restart operations
3. instance_maintenance    - Backups, updates
4. instance_monitoring     - Health checks, metrics
5. database_provisioning   - Pool creation, dedicated servers
6. database_monitoring     - Pool health checks
7. database_maintenance    - Cleanup, orphan removal

TASK TYPES:
───────────
1. Synchronous (FastAPI routes)
   - database-service allocation logic (1-2 seconds)
   - instance-service record creation (< 1 second)

2. Asynchronous (Celery tasks)
   - provision_instance_task (2-3 minutes)
   - wait_for_database_and_provision (polls until pool ready)
   - provision_shared_pool (3-5 minutes)
   - health_check_db_pools (periodic, every 5 minutes)

RETRY LOGIC:
────────────
- instance-service tasks: NO automatic retry (task_max_retries=0)
- database-service tasks: 3 retries with exponential backoff
- Polling tasks: Custom retry logic (30 attempts × 10 seconds)

RESULT STORAGE:
───────────────
- Celery results stored in Redis (result_backend)
- Results expire after 24 hours (result_expires=86400)
- Tasks tracked in Redis for monitoring

TIME LIMITS:
────────────
- instance-service: 30 minutes hard, 25 minutes soft
- database-service: 12 minutes hard, 10 minutes soft
- Provisioning tasks: ~3-5 minutes actual duration

ACK BEHAVIOR:
─────────────
- Both services use task_acks_late=True
- Tasks acknowledged AFTER completion (not on pickup)
- Ensures tasks aren't lost if worker crashes mid-execution

PREFETCH:
─────────
- Both services use worker_prefetch_multiplier=1
- Workers process ONE task at a time
- Prevents resource starvation during heavy provisioning


════════════════════════════════════════════════════════════════════════════
                    🎓 KEY CONCEPTS EXPLAINED
════════════════════════════════════════════════════════════════════════════

Q: Why does database-service return "provisioning" instead of provisioning automatically?
A: Separation of concerns! The allocation route is a simple HTTP endpoint that should
   respond quickly. Provisioning takes 3-5 minutes and should be handled by Celery workers.
   Currently, an admin must manually trigger pool provisioning via the admin API.

Q: Why does instance-service poll instead of using webhooks?
A: Simplicity and reliability. Polling with retry logic is easier to implement and debug
   than webhook-based callbacks. The 10-second polling interval is reasonable for a
   3-5 minute provisioning time.

Q: What happens if the polling task times out (5 minutes)?
A: The instance status remains "waiting_for_database" and the task fails with an error.
   An admin can manually retry the task or investigate why the pool isn't provisioning.

Q: Can multiple instances request databases simultaneously?
A: YES! The database allocation logic is designed for concurrency:
   - FastAPI handles multiple HTTP requests concurrently (async)
   - Database transactions ensure atomic instance count updates
   - Celery workers process provisioning tasks in parallel (multiple workers)

Q: What if a pool fills up during allocation?
A: The allocation service selects pools using current_instances < max_instances.
   If a pool fills up between selection and allocation, the database INSERT will
   succeed but the pool's instance count will be incremented. The next allocation
   request will skip the full pool and either find another or return "provisioning".

Q: When should I use dedicated vs shared databases?
A: Based on db_type from plan_entitlements:
   - shared: basic-monthly, standard-monthly (multiple instances per PostgreSQL server)
   - dedicated: premium-monthly (one instance = one dedicated PostgreSQL server)
