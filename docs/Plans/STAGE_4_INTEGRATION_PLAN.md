# Stage 4: Instance-Service Integration with Database-Driven Allocation

**Date**: 2025-12-05
**Status**: Ready for Implementation
**Prerequisites**: Stages 1-3 Complete ✅

---

## 📋 Executive Summary

This plan integrates instance-service with database-service to enable **database-driven allocation** where the database type (shared vs dedicated) is determined by the `db_type` field in the `plan_entitlements` table, NOT hardcoded plan names.

**Key Benefits**:
- ✅ Flexible plan configuration (add new plans without code changes)
- ✅ Automatic database allocation based on plan entitlements
- ✅ Seamless plan upgrades with database migration
- ✅ Zero downtime for shared → shared or dedicated → dedicated upgrades
- ✅ Automatic maintenance mode for shared → dedicated migrations

---

## 🎯 Implementation Goals

1. **Add `db_type` to Plan Entitlements**: Extend billing database schema
2. **Wipe and Reinitialize Databases**: Fresh start with new schema
3. **Create Database Service Client**: HTTP client in instance-service
4. **Modify Instance Creation**: Call database-service for allocation
5. **Implement Upgrade Detection**: Detect db_type changes during upgrades
6. **Build Migration System**: Migrate databases (shared → dedicated)
7. **Deploy and Test**: End-to-end validation

---

## 📐 Architecture Overview

```
Frontend (CreateInstance.tsx)
    ↓
    User selects plan (e.g., "basic-monthly")
    ↓
POST /api/billing/subscriptions
    {plan_name: "basic-monthly", customer_id: "..."}
    ↓
┌─────────────────────────────────────────────────────────────────┐
│                      Billing Service                            │
│  1. Create KillBill subscription with plan_name                │
│  2. KillBill fires webhook (SUBSCRIPTION_CREATION)             │
│  3. Webhook handler:                                            │
│     ┌────────────────────────────────────────────────────┐    │
│     │ plan_entitlements Table (in-memory cache)          │    │
│     │ ┌──────────────┬──────────┬──────────┬──────────┐ │    │
│     │ │ plan_name    │ db_type  │ storage  │ cpu/ram  │ │    │
│     │ ├──────────────┼──────────┼──────────┼──────────┤ │    │
│     │ │ basic-mon... │ shared   │ 10GB     │ 2/4GB    │ │    │
│     │ │ standard-... │ shared   │ 25GB     │ 4/8GB    │ │    │
│     │ │ premium-m... │ dedicated│ 100GB    │ 8/16GB   │ │    │
│     │ └──────────────┴──────────┴──────────┴──────────┘ │    │
│     └────────────────────────────────────────────────────┘    │
│  4. Look up plan_name → get db_type + entitlements             │
│  5. Call instance-service with db_type                         │
└────────────────────┬────────────────────────────────────────────┘
                     │ POST /api/instances
                     │ {
                     │   subscription_id: "...",
                     │   plan_name: "basic-monthly",
                     │   db_type: "shared",  ← NEW!
                     │   cpu_limit: 2,
                     │   memory_limit: "4GB",
                     │   storage_limit: "10GB"
                     │ }
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Instance Service                            │
│  1. Create instance record in database                         │
│  2. Call database-service to allocate database                 │
│     → Pass db_type from billing-service                        │
└────────────────────┬────────────────────────────────────────────┘
                     │ POST /api/database/allocate
                     │ {
                     │   instance_id: "...",
                     │   customer_id: "...",
                     │   db_type: "shared"  ← from billing!
                     │ }
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Database Service                             │
│  IF db_type == 'dedicated':                                     │
│    → Provision dedicated PostgreSQL server (4 CPU, 8GB RAM)    │
│    → Return db_config immediately or status='provisioning'     │
│  IF db_type == 'shared':                                        │
│    → Find available shared pool                                │
│    → Allocate database in pool                                 │
│    → Return db_config immediately                              │
└────────────────────┬────────────────────────────────────────────┘
                     │ Returns:
                     │ {
                     │   status: "allocated",
                     │   db_host: "postgres-pool-1",
                     │   db_name: "odoo_customer_abc123",
                     │   db_user: "...",
                     │   db_password: "..."
                     │ }
                     ▼
         ┌──────────────────────────────────────┐
         │  Instance Service                     │
         │  → Update instance with db_config     │
         │  → Queue Celery task to provision     │
         │     Odoo container with credentials   │
         └───────────────────────────────────────┘
```

## Key Points

✅ **Billing service** is the source of truth for plan entitlements (loaded into memory on startup)
✅ **Billing service** looks up `db_type` from `plan_entitlements` table
✅ **Billing service** passes `db_type` + entitlements to instance-service
✅ **Instance service** uses `db_type` to call database-service (no need to call billing-service again)
✅ **Database service** allocates based on `db_type` (shared pool vs dedicated server)

---

## 🗄️ Phase 1: Database Schema Changes

### 1.1 Add `db_type` Column to `plan_entitlements`

**Current Schema** (from `shared/configs/postgres/05-plan-entitlements.sql`):
```sql
CREATE TABLE plan_entitlements (
    id SERIAL PRIMARY KEY,
    plan_name VARCHAR(100) NOT NULL,
    effective_date TIMESTAMP NOT NULL,
    cpu_limit DECIMAL(4,2) NOT NULL,
    memory_limit VARCHAR(10) NOT NULL,
    storage_limit VARCHAR(10) NOT NULL,
    description TEXT,
    created_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(plan_name, effective_date)
);
```

**New Schema File**: `shared/configs/postgres/06-add-db-type-to-plan-entitlements.sql`

```sql
-- Add db_type column to plan_entitlements table
\c billing;

ALTER TABLE plan_entitlements
ADD COLUMN db_type VARCHAR(20) NOT NULL DEFAULT 'shared'
CHECK (db_type IN ('shared', 'dedicated'));

-- Create index for faster queries
CREATE INDEX idx_plan_entitlements_db_type ON plan_entitlements(db_type);

-- Update existing plans with db_type values
UPDATE plan_entitlements
SET db_type = 'shared'
WHERE plan_name IN ('basic-monthly', 'basic-immediate', 'basic-test-trial', 'standard-monthly');

UPDATE plan_entitlements
SET db_type = 'dedicated'
WHERE plan_name IN ('premium-monthly');

-- Verify changes
SELECT plan_name, db_type, cpu_limit, memory_limit, storage_limit
FROM plan_entitlements
ORDER BY plan_name;
```

**Rollback Script**: `shared/configs/postgres/rollback_db_type.sql`

```sql
\c billing;

-- Rollback: Remove db_type column
DROP INDEX IF EXISTS idx_plan_entitlements_db_type;
ALTER TABLE plan_entitlements DROP COLUMN IF EXISTS db_type;
```

### 1.2 Update Billing Service to Include db_type

**No schema changes needed!** The billing service already loads plan_entitlements into memory on startup.

We just need to update the webhook handler to include `db_type` when calling instance-service.

The existing code in `billing-service/app/main.py:28-43` already loads entitlements:
```python
entitlements_rows = await get_all_current_entitlements()
app.state.plan_entitlements = {
    row['plan_name']: {
        'cpu_limit': float(row['cpu_limit']),
        'memory_limit': row['memory_limit'],
        'storage_limit': row['storage_limit'],
        'description': row['description'],
        'effective_date': row['effective_date']
        # Will also include 'db_type' after schema change!
    }
    for row in entitlements_rows
}
```

---

## 🗑️ Phase 2: Database Wipe and Reinitialization

**⚠️ WARNING**: This will DELETE all data. Only proceed if you have no active customers.

### 2.1 Complete Stack Shutdown

```bash
# 1. Scale down all services
docker service scale saasodoo_postgres=0
docker service scale saasodoo_killbill-db=0
docker service scale saasodoo_redis=0

# 2. Wait for graceful shutdown
sleep 10

# 3. Verify services are stopped
docker service ls | grep saasodoo
```

### 2.2 Wipe Database Data

```bash
# Backup existing data (just in case)
sudo mkdir -p /mnt/cephfs/backups/pre-stage4-migration
sudo tar -czf /mnt/cephfs/backups/pre-stage4-migration/postgres_data_backup.tar.gz \
  /mnt/cephfs/postgres_data/

# Wipe PostgreSQL data
sudo rm -rf /mnt/cephfs/postgres_data/*

# Wipe KillBill MariaDB data
sudo rm -rf /mnt/cephfs/killbill_db_data/*

# Wipe Redis data
sudo rm -rf /mnt/cephfs/redis_data/*

# Verify directories are empty
ls -la /mnt/cephfs/postgres_data/
ls -la /mnt/cephfs/killbill_db_data/
```

### 2.3 Update Schema Files

The schema file should already be created at:
`shared/configs/postgres/06-add-db-type-to-plan-entitlements.sql`

This will be automatically executed when postgres initializes from the wiped data directory.

### 2.4 Rebuild and Redeploy Postgres

```bash
# 1. Rebuild postgres image with updated init scripts
docker build -t registry.62.171.153.219.nip.io/compose-postgres:latest \
  -f infrastructure/postgres/Dockerfile .

# 2. Push to registry
docker push registry.62.171.153.219.nip.io/compose-postgres:latest

# 3. Redeploy entire stack (will reinitialize databases)
set -a && source infrastructure/compose/.env.swarm && set +a && \
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# 4. Wait for postgres to initialize (2-3 minutes)
sleep 180

# 5. Check postgres logs for initialization
docker service logs saasodoo_postgres --tail 100
```

### 2.5 Verify Schema Changes

```bash
# Get postgres container ID
PGID=$(docker ps --filter name=saasodoo_postgres --format "{{.ID}}" | head -1)

# Verify db_type column exists
docker exec $PGID psql -U billing_service -d billing -c \
  "SELECT column_name, data_type FROM information_schema.columns
   WHERE table_name = 'plan_entitlements' AND column_name = 'db_type';"

# Check plan entitlements with db_type
docker exec $PGID psql -U billing_service -d billing -c \
  "SELECT plan_id, db_type, storage_gb, ram_gb FROM plan_entitlements ORDER BY plan_id;"

# Expected output:
#     plan_id      | db_type | storage_gb | ram_gb
# -----------------+---------+------------+--------
#  basic-monthly   | shared  |         10 |      2
#  standard-monthly| shared  |         25 |      4
#  premium-monthly | dedicated|        100 |      8
```

---

## 🔌 Phase 3: Billing Service Webhook Updates

### 3.1 Update Billing Service Webhook Handler

**File**: `services/billing-service/app/routes/webhooks.py`

Modify the webhook handler to pass `db_type` to instance-service when creating instances.

Find the section that calls instance-service (around SUBSCRIPTION_CREATION or INVOICE_PAYMENT_SUCCESS handlers) and update it to include db_type from plan_entitlements.

```python
# In webhook handler (example for SUBSCRIPTION_CREATION)
async def handle_subscription_creation(event_data: Dict[str, Any], request: Request):
    """Handle SUBSCRIPTION_CREATION webhook from KillBill"""

    # ... existing code to get subscription details ...

    plan_name = subscription.get("planName")
    customer_id = subscription.get("externalKey")  # customer_id
    subscription_id = subscription.get("subscriptionId")

    # NEW: Get plan entitlements including db_type
    plan_entitlements = request.app.state.plan_entitlements.get(plan_name, {})
    db_type = plan_entitlements.get('db_type', 'shared')  # Default to shared
    cpu_limit = plan_entitlements.get('cpu_limit', 1.0)
    memory_limit = plan_entitlements.get('memory_limit', '2G')
    storage_limit = plan_entitlements.get('storage_limit', '10G')

    logger.info(
        "creating_instance_with_entitlements",
        plan_name=plan_name,
        db_type=db_type,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
    )

    # Call instance-service with db_type
    instance_service_url = os.getenv("INSTANCE_SERVICE_URL", "http://instance-service:8003")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{instance_service_url}/api/instances",
            json={
                "customer_id": customer_id,
                "subscription_id": subscription_id,
                "name": f"Instance for {plan_name}",
                "plan_name": plan_name,
                "db_type": db_type,  # NEW: Pass db_type from plan_entitlements
                "cpu_limit": cpu_limit,
                "memory_limit": memory_limit,
                "storage_limit": storage_limit,
                # ... other fields ...
            }
        )
        response.raise_for_status()
```

### 3.2 Update Billing Service Startup to Load db_type

**File**: `services/billing-service/app/main.py`

Update the entitlements loading to include `db_type`:

```python
# Around line 28-43, update the dictionary comprehension
entitlements_rows = await get_all_current_entitlements()
app.state.plan_entitlements = {
    row['plan_name']: {
        'cpu_limit': float(row['cpu_limit']),
        'memory_limit': row['memory_limit'],
        'storage_limit': row['storage_limit'],
        'description': row['description'],
        'effective_date': row['effective_date'],
        'db_type': row.get('db_type', 'shared')  # NEW: Include db_type
    }
    for row in entitlements_rows
}
logger.info(f"Loaded entitlements for {len(app.state.plan_entitlements)} plans")
```

---

## 🔌 Phase 4: Instance-Service Integration

### 4.1 Update Instance Models to Accept db_type

**File**: `services/instance-service/app/models/instance.py`

Add `db_type` field to `InstanceCreate` model:

```python
class InstanceCreate(BaseModel):
    customer_id: UUID
    subscription_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    odoo_version: str = "16.0"
    instance_type: str = "production"

    # Plan entitlements (passed from billing-service)
    plan_name: Optional[str] = None
    db_type: str = "shared"  # NEW: 'shared' or 'dedicated'
    cpu_limit: float = 1.0
    memory_limit: str = "2G"
    storage_limit: str = "10G"

    # ... other existing fields ...
```

### 4.2 Create Database Service Client

**File**: `services/instance-service/app/utils/database_service_client.py`

```python
"""
HTTP client for database-service API.
Handles database allocation requests with retry logic.
"""
import httpx
import structlog
from typing import Optional, Dict, Any
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = structlog.get_logger(__name__)


class DatabaseServiceClient:
    """Client for communicating with database-service."""

    def __init__(self, base_url: str):
        """
        Initialize database service client.

        Args:
            base_url: Base URL of database-service (e.g., http://database-service:8005)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(30.0, connect=10.0)  # 30s total, 10s connect

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    async def allocate_database(
        self,
        instance_id: str,
        customer_id: str,
        db_type: str,  # 'shared' or 'dedicated'
    ) -> Optional[Dict[str, Any]]:
        """
        Allocate database for an instance based on db_type from plan entitlements.

        Args:
            instance_id: UUID of the instance
            customer_id: UUID of the customer
            db_type: Database type ('shared' or 'dedicated')

        Returns:
            Dict with db_config if allocated immediately:
            {
                "status": "allocated",
                "db_server_id": "uuid",
                "db_host": "postgres-pool-1",
                "db_port": 5432,
                "db_name": "odoo_customer123_abc456",
                "db_user": "odoo_customer123_abc456_user",
                "db_password": "generated_password"
            }

            None if provisioning needed (caller should retry)

        Raises:
            httpx.HTTPStatusError: If API returns 4xx/5xx
            httpx.ConnectError: If cannot connect to database-service
        """
        url = f"{self.base_url}/api/database/allocate"
        payload = {
            "instance_id": instance_id,
            "customer_id": customer_id,
            "db_type": db_type,  # Pass db_type from plan entitlements
        }

        logger.info(
            "requesting_database_allocation",
            instance_id=instance_id,
            customer_id=customer_id,
            db_type=db_type,
            url=url,
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()

                if result.get("status") == "allocated":
                    logger.info(
                        "database_allocated_successfully",
                        instance_id=instance_id,
                        db_host=result.get("db_host"),
                        db_name=result.get("db_name"),
                    )
                    return result

                elif result.get("status") == "provisioning":
                    logger.info(
                        "database_provisioning_in_progress",
                        instance_id=instance_id,
                        message=result.get("message"),
                        retry_after=result.get("retry_after"),
                    )
                    return None  # Caller should poll/retry

                else:
                    logger.error(
                        "unexpected_allocation_response",
                        instance_id=instance_id,
                        response=result,
                    )
                    return None

            except httpx.HTTPStatusError as e:
                logger.error(
                    "database_allocation_http_error",
                    instance_id=instance_id,
                    status_code=e.response.status_code,
                    response_text=e.response.text,
                )
                raise

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.error(
                    "database_service_connection_failed",
                    instance_id=instance_id,
                    error=str(e),
                )
                raise

    async def get_db_server_info(self, db_server_id: str) -> Dict[str, Any]:
        """
        Get information about a database server.

        Args:
            db_server_id: UUID of the database server

        Returns:
            Dict with server information
        """
        url = f"{self.base_url}/api/database/admin/pools/{db_server_id}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """
        Check if database-service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        url = f"{self.base_url}/health"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.error("database_service_health_check_failed", error=str(e))
            return False
```

### 4.3 Update Instance Creation Route to Use Database Service

**File**: `services/instance-service/app/routes/instances.py`

Modify the `create_instance` route to:
1. Extract `db_type` from the request (passed by billing-service)
2. Call database-service to allocate database
3. Store db_type in instance record

```python
@router.post("/", response_model=InstanceResponse, status_code=201)
async def create_instance(
    instance_data: InstanceCreate,
    db: InstanceDatabase = Depends(get_database)
):
    """Create a new Odoo instance with database allocation"""
    try:
        logger.info("Creating instance",
                    name=instance_data.name,
                    customer_id=str(instance_data.customer_id),
                    db_type=instance_data.db_type)  # NEW: Log db_type

        # ... existing validation code ...

        # Create instance in database
        instance = await db.create_instance(
            instance_data,
            billing_status=instance_data.billing_status,
            provisioning_status=instance_data.provisioning_status
        )

        # NEW: Call database-service to allocate database
        database_service_url = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8005")
        async with httpx.AsyncClient(timeout=30.0) as client:
            db_response = await client.post(
                f"{database_service_url}/api/database/allocate",
                json={
                    "instance_id": str(instance.id),
                    "customer_id": str(instance_data.customer_id),
                    "db_type": instance_data.db_type,  # Use db_type from billing-service
                }
            )
            db_response.raise_for_status()
            db_allocation = db_response.json()

        if db_allocation.get("status") == "allocated":
            # Database allocated immediately
            logger.info("Database allocated",
                        instance_id=str(instance.id),
                        db_host=db_allocation["db_host"],
                        db_name=db_allocation["db_name"])

            # Update instance with database config
            await db.update_instance_database_config(
                instance.id,
                db_server_id=db_allocation["db_server_id"],
                db_host=db_allocation["db_host"],
                db_port=db_allocation["db_port"],
                db_name=db_allocation["db_name"],
            )

            # Queue provisioning task
            provision_instance_task.delay(
                instance_id=str(instance.id),
                db_config=db_allocation
            )

        elif db_allocation.get("status") == "provisioning":
            # Database provisioning in progress (dedicated server or new pool)
            logger.info("Database provisioning queued", instance_id=str(instance.id))

            # Update instance status to waiting_for_database
            await db.update_instance_status(str(instance.id), "waiting_for_database")

            # Queue polling task to wait for database
            from app.tasks.provisioning import wait_for_database_and_provision
            wait_for_database_and_provision.delay(
                instance_id=str(instance.id),
                customer_id=str(instance_data.customer_id),
                db_type=instance_data.db_type
            )

            else:
                # Database provisioning needed (no available pool or dedicated server being created)
                logger.info(
                    "database_provisioning_queued",
                    instance_id=instance_id,
                    db_type=db_type,
                )

                # Update status to waiting_for_database
                await self._update_instance_status(instance_id, "waiting_for_database")

                # Queue Celery task to poll for database availability
                from app.tasks.provisioning import wait_for_database_and_provision
                wait_for_database_and_provision.delay(
                    instance_id=instance_id,
                    customer_id=customer_id,
                    db_type=db_type,
                    plan_entitlements=plan_entitlements,
                )

        except (httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.error(
                "database_allocation_failed",
                instance_id=instance_id,
                error=str(e),
            )
            await self._update_instance_status(instance_id, "error")
            raise

        # Return instance record
        return await self._get_instance_by_id(instance_id)

    async def _get_plan_entitlements(self, plan_id: str) -> Dict[str, Any]:
        """
        Get plan entitlements from billing-service.

        NEW: Now includes db_type field.
        """
        billing_service_url = os.getenv("BILLING_SERVICE_URL", "http://billing-service:8004")
        url = f"{billing_service_url}/api/billing/plans/{plan_id}/entitlements"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def _create_instance_record(
        self,
        instance_id: str,
        customer_id: str,
        name: str,
        subscription_id: str,
        plan_id: str,
        version: str,
        db_type: str,  # NEW parameter
    ) -> Dict[str, Any]:
        """Create instance record in database."""
        query = """
            INSERT INTO instances (
                id, customer_id, name, subscription_id, plan_id,
                version, db_type, status, created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'creating', NOW(), NOW())
            RETURNING *
        """
        result = await self.db.fetchrow(
            query,
            instance_id,
            customer_id,
            name,
            subscription_id,
            plan_id,
            version,
            db_type,  # NEW: Store db_type in instances table
            "creating",
        )
        return dict(result)

    async def _update_instance_database_config(
        self, instance_id: str, db_config: Dict[str, Any]
    ) -> None:
        """Update instance record with database configuration."""
        query = """
            UPDATE instances
            SET db_server_id = $2,
                db_host = $3,
                db_port = $4,
                db_name = $5,
                updated_at = NOW()
            WHERE id = $1
        """
        await self.db.execute(
            query,
            instance_id,
            db_config["db_server_id"],
            db_config["db_host"],
            db_config["db_port"],
            db_config["db_name"],
        )

    async def _update_instance_status(self, instance_id: str, status: str) -> None:
        """Update instance status."""
        query = """
            UPDATE instances
            SET status = $2, updated_at = NOW()
            WHERE id = $1
        """
        await self.db.execute(query, instance_id, status)
```

### 3.3 Add Wait and Provision Task

**File**: `services/instance-service/app/tasks/provisioning.py`

Add new task for polling database availability:

```python
@celery_app.task(
    bind=True,
    name="instance.wait_for_database_and_provision",
    queue="instance_provisioning",
    max_retries=30,  # 30 attempts × 10 seconds = 5 minutes
    default_retry_delay=10,  # Wait 10 seconds between retries
)
def wait_for_database_and_provision(
    self,
    instance_id: str,
    customer_id: str,
    db_type: str,
    plan_entitlements: Dict[str, Any],
):
    """
    Poll database-service until database is allocated, then provision Odoo container.

    This task is queued when database allocation returns status='provisioning'.
    It polls every 10 seconds for up to 5 minutes.
    """
    logger.info(
        "waiting_for_database_allocation",
        instance_id=instance_id,
        db_type=db_type,
        attempt=self.request.retries + 1,
    )

    # Initialize database service client
    database_service_url = os.getenv("DATABASE_SERVICE_URL", "http://database-service:8005")
    db_service_client = DatabaseServiceClient(database_service_url)

    # Try to allocate database
    loop = asyncio.get_event_loop()
    db_config = loop.run_until_complete(
        db_service_client.allocate_database(
            instance_id=instance_id,
            customer_id=customer_id,
            db_type=db_type,
        )
    )

    if db_config:
        # Database is now allocated!
        logger.info(
            "database_now_available",
            instance_id=instance_id,
            db_host=db_config["db_host"],
            db_name=db_config["db_name"],
        )

        # Update instance record with database config
        db_manager = DatabaseManager()
        conn = loop.run_until_complete(db_manager.get_connection())

        update_query = """
            UPDATE instances
            SET db_server_id = $2,
                db_host = $3,
                db_port = $4,
                db_name = $5,
                status = 'provisioning',
                updated_at = NOW()
            WHERE id = $1
        """
        loop.run_until_complete(
            conn.execute(
                update_query,
                instance_id,
                db_config["db_server_id"],
                db_config["db_host"],
                db_config["db_port"],
                db_config["db_name"],
            )
        )
        loop.run_until_complete(conn.close())

        # Queue Odoo container provisioning
        provision_odoo_container.delay(
            instance_id=instance_id,
            db_config=db_config,
            plan_entitlements=plan_entitlements,
        )

        return {
            "status": "success",
            "message": "Database allocated, Odoo provisioning queued",
            "db_config": db_config,
        }

    else:
        # Still provisioning, retry
        logger.info(
            "database_still_provisioning",
            instance_id=instance_id,
            attempt=self.request.retries + 1,
            max_retries=self.max_retries,
        )

        if self.request.retries >= self.max_retries:
            # Timeout after 5 minutes
            logger.error(
                "database_allocation_timeout",
                instance_id=instance_id,
                timeout_minutes=5,
            )

            # Update instance to error status
            db_manager = DatabaseManager()
            conn = loop.run_until_complete(db_manager.get_connection())
            error_query = """
                UPDATE instances
                SET status = 'error',
                    error_message = 'Database allocation timeout after 5 minutes',
                    updated_at = NOW()
                WHERE id = $1
            """
            loop.run_until_complete(conn.execute(error_query, instance_id))
            loop.run_until_complete(conn.close())

            raise Exception("Database allocation timeout")

        # Retry after 10 seconds
        raise self.retry(countdown=10)
```

### 3.4 Add db_type to instances Table

**File**: `shared/configs/postgres/08-add-db-type-to-instances.sql`

```sql
-- Add db_type column to instances table
ALTER TABLE instances
ADD COLUMN db_type VARCHAR(20) DEFAULT 'shared'
CHECK (db_type IN ('shared', 'dedicated'));

-- Create index for queries
CREATE INDEX idx_instances_db_type ON instances(db_type);

-- Verify
SELECT id, name, db_type, status FROM instances LIMIT 5;
```

### 3.5 Update Environment Variables

**File**: `infrastructure/compose/.env.swarm`

Add these lines:

```bash
# Database Service Configuration
DATABASE_SERVICE_URL=http://database-service:8005
```

---

## 🔄 Phase 4: Plan Upgrade with Database Migration

### 4.1 Detect Plan Upgrades in Billing Service

**File**: `services/billing-service/app/services/subscription_service.py`

Modify the subscription change handler:

```python
async def handle_subscription_change(
    self,
    subscription_id: str,
    old_plan_id: str,
    new_plan_id: str,
    customer_id: str,
) -> Dict[str, Any]:
    """
    Handle subscription plan changes.

    NEW: Detects db_type changes and triggers database migration.
    """
    logger.info(
        "handling_subscription_change",
        subscription_id=subscription_id,
        old_plan_id=old_plan_id,
        new_plan_id=new_plan_id,
    )

    # Get plan entitlements for both plans
    old_entitlements = await self._get_plan_entitlements(old_plan_id)
    new_entitlements = await self._get_plan_entitlements(new_plan_id)

    old_db_type = old_entitlements.get("db_type", "shared")
    new_db_type = new_entitlements.get("db_type", "shared")

    # Check if database type changed
    db_migration_required = old_db_type != new_db_type

    if db_migration_required:
        logger.info(
            "database_migration_required",
            subscription_id=subscription_id,
            old_db_type=old_db_type,
            new_db_type=new_db_type,
        )

        # Call instance-service to trigger migration
        instance_service_url = os.getenv("INSTANCE_SERVICE_URL", "http://instance-service:8003")
        url = f"{instance_service_url}/api/instances/subscription/{subscription_id}/upgrade-plan"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json={
                    "old_plan_id": old_plan_id,
                    "new_plan_id": new_plan_id,
                    "old_db_type": old_db_type,
                    "new_db_type": new_db_type,
                    "requires_migration": True,
                },
            )
            response.raise_for_status()
            migration_result = response.json()

        logger.info(
            "database_migration_triggered",
            subscription_id=subscription_id,
            migration_status=migration_result.get("status"),
        )

        return {
            "status": "migration_queued",
            "message": "Plan upgrade initiated, database migration in progress",
            "estimated_downtime_minutes": 5,
        }

    else:
        # No database migration needed, just update billing records
        logger.info(
            "no_database_migration_needed",
            subscription_id=subscription_id,
            db_type=new_db_type,
        )

        return {
            "status": "completed",
            "message": "Plan upgraded successfully, no database migration required",
        }
```

### 4.2 Create Upgrade API Endpoint in Instance Service

**File**: `services/instance-service/app/routes/instances.py`

Add new endpoint:

```python
@router.post("/subscription/{subscription_id}/upgrade-plan")
async def upgrade_plan_with_migration(
    subscription_id: str,
    upgrade_request: Dict[str, Any],
    db=Depends(get_db),
):
    """
    Handle plan upgrade with database migration if db_type changed.

    Called by billing-service when subscription plan changes.
    """
    logger.info(
        "plan_upgrade_requested",
        subscription_id=subscription_id,
        upgrade_request=upgrade_request,
    )

    old_db_type = upgrade_request.get("old_db_type")
    new_db_type = upgrade_request.get("new_db_type")
    requires_migration = upgrade_request.get("requires_migration", False)

    # Get instance by subscription_id
    query = "SELECT * FROM instances WHERE subscription_id = $1"
    instance = await db.fetchrow(query, subscription_id)

    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"Instance not found for subscription: {subscription_id}",
        )

    instance_id = instance["id"]

    # Check if instance is in a state that allows migration
    if instance["status"] not in ["running", "stopped"]:
        raise HTTPException(
            status_code=409,
            detail=f"Instance cannot be migrated in status: {instance['status']}",
        )

    if requires_migration:
        # Queue database migration task
        from app.tasks.migration import migrate_database_for_plan_upgrade

        migrate_database_for_plan_upgrade.delay(
            instance_id=instance_id,
            subscription_id=subscription_id,
            old_db_type=old_db_type,
            new_db_type=new_db_type,
        )

        # Update instance status
        update_query = """
            UPDATE instances
            SET status = 'migrating', updated_at = NOW()
            WHERE id = $1
        """
        await db.execute(update_query, instance_id)

        return {
            "status": "migration_queued",
            "instance_id": instance_id,
            "message": "Database migration queued, estimated time 5-15 minutes",
        }
    else:
        # No migration needed, just update plan_id
        update_query = """
            UPDATE instances
            SET plan_id = $2, updated_at = NOW()
            WHERE id = $1
        """
        await db.execute(update_query, instance_id, upgrade_request["new_plan_id"])

        return {
            "status": "completed",
            "instance_id": instance_id,
            "message": "Plan upgraded successfully",
        }
```

### 4.3 Create Database Migration Task

**File**: `services/instance-service/app/tasks/migration.py`

```python
"""
Database migration tasks for plan upgrades.
Handles shared → dedicated and dedicated → shared migrations.
"""
import os
import subprocess
import asyncio
from celery import Task
from app.celery_config import celery_app
from app.utils.docker_client import DockerClientWrapper
from app.utils.database_service_client import DatabaseServiceClient
from shared.utils.database import DatabaseManager
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    name="instance.migrate_database_for_plan_upgrade",
    queue="instance_maintenance",
    max_retries=0,  # No automatic retries (admin must retry manually)
)
def migrate_database_for_plan_upgrade(
    self,
    instance_id: str,
    subscription_id: str,
    old_db_type: str,
    new_db_type: str,
):
    """
    Migrate instance database when plan db_type changes.

    Process:
    1. Stop Odoo container (maintenance mode)
    2. Provision new database (shared pool or dedicated server)
    3. Dump old database
    4. Restore to new database
    5. Verify data integrity
    6. Update Odoo container environment variables
    7. Restart Odoo container
    8. Cleanup old database

    Downtime: 5-15 minutes depending on database size.
    """
    logger.info(
        "starting_database_migration",
        instance_id=instance_id,
        old_db_type=old_db_type,
        new_db_type=new_db_type,
    )

    docker_client = DockerClientWrapper()
    db_service_client = DatabaseServiceClient(
        os.getenv("DATABASE_SERVICE_URL", "http://database-service:8005")
    )

    loop = asyncio.get_event_loop()
    db_manager = DatabaseManager()
    conn = loop.run_until_complete(db_manager.get_connection())

    try:
        # PHASE 1: Preparation
        logger.info("migration_phase_1_preparation", instance_id=instance_id)

        # Get instance details
        instance_query = "SELECT * FROM instances WHERE id = $1"
        instance = loop.run_until_complete(conn.fetchrow(instance_query, instance_id))

        if not instance:
            raise ValueError(f"Instance not found: {instance_id}")

        old_db_host = instance["db_host"]
        old_db_name = instance["db_name"]
        old_db_server_id = instance["db_server_id"]
        customer_id = instance["customer_id"]

        logger.info(
            "current_database_info",
            instance_id=instance_id,
            old_db_host=old_db_host,
            old_db_name=old_db_name,
        )

        # PHASE 2: Stop Odoo Container (DOWNTIME STARTS)
        logger.info("migration_phase_2_stopping_odoo", instance_id=instance_id)

        service_name = f"odoo_{instance_id[:8]}"
        docker_client.stop_service(service_name)

        # Update status to migrating
        update_query = "UPDATE instances SET status = 'migrating', updated_at = NOW() WHERE id = $1"
        loop.run_until_complete(conn.execute(update_query, instance_id))

        # PHASE 3: Provision New Database
        logger.info("migration_phase_3_provisioning_new_database", instance_id=instance_id)

        db_config = loop.run_until_complete(
            db_service_client.allocate_database(
                instance_id=instance_id,
                customer_id=customer_id,
                db_type=new_db_type,
            )
        )

        if not db_config:
            raise Exception("Failed to allocate new database")

        new_db_host = db_config["db_host"]
        new_db_name = db_config["db_name"]
        new_db_user = db_config["db_user"]
        new_db_password = db_config["db_password"]

        logger.info(
            "new_database_provisioned",
            instance_id=instance_id,
            new_db_host=new_db_host,
            new_db_name=new_db_name,
        )

        # PHASE 4: Dump Old Database
        logger.info("migration_phase_4_dumping_old_database", instance_id=instance_id)

        dump_file = f"/tmp/migration_{instance_id}.dump"
        dump_command = [
            "pg_dump",
            "-h", old_db_host,
            "-U", "postgres",  # Admin user
            "-d", old_db_name,
            "-Fc",  # Custom format (compressed)
            "-f", dump_file,
            "--no-owner",
            "--no-acl",
        ]

        result = subprocess.run(
            dump_command,
            env={"PGPASSWORD": os.getenv("POSTGRES_ADMIN_PASSWORD", "postgres")},
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise Exception(f"pg_dump failed: {result.stderr}")

        # Check dump file size
        dump_size = os.path.getsize(dump_file)
        logger.info(
            "database_dump_completed",
            instance_id=instance_id,
            dump_size_mb=dump_size / 1024 / 1024,
        )

        # PHASE 5: Restore to New Database
        logger.info("migration_phase_5_restoring_new_database", instance_id=instance_id)

        restore_command = [
            "pg_restore",
            "-h", new_db_host,
            "-U", new_db_user,
            "-d", new_db_name,
            "--no-owner",
            "--clean",
            "--if-exists",
            dump_file,
        ]

        result = subprocess.run(
            restore_command,
            env={"PGPASSWORD": new_db_password},
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            raise Exception(f"pg_restore failed: {result.stderr}")

        logger.info("database_restore_completed", instance_id=instance_id)

        # PHASE 6: Verify Data Integrity
        logger.info("migration_phase_6_verifying_data", instance_id=instance_id)

        # TODO: Add table count verification
        # Compare critical tables: res_partner, res_users, sale_order

        # PHASE 7: Update Instance Record
        logger.info("migration_phase_7_updating_instance", instance_id=instance_id)

        update_query = """
            UPDATE instances
            SET db_server_id = $2,
                db_host = $3,
                db_name = $4,
                db_type = $5,
                updated_at = NOW()
            WHERE id = $1
        """
        loop.run_until_complete(
            conn.execute(
                update_query,
                instance_id,
                db_config["db_server_id"],
                new_db_host,
                new_db_name,
                new_db_type,
            )
        )

        # PHASE 8: Update Odoo Container Environment
        logger.info("migration_phase_8_updating_odoo_config", instance_id=instance_id)

        docker_client.update_service_env(
            service_name,
            {
                "DB_HOST": new_db_host,
                "DB_NAME": new_db_name,
                "DB_USER": new_db_user,
                "DB_PASSWORD": new_db_password,
            },
        )

        # PHASE 9: Restart Odoo Container (DOWNTIME ENDS)
        logger.info("migration_phase_9_restarting_odoo", instance_id=instance_id)

        docker_client.start_service(service_name)

        # Update status to running
        update_query = "UPDATE instances SET status = 'running', updated_at = NOW() WHERE id = $1"
        loop.run_until_complete(conn.execute(update_query, instance_id))

        # PHASE 10: Cleanup
        logger.info("migration_phase_10_cleanup", instance_id=instance_id)

        # Remove dump file
        if os.path.exists(dump_file):
            os.remove(dump_file)

        # Update old db_server instance count
        decrement_query = """
            UPDATE db_servers
            SET current_instances = current_instances - 1,
                status = CASE
                    WHEN current_instances - 1 < max_instances THEN 'active'
                    ELSE status
                END
            WHERE id = $1
        """
        loop.run_until_complete(conn.execute(decrement_query, old_db_server_id))

        # Drop old database (async via database-service)
        # TODO: Implement cleanup endpoint in database-service

        logger.info(
            "database_migration_completed",
            instance_id=instance_id,
            new_db_host=new_db_host,
            new_db_type=new_db_type,
        )

        return {
            "status": "success",
            "instance_id": instance_id,
            "old_db_type": old_db_type,
            "new_db_type": new_db_type,
            "new_db_host": new_db_host,
        }

    except Exception as e:
        logger.error(
            "database_migration_failed",
            instance_id=instance_id,
            error=str(e),
        )

        # Rollback: Keep Odoo on old database
        try:
            docker_client.start_service(service_name)
            update_query = """
                UPDATE instances
                SET status = 'error',
                    error_message = $2,
                    updated_at = NOW()
                WHERE id = $1
            """
            loop.run_until_complete(
                conn.execute(update_query, instance_id, f"Migration failed: {str(e)}")
            )
        except Exception as rollback_error:
            logger.error(
                "rollback_failed",
                instance_id=instance_id,
                error=str(rollback_error),
            )

        raise

    finally:
        loop.run_until_complete(conn.close())
```

---

## 🚀 Phase 5: Deployment

### 5.1 Build and Push Updated Services

```bash
# Build instance-service with new database client
docker build -t registry.62.171.153.219.nip.io/compose-instance-service:latest \
  -f services/instance-service/Dockerfile .

# Tag instance-worker (same image)
docker tag registry.62.171.153.219.nip.io/compose-instance-service:latest \
  registry.62.171.153.219.nip.io/compose-instance-worker:latest

# Build billing-service with upgrade detection
docker build -t registry.62.171.153.219.nip.io/compose-billing-service:latest \
  -f services/billing-service/Dockerfile .

# Push to registry
docker push registry.62.171.153.219.nip.io/compose-instance-service:latest
docker push registry.62.171.153.219.nip.io/compose-instance-worker:latest
docker push registry.62.171.153.219.nip.io/compose-billing-service:latest
```

### 5.2 Redeploy Services

```bash
# Source environment and redeploy
set -a && source infrastructure/compose/.env.swarm && set +a && \
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Verify services updated
docker service ls | grep -E 'instance-service|billing-service|database'

# Check logs for errors
docker service logs saasodoo_instance-service --tail 50
docker service logs saasodoo_billing-service --tail 50
```

### 5.3 Provision First Shared Pool

```bash
# Trigger pool provisioning via API
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/admin/provision-pool \
  -H "Content-Type: application/json" \
  -d '{"max_instances": 50}'

# Monitor provisioning
docker service logs saasodoo_database-worker --tail 100 --follow

# Verify pool is active (wait 3-5 minutes)
curl http://api.62.171.153.219.nip.io/database/api/database/admin/pools
```

---

## 🧪 Phase 6: Testing

### 6.1 Test Database Allocation (Shared)

```bash
# Create test instance with basic plan (shared database)
curl -X POST http://api.62.171.153.219.nip.io/instance/api/instances \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test-customer-001",
    "name": "Test Instance Shared",
    "subscription_id": "test-sub-001",
    "plan_id": "basic-monthly",
    "version": "16.0"
  }'

# Monitor instance creation
docker service logs saasodoo_instance-worker --tail 100 --follow

# Verify instance allocated to shared pool
PGID=$(docker ps --filter name=saasodoo_postgres --format "{{.ID}}" | head -1)
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT id, name, db_host, db_type, status FROM instances WHERE name = 'Test Instance Shared';"
```

### 6.2 Test Database Allocation (Dedicated)

```bash
# Create test instance with premium plan (dedicated database)
curl -X POST http://api.62.171.153.219.nip.io/instance/api/instances \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test-customer-002",
    "name": "Test Instance Dedicated",
    "subscription_id": "test-sub-002",
    "plan_id": "premium-monthly",
    "version": "16.0"
  }'

# Monitor dedicated server provisioning (takes 3-5 minutes)
docker service logs saasodoo_database-worker --tail 100 --follow

# Verify dedicated server created
curl http://api.62.171.153.219.nip.io/database/api/database/admin/pools | python3 -m json.tool

# Check instance status
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT id, name, db_host, db_type, status FROM instances WHERE name = 'Test Instance Dedicated';"
```

### 6.3 Test Plan Upgrade with Migration

```bash
# 1. Create instance with standard plan (shared)
# 2. Upgrade to premium plan (dedicated) via KillBill API
# 3. Monitor migration task
docker service logs saasodoo_instance-worker --tail 200 --follow | grep migration

# 4. Verify instance migrated to dedicated server
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT id, name, db_host, db_type, status FROM instances WHERE subscription_id = 'SUB_ID';"

# 5. Verify old database removed from shared pool
curl http://api.62.171.153.219.nip.io/database/api/database/admin/stats
```

---

## 📊 Phase 7: Monitoring and Validation

### 7.1 Health Checks

```bash
# Check all services healthy
docker service ls

# Check API health
curl http://api.62.171.153.219.nip.io/instance/health
curl http://api.62.171.153.219.nip.io/database/health
curl http://api.62.171.153.219.nip.io/billing/health

# Check database pools
curl http://api.62.171.153.219.nip.io/database/api/database/admin/stats
```

### 7.2 Database Queries

```bash
PGID=$(docker ps --filter name=saasodoo_postgres --format "{{.ID}}" | head -1)

# Check db_servers table
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT name, server_type, status, health_status, current_instances, max_instances
   FROM db_servers ORDER BY created_at;"

# Check instances table
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT id, name, db_host, db_type, status
   FROM instances ORDER BY created_at DESC LIMIT 10;"

# Check plan entitlements
docker exec $PGID psql -U billing_service -d billing -c \
  "SELECT plan_id, db_type, storage_gb, ram_gb FROM plan_entitlements ORDER BY plan_id;"
```

### 7.3 Celery Task Monitoring

```bash
# Check Celery worker logs
docker service logs saasodoo_instance-worker --tail 100

# Check Celery beat (task scheduler)
docker service logs saasodoo_database-beat --tail 50

# Check health check task runs (every 5 minutes)
docker service logs saasodoo_database-worker | grep health_check_db_pools
```

---

## 🔄 Rollback Procedures

### Rollback Level 1: Revert to Hardcoded postgres2

If database-service integration fails:

```bash
# 1. Scale down database-service
docker service scale saasodoo_database-service=0
docker service scale saasodoo_database-worker=0

# 2. Update instance-service code to use hardcoded postgres2
# Revert changes to instance_service.py

# 3. Rebuild and redeploy instance-service
docker build -t registry.62.171.153.219.nip.io/compose-instance-service:latest \
  -f services/instance-service/Dockerfile .
docker push registry.62.171.153.219.nip.io/compose-instance-service:latest
docker service update --force saasodoo_instance-service

# 4. All new instances will use postgres2
```

### Rollback Level 2: Remove db_type Column

```bash
# Run rollback SQL script
PGID=$(docker ps --filter name=saasodoo_postgres --format "{{.ID}}" | head -1)

docker exec $PGID psql -U billing_service -d billing \
  -f /tmp/rollback_db_type.sql
```

---

## 📚 Summary

This plan provides a complete implementation for Stage 4 integration with the following highlights:

✅ **Database-Driven Allocation**: `db_type` in plan entitlements drives allocation logic
✅ **Flexible Configuration**: Add new plans without code changes
✅ **Seamless Upgrades**: Automatic migration for db_type changes
✅ **Zero-Downtime**: For upgrades within same db_type
✅ **Minimal Downtime**: 5-15 minutes for shared → dedicated migrations
✅ **DevOps Best Practices**: Proper deployment, monitoring, rollback procedures

**Estimated Implementation Time**: 2-3 days
- Day 1: Schema changes, database wipe, client implementation
- Day 2: Migration task, testing, debugging
- Day 3: Production deployment, validation, documentation

**Next Steps After Stage 4**:
- Stage 5: Backup and restore system
- Stage 6: Monitoring dashboards
- Stage 7: Automated scaling policies
