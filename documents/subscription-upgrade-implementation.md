# Subscription Upgrade Implementation Summary

## Overview
Implementation of live subscription plan upgrades/downgrades with automatic container resource reconfiguration (CPU, memory, storage) without downtime.

## What We Implemented

### 1. Billing Service - Webhook Handler
**File**: `services/billing-service/app/routes/webhooks.py`

- Added `SUBSCRIPTION_CHANGE` webhook handler
- Created `handle_subscription_change()` function that:
  - Filters for `actionType == "EFFECTIVE"` (ignores "REQUESTED")
  - Fetches new plan details from KillBill
  - Queries `plan_entitlements` database table for resource specifications
  - Finds instance by subscription_id
  - Updates instance database with new resource limits
  - Triggers live container resource update
  - Sends upgrade notification email (template missing)

### 2. Billing Service - Instance Client Methods
**File**: `services/billing-service/app/utils/instance_client.py`

Added two new methods:
- `update_instance_resources()` - Updates instance DB via PUT to instance-service
- `apply_resource_upgrade()` - Triggers live container update via POST to instance-service

### 3. Instance Service - Response Model Fix
**File**: `services/instance-service/app/routes/instances.py`

- Fixed `update_instance()` endpoint response to include `billing_status` and `provisioning_status` fields (bug fix)

### 4. Instance Service - Apply Resources Endpoint
**File**: `services/instance-service/app/routes/instances.py`

- New endpoint: `POST /api/v1/instances/{instance_id}/apply-resources`
- Reads instance from database
- Updates Docker container CPU/memory via Docker client
- Updates CephFS storage quota via `setfattr`

### 5. Docker Client - Update Resources Method
**File**: `services/instance-service/app/utils/docker_client.py`

- Added `update_container_resources()` method
- Uses `cpu_period` and `cpu_quota` for CPU limits
- Uses `mem_limit` and `memswap_limit` for memory

## Current Issue: Docker API Conflict

### Problem
Containers created with `nano_cpus` parameter **cannot** be updated with `cpu_period`/`cpu_quota` parameters. Docker returns error:
```
409 Conflict: "CPU Period cannot be updated as NanoCPUs has already been set"
```

### Root Cause
- **Provisioning** (`provisioning.py:377`) creates containers using: `nano_cpus=int(cpu_limit * 1_000_000_000)`
- **Update** (`docker_client.py:399`) tries to update using: `cpu_period` and `cpu_quota`
- Docker treats these as conflicting options

## Solution: Use Consistent CPU Format

### What Needs to Change
**File**: `services/instance-service/app/tasks/provisioning.py` (line ~377)

Change FROM:
```python
nano_cpus=int(cpu_limit * 1_000_000_000)
```

Change TO:
```python
cpu_period=100000,
cpu_quota=int(cpu_limit * 100000)
```

### Why This Works
- Both creation and update will use `cpu_period`/`cpu_quota` format
- Docker will allow updates since the format is consistent
- No conflicts between nano_cpus and cpu_quota

## Remaining Tasks

### 1. Update Provisioning Code
- [ ] Change `provisioning.py` to use `cpu_period` and `cpu_quota` instead of `nano_cpus`
- [ ] Rebuild instance-service
- [ ] Test creating a new instance

### 2. Test End-to-End Upgrade
- [ ] Create a fresh test subscription with new instance
- [ ] Verify container created with cpu_quota (not nano_cpus)
- [ ] Upgrade subscription from basic → premium
- [ ] Verify container resources updated (1 vCPU/2GB → 4 vCPU/8GB)
- [ ] Verify storage quota updated (10GB → 50GB)
- [ ] Verify zero downtime (container stays running)

### 3. Add Email Template
- [ ] Create `subscription_upgraded` email template in notification-service
- [ ] Test upgrade notification email

## Pitfalls and Considerations

### 1. Existing Containers (Critical)
**Issue**: All existing containers were created with `nano_cpus`
**Impact**: Cannot upgrade existing containers without recreating them
**Solutions**:
- **Option A**: Accept that existing containers can't be upgraded (document as known limitation)
- **Option B**: Add migration logic to detect old format and recreate container
- **Option C**: Provide manual migration script for existing customers

**Recommendation**: Option A for now (document as limitation). New containers going forward will support upgrades.

### 2. Container Downtime During Recreation
If we need to recreate old containers:
- Stop container
- Remove container
- Create new container with updated limits
- **Downtime**: 10-30 seconds during recreation
- Data persists (volumes not affected)

### 3. Storage Quota Update via setfattr
**Current**: Runs inside instance-service container
**Requirement**: Container needs CephFS mounted at `/mnt/cephfs`
**Failure Mode**: If CephFS not mounted, storage quota update fails silently (logs warning, continues)

### 4. Memory Swap Configuration
**Current**: Set `memswap_limit = mem_limit` (no swap)
**Impact**: Container has no swap space
**Trade-off**: Better performance but less flexibility if memory spikes

### 5. Docker API Version Compatibility
**Current**: Uses Docker API v1.51
**Risk**: Older Docker versions may not support all parameters
**Mitigation**: Document minimum Docker version required

### 6. Concurrent Upgrades
**Current**: No locking mechanism
**Risk**: If multiple upgrades happen simultaneously, race conditions possible
**Impact**: Database updates may conflict
**Mitigation**: KillBill ensures only one EFFECTIVE event per subscription at a time

### 7. Failed Upgrade Recovery
**Current**: If Docker update fails, DB is updated but container unchanged
**Impact**: Mismatch between DB and actual container resources
**Recovery**: Manual intervention required or wait for container restart
**Improvement Needed**: Add rollback logic or retry mechanism

### 8. Resource Validation
**Current**: Instance-service validates resource limits against plan
**Gap**: No validation that Docker host has sufficient resources
**Risk**: Update may succeed in DB but fail at Docker level if host overcommitted

## Testing Strategy

### Test Case 1: New Container Upgrade (Happy Path)
1. Create instance with basic plan (after provisioning fix)
2. Verify container has 1 vCPU, 2GB, 10GB
3. Upgrade to premium plan
4. Verify container has 4 vCPU, 8GB, 50GB
5. Verify container never stopped (zero downtime)

### Test Case 2: Downgrade
1. Start with premium plan (4 vCPU, 8GB)
2. Downgrade to basic plan (1 vCPU, 2GB)
3. Verify resources reduced
4. Verify container still running

### Test Case 3: Failed Payment After Upgrade
1. Upgrade to premium
2. Simulate payment failure
3. Verify instance suspended (existing logic)
4. Pay invoice
5. Verify instance reactivated with premium resources

### Test Case 4: Rapid Multiple Upgrades
1. Upgrade basic → standard
2. Immediately upgrade standard → premium
3. Verify final state is premium
4. Verify no race conditions

## Success Criteria

✅ Subscription webhook received and processed
✅ Database updated with new resource limits
✅ Docker container CPU/memory updated live
✅ CephFS storage quota updated
✅ Container remains running (zero downtime)
✅ No manual intervention required

## Flow Diagram

```
User upgrades plan in KillBill
         ↓
KillBill sends SUBSCRIPTION_CHANGE (EFFECTIVE) webhook
         ↓
Billing-service receives webhook
         ↓
Get new plan from KillBill subscription
         ↓
Query plan_entitlements database for resources
         ↓
Update instance database record
         ↓
Call instance-service /apply-resources endpoint
         ↓
    ↙            ↘
Docker update      setfattr CephFS quota
(CPU/memory)       (storage)
         ↘            ↙
              ↓
    Resources applied (zero downtime)
         ↓
    Send notification email
```

## Database Schema

### plan_entitlements table
```sql
plan_name        | cpu_limit | memory_limit | storage_limit
-----------------+-----------+--------------+---------------
basic-monthly    | 1.0       | 2G           | 10G
standard-monthly | 2.0       | 4G           | 20G
premium-monthly  | 4.0       | 8G           | 50G
```

## Key Files Modified

1. `services/billing-service/app/routes/webhooks.py` - Added subscription change handler
2. `services/billing-service/app/utils/instance_client.py` - Added update methods
3. `services/instance-service/app/routes/instances.py` - Added apply-resources endpoint, fixed response
4. `services/instance-service/app/utils/docker_client.py` - Added update_container_resources method
5. **TO DO**: `services/instance-service/app/tasks/provisioning.py` - Need to change nano_cpus to cpu_quota

## Next Steps

1. **Immediate**: Change provisioning to use cpu_quota
2. **Testing**: Create fresh instance and test upgrade
3. **Documentation**: Update user docs about upgrade feature
4. **Monitoring**: Add metrics for upgrade success/failure rates
5. **Future**: Consider adding rollback capability for failed upgrades
