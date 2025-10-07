# Complete Instance Status Refactor Prompt

## Objective
Refactor the InstanceStatus enum to separate business/application states from Docker infrastructure states across the entire codebase (backend AND frontend), then rebuild and test.

## Context
The current implementation mixes business states (what users see) with Docker container states (infrastructure details). This creates confusion and tight coupling between business logic and infrastructure.

### Current Problem
- `InstanceStatus` enum contains: `CREATING`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `RESTARTING`, `UPDATING`, `MAINTENANCE`, `ERROR`, `TERMINATED`, `CONTAINER_MISSING`, `PAUSED`
- Docker states like `STARTING`, `STOPPING`, `RESTARTING`, `PAUSED`, `CONTAINER_MISSING` are mixed with business states
- Frontend displays these Docker states to users (confusing)
- Monitoring directly maps Docker states 1:1 to instance states (incorrect)

### Desired Architecture
**Business States (InstanceStatus - what users care about):**
- `CREATING` - Instance being provisioned
- `RUNNING` - Instance operational, user can access
- `STOPPED` - Instance stopped by user, can restart
- `SUSPENDED` - Instance suspended (billing/admin action)
- `MAINTENANCE` - Instance in scheduled maintenance
- `UPDATING` - Software update in progress
- `ERROR` - Failed state, needs intervention
- `TERMINATED` - Permanently deleted

**Infrastructure States (DockerContainerState - already exists, query on-demand):**
- `RUNNING`, `STOPPED`, `PAUSED`, `RESTARTING`, `CREATED`, `EXITED`, `DEAD`, `REMOVING`

## Requirements

### Phase 1: Code Analysis & Planning
1. **Identify all files** that reference InstanceStatus (backend and frontend)
2. **Document current usage** of each status value
3. **Map dependencies** between status changes and business logic
4. **Identify webhook handlers** that change instance status
5. **Create a comprehensive file change list** before making any changes

### Phase 2: Backend Refactoring

**A. Update Enums (both locations must match):**
- `shared/schemas/instance.py` - Update InstanceStatus to 8 business states only
- `services/instance-service/app/models/instance.py` - Sync with shared schema

**B. Create Intelligent Mapping Logic:**
- Update `services/instance-service/app/models/events.py`
- Add `derive_instance_status_from_docker(current_status, docker_state)` function
- Logic: Transient Docker states (PAUSED, RESTARTING) → keep current business state
- Logic: Container missing → ERROR with descriptive error_message
- Logic: Docker RUNNING → Business RUNNING (unless suspended/terminated)

**C. Update Monitoring Reconciliation:**
- `services/instance-service/app/tasks/monitoring.py`
- Use intelligent mapping (not 1:1)
- Never override TERMINATED status
- Log when keeping status due to transient Docker state

**D. Update All Status References:**
- Remove: `STARTING` → Use `CREATING` or transition directly to `RUNNING`
- Remove: `STOPPING` → Transition directly to `STOPPED`
- Remove: `RESTARTING` → Keep as `RUNNING`
- Remove: `PAUSED` → Use `SUSPENDED` for business suspension
- Remove: `CONTAINER_MISSING` → Use `ERROR` with error_message

**Files to update:**
- `app/services/instance_service.py` - Status validation
- `app/routes/instances.py` - State machine, action validation
- `app/routes/admin.py` - Statistics endpoints
- `app/tasks/lifecycle.py` - Start/stop/restart workflows
- `app/tasks/provisioning.py` - Instance provisioning
- `app/tasks/maintenance.py` - Maintenance tasks
- All other files with InstanceStatus references

**E. Verify Webhook Integration:**
- Confirm webhooks already use business states (suspend/unsuspend/terminate)
- NO changes should be needed to webhook handlers
- If changes needed, document why

### Phase 3: Frontend Refactoring

**A. Update TypeScript Types:**
- `frontend/src/utils/api.ts` - Update Instance status type definition
- Remove: `'starting'`, `'stopping'`, `'paused'`, `'restarting'`, `'container_missing'`
- Add: `'suspended'`, `'maintenance'`, `'updating'`

**B. Update Status Display:**
- `frontend/src/pages/Instances.tsx`
  - Update status badge colors and labels
  - Remove conditional logic for removed statuses
  - Add handling for new statuses (suspended, maintenance, updating)

- `frontend/src/pages/Billing.tsx`
  - Update status checks
  - Change 'paused' references to 'suspended'

- `frontend/src/pages/BillingInstanceManage.tsx`
  - Update status-based actions
  - Change 'unpause' to 'unsuspend'

**C. Update Action Buttons:**
- Show correct actions based on business state:
  - `RUNNING` → stop, restart, backup, suspend, terminate
  - `STOPPED` → start, backup, restore, terminate
  - `SUSPENDED` → unsuspend, terminate
  - `ERROR` → start, restart, restore, terminate
  - `TERMINATED` → no actions

### Phase 4: Database Reset (NO MIGRATION)

Since you want to delete and recreate the database:

**Steps:**
1. Stop all services
2. Delete database volumes: `docker compose -f infrastructure/compose/docker-compose.dev.yml down -v`
3. Recreate database: `docker compose -f infrastructure/compose/docker-compose.dev.yml up -d postgres`
4. Database will be initialized fresh with init scripts

**NO migration script needed** - fresh start

### Phase 5: Rebuild & Deploy

**A. Build Services:**
```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml build instance-service
docker compose -f infrastructure/compose/docker-compose.dev.yml build frontend-service
```

**B. Start Services:**
```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml up -d
```

**C. Verify Services Started:**
```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml ps
docker logs instance-service --tail=50
docker logs frontend-service --tail=50
```

### Phase 6: Testing

**A. Backend API Tests:**

1. **Health Check:**
```bash
curl http://localhost:8003/health
```

2. **Create Instance:**
```bash
curl -X POST http://localhost:8003/instances \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-instance",
    "admin_email": "test@example.com",
    "admin_password": "test123",
    "database_name": "testdb",
    "odoo_version": "17.0"
  }'
```
Expected: Status should be `creating`

3. **Check Instance Status:**
```bash
curl http://localhost:8003/instances/{instance-id}
```
Expected: Status should transition `creating` → `running`

4. **Stop Instance:**
```bash
curl -X POST http://localhost:8003/instances/{instance-id}/actions \
  -H "Content-Type: application/json" \
  -d '{"action": "stop"}'
```
Expected: Status should be `stopped` (NOT `stopping`)

5. **Start Instance:**
```bash
curl -X POST http://localhost:8003/instances/{instance-id}/actions \
  -H "Content-Type: application/json" \
  -d '{"action": "start"}'
```
Expected: Status should be `running` (NOT `starting`)

6. **Admin Statistics:**
```bash
curl http://localhost:8003/admin/stats
```
Expected: Should show counts for 8 business states only (no Docker states)

**B. Frontend UI Tests:**

1. **Open Frontend:**
   - Navigate to `http://localhost:3000` (or configured port)

2. **Check Instances Page:**
   - Status badges should show: creating, running, stopped, suspended, maintenance, updating, error, terminated
   - NO badges for: starting, stopping, restarting, paused, container_missing
   - Colors should be appropriate for each status

3. **Test Instance Actions:**
   - Create instance → Should show "creating" status
   - Wait for provisioning → Should change to "running"
   - Stop instance → Should show "stopped" (immediately, no "stopping")
   - Start instance → Should show "running" (immediately, no "starting")

4. **Test Billing Integration:**
   - Suspend instance (billing) → Should show "suspended" (not "paused")
   - Unsuspend instance → Should show "running" or "stopped"

**C. Monitoring Tests:**

1. **Pause Docker Container (transient state):**
```bash
docker pause odoo_testdb_12345678
```
Check instance status in API - should STAY "running" (intelligent mapping)

2. **Unpause Docker Container:**
```bash
docker unpause odoo_testdb_12345678
```
Check instance status - should still be "running"

3. **Stop Docker Container:**
```bash
docker stop odoo_testdb_12345678
```
Check instance status - should change to "stopped"

4. **Remove Docker Container:**
```bash
docker rm odoo_testdb_12345678
```
Check instance status - should change to "error" with error_message

**D. Webhook Tests (if applicable):**

1. Trigger payment failure webhook → Instance should be `suspended`
2. Trigger payment success webhook → Instance should be `running` or `stopped`
3. Trigger subscription cancellation webhook → Instance should be `terminated`

### Phase 7: Verification Checklist

- [ ] No references to `STARTING`, `STOPPING`, `RESTARTING`, `PAUSED`, `CONTAINER_MISSING` in backend code
- [ ] No references to `'starting'`, `'stopping'`, `'restarting'`, `'paused'`, `'container_missing'` in frontend code
- [ ] Both backend enums (shared and service) have exactly 8 business states
- [ ] Frontend TypeScript type has exactly 8 business states
- [ ] Intelligent mapping function exists and is used by monitoring
- [ ] All lifecycle operations (create/start/stop/restart) work correctly
- [ ] Status badges display correctly in frontend
- [ ] Action buttons show correct options based on status
- [ ] Admin statistics show 8 states only
- [ ] Monitoring reconciliation uses intelligent mapping (doesn't change status for transient Docker states)
- [ ] Webhooks continue to work (suspend/unsuspend/terminate)
- [ ] No errors in backend logs
- [ ] No errors in frontend console
- [ ] Database contains only 8 business status values

### Success Criteria

1. ✅ Clean separation: Business states in `InstanceStatus`, Docker states queried on-demand
2. ✅ Zero enum references to Docker states in code
3. ✅ Frontend displays 8 business states only
4. ✅ Intelligent mapping prevents false status changes
5. ✅ All tests pass
6. ✅ No errors in logs
7. ✅ Webhooks work correctly
8. ✅ Instance lifecycle operations work as expected

### Important Notes

1. **DO NOT** create migration scripts - we're deleting and recreating the database
2. **DO** update both backend AND frontend in the same refactor
3. **DO** rebuild services after code changes
4. **DO** test thoroughly before considering it complete
5. **DO** verify monitoring reconciliation with intelligent mapping
6. **DO** confirm webhooks are not broken
7. **DO** check that transient Docker states don't trigger unnecessary status updates

### Rollback Plan

If issues occur:
1. `git revert <commit-hash>` (revert all changes)
2. `docker compose -f infrastructure/compose/docker-compose.dev.yml down -v` (delete database)
3. `docker compose -f infrastructure/compose/docker-compose.dev.yml build` (rebuild with old code)
4. `docker compose -f infrastructure/compose/docker-compose.dev.yml up -d` (restart)

---

## Expected Deliverables

1. **Refactored backend code** - All 11 backend files updated
2. **Refactored frontend code** - All 4 frontend files updated
3. **Working system** - Services built and running
4. **Test results** - All tests passing
5. **Verification report** - Checklist completed
6. **Summary document** - What changed and why

---

## Questions to Ask Before Starting

1. Are there any custom status values in use that we haven't identified?
2. Are there any external systems that depend on the current status values?
3. Should we add a `container_status` field to API responses for debugging?
4. What should the frontend show when Docker container is paused but business state is running?
5. Are there any scheduled jobs or cron tasks that check instance status?

---

## Execution Instructions

**Run this prompt in a fresh conversation with Claude Code:**

"Please execute the complete Instance Status Refactor as documented in this file. Follow all phases in order:
1. Analyze and plan (identify all files)
2. Refactor backend (update enums, mapping, all references)
3. Refactor frontend (update types, UI, actions)
4. Reset database (delete volumes and recreate)
5. Rebuild services (backend and frontend)
6. Test thoroughly (API, UI, monitoring, webhooks)
7. Verify checklist and create summary

Do NOT skip the frontend updates. Do NOT create migration scripts. DO delete and recreate the database. DO rebuild services. DO test everything.

