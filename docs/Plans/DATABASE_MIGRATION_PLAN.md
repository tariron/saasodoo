# Database Migration Plan: Shared → Dedicated

**Purpose**: Extend `apply_resource_upgrade()` to handle database migration when upgrading to premium plans.

---

## Current Flow

```
Upgrade webhook → detect upgrade → call apply_resource_upgrade()
                                    ↓
                            Updates CPU/RAM/Storage
```

## New Flow

```
Upgrade webhook → detect upgrade → call apply_resource_upgrade()
                                    ↓
                            Check if db_type changed
                            ↓               ↓
                    Yes: Migrate DB    No: Update CPU/RAM/Storage only
```

---

## Code Changes

### **Total: ~80 lines**

### 1. Extend `apply_resource_upgrade()`
**File**: `services/instance-service/app/routes/instances.py:1297`

**Add at line ~1310** (after getting instance from DB):
```python
# Check if database migration is needed
current_db_type = instance.db_type or 'shared'
plan_name = await _get_plan_name_for_instance(instance_id)  # Query billing/subscription
new_entitlements = await _get_plan_entitlements(plan_name)
new_db_type = new_entitlements.get('db_type', 'shared')

if current_db_type == 'shared' and new_db_type == 'dedicated':
    # Queue database migration task
    from app.tasks.migration import migrate_database_task
    migrate_database_task.delay(str(instance_id))

    return {
        "status": "migrating",
        "message": "Database migration queued",
        "instance_id": str(instance_id)
    }

# Otherwise, continue with normal resource upgrade (CPU/RAM/Storage)
```

---

### 2. Create Migration Task
**File**: `services/instance-service/app/tasks/migration.py` (NEW)

**~70 lines total:**

```python
@celery_app.task(bind=True)
def migrate_database_task(self, instance_id: str):
    asyncio.run(_migrate_workflow(instance_id))


async def _migrate_workflow(instance_id: str):
    """
    1. Stop instance
    2. Backup database (reuse _backup_instance_workflow)
    3. Provision dedicated server (call database-service)
    4. Update instance record (db_server_id, db_host, db_type='dedicated')
    5. Restore backup (reuse _restore_database_backup - reads new db_server)
    6. Update Docker service environment variables (point to new dedicated DB)
    7. Restart instance (reuse _start_docker_service)
    """

    # Import existing functions from maintenance.py
    from app.tasks.maintenance import (
        _get_instance_from_db,
        _stop_docker_service,
        _backup_instance_workflow,
        _restore_database_backup,
        _get_backup_record,
        _wait_for_odoo_startup,
        _update_instance_status
    )

    instance = await _get_instance_from_db(instance_id)

    # 1. Stop
    await _stop_docker_service(instance)

    # 2. Backup
    backup_result = await _backup_instance_workflow(instance_id, "pre_migration")

    # 3. Provision dedicated (HTTP call to database-service)
    dedicated = await _provision_dedicated_via_api(instance_id)
    # Returns: {db_server_id, db_host, db_port, db_user, db_password}

    # 4. Update instance record with new DB connection
    await _update_db_connection(instance_id, dedicated)

    # 5. Restore (will use new db_server from instance record)
    backup_info = await _get_backup_record(backup_result['backup_id'])
    instance = await _get_instance_from_db(instance_id)  # Reload with new db info
    await _restore_database_backup(instance, backup_info)

    # 6. Update Docker service environment variables
    await _update_service_environment(instance, dedicated)

    # 7. Restart (service will connect to new dedicated server)
    container = await _start_docker_service_after_migration(instance)
    await _wait_for_odoo_startup(container)
```

**Helper functions** (~50 lines):

```python
async def _provision_dedicated_via_api(instance_id):
    """Call database-service to provision dedicated server"""
    async with httpx.AsyncClient(timeout=600) as client:
        response = await client.post(
            f"{DATABASE_SERVICE_URL}/api/database/provision-dedicated",
            json={"instance_id": instance_id}
        )
        return response.json()


async def _update_db_connection(instance_id, dedicated):
    """Update instance record with new database connection details"""
    conn = await asyncpg.connect(...)
    await conn.execute("""
        UPDATE instances
        SET db_server_id = $1, db_host = $2, db_port = $3,
            db_user = $4, db_type = 'dedicated'
        WHERE id = $5
    """, dedicated['db_server_id'], dedicated['db_host'],
         dedicated['db_port'], dedicated['db_user'], instance_id)


async def _update_service_environment(instance, dedicated):
    """
    Update both odoo.conf and Docker service environment variables

    CRITICAL: Environment variables DO NOT override odoo.conf when ODOO_SKIP_BOOTSTRAP=yes.
    Bitnami Odoo ONLY reads odoo.conf after bootstrap phase.
    We must manually edit odoo.conf AND update env vars for consistency.

    Test Results (2025-12-17):
    - Scenario 1: Env vars only → FAILED (ignored by Bitnami)
    - Scenario 2: Delete odoo.conf → FAILED (container crashes)
    - Scenario 3: Manual edit odoo.conf + env vars → SUCCESS ✓
    """
    import configparser

    client = docker.from_env()
    service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

    # Step 1: Update odoo.conf file (REQUIRED - this is what Odoo actually uses)
    cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
    odoo_conf_path = f"{cephfs_path}/conf/odoo.conf"

    logger.info("Updating odoo.conf with new database connection",
                odoo_conf_path=odoo_conf_path,
                new_db_host=dedicated['db_host'])

    # Read existing config to preserve all settings
    config = configparser.ConfigParser()
    config.read(odoo_conf_path)

    # Update ONLY database connection fields
    config['options']['db_host'] = dedicated['db_host']
    config['options']['db_user'] = dedicated['db_user']
    config['options']['db_password'] = dedicated['db_password']
    # Note: db_name stays the same (we're moving the same database)

    # Write back complete config
    with open(odoo_conf_path, 'w') as f:
        config.write(f)

    logger.info("odoo.conf updated successfully")

    # Step 2: Update Docker service environment variables (for consistency & documentation)
    # These won't override odoo.conf, but keeps env vars in sync
    service = client.services.get(service_name)

    service.update(
        env_add=[
            f'ODOO_DATABASE_HOST={dedicated["db_host"]}',
            f'ODOO_DATABASE_USER={dedicated["db_user"]}',
            f'ODOO_DATABASE_PASSWORD={dedicated["db_password"]}',
        ],
        force_update=True  # Force restart to pick up new odoo.conf
    )

    logger.info("Service environment variables updated and restart triggered")
```

---

## What Gets Reused (already exists)

- `_backup_instance_workflow()` - maintenance.py:103
- `_restore_database_backup()` - maintenance.py:532
- `_stop_docker_service()` - maintenance.py:1103
- `_start_docker_service()` - maintenance.py:1138
- `_wait_for_odoo_startup()` - maintenance.py:1187
- `provision_dedicated_server()` - database-service/provisioning.py:310

---

## Summary

**New code**: ~120 lines
- Detection in `apply_resource_upgrade()`: 10 lines
- Migration task: 40 lines
- Helper functions: 70 lines (including updated `_update_service_environment()`)

**Reused code**: ~1000 lines

**Critical steps**:
1. **Manually edit odoo.conf** - Change db_host, db_user, db_password (REQUIRED)
2. **Update Docker service env vars** - Keep environment in sync (for consistency)
3. **Force service restart** - Pick up new odoo.conf settings

**⚠️ CRITICAL FINDING (Tested 2025-12-17)**:
- Environment variables DO NOT override odoo.conf when `ODOO_SKIP_BOOTSTRAP=yes`
- Deleting odoo.conf causes container crash (Bitnami requires it)
- Must manually edit odoo.conf file - this is what Odoo actually reads
- Update env vars too for consistency, but they won't be used by Odoo

**Database changes**: None

**Downtime**: 5-15 minutes

**Implementation time**: 4-6 hours

---

## Appendix: Bitnami Odoo Configuration Behavior (Test Results)

### Test Date: 2025-12-17
### Test Instance: Migration (ID: 46784872)
### Test: Database migration from postgres-pool-2 → postgres-pool-1

### Key Finding: Environment Variables Are Ignored After Bootstrap

**Bitnami Odoo has TWO distinct phases:**

#### Phase 1: Bootstrap (First Startup)
- Triggered when `ODOO_SKIP_BOOTSTRAP` is NOT set
- Generates odoo.conf from environment variables
- Initializes database
- Creates admin user

#### Phase 2: Normal Operation (All Subsequent Restarts)
- Triggered when `ODOO_SKIP_BOOTSTRAP=yes`
- **Reads odoo.conf file ONLY**
- **Completely ignores environment variables**
- Requires odoo.conf to exist (crashes if missing)

### Test Results

| Scenario | Action | Result | Reason |
|----------|--------|--------|--------|
| 1 | Update env vars only | ❌ FAILED | Env vars ignored when odoo.conf exists |
| 2 | Delete odoo.conf | ❌ FAILED | Container crashes: "No such file or directory" |
| 3 | Manually edit odoo.conf | ✅ SUCCESS | Odoo reads the updated file on restart |

### Why Scenario 2 Failed

When we set `ODOO_SKIP_BOOTSTRAP=yes`:
- Bitnami startup script assumes configuration already exists
- Script tries to read odoo.conf with grep: `grep /opt/bitnami/odoo/conf/odoo.conf`
- If file doesn't exist: Container crashes with exit code 255
- Environment variables are NOT used to regenerate the file

From Bitnami docs:
> "When setting ODOO_SKIP_BOOTSTRAP to yes, values for environment variables such as ODOO_EMAIL or ODOO_PASSWORD will be ignored."

### Implementation Implications

1. **Never delete odoo.conf on running instances**
2. **Always use `ODOO_SKIP_BOOTSTRAP=yes` to prevent reinitializing database**
3. **Manually edit odoo.conf for database connection changes**
4. **Update env vars for documentation/consistency, but they won't affect Odoo**
5. **Use `force_update=True` to trigger service restart with new config**

### Code Pattern

```python
# CORRECT: Edit odoo.conf + update env vars
config = configparser.ConfigParser()
config.read(odoo_conf_path)
config['options']['db_host'] = new_host
with open(odoo_conf_path, 'w') as f:
    config.write(f)

service.update(
    env_add=[f'ODOO_DATABASE_HOST={new_host}'],
    force_update=True
)

# WRONG: Update env vars only (will be ignored!)
service.update(env_add=[f'ODOO_DATABASE_HOST={new_host}'])
```

### Test Verification

**Before migration:**
- Pool-2 connections: 1
- Pool-1 connections: 0
- odoo.conf db_host: postgres-pool-2

**After migration (Scenario 3):**
- Pool-2 connections: 0 ✓
- Pool-1 connections: 3 ✓
- odoo.conf db_host: postgres-pool-1 ✓
- Data integrity: 100% (7 users, 40 partners preserved) ✓
- Service stability: Running without crashes ✓

---

## Appendix B: How to Connect to PostgreSQL Pools (For Testing/Debugging)

### Challenge
PostgreSQL pool containers (`postgres-pool-1`, `postgres-pool-2`) are not directly accessible because Docker Swarm generates unpredictable container names.

### Solution: Use Docker Swarm DNS from Another Container

**Access pools via Swarm DNS from any container on the same network** (e.g., the main platform postgres container).

### Step 1: Get Pool Admin Credentials

```bash
# Get admin password for pool-1
docker exec saasodoo_postgres.1.xxx psql -U instance_service -d instance -c \
  "SELECT admin_password FROM db_servers WHERE name = 'postgres-pool-1';"

# Get admin password for pool-2
docker exec saasodoo_postgres.1.xxx psql -U instance_service -d instance -c \
  "SELECT admin_password FROM db_servers WHERE name = 'postgres-pool-2';"
```

### Step 2: Connect to Pools Using Swarm DNS

```bash
# Connect to pool-1 (via Swarm DNS from platform postgres container)
docker exec -e PGPASSWORD="<pool1_admin_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-1 -U postgres -c "SELECT current_database();"

# Connect to pool-2 (via Swarm DNS from platform postgres container)
docker exec -e PGPASSWORD="<pool2_admin_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-2 -U postgres -c "SELECT current_database();"
```

**Key point**: The `-h postgres-pool-1` uses the **service name**, which Swarm DNS resolves to the actual container IP automatically.

### Useful Queries for Migration Testing

#### Check Active Connections to a Database

```bash
# Check which pool has connections to the migrated database
docker exec -e PGPASSWORD="<pool_admin_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-1 -U postgres -c \
  "SELECT count(*) as connections, string_agg(state, ', ') as states
   FROM pg_stat_activity
   WHERE datname = 'odoo_xxx_yyy';"
```

#### Verify Database Exists on Target Pool

```bash
# Check if database exists on pool-1 (target)
docker exec -e PGPASSWORD="<pool1_admin_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-1 -U postgres -c "\l odoo_xxx_yyy"
```

#### Check Data Integrity After Migration

```bash
# Count records to verify data migrated correctly
docker exec -e PGPASSWORD="<db_user_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-1 -U <db_user> -d odoo_xxx_yyy -c \
  "SELECT
    (SELECT count(*) FROM res_users) as users,
    (SELECT count(*) FROM res_partner) as partners;"
```

#### Verify Database User Exists on Target Pool

```bash
# Check if user exists on pool-1 before restore
docker exec -e PGPASSWORD="<pool1_admin_password>" \
  saasodoo_postgres.1.xxx \
  psql -h postgres-pool-1 -U postgres -c "\du <db_user_name>"
```

### Why This Approach Works

1. **No need to find actual container names** - use service names
2. **Works across nodes** - Swarm DNS routes correctly
3. **Uses existing network** - platform postgres is already on `saasodoo-network`
4. **No additional setup** - just use `-h <service-name>` flag

### Alternative: Direct Container Access (Not Recommended)

If you really need to find the actual container:

```bash
# Find pool-2 container ID
POOL2_ID=$(docker inspect $(docker service ps postgres-pool-2 -q) \
  --format '{{.Status.ContainerStatus.ContainerID}}')

# But you still can't exec into it if it's on a different node!
docker exec $POOL2_ID psql -U postgres ...  # Fails if on different node
```

**Use the Swarm DNS approach instead** - it's node-agnostic and always works.
