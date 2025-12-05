# Stage 4 Implementation Progress

**Date**: 2025-12-05
**Status**: IN PROGRESS

---

## ✅ Completed Tasks

### 1. Database Schema Changes
- ✅ Created `shared/configs/postgres/06-add-db-type-to-plan-entitlements.sql`
- ✅ Created rollback script `shared/configs/postgres/rollback_db_type.sql`
- ✅ Added `db_type` column to `plan_entitlements` table with CHECK constraint
- ✅ Created index on `db_type` for performance
- ✅ Set default values: basic/standard = 'shared', premium = 'dedicated'

### 2. Billing Service Updates
- ✅ Updated `services/billing-service/app/main.py` to load `db_type` from plan_entitlements
- ✅ Created helper functions in `services/billing-service/app/routes/webhooks.py`:
  - `_set_app_state()` - Sets module-level app state reference
  - `_get_plan_entitlements_db_type()` - Retrieves db_type for a plan
- ✅ Updated webhook handler to set app state on webhook receipt
- ✅ Modified `_create_instance_for_subscription()` to get db_type from plan_entitlements
- ✅ Updated `services/billing-service/app/utils/instance_client.py` to pass db_type to instance-service

### 3. Instance Service Model Updates
- ✅ Added `db_type` field to `InstanceCreate` model in `services/instance-service/app/models/instance.py`

### 4. Instance Service Route Updates ✅
**File**: `services/instance-service/app/routes/instances.py`

**COMPLETED** - Modified `create_instance` route to:
1. ✅ Extract `db_type` from request (passed by billing-service)
2. ✅ Call database-service `/api/database/allocate` endpoint
3. ✅ Handle two response types:
   - `status="allocated"` → Database ready immediately (wait for billing webhook)
   - `status="provisioning"` → Pool being created, set status to waiting
4. ✅ Error handling for HTTP errors and connection failures

**Implementation notes:**
- Database allocation is called during instance creation
- Provisioning is still triggered by billing webhooks (SUBSCRIPTION_CREATION or INVOICE_PAYMENT_SUCCESS)
- If database is not immediately available, instance waits for webhook trigger

### 5. Create Polling Task ✅
**File**: `services/instance-service/app/tasks/provisioning.py`

**COMPLETED** - Created `wait_for_database_and_provision` task:
- ✅ Celery task with 30 retries (5 minutes timeout)
- ✅ Polls database-service every 10 seconds
- ✅ Logs detailed status for monitoring
- ✅ Updates instance to error status on timeout
- ✅ Does NOT trigger provisioning (waits for billing webhook)

---

## 🚧 Remaining Tasks

### 6. Database Service Updates (MEDIUM PRIORITY)
**File**: `services/database-service/app/routes/allocation.py`

Currently uses `plan_tier` parameter. Need to verify it works with the db_type flow:
- `require_dedicated=True` → Provision dedicated server
- `require_dedicated=False` → Use shared pool

**Current behavior:**
- Shared pools: Allocates immediately if pool exists
- Dedicated: Returns "provisioning" (admin must manually provision)

**May need to add auto-provisioning logic for dedicated servers**

### 7. Wipe and Reinitialize Databases (BEFORE DEPLOYMENT)
**Commands to run:**
```bash
# 1. Scale down postgres
docker service scale saasodoo_postgres=0

# 2. Wipe data
sudo rm -rf /mnt/cephfs/postgres_data/*
sudo rm -rf /mnt/cephfs/killbill_db_data/*
sudo rm -rf /mnt/cephfs/redis_data/*

# 3. Rebuild postgres image with new schema
docker build -t registry.62.171.153.219.nip.io/compose-postgres:latest \
  -f infrastructure/postgres/Dockerfile .
docker push registry.62.171.153.219.nip.io/compose-postgres:latest

# 4. Redeploy stack
set -a && source infrastructure/compose/.env.swarm && set +a && \
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

### 8. Build and Deploy Services
```bash
# Build instance-service
docker build -t registry.62.171.153.219.nip.io/compose-instance-service:latest \
  -f services/instance-service/Dockerfile .
docker tag registry.62.171.153.219.nip.io/compose-instance-service:latest \
  registry.62.171.153.219.nip.io/compose-instance-worker:latest

# Build billing-service
docker build -t registry.62.171.153.219.nip.io/compose-billing-service:latest \
  -f services/billing-service/Dockerfile .

# Push images
docker push registry.62.171.153.219.nip.io/compose-instance-service:latest
docker push registry.62.171.153.219.nip.io/compose-instance-worker:latest
docker push registry.62.171.153.219.nip.io/compose-billing-service:latest

# Redeploy stack
set -a && source infrastructure/compose/.env.swarm && set +a && \
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

### 9. Provision Initial Shared Pool
```bash
# After deployment, provision first pool
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/admin/provision-pool \
  -H "Content-Type: application/json" \
  -d '{"max_instances": 50}'

# Monitor provisioning
docker service logs saasodoo_database-worker --tail 100 --follow

# Verify pool created (wait ~3-5 minutes)
curl http://api.62.171.153.219.nip.io/database/api/database/admin/pools
```

### 10. Testing
```bash
# Test 1: Create instance with shared database (basic plan)
# - Should allocate from shared pool immediately
# - Instance should provision in 1-2 minutes

# Test 2: Verify db_type stored correctly
PGID=$(docker ps --filter name=saasodoo_postgres --format "{{.ID}}" | head -1)
docker exec $PGID psql -U billing_service -d billing -c \
  "SELECT plan_name, db_type FROM plan_entitlements ORDER BY plan_name;"

# Test 3: Check instance allocation
docker exec $PGID psql -U database_service -d instance -c \
  "SELECT id, name, db_type, db_host, status FROM instances LIMIT 5;"
```

---

## 📝 Next Steps (Priority Order)

1. ✅ ~~Update instance-service create route to call database-service~~
2. ✅ ~~Create polling task for slow path (when pool doesn't exist)~~
3. **Build and deploy services** (billing-service, instance-service, instance-worker)
4. **Wipe and reinitialize databases** with new schema (⚠️ destroys all data)
5. **Provision initial shared pool** via database-service API
6. **End-to-end testing** with instance creation

---

## ⚠️ Important Notes

- **No customers yet** → Safe to wipe databases
- **Schema changes are additive** → Can be applied without breaking existing code
- **Default db_type** → Everything defaults to 'shared' for safety
- **Polling task timeout** → 5 minutes max (30 retries × 10 seconds)
- **Manual pool provisioning** → Admin must provision first pool before instances can be created

---

## 🔧 Environment Variables Needed

Add to `.env.swarm`:
```bash
DATABASE_SERVICE_URL=http://database-service:8005
```

Already exists, no changes needed.

---

## 🎯 Success Criteria

- ✅ Billing service loads db_type from plan_entitlements
- ✅ Instance-service receives db_type from billing-service
- ✅ Instance-service calls database-service with db_type
- ✅ Polling task created for slow path (when pool doesn't exist)
- ⏳ Test: Shared pool allocations work (fast path)
- ⏳ Test: End-to-end instance creation succeeds
- ⏳ Deploy and validate in production
