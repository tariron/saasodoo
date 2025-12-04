# Testing Plan - Database Service Stages 1-3

**Date**: 2025-12-04
**Target**: `http://api.62.171.153.219.nip.io/database`
**Status**: Ready for Testing

---

## Prerequisites

Before running tests, ensure:

```bash
# 1. Verify database schema is applied
docker exec saasodoo-postgres psql -U instance_service -d instance \
  -c "SELECT COUNT(*) FROM db_servers;"

# 2. Verify services are running
docker service ls | grep database

# Expected output:
# saasodoo_database-service  (replicated, 1/1)
# saasodoo_database-worker   (replicated, 1/1)

# 3. Check service logs for startup errors
docker service logs saasodoo_database-service --tail 50
docker service logs saasodoo_database-worker --tail 50
```

---

## Test Suite

### Test 1: Health Check ✅

**Purpose**: Verify service is running and accessible

```bash
curl -X GET http://api.62.171.153.219.nip.io/database/health
```

**Expected Response**:
```json
{
  "status": "healthy",
  "service": "database-service",
  "timestamp": "2025-12-04T..."
}
```

**Status Codes**:
- ✅ `200 OK` - Service healthy
- ❌ `503 Service Unavailable` - Service down
- ❌ `504 Gateway Timeout` - Traefik can't reach service

---

### Test 2: Get Pool Statistics (Empty State) ✅

**Purpose**: Verify admin endpoints work with no pools

```bash
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/stats
```

**Expected Response**:
```json
{
  "total_pools": 0,
  "active_pools": 0,
  "total_capacity": 0,
  "total_used": 0,
  "overall_utilization": 0.0,
  "by_status": {},
  "by_type": {}
}
```

**Status**: `200 OK`

---

### Test 3: List Pools (Empty State) ✅

**Purpose**: Verify pool listing endpoint

```bash
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/pools
```

**Expected Response**:
```json
{
  "pools": [],
  "total_count": 0
}
```

**Status**: `200 OK`

---

### Test 4: Trigger First Pool Provisioning 🔧

**Purpose**: Test async pool provisioning (Celery task)

```bash
# Method 1: Via Python inside worker container
docker exec $(docker ps -q -f name=saasodoo_database-worker) python3 -c "
from app.tasks.provisioning import provision_database_pool
result = provision_database_pool.delay(max_instances=50)
print(f'Task ID: {result.id}')
"

# Method 2: Alternative - exec into worker and use Python shell
docker exec -it $(docker ps -q -f name=saasodoo_database-worker) python3
>>> from app.tasks.provisioning import provision_database_pool
>>> result = provision_database_pool.delay(max_instances=50)
>>> print(result.id)
>>> exit()
```

**Expected Output**:
```
Task ID: abc123-def456-...
```

**Monitor Progress**:
```bash
# Watch worker logs
docker service logs -f saasodoo_database-worker

# Expected log sequence:
# 1. "Starting pool provisioning..."
# 2. "Creating CephFS directory: /mnt/cephfs/postgres_pools/pool-1"
# 3. "Creating Docker Swarm service: postgres-pool-1"
# 4. "Waiting for service to become healthy..."
# 5. "Pool postgres-pool-1 provisioned successfully"
```

**Timing**: ~2-3 minutes for completion

---

### Test 5: Verify Pool Created ✅

**Purpose**: Confirm pool is in database and healthy

```bash
# Wait 3 minutes after triggering provisioning, then:
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/pools
```

**Expected Response**:
```json
{
  "pools": [
    {
      "id": "uuid-here",
      "name": "postgres-pool-1",
      "server_type": "shared",
      "status": "active",
      "health_status": "healthy",
      "current_instances": 0,
      "max_instances": 50,
      "capacity_percentage": 0.0,
      "host": "postgres-pool-1",
      "port": 5432,
      "postgres_version": "16",
      "cpu_limit": "2",
      "memory_limit": "4G",
      "created_at": "2025-12-04T...",
      "last_health_check": "2025-12-04T..."
    }
  ],
  "total_count": 1
}
```

**Verification Steps**:
- ✅ `status` = "active"
- ✅ `health_status` = "healthy"
- ✅ `current_instances` = 0
- ✅ `max_instances` = 50

---

### Test 6: Get Pool Details by ID ✅

**Purpose**: Test single pool retrieval

```bash
# Replace POOL_ID with ID from Test 5
POOL_ID="uuid-from-test-5"

curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/pools/$POOL_ID
```

**Expected Response**: Same as Test 5 but single pool object (not array)

---

### Test 7: Manual Health Check ⚠️

**Purpose**: Trigger immediate health check

```bash
POOL_ID="uuid-from-test-5"

curl -X POST http://api.62.171.153.219.nip.io/database/api/database/admin/pools/$POOL_ID/health-check
```

**Expected Response**:
```json
{
  "pool_id": "uuid",
  "health_status": "healthy",
  "message": "Health check completed successfully",
  "response_time_ms": 15
}
```

**Status**: `200 OK`

**Note**: This endpoint may return placeholder response if not fully implemented.

---

### Test 8: Allocate Database (First Instance) 🚀

**Purpose**: Test database allocation on existing pool

```bash
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-instance-001",
    "customer_id": "test-customer-001",
    "plan_tier": "standard"
  }'
```

**Expected Response**:
```json
{
  "status": "allocated",
  "db_server_id": "pool-uuid",
  "db_host": "postgres-pool-1",
  "db_port": 5432,
  "db_name": "odoo_testcustomer001_testinst",
  "db_user": "odoo_testcustomer001_testinst_user",
  "db_password": "generated-32-char-password"
}
```

**Status**: `200 OK`

**Verification**:
```bash
# 1. Check pool instance count increased
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/pools | grep current_instances
# Should show: "current_instances": 1

# 2. Verify database exists on pool
docker exec postgres-pool-1 psql -U postgres -c "\l" | grep odoo_testcustomer
```

---

### Test 9: Allocate Multiple Databases 📊

**Purpose**: Test pool capacity tracking

```bash
# Allocate 5 more databases
for i in {2..6}; do
  curl -X POST http://api.62.171.153.219.nip.io/database/api/database/allocate \
    -H "Content-Type: application/json" \
    -d "{
      \"instance_id\": \"test-instance-00$i\",
      \"customer_id\": \"test-customer-00$i\",
      \"plan_tier\": \"standard\"
    }"
  echo ""
  sleep 2
done
```

**Expected**: All 6 allocations succeed

**Verify Pool Capacity**:
```bash
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/stats
```

**Expected**:
```json
{
  "total_pools": 1,
  "active_pools": 1,
  "total_capacity": 50,
  "total_used": 6,
  "overall_utilization": 12.0,
  "by_status": {
    "active": 1
  },
  "by_type": {
    "shared": 1
  }
}
```

---

### Test 10: Allocation When Pool Full 🔄

**Purpose**: Test provisioning trigger when pool at capacity

```bash
# First, fill pool to capacity (simulate 50 instances)
# This would require database manipulation:
docker exec saasodoo-postgres psql -U instance_service -d instance -c \
  "UPDATE db_servers SET current_instances = 50, status = 'full' WHERE name = 'postgres-pool-1';"

# Now try allocating
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-instance-051",
    "customer_id": "test-customer-051",
    "plan_tier": "standard"
  }'
```

**Expected Response**:
```json
{
  "status": "provisioning",
  "message": "No pool available, provisioning new pool...",
  "retry_after": 30
}
```

**Status**: `200 OK`

**Background**: Celery task should automatically start provisioning `postgres-pool-2`

**Monitor**:
```bash
docker service logs -f saasodoo_database-worker
# Should see: "No available pool found, provisioning new pool..."
```

---

### Test 11: Provision Dedicated Server 💎

**Purpose**: Test dedicated server provisioning for premium plans

```bash
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/provision-dedicated \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "premium-instance-001",
    "customer_id": "premium-customer-001",
    "plan_tier": "premium"
  }'
```

**Expected Response** (after 2-3 minutes):
```json
{
  "status": "provisioned",
  "db_server_id": "dedicated-uuid",
  "db_host": "postgres-dedicated-premium",
  "message": "Dedicated database server provisioned successfully"
}
```

**Status**: `200 OK`

**Note**: This is a **blocking call** - takes 2-3 minutes to complete

**Verification**:
```bash
# Check dedicated server in pool list
curl -X GET http://api.62.171.153.219.nip.io/database/api/database/admin/pools?server_type=dedicated

# Check Docker service exists
docker service ls | grep postgres-dedicated
```

---

### Test 12: Filter Pools by Status 🔍

**Purpose**: Test query filtering

```bash
# Active pools
curl -X GET "http://api.62.171.153.219.nip.io/database/api/database/admin/pools?status=active"

# Full pools
curl -X GET "http://api.62.171.153.219.nip.io/database/api/database/admin/pools?status=full"

# Shared pools
curl -X GET "http://api.62.171.153.219.nip.io/database/api/database/admin/pools?server_type=shared"

# Dedicated pools
curl -X GET "http://api.62.171.153.219.nip.io/database/api/database/admin/pools?server_type=dedicated"
```

---

### Test 13: Periodic Health Check Task 🏥

**Purpose**: Verify Celery Beat scheduled task

```bash
# Wait 5+ minutes after service start, then check logs
docker service logs saasodoo_database-worker | grep "health_check_db_pools"

# Expected logs (every 5 minutes):
# "Starting health check for all active database pools"
# "Checked 2 pools: 2 healthy, 0 degraded, 0 unhealthy"
```

---

### Test 14: Error Handling - Invalid Plan Tier ❌

**Purpose**: Test validation errors

```bash
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-instance-999",
    "customer_id": "test-customer-999",
    "plan_tier": "invalid-tier"
  }'
```

**Expected**: `400 Bad Request` or allocation succeeds (validation may be permissive)

---

### Test 15: Error Handling - Missing Fields ❌

**Purpose**: Test required field validation

```bash
curl -X POST http://api.62.171.153.219.nip.io/database/api/database/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "instance_id": "test-instance-999"
  }'
```

**Expected Response**:
```json
{
  "detail": [
    {
      "loc": ["body", "customer_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Status**: `422 Unprocessable Entity`

---

## Cleanup After Testing

```bash
# 1. Remove test Docker services
docker service rm postgres-pool-1 postgres-pool-2 postgres-dedicated-premium

# 2. Clean database records
docker exec saasodoo-postgres psql -U instance_service -d instance -c \
  "DELETE FROM db_servers WHERE name LIKE 'postgres-%';"

# 3. Remove CephFS directories
sudo rm -rf /mnt/cephfs/postgres_pools/pool-*
sudo rm -rf /mnt/cephfs/postgres_dedicated/postgres-dedicated-*
```

---

## Expected Test Results Summary

| Test | Description | Expected Result | Status |
|------|-------------|-----------------|--------|
| 1 | Health check | 200 OK | ⏳ |
| 2 | Empty stats | 200 OK, 0 pools | ⏳ |
| 3 | Empty pool list | 200 OK, empty array | ⏳ |
| 4 | Provision first pool | Task queued | ⏳ |
| 5 | Verify pool created | 200 OK, 1 pool active | ⏳ |
| 6 | Get pool by ID | 200 OK, pool details | ⏳ |
| 7 | Manual health check | 200 OK, healthy | ⏳ |
| 8 | First allocation | 200 OK, DB created | ⏳ |
| 9 | Multiple allocations | 200 OK x 6 | ⏳ |
| 10 | Full pool handling | 200 OK, provisioning | ⏳ |
| 11 | Dedicated server | 200 OK, dedicated pool | ⏳ |
| 12 | Filter pools | 200 OK, filtered | ⏳ |
| 13 | Periodic health | Logs every 5 min | ⏳ |
| 14 | Invalid plan tier | 400 or accepted | ⏳ |
| 15 | Missing fields | 422 validation error | ⏳ |

---

## Troubleshooting Guide

### Issue: Health endpoint returns 404

**Cause**: Traefik routing not configured or service not deployed

**Fix**:
```bash
docker service ls | grep database-service
docker service logs saasodoo_database-service

# Check Traefik labels
docker service inspect saasodoo_database-service --format '{{.Spec.Labels}}'
```

---

### Issue: "No pool available" immediately

**Cause**: No pools provisioned yet

**Fix**: Run Test 4 to provision first pool

---

### Issue: Pool stuck in "provisioning" status

**Cause**: Docker service creation failed or health check timeout

**Debug**:
```bash
# Check Docker services
docker service ls | grep postgres-pool

# Check service logs
docker service logs postgres-pool-1

# Check worker logs
docker service logs saasodoo_database-worker

# Manually inspect pool status
docker exec saasodoo-postgres psql -U instance_service -d instance -c \
  "SELECT name, status, health_status FROM db_servers;"
```

---

### Issue: Database allocation fails with connection error

**Cause**: Pool service not healthy or network issue

**Debug**:
```bash
# Test connection to pool
docker exec postgres-pool-1 pg_isready

# Check pool container logs
docker service logs postgres-pool-1

# Verify network connectivity
docker exec saasodoo_database-service ping postgres-pool-1
```

---

## Success Criteria

**Stages 1-3 are PASSING if**:

✅ All health endpoints return 200 OK
✅ First pool provisions successfully in < 5 minutes
✅ Pool appears in admin API with status "active"
✅ Database allocation succeeds and creates database on pool
✅ Pool instance counter increments correctly
✅ Stats endpoint shows accurate metrics
✅ Periodic health checks run every 5 minutes
✅ Dedicated server provisioning works
✅ Error handling returns appropriate HTTP codes

---

## Next Steps After Testing

Once all tests pass:

1. **Document Results**: Update `IMPLEMENTATION_STATUS.md` with test outcomes
2. **Stage 4 Integration**: Proceed to instance-service integration
3. **Production Readiness**: Review security, monitoring, backup procedures

---

**Test Report Template**:

```markdown
# Test Execution Report - 2025-12-04

## Environment
- Base URL: http://api.62.171.153.219.nip.io/database
- Services: database-service v1.0, database-worker v1.0
- Database: PostgreSQL 16-alpine

## Results
- Tests Passed: X/15
- Tests Failed: X/15
- Tests Skipped: X/15

## Issues Found
1. [Issue description]
2. [Issue description]

## Recommendations
- [Action item]
- [Action item]
```
