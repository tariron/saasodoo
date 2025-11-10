# CephFS Volume Fix for Docker Swarm

## Issue Summary

**Problem**: Odoo instances that moved to different nodes in Docker Swarm are experiencing HTML rendering issues (missing logos, broken static assets) on the login page.

**Root Cause**: The provisioning code creates Docker volumes with `driver='local'` that bind to CephFS. These local volumes are registered in Docker's volume database on a per-node basis, so when a service moves to a different node, Docker creates a new empty volume instead of accessing the existing CephFS data.

**Impact**:
- Instances moved from their original nodes lose access to persistent data
- Static assets (logos, CSS, images) appear broken
- User experience degraded on login pages

## Affected Instances

As of the investigation, these instances moved nodes and are affected:

| Instance ID | Original Node | Current Node | Status |
|------------|---------------|--------------|--------|
| odoo-jjjjjjjj-f4f55815 | vmi2887101 | vmi2887103 | Missing logos |
| odoo-nbbbbb-43b68011 | vmi2887101 | vmi2887103 | Missing logos |
| odoo-onefour-9d5e550b | vmi2887103 | vmi2887101 | Missing logos |
| odoo-onethree-9a4f81ac | vmi2887103 | vmi2887101 | Missing logos |
| odoo-onetwo-b764e991 | vmi2887103 | vmi2887101 | Missing logos |

## Technical Details

### Current Implementation (Problematic)

The issue exists in **THREE locations** across two files.

#### Location 1: Instance Provisioning

**File**: `services/instance-service/app/tasks/provisioning.py`

**Lines 348-370**:
```python
# Get storage limit from instance
storage_limit = instance.get('storage_limit', '10G')
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"

# Create CephFS directory with quota BEFORE Docker volume
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
_create_cephfs_directory_with_quota(cephfs_path, storage_limit)
logger.info("Created CephFS volume with quota", ...)

# ❌ PROBLEM: Creates local volume that only exists on current node
volume = client.volumes.create(
    name=volume_name,
    driver='local',  # ← Node-specific registration
    driver_opts={
        'type': 'none',
        'o': 'bind',
        'device': cephfs_path
    }
)
logger.info("Created Docker volume with CephFS backing", volume_name=volume_name)
```

**Lines 383-388**:
```python
# Create mount for volume
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=volume_name,  # ❌ References local volume
    type='volume'        # ❌ Volume type
)
```

#### Location 2: Instance Restore

**File**: `services/instance-service/app/tasks/maintenance.py`

**Lines 591-620**:
```python
# Remove existing volume if it exists
try:
    existing_volume = client.volumes.get(volume_name)
    existing_volume.remove(force=True)
    logger.info("Existing data volume removed", volume=volume_name)
except docker.errors.NotFound:
    pass

# Get storage limit from instance for CephFS quota
storage_limit = instance.get('storage_limit', '10G')
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

# Import helper function from provisioning
from app.tasks.provisioning import _create_cephfs_directory_with_quota

# Create CephFS directory with quota
_create_cephfs_directory_with_quota(cephfs_path, storage_limit)
logger.info("Created CephFS directory with quota for restore", path=cephfs_path, storage_limit=storage_limit)

# ❌ PROBLEM: Creates local volume that only exists on current node
new_volume = client.volumes.create(
    name=volume_name,
    driver='local',  # ← Node-specific registration
    driver_opts={
        'type': 'none',
        'o': 'bind',
        'device': cephfs_path
    }
)
logger.info("New data volume created with CephFS backing", volume=volume_name)
```

**Lines 1227-1233**:
```python
# Create mount for volume
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=volume_name,  # ❌ References local volume
    type='volume'        # ❌ Volume type
)
```

#### Location 3: Backup Operations

**File**: `services/instance-service/app/tasks/maintenance.py`

**Lines 431-453** - Backup operations reference local volumes:
```python
async def _create_data_volume_backup(instance: Dict[str, Any], backup_name: str) -> tuple[str, int]:
    """Create backup of Odoo data volume"""
    client = docker.from_env()
    backup_file = f"{BACKUP_ACTIVE_PATH}/{backup_name}_data.tar.gz"

    try:
        # Create temporary container to access data volume
        volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"

        # Run tar command in temporary container to backup volume
        logger.info("Starting data volume backup", volume_name=volume_name, backup_file=backup_file)

        try:
            # ❌ PROBLEM: Expects volume to exist locally
            result = client.containers.run(
                image="alpine:latest",
                command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
                volumes={
                    volume_name: {'bind': '/data', 'mode': 'ro'},  # ❌ References local volume
                    BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'rw'}
                },
                remove=True,
                detach=False
            )
```

Similarly for **Lines 623-632** in restore operations:
```python
# Extract backup to new volume
client.containers.run(
    image="alpine:latest",
    command=f"tar -xzf /backup/active/{backup_filename} -C /data",
    volumes={
        volume_name: {'bind': '/data', 'mode': 'rw'},  # ❌ References local volume
        BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'ro'}
    },
    remove=True,
    detach=False
)
```

### Why This Fails in Docker Swarm

1. **Local Volume Registration**: When `client.volumes.create()` is called with `driver='local'`, Docker registers the volume in its **local node database**
2. **Service Migration**: When Docker Swarm moves a service to a different node (due to node failure, rebalancing, or constraints):
   - Swarm looks for a volume named `odoo_data_xxx` on the NEW node
   - The volume doesn't exist in the new node's local database
   - Docker creates a **brand new empty volume** with the same name
3. **Data Loss**: The container starts with an empty volume, losing all persistent data including static assets

### CephFS Mount Verification

```bash
# CephFS is mounted on all nodes
mount | grep ceph
# Output: 10.0.0.2:6789,10.0.0.1:6789,10.0.0.3:6789:/ on /mnt/cephfs type ceph (...)
```

The CephFS filesystem is accessible at `/mnt/cephfs` on **all swarm nodes**, which makes direct bind mounts the correct solution.

## Solution: Direct CephFS Bind Mounts

### Proposed Changes

All changes follow the same pattern: **remove local volume creation** and **use direct CephFS bind mounts**.

#### File 1: `services/instance-service/app/tasks/provisioning.py`

##### Change 1.1: Remove Local Volume Creation (Lines 360-370)

**Remove**:
```python
volume = client.volumes.create(
    name=volume_name,
    driver='local',
    driver_opts={
        'type': 'none',
        'o': 'bind',
        'device': cephfs_path
    }
)
logger.info("Created Docker volume with CephFS backing", volume_name=volume_name)
```

**Result**: Only the CephFS directory is created with quotas. No Docker volume is registered.

##### Change 1.2: Update Mount Configuration (Lines 383-388)

**Before**:
```python
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=volume_name,  # References local volume
    type='volume'
)
```

**After**:
```python
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=cephfs_path,  # ✅ Direct CephFS path
    type='bind'          # ✅ Bind mount type
)
```

##### Change 1.3: Update Cleanup Code (Lines 531-538)

**Remove** from `_cleanup_failed_provisioning()`:
```python
# Remove Docker volume if created
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
try:
    volume = client.volumes.get(volume_name)
    volume.remove()
    logger.info("Volume cleaned up", volume_name=volume_name)
except docker.errors.NotFound:
    pass  # Volume doesn't exist
```

This code is no longer needed since we won't be creating Docker volumes.

---

#### File 2: `services/instance-service/app/tasks/maintenance.py`

##### Change 2.1: Remove Local Volume Creation in Restore (Lines 591-620)

**Remove**:
```python
# Remove existing volume if it exists
try:
    existing_volume = client.volumes.get(volume_name)
    existing_volume.remove(force=True)
    logger.info("Existing data volume removed", volume=volume_name)
except docker.errors.NotFound:
    pass

# Create new volume backed by CephFS
new_volume = client.volumes.create(
    name=volume_name,
    driver='local',
    driver_opts={
        'type': 'none',
        'o': 'bind',
        'device': cephfs_path
    }
)
logger.info("New data volume created with CephFS backing", volume=volume_name)
```

**Keep only**:
```python
# Get storage limit from instance for CephFS quota
storage_limit = instance.get('storage_limit', '10G')
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

# Import helper function from provisioning
from app.tasks.provisioning import _create_cephfs_directory_with_quota

# Create CephFS directory with quota
_create_cephfs_directory_with_quota(cephfs_path, storage_limit)
logger.info("Created CephFS directory with quota for restore", path=cephfs_path, storage_limit=storage_limit)
```

##### Change 2.2: Update Mount in Restore Service Creation (Lines 1227-1233)

**Before**:
```python
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=volume_name,
    type='volume'
)
```

**After**:
```python
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
mount = docker.types.Mount(
    target='/bitnami/odoo',
    source=cephfs_path,  # ✅ Direct CephFS path
    type='bind'          # ✅ Bind mount type
)
```

##### Change 2.3: Update Backup Operations to Use CephFS Paths (Lines 431-453)

**Before**:
```python
# Run tar command in temporary container to backup volume
result = client.containers.run(
    image="alpine:latest",
    command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
    volumes={
        volume_name: {'bind': '/data', 'mode': 'ro'},  # ❌ References local volume
        BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'rw'}
    },
    remove=True,
    detach=False
)
```

**After**:
```python
# Get CephFS path for instance data
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

# Run tar command using direct CephFS path
result = client.containers.run(
    image="alpine:latest",
    command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
    volumes={
        cephfs_path: {'bind': '/data', 'mode': 'ro'},  # ✅ Direct CephFS path
        BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'rw'}
    },
    remove=True,
    detach=False
)
```

Similarly for the size check operation (Lines 456-464):
```python
# Before
volumes={BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'ro'}}

# No change needed - this only accesses backup storage
```

##### Change 2.4: Update Restore Extract Operations (Lines 623-632)

**Before**:
```python
# Extract backup to new volume
client.containers.run(
    image="alpine:latest",
    command=f"tar -xzf /backup/active/{backup_filename} -C /data",
    volumes={
        volume_name: {'bind': '/data', 'mode': 'rw'},  # ❌ References local volume
        BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'ro'}
    },
    remove=True,
    detach=False
)
```

**After**:
```python
# Get CephFS path for instance data
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

# Extract backup to CephFS directory
client.containers.run(
    image="alpine:latest",
    command=f"tar -xzf /backup/active/{backup_filename} -C /data",
    volumes={
        cephfs_path: {'bind': '/data', 'mode': 'rw'},  # ✅ Direct CephFS path
        BACKUP_BASE_PATH: {'bind': '/backup', 'mode': 'ro'}
    },
    remove=True,
    detach=False
)
```

### Why This Works

1. **No Volume Registration**: No local volume is created in Docker's database
2. **Service Definition Storage**: The mount specification is stored in the **service definition**, which is replicated across all manager nodes
3. **Universal Access**: When a service moves to any node, it mounts `/mnt/cephfs/odoo_instances/{volume_name}` directly
4. **Data Persistence**: Since CephFS is mounted on all nodes, the data is accessible from anywhere
5. **Swarm-Native**: This is the standard pattern for using shared storage in Docker Swarm

## Implementation Steps

### Summary of Changes

**Total Files to Modify**: 2
- `services/instance-service/app/tasks/provisioning.py` - 3 changes
- `services/instance-service/app/tasks/maintenance.py` - 4 changes

**Pattern**: Remove all `client.volumes.create()` calls and change all `Mount(type='volume')` to `Mount(type='bind')` with CephFS paths.

### 1. Apply Code Changes

Apply all changes described in the "Proposed Changes" section above.

### 2. Rebuild and Redeploy Services

```bash
# Rebuild instance-service and instance-worker
cd /root/saasodoo
docker compose -f infrastructure/compose/docker-compose.ceph.yml build instance-service instance-worker

# Redeploy to swarm
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

### 3. Fix Existing Affected Instances

For instances already experiencing issues, you have two options:

#### Option A: Recreate Services with Correct Mounts

For each affected instance, update the service to use bind mounts:

```bash
# Get service details
SERVICE_NAME="odoo-jjjjjjjj-f4f55815"
CEPHFS_PATH="/mnt/cephfs/odoo_instances/odoo_data_jjjjjjjj_f4f55815"

# Update service with bind mount
docker service update \
  --mount-rm /bitnami/odoo \
  --mount type=bind,source=${CEPHFS_PATH},target=/bitnami/odoo \
  ${SERVICE_NAME}
```

#### Option B: Use Placement Constraints (Temporary Fix)

Pin each service back to its original node where the volume was created:

```bash
# Example: Pin service back to vmi2887101
docker service update --constraint-add node.hostname==vmi2887101 odoo-jjjjjjjj-f4f55815
```

**Note**: Option A is recommended for a permanent fix. Option B is a quick workaround.

## Testing Plan

### 1. Test New Instance Creation

```bash
# Create a new test instance through the API
curl -X POST http://localhost:8003/instances \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-cephfs-fix",
    "customer_id": "test-user-123",
    ...
  }'

# Verify CephFS directory is created
ls -la /mnt/cephfs/odoo_instances/ | grep test-cephfs-fix

# Verify NO Docker volume was created
docker volume ls | grep test-cephfs-fix
# Should return nothing

# Verify service is running
docker service ps odoo-test-cephfs-fix
```

### 2. Test Service Migration

```bash
# Force service to move to different node
docker service update --constraint-add node.hostname==vmi2887103 odoo-test-cephfs-fix

# Wait for migration
docker service ps odoo-test-cephfs-fix

# Access the instance and verify:
# - Login page loads correctly
# - Logos are visible
# - Static assets load
# - Data persists
```

### 3. Verify Existing Instances

After applying fixes to affected instances:

```bash
# Check each affected instance
for service in odoo-jjjjjjjj-f4f55815 odoo-nbbbbb-43b68011 odoo-onefour-9d5e550b; do
  echo "Testing $service..."
  # Access login page and verify logos appear
  # Check browser console for asset loading errors
done
```

## Rollback Plan

If issues arise after deployment:

```bash
# Revert to previous version
cd /root/saasodoo
git revert <commit-hash>

# Rebuild and redeploy
docker compose -f infrastructure/compose/docker-compose.ceph.yml build instance-service instance-worker
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo

# Services will continue using local volumes until manually migrated
```

## Additional Considerations

### Volume Cleanup

After successful migration, old local volumes can be cleaned up:

```bash
# List orphaned volumes on each node
docker volume ls -qf dangling=true

# Remove unused volumes (be careful!)
docker volume prune -f
```

### Monitoring

Monitor CephFS usage and quotas:

```bash
# Check CephFS usage
df -h /mnt/cephfs

# Check quota for specific instance
getfattr -n ceph.quota.max_bytes /mnt/cephfs/odoo_instances/odoo_data_xxx
```

### Future Provisioning

All new instances created after this fix will automatically:
- Use direct CephFS bind mounts
- Be portable across all swarm nodes
- Maintain data persistence during migrations
- Avoid the local volume issue

## References

- Docker Swarm Volumes: https://docs.docker.com/engine/swarm/services/#volumes-and-bind-mounts
- CephFS Quotas: https://docs.ceph.com/en/latest/cephfs/quota/
- Related Documentation: `docs/DOCKER_SWARM_MIGRATION_PLAN.md`
- Issue Log: `docs/ISSUES_LOG.md`
