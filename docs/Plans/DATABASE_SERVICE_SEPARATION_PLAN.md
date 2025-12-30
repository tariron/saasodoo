# Database Service Separation Plan

**Goal:** Remove direct DB access from `database-service` to `instance` database. Use API instead.

---

## Current State (Problem)

```
database-service ──► instance DB (db_servers table)  ❌ Cross-service DB write
```

## Target State

```
database-service ──► instance-service API ──► instance DB  ✅ Clean boundaries
```

---

## Changes Required

### 1. instance-service: Add Internal API

**File:** `services/instance-service/app/routes/db_servers.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/internal/db-servers` | GET | List pools (with filters) |
| `/internal/db-servers` | POST | Register new pool |
| `/internal/db-servers/{id}` | PATCH | Update pool status/health |
| `/internal/db-servers/{id}` | DELETE | Remove pool |
| `/internal/db-servers/available` | GET | Find available pool for allocation |
| `/internal/db-servers/{id}/increment` | POST | Increment instance count |

### 2. database-service: Replace Direct DB Calls

**Files to modify:**
- `app/tasks/provisioning.py` - Replace INSERT/UPDATE with API calls
- `app/tasks/monitoring.py` - Replace UPDATE with API calls
- `app/services/db_allocation_service.py` - Replace all db_servers queries with API calls

### 3. Shared: Create Client

**File:** `shared/clients/instance_service_client.py`

```python
class InstanceServiceClient:
    async def create_db_server(self, data: dict) -> dict
    async def update_db_server(self, id: str, data: dict) -> dict
    async def get_available_pool(self, server_type: str) -> Optional[dict]
    async def increment_instance_count(self, id: str) -> bool
```

### 4. Remove Grants

After migration, remove `database_service` grants from:
- `infrastructure/postgres-cnpg/08-schema-job.yaml`

---

## Migration Steps

1. Add internal API to instance-service
2. Create shared client
3. Update database-service to use client
4. Test
5. Remove direct DB grants
6. Delete unused database-service DB code

---

## Not Changing

- `db_servers` table stays in `instance` database
- FK constraint `instances.db_server_id → db_servers.id` preserved
- database-worker still handles pool provisioning logic
