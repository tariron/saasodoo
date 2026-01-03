# Issue: Instance Provisioning Retry Mechanism

**Date Identified:** 2026-01-03
**Status:** Open
**Priority:** High
**Affected Services:** instance-service, frontend-service

---

## Problem Summary

When instance provisioning fails (e.g., due to insufficient cluster resources), the system leaves the instance in an inconsistent state with no way for users to retry.

---

## Current Behavior

### What Happens on Provisioning Failure

1. Instance created in database (status: `creating`)
2. Database allocated successfully (dedicated postgres running)
3. Odoo deployment created but pod stuck `Pending` (insufficient resources)
4. Timeout after 3 minutes
5. Cleanup runs:
   - K8s Deployment: **deleted**
   - K8s PVC (Odoo): **deleted**
   - Dedicated Postgres: **NOT deleted** (still running)
   - Instance DB record: **NOT deleted** (status set to `error`)
   - `provisioning_status`: **NOT updated** (still says `provisioning`)

### Result

```
Instance Record:
├── status: error              ✅ Updated
├── provisioning_status: provisioning  ❌ NOT updated (should be 'failed')
├── error_message: "Deployment did not become ready..."  ✅ Set
├── db_server_id: <uuid>       ✅ Points to still-running postgres
└── K8s resources: deleted     ✅ Cleaned up
```

---

## Issues Identified

### 1. Backend: `provisioning_status` Not Updated on Failure

**Location:** `services/instance-service/app/tasks/provisioning.py`

When provisioning fails, only `status` is updated to `error`, but `provisioning_status` remains `provisioning` instead of being set to `failed`.

### 2. Backend: Retry Endpoint is Broken

**Location:** `services/instance-service/app/routes/admin.py:63`

```python
# Current (BROKEN):
job = provision_instance_task.delay(str(instance_id))  # Missing db_info!
```

The `provision_instance_task` requires `db_info` (including password) but the retry endpoint doesn't provide it.

**Fix Required:**
```python
# Should use wait_for_database_and_provision instead:
from app.tasks.provisioning import wait_for_database_and_provision

job = wait_for_database_and_provision.delay(
    instance_id=str(instance_id),
    customer_id=str(instance.customer_id),
    db_type=instance.db_type or 'shared'
)
```

This works because:
- `wait_for_database_and_provision` calls database-service's `/api/database/allocate`
- The allocate endpoint is idempotent - returns existing credentials if DB already allocated
- Password is retrieved fresh from database-service (not stored in instance record)

### 3. Frontend: No Retry Button

**Location:** `frontend/src/pages/InstanceDashboard.tsx` or similar

Users see the error status but have no way to retry provisioning. Need to add:
- Retry button for instances in `error` status
- Call to `POST /api/instance/admin/retry-instance/{instance_id}`
- Loading state while retry is in progress

---

## Proposed Solution

### Phase 1: Backend Fixes

#### 1.1 Update `provisioning_status` on failure

**File:** `services/instance-service/app/tasks/provisioning.py`

In the exception handler, also update `provisioning_status`:

```python
except Exception as e:
    logger.error("Instance provisioning failed", instance_id=instance_id, error=str(e))

    # Update both status AND provisioning_status
    asyncio.run(_update_instance_status(
        instance_id,
        InstanceStatus.ERROR,
        str(e),
        provisioning_status='failed'  # Add this
    ))
    raise
```

#### 1.2 Fix retry endpoint

**File:** `services/instance-service/app/routes/admin.py`

```python
from app.tasks.provisioning import wait_for_database_and_provision

@router.post("/retry-instance/{instance_id}")
async def retry_instance_provisioning(
    instance_id: UUID,
    db: InstanceDatabase = Depends(get_database)
):
    """Retry provisioning for a failed instance"""
    instance = await db.get_instance(instance_id)
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    if instance.status != InstanceStatus.ERROR:
        raise HTTPException(
            status_code=400,
            detail=f"Instance is not in ERROR status (current: {instance.status})"
        )

    # Reset statuses
    await db.update_instance_status(instance_id, InstanceStatus.CREATING)
    # Also reset provisioning_status to 'pending'

    # Use wait_for_database_and_provision to get fresh credentials
    job = wait_for_database_and_provision.delay(
        instance_id=str(instance_id),
        customer_id=str(instance.customer_id),
        db_type=instance.db_type or 'shared'
    )

    return {
        "message": "Instance provisioning retry queued",
        "instance_id": str(instance_id),
        "job_id": job.id
    }
```

### Phase 2: Frontend Changes

#### 2.1 Add retry button to instance card/detail

Show retry button when `status === 'error'`:

```tsx
{instance.status === 'error' && (
  <Button
    onClick={() => retryProvisioning(instance.id)}
    variant="warning"
  >
    Retry Provisioning
  </Button>
)}
```

#### 2.2 Show error message

Display the `error_message` field to help users understand what went wrong:

```tsx
{instance.status === 'error' && instance.error_message && (
  <Alert variant="error">
    <AlertTitle>Provisioning Failed</AlertTitle>
    <AlertDescription>{instance.error_message}</AlertDescription>
  </Alert>
)}
```

---

## Testing Checklist

- [ ] Create instance with insufficient resources (force failure)
- [ ] Verify `provisioning_status` is set to `failed`
- [ ] Verify retry button appears in frontend
- [ ] Click retry and verify new provisioning task is queued
- [ ] Verify database credentials are retrieved (not missing)
- [ ] Verify provisioning succeeds on retry (if resources available)

---

## Related Files

| File | Purpose |
|------|---------|
| `services/instance-service/app/routes/admin.py` | Retry endpoint |
| `services/instance-service/app/tasks/provisioning.py` | Provisioning task |
| `services/instance-service/app/utils/database.py` | Instance database operations |
| `frontend/src/pages/Instances.tsx` | Instance list page |
| `frontend/src/components/InstanceCard.tsx` | Instance card component |

---

## Notes

- The dedicated postgres remains running after failure - this is intentional so retry doesn't need to re-provision the database
- The database-service allocate endpoint is idempotent - calling it again returns existing credentials
- Password is never stored in the instance record (security) - must be retrieved from database-service on retry
