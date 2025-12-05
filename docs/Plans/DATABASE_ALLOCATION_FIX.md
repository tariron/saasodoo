# Database Allocation Integration Fix

## Problem Statement

The database-service successfully allocates databases and returns credentials, but the instance-service is not properly saving the allocation details or passing credentials to the provisioning worker. This causes provisioning to fail because the worker doesn't know which postgres pool to use.

## Current State

### What Works ✅
- Database-service allocates database on postgres-pool-1
- Database-service creates PostgreSQL database with user and password
- Database-service returns complete allocation response:
  ```json
  {
    "status": "allocated",
    "db_server_id": "19b64c5d-acdd-4c25-8b82-f7544c8bb81e",
    "db_host": "postgres-pool-1",
    "db_port": 5432,
    "db_name": "odoo_d425c7f257b1439f_fbaa8c92",
    "db_user": "odoo_d425c7f257b1439f_fbaa8c92_user",
    "db_password": "<random-32-char-password>"
  }
  ```

### What's Broken ❌
- Instance-service receives allocation response but doesn't save `db_server_id`, `db_host`, `db_port` to instance table
- Instance-service doesn't pass database credentials to Celery worker
- Provisioning worker tries to connect to hardcoded postgres host (fails with "Name or service not known")
- Provisioning worker tries to create database (but it's already created!)

## Solution Overview

### 1. Add Missing Fields to Instance Table
Add fields to store which postgres pool was allocated:
- `db_server_id` (UUID, references db_servers.id)
- `db_host` (VARCHAR) - redundant but useful for quick access
- `db_port` (INTEGER) - default 5432

**Note:** We do NOT store `db_name`, `db_user`, `db_password` in the instance table. These are passed directly to Celery worker as task parameters.

### 2. Update Instance-Service Route
After successful database allocation, save pool info to instance table and pass credentials to Celery worker.

### 3. Update Provisioning Worker
- Skip database creation (database-service already created it)
- Use credentials passed as task parameters
- Remove hardcoded postgres host/port from environment variables

## Implementation Steps

### Step 1: Update Database Schema

**File:** `shared/configs/postgres/08-add-db-allocation-fields.sql`

```sql
-- Add database allocation fields to instances table
ALTER TABLE instances
  ADD COLUMN IF NOT EXISTS db_server_id UUID REFERENCES db_servers(id),
  ADD COLUMN IF NOT EXISTS db_host VARCHAR(255),
  ADD COLUMN IF NOT EXISTS db_port INTEGER DEFAULT 5432;

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_instances_db_server_id ON instances(db_server_id);

COMMENT ON COLUMN instances.db_server_id IS 'ID of the postgres pool allocated by database-service';
COMMENT ON COLUMN instances.db_host IS 'Hostname of the postgres pool (e.g., postgres-pool-1)';
COMMENT ON COLUMN instances.db_port IS 'Port of the postgres pool (default 5432)';
```

**Note:** This is a new init script. We will wipe postgres data and reinitialize.

### Step 2: Update Instance-Service Route

**File:** `services/instance-service/app/routes/instances.py`

**Location:** After line 132 (inside the `if db_allocation.get("status") == "allocated":` block)

**Add:**
```python
if db_allocation.get("status") == "allocated":
    # Database allocated immediately (shared pool available)
    logger.info("Database allocated immediately",
               instance_id=str(instance.id),
               db_host=db_allocation.get("db_host"),
               db_name=db_allocation.get("db_name"))

    # SAVE ALLOCATION INFO TO INSTANCE TABLE
    await db.execute("""
        UPDATE instances
        SET db_server_id = $1,
            db_host = $2,
            db_port = $3,
            updated_at = NOW()
        WHERE id = $4
    """,
        db_allocation.get("db_server_id"),
        db_allocation.get("db_host"),
        db_allocation.get("db_port"),
        str(instance.id)
    )

    logger.info("Instance updated with database allocation",
               instance_id=str(instance.id),
               db_server_id=db_allocation.get("db_server_id"),
               db_host=db_allocation.get("db_host"))

    # Store credentials to pass to provisioning worker later
    # These will be passed when billing webhook triggers provisioning
    instance.db_credentials = {
        'db_host': db_allocation.get('db_host'),
        'db_port': db_allocation.get('db_port'),
        'db_name': db_allocation.get('db_name'),
        'db_user': db_allocation.get('db_user'),
        'db_password': db_allocation.get('db_password')
    }

    # CRITICAL: NO immediate provisioning here!
    # Provisioning will be triggered by billing webhooks:
    # - For trial instances: SUBSCRIPTION_CREATION webhook
    # - For paid instances: INVOICE_PAYMENT_SUCCESS webhook
```

### Step 3: Update Provision Endpoint to Pass Credentials

**File:** `services/instance-service/app/routes/instances.py`

**Location:** The `/provision` endpoint (around line 1067)

**Current:**
```python
@router.post("/{instance_id}/provision")
async def trigger_provisioning(
    instance_id: str,
    db: Database = Depends(get_database_connection)
):
    # ... validation code ...

    # Queue provisioning task
    task = provision_instance_task.delay(instance_id)
```

**Change to:**
```python
@router.post("/{instance_id}/provision")
async def trigger_provisioning(
    instance_id: str,
    db: Database = Depends(get_database_connection)
):
    # ... validation code ...

    # Check if database was allocated
    instance_record = await db.get_instance(instance_id)
    if not instance_record.db_host:
        raise HTTPException(
            status_code=400,
            detail="Database not allocated. Cannot provision instance."
        )

    # We need to get the database credentials
    # Query database-service to get credentials for this instance
    database_service_url = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8005")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            creds_response = await client.get(
                f"{database_service_url}/api/database/credentials/{instance_id}"
            )
            creds_response.raise_for_status()
            db_credentials = creds_response.json()
    except Exception as e:
        logger.error("Failed to get database credentials",
                    instance_id=instance_id,
                    error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve database credentials"
        )

    # Queue provisioning task with credentials
    task = provision_instance_task.delay(
        instance_id,
        db_credentials=db_credentials
    )
```

**WAIT - THIS IS WRONG.** The database credentials are only available at allocation time. We can't retrieve them later.

**BETTER APPROACH:** Store credentials temporarily in Redis with instance_id as key, retrieve in provision endpoint.

**REVISED Step 3:**

### Step 3: Store Credentials in Redis (Temporary)

**File:** `services/instance-service/app/routes/instances.py`

After saving allocation to instance table:

```python
# Store credentials in Redis temporarily (TTL: 1 hour)
# These will be retrieved when provisioning is triggered
import redis
redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    decode_responses=True
)

credentials_key = f"instance:{instance.id}:db_credentials"
redis_client.setex(
    credentials_key,
    3600,  # 1 hour TTL
    json.dumps({
        'db_host': db_allocation.get('db_host'),
        'db_port': db_allocation.get('db_port'),
        'db_name': db_allocation.get('db_name'),
        'db_user': db_allocation.get('db_user'),
        'db_password': db_allocation.get('db_password')
    })
)

logger.info("Database credentials stored in Redis",
           instance_id=str(instance.id),
           ttl=3600)
```

**In provision endpoint:**

```python
@router.post("/{instance_id}/provision")
async def trigger_provisioning(
    instance_id: str,
    db: Database = Depends(get_database_connection)
):
    # ... validation code ...

    # Retrieve credentials from Redis
    import redis
    import json
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST', 'redis'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        decode_responses=True
    )

    credentials_key = f"instance:{instance_id}:db_credentials"
    credentials_json = redis_client.get(credentials_key)

    if not credentials_json:
        raise HTTPException(
            status_code=400,
            detail="Database credentials not found. Instance may be too old or not allocated."
        )

    db_credentials = json.loads(credentials_json)

    # Queue provisioning task with credentials
    task = provision_instance_task.delay(
        instance_id,
        db_credentials=db_credentials
    )

    # Delete credentials from Redis after queuing (one-time use)
    redis_client.delete(credentials_key)
```

### Step 4: Update Celery Task Signature

**File:** `services/instance-service/app/tasks/provisioning.py`

**Location:** Line ~50 (the `provision_instance_task` function signature)

**Change from:**
```python
@celery_app.task(
    bind=True,
    name="instance.provision_instance",
    queue="instance_provisioning"
)
def provision_instance_task(self, instance_id: str):
```

**Change to:**
```python
@celery_app.task(
    bind=True,
    name="instance.provision_instance",
    queue="instance_provisioning"
)
def provision_instance_task(self, instance_id: str, db_credentials: dict = None):
```

**Pass credentials to workflow:**
```python
# Run provisioning workflow
result = asyncio.run(_provision_instance_workflow(
    instance_id=instance_id,
    db_credentials=db_credentials  # NEW
))
```

### Step 5: Update Provisioning Workflow

**File:** `services/instance-service/app/tasks/provisioning.py`

**Location:** Line ~100 (`_provision_instance_workflow` function signature)

**Change from:**
```python
async def _provision_instance_workflow(instance_id: str) -> Dict[str, Any]:
```

**Change to:**
```python
async def _provision_instance_workflow(
    instance_id: str,
    db_credentials: dict = None
) -> Dict[str, Any]:
```

**Pass to database creation:**
```python
# Create database (line ~143)
db_info = await _create_odoo_database(instance, db_credentials=db_credentials)
```

### Step 6: Update Database Creation Function

**File:** `services/instance-service/app/tasks/provisioning.py`

**Location:** Line ~270 (`_create_odoo_database` function)

**Replace entire function with:**

```python
async def _create_odoo_database(
    instance: Dict[str, Any],
    db_credentials: dict = None
) -> Dict[str, str]:
    """
    Return database credentials for Odoo instance.

    Database is already created by database-service during allocation.
    This function just returns the credentials passed from allocation.

    Args:
        instance: Instance record from database
        db_credentials: Database credentials from allocation (passed via Celery task)

    Returns:
        Dictionary with database connection details
    """
    if not db_credentials:
        raise ValueError(
            f"Database credentials not provided for instance {instance['id']}. "
            "Database must be allocated before provisioning."
        )

    logger.info(
        "Using pre-allocated database",
        instance_id=instance['id'],
        db_host=db_credentials['db_host'],
        db_name=db_credentials['db_name']
    )

    return {
        "db_name": db_credentials['db_name'],
        "db_user": db_credentials['db_user'],
        "db_password": db_credentials['db_password'],
        "db_host": db_credentials['db_host'],
        "db_port": str(db_credentials['db_port'])
    }
```

## Testing Plan

### 1. Wipe and Reinitialize Database
```bash
# Stop postgres service
docker service scale saasodoo_postgres=0

# Delete postgres data
rm -rf /mnt/cephfs/postgres_data/*

# Rebuild postgres image with new schema
docker build -t registry.62.171.153.219.nip.io/compose-postgres:latest -f infrastructure/postgres/Dockerfile .
docker push registry.62.171.153.219.nip.io/compose-postgres:latest

# Redeploy stack
set -a && source infrastructure/compose/.env.swarm && set +a && \
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Wait for postgres to be healthy
sleep 30
docker service ps saasodoo_postgres
```

### 2. Provision New Pool
```bash
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/admin/provision-pool \
  -H "Content-Type: application/json" \
  -d '{"max_instances": 50}'
```

### 3. Test Instance Creation
1. Create new subscription via frontend
2. Verify database allocation happens
3. Check instance table has `db_server_id`, `db_host`, `db_port` populated
4. Verify provisioning completes successfully
5. Check Odoo instance is accessible

### 4. Verify Database
```bash
# Check instance record
docker exec <postgres-container> psql -U database_service -d instance -c \
  "SELECT id, name, status, db_server_id, db_host, db_port FROM instances WHERE id = '<instance-id>';"

# Should show:
# - db_server_id: <pool-uuid>
# - db_host: postgres-pool-1
# - db_port: 5432
```

## Rollback Plan

If something fails:
1. The old postgres2 server is still available
2. Can revert to old provisioning flow by removing database-service allocation call
3. Schema changes are additive (new columns), won't break old code

## Summary

**Files to Modify:**
1. `shared/configs/postgres/08-add-db-allocation-fields.sql` - NEW
2. `services/instance-service/app/routes/instances.py` - Update instance creation route (2 places)
3. `services/instance-service/app/tasks/provisioning.py` - Update task signature and database creation

**Key Changes:**
- Add `db_server_id`, `db_host`, `db_port` columns to instances table
- Save allocation info after successful allocation
- Store credentials in Redis temporarily
- Pass credentials to Celery worker as task parameter
- Skip database creation in provisioning worker (already created)

**No Password Storage:**
Database passwords are never stored in the instance table. They are:
1. Generated by database-service
2. Stored in Redis temporarily (1 hour TTL)
3. Retrieved when provisioning is triggered
4. Passed directly to Celery worker
5. Used to configure Odoo container
6. Deleted from Redis after use
