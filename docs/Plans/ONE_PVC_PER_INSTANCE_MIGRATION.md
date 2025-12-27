# Migration Plan: One-PVC-Per-Instance Architecture

## Executive Summary

Migrate from shared PVCs to dedicated PVCs per Odoo instance for proper storage isolation and quota enforcement.

---

## 1. Current State Assessment

### Existing Architecture

```
Shared Storage:
├── odoo-instances-pvc (200Gi RWX)
│   └── /mnt/cephfs/odoo_instances/
│       ├── odoo_data_{instance1}/
│       └── odoo_data_{instance2}/
└── odoo-backups-pvc (100Gi RWX)
    └── /mnt/cephfs/odoo_backups/
```

**Quota Mechanism**: `setfattr ceph.quota.max_bytes` (NOT WORKING)

### Problems

- ❌ `setfattr` doesn't work on CephFS subvolumes (PVCs)
- ❌ No per-instance storage isolation
- ❌ No quota enforcement
- ❌ All instances share 200Gi total

---

## 2. Target Architecture

### Per-Instance Storage

```
Instance 1:
├── odoo-instance-{uuid}-pvc (10Gi RWO)
│   └── /var/lib/odoo/ (mounted in Odoo pod)
│       ├── addons/
│       ├── filestore/
│       └── sessions/

Instance 2:
├── odoo-instance-{uuid}-pvc (25Gi RWO)
│   └── /var/lib/odoo/

Shared:
└── odoo-backups-pvc (100Gi RWX)
    └── /mnt/cephfs/odoo_backups/ (mounted in backup jobs)
```

### Quota Mechanism

- ✅ PVC size = instance quota (Kubernetes-native)
- ✅ Enforced at filesystem level
- ✅ Resizable (PVC expansion)

### Naming Convention

**No database schema changes needed!** We derive everything from existing data:

```python
# PVC Name (deterministic)
pvc_name = f"odoo-instance-{instance_id}"

# PVC Size (from existing storage_limit column)
def convert_storage_to_k8s_format(storage_limit: str) -> str:
    """Convert: "10G" → "10Gi", "512M" → "512Mi" """
    if storage_limit.endswith('G'):
        return storage_limit + 'i'
    elif storage_limit.endswith('M'):
        return storage_limit + 'i'
    return storage_limit
```

---

## 3. Detailed Code Changes

### 3.1 instance-service/app/utils/k8s_client.py

#### New Utility Functions

```python
def get_instance_pvc_name(instance_id: str) -> str:
    """Build deterministic PVC name from instance ID"""
    return f"odoo-instance-{instance_id}"

def convert_storage_to_k8s_format(storage_limit: str) -> str:
    """Convert storage_limit to Kubernetes format

    Examples:
        "10G" → "10Gi"
        "512M" → "512Mi"
        "1T" → "1Ti"
    """
    if storage_limit.endswith('G'):
        return storage_limit + 'i'
    elif storage_limit.endswith('M'):
        return storage_limit + 'i'
    elif storage_limit.endswith('T'):
        return storage_limit + 'i'
    return storage_limit

def parse_size_to_bytes(size_str: str) -> int:
    """Parse Kubernetes size to bytes for comparison

    Examples:
        "10Gi" → 10737418240
        "512Mi" → 536870912
    """
    units = {
        'Ki': 1024,
        'Mi': 1024**2,
        'Gi': 1024**3,
        'Ti': 1024**4,
        'K': 1000,
        'M': 1000**2,
        'G': 1000**3,
        'T': 1000**4,
    }

    for unit, multiplier in units.items():
        if size_str.endswith(unit):
            value = float(size_str[:-len(unit)])
            return int(value * multiplier)

    return int(size_str)  # Assume bytes if no unit
```

#### New PVC Management Methods

```python
def create_instance_pvc(
    instance_id: str,
    storage_size: str,  # e.g., "10Gi"
    storage_class: str = "rook-cephfs",
    namespace: str = "saasodoo"
) -> str:
    """Create PVC for specific instance

    Args:
        instance_id: UUID of the instance
        storage_size: Kubernetes storage format (e.g., "10Gi")
        storage_class: Storage class name
        namespace: Kubernetes namespace

    Returns:
        PVC name

    Raises:
        K8sException: If PVC creation fails
    """
    pvc_name = get_instance_pvc_name(instance_id)

    pvc_manifest = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            namespace=namespace,
            labels={
                "app": "odoo-instance",
                "instance-id": instance_id,
                "managed-by": "saasodoo"
            },
            annotations={
                "saasodoo.io/instance-id": instance_id,
                "saasodoo.io/created-at": datetime.utcnow().isoformat(),
                "saasodoo.io/storage-size": storage_size
            },
            finalizers=["kubernetes.io/pvc-protection"]  # Prevent accidental deletion
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],  # RWO for single-instance use
            storage_class_name=storage_class,
            resources=client.V1ResourceRequirements(
                requests={"storage": storage_size}
            )
        )
    )

    try:
        self.core_v1.create_namespaced_persistent_volume_claim(
            namespace=namespace,
            body=pvc_manifest
        )
        logger.info(f"Created PVC: {pvc_name} with size {storage_size}")

        # Wait for PVC to be Bound (with timeout)
        self._wait_for_pvc_bound(pvc_name, namespace, timeout=120)

        return pvc_name

    except ApiException as e:
        logger.error(f"Failed to create PVC {pvc_name}: {e}")
        raise K8sException(f"PVC creation failed: {e.reason}")

def _wait_for_pvc_bound(self, pvc_name: str, namespace: str, timeout: int = 120):
    """Wait for PVC to reach Bound status"""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace
            )

            if pvc.status.phase == "Bound":
                logger.info(f"PVC {pvc_name} is Bound")
                return

            elif pvc.status.phase == "Lost":
                raise K8sException(f"PVC {pvc_name} is in Lost state")

        except ApiException as e:
            logger.error(f"Error checking PVC status: {e}")

        time.sleep(2)

    raise K8sException(f"PVC {pvc_name} did not reach Bound state within {timeout}s")

def resize_pvc(
    pvc_name: str,
    new_size: str,
    namespace: str = "saasodoo"
):
    """Resize existing PVC (expansion only)

    Note: Requires allowVolumeExpansion: true in StorageClass

    Args:
        pvc_name: Name of the PVC to resize
        new_size: New size in Kubernetes format (e.g., "20Gi")
        namespace: Kubernetes namespace

    Raises:
        ValueError: If new_size is not larger than current size
        K8sException: If resize operation fails
    """
    try:
        # Get current PVC
        pvc = self.core_v1.read_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace
        )

        current_size = pvc.spec.resources.requests["storage"]

        # Validate: new_size > current_size
        current_bytes = parse_size_to_bytes(current_size)
        new_bytes = parse_size_to_bytes(new_size)

        if new_bytes <= current_bytes:
            raise ValueError(
                f"Cannot resize PVC from {current_size} to {new_size}. "
                f"New size must be larger (Kubernetes only supports expansion)."
            )

        # Patch PVC with new size
        pvc.spec.resources.requests["storage"] = new_size

        self.core_v1.patch_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace,
            body=pvc
        )

        logger.info(f"Initiated PVC resize: {pvc_name} from {current_size} to {new_size}")

        # Update annotation
        self.core_v1.patch_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace,
            body={
                "metadata": {
                    "annotations": {
                        "saasodoo.io/last-resized-at": datetime.utcnow().isoformat(),
                        "saasodoo.io/storage-size": new_size
                    }
                }
            }
        )

    except ApiException as e:
        logger.error(f"Failed to resize PVC {pvc_name}: {e}")
        raise K8sException(f"PVC resize failed: {e.reason}")

def delete_pvc(
    pvc_name: str,
    namespace: str = "saasodoo",
    force: bool = False
):
    """Delete instance PVC

    WARNING: This will permanently delete instance data!

    Args:
        pvc_name: Name of the PVC to delete
        namespace: Kubernetes namespace
        force: If True, remove finalizers first (use with caution)
    """
    try:
        if force:
            # Remove finalizers to allow deletion
            pvc = self.core_v1.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace
            )
            pvc.metadata.finalizers = []
            self.core_v1.patch_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=namespace,
                body=pvc
            )

        self.core_v1.delete_namespaced_persistent_volume_claim(
            name=pvc_name,
            namespace=namespace,
            body=client.V1DeleteOptions(
                propagation_policy="Foreground"
            )
        )

        logger.info(f"Deleted PVC: {pvc_name}")

    except ApiException as e:
        if e.status == 404:
            logger.warning(f"PVC {pvc_name} not found (already deleted)")
        else:
            logger.error(f"Failed to delete PVC {pvc_name}: {e}")
            raise K8sException(f"PVC deletion failed: {e.reason}")

def list_instance_pvcs(namespace: str = "saasodoo") -> List[str]:
    """List all instance PVCs

    Returns:
        List of PVC names managed by SaaSOdoo
    """
    try:
        pvcs = self.core_v1.list_namespaced_persistent_volume_claim(
            namespace=namespace,
            label_selector="app=odoo-instance"
        )
        return [pvc.metadata.name for pvc in pvcs.items]

    except ApiException as e:
        logger.error(f"Failed to list PVCs: {e}")
        return []

def get_pvc_usage(pvc_name: str, namespace: str = "saasodoo") -> dict:
    """Get PVC usage statistics

    Note: Requires metrics-server or similar

    Returns:
        dict with 'capacity', 'used', 'available', 'percent_used'
    """
    # This requires custom implementation or metrics-server integration
    # Placeholder for future implementation
    pass
```

#### Update Existing create_odoo_deployment Method

```python
def create_odoo_deployment(
    instance: dict,
    pvc_name: str,  # NEW: Instance-specific PVC name
    namespace: str = "saasodoo"
) -> str:
    """Create Odoo deployment with dedicated PVC

    Args:
        instance: Instance data from database
        pvc_name: Name of the instance PVC to mount
        namespace: Kubernetes namespace
    """
    # ... existing code ...

    # UPDATED: Volume configuration
    volumes = [
        {
            "name": "odoo-data",
            "persistentVolumeClaim": {
                "claimName": pvc_name  # Instance-specific PVC
            }
        }
    ]

    volume_mounts = [
        {
            "name": "odoo-data",
            "mountPath": "/var/lib/odoo"  # Standard Odoo data directory
        }
    ]

    # ... rest of deployment creation ...
```

#### Update create_backup_job Method

```python
def create_backup_job(
    instance_id: str,
    instance_pvc_name: str,  # NEW: Instance PVC to backup
    database_name: str,
    backup_id: str,
    namespace: str = "saasodoo"
) -> bool:
    """Create backup job with instance PVC mounted

    Args:
        instance_id: Instance UUID
        instance_pvc_name: Name of the instance PVC
        database_name: Odoo database name
        backup_id: Unique backup identifier
        namespace: Kubernetes namespace
    """
    job_name = f"backup-{instance_id}-{backup_id}"

    # Mount BOTH instance PVC (source) and backups PVC (destination)
    volumes = [
        {
            "name": "instance-data",
            "persistentVolumeClaim": {
                "claimName": instance_pvc_name  # Instance-specific
            }
        },
        {
            "name": "backups",
            "persistentVolumeClaim": {
                "claimName": "odoo-backups-pvc"  # Shared
            }
        }
    ]

    volume_mounts = [
        {
            "name": "instance-data",
            "mountPath": "/var/lib/odoo",
            "readOnly": True  # Read-only for backup
        },
        {
            "name": "backups",
            "mountPath": "/backups"
        }
    ]

    # Backup command
    command = [
        "/bin/bash",
        "-c",
        f"""
        set -e
        BACKUP_PATH="/backups/{database_name}/{backup_id}"
        mkdir -p "$BACKUP_PATH"

        # Backup filestore
        tar -czf "$BACKUP_PATH/filestore.tar.gz" -C /var/lib/odoo/filestore .

        # Database backup handled separately via pg_dump

        echo "Backup completed: $BACKUP_PATH"
        """
    ]

    # ... create job with volumes and command ...
```

---

### 3.2 instance-service/app/tasks/provisioning.py

#### Remove Broken setfattr Logic

```python
# DELETE THIS ENTIRE FUNCTION
def _create_cephfs_directory_with_quota(path: str, size_limit: str):
    """DEPRECATED - setfattr doesn't work on CephFS PVCs"""
    pass  # Remove completely
```

#### Update provision_instance_task

```python
@celery_app.task(
    bind=True,
    name='instance.provision',
    max_retries=0,
    time_limit=1800,
    soft_time_limit=1500
)
def provision_instance_task(self, instance_id: str):
    """Provision new Odoo instance with dedicated PVC

    Flow:
        1. Create instance PVC
        2. Create Odoo deployment (mounts PVC)
        3. Create Kubernetes service
        4. Wait for pod to be ready
        5. Initialize Odoo database
    """
    logger.info(f"Starting instance provisioning: {instance_id}")

    try:
        # Get instance data
        instance = get_instance_from_db(instance_id)
        storage_limit = instance.get('storage_limit', '10G')

        # Convert to Kubernetes format
        k8s_storage_size = k8s_client.convert_storage_to_k8s_format(storage_limit)
        pvc_name = k8s_client.get_instance_pvc_name(str(instance['id']))

        # Update status
        update_instance_status(instance_id, 'creating', 'Creating storage')

        # STEP 1: Create PVC FIRST (critical - deployment needs this)
        logger.info(f"Creating PVC: {pvc_name} with size {k8s_storage_size}")
        try:
            k8s_client.create_instance_pvc(
                instance_id=str(instance['id']),
                storage_size=k8s_storage_size,
                storage_class="rook-cephfs"
            )
        except K8sException as e:
            logger.error(f"PVC creation failed: {e}")
            update_instance_status(instance_id, 'error', f'Storage allocation failed: {e}')
            raise ProvisioningError(f"Failed to create storage: {e}")

        # STEP 2: Create Odoo Deployment (uses PVC)
        update_instance_status(instance_id, 'creating', 'Creating Odoo deployment')
        deployment_name = k8s_client.create_odoo_deployment(
            instance=instance,
            pvc_name=pvc_name,  # Pass PVC to mount
            namespace="saasodoo"
        )
        logger.info(f"Created deployment: {deployment_name}")

        # STEP 3: Create Kubernetes Service
        update_instance_status(instance_id, 'creating', 'Creating service endpoint')
        service_name = k8s_client.create_odoo_service(
            instance=instance,
            namespace="saasodoo"
        )
        logger.info(f"Created service: {service_name}")

        # STEP 4: Wait for pod to be ready
        update_instance_status(instance_id, 'creating', 'Waiting for pod to start')
        pod_ready = k8s_client.wait_for_pod_ready(
            deployment_name=deployment_name,
            namespace="saasodoo",
            timeout=300
        )

        if not pod_ready:
            raise ProvisioningError("Pod failed to become ready")

        # STEP 5: Initialize Odoo database
        update_instance_status(instance_id, 'creating', 'Initializing database')
        initialize_odoo_database(instance)

        # DONE
        update_instance_status(instance_id, 'running', 'Instance provisioned successfully')
        logger.info(f"Instance {instance_id} provisioned successfully")

        return {
            "instance_id": instance_id,
            "status": "running",
            "pvc_name": pvc_name,
            "deployment": deployment_name,
            "service": service_name
        }

    except Exception as e:
        logger.error(f"Provisioning failed for {instance_id}: {e}", exc_info=True)

        # ROLLBACK: Clean up on failure
        try:
            logger.info(f"Rolling back failed provisioning for {instance_id}")

            # Delete deployment if created
            if 'deployment_name' in locals():
                k8s_client.delete_deployment(deployment_name, "saasodoo")

            # Delete service if created
            if 'service_name' in locals():
                k8s_client.delete_service(service_name, "saasodoo")

            # Delete PVC if created (IMPORTANT: only if provisioning failed)
            if 'pvc_name' in locals():
                k8s_client.delete_pvc(pvc_name, "saasodoo", force=True)

        except Exception as cleanup_error:
            logger.error(f"Rollback failed: {cleanup_error}")

        update_instance_status(instance_id, 'error', str(e))
        raise
```

---

### 3.3 instance-service/app/tasks/maintenance.py

#### Update Backup Paths and Logic

```python
# UPDATED CONSTANTS
BACKUP_BASE_PATH = "/backups"  # Inside backup job container
INSTANCE_DATA_PATH = "/var/lib/odoo"  # Inside backup job container

@celery_app.task(...)
def backup_instance_task(instance_id: str, backup_type: str = "full"):
    """Create backup of instance data

    Creates Kubernetes Job that:
        1. Mounts instance PVC (read-only)
        2. Mounts shared backups PVC (read-write)
        3. Tars up filestore
        4. Dumps database via pg_dump
    """
    logger.info(f"Starting backup for instance {instance_id}")

    try:
        # Get instance data
        instance = get_instance_from_db(instance_id)
        database_name = instance['database_name']

        # Derive PVC name (no database lookup needed!)
        pvc_name = k8s_client.get_instance_pvc_name(str(instance['id']))

        # Generate backup ID
        backup_id = f"{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"

        # Create backup job (mounts instance PVC)
        job_created = k8s_client.create_backup_job(
            instance_id=str(instance['id']),
            instance_pvc_name=pvc_name,  # Mount instance PVC
            database_name=database_name,
            backup_id=backup_id,
            namespace="saasodoo"
        )

        if not job_created:
            raise BackupError("Failed to create backup job")

        # Wait for job completion
        job_completed = k8s_client.wait_for_job_completion(
            job_name=f"backup-{instance_id}-{backup_id}",
            namespace="saasodoo",
            timeout=600
        )

        if not job_completed:
            raise BackupError("Backup job did not complete in time")

        # Record backup in database
        record_backup(
            instance_id=instance_id,
            backup_id=backup_id,
            backup_type=backup_type,
            status="completed"
        )

        logger.info(f"Backup completed for {instance_id}: {backup_id}")
        return {"backup_id": backup_id, "status": "completed"}

    except Exception as e:
        logger.error(f"Backup failed for {instance_id}: {e}")
        raise

@celery_app.task(...)
def restore_instance_task(instance_id: str, backup_id: str):
    """Restore instance from backup

    Creates Kubernetes Job that:
        1. Mounts instance PVC (read-write)
        2. Mounts shared backups PVC (read-only)
        3. Extracts filestore backup
        4. Restores database via psql
    """
    logger.info(f"Starting restore for instance {instance_id} from backup {backup_id}")

    try:
        instance = get_instance_from_db(instance_id)
        database_name = instance['database_name']
        pvc_name = k8s_client.get_instance_pvc_name(str(instance['id']))

        # Stop instance before restore
        update_instance_status(instance_id, 'stopped', 'Restoring from backup')
        k8s_client.scale_deployment(
            deployment_name=f"odoo-{instance_id}",
            replicas=0,
            namespace="saasodoo"
        )

        # Create restore job
        job_created = k8s_client.create_restore_job(
            instance_id=str(instance['id']),
            instance_pvc_name=pvc_name,
            backup_id=backup_id,
            database_name=database_name,
            namespace="saasodoo"
        )

        if not job_created:
            raise RestoreError("Failed to create restore job")

        # Wait for job completion
        job_completed = k8s_client.wait_for_job_completion(
            job_name=f"restore-{instance_id}-{backup_id}",
            namespace="saasodoo",
            timeout=600
        )

        if not job_completed:
            raise RestoreError("Restore job did not complete in time")

        # Restart instance
        k8s_client.scale_deployment(
            deployment_name=f"odoo-{instance_id}",
            replicas=1,
            namespace="saasodoo"
        )
        update_instance_status(instance_id, 'running', 'Restored from backup')

        logger.info(f"Restore completed for {instance_id}")
        return {"status": "completed"}

    except Exception as e:
        logger.error(f"Restore failed for {instance_id}: {e}")
        raise
```

---

### 3.4 instance-service/app/routes/instances.py

#### Add Storage Update Endpoint

```python
@router.patch("/{instance_id}/storage")
async def update_instance_storage(
    instance_id: str,
    new_size: str = Body(..., description="New storage size (e.g., '20Gi')"),
    current_user: dict = Depends(get_current_user)
):
    """Update instance storage quota by resizing PVC

    Note: Only expansion supported (cannot shrink PVC)

    Args:
        instance_id: Instance UUID
        new_size: New storage size in Kubernetes format (e.g., "20Gi", "50Gi")

    Returns:
        dict with resize status

    Raises:
        400: If new_size is invalid or smaller than current
        404: If instance not found
        403: If user doesn't own instance
    """
    # Verify ownership
    instance = get_instance_from_db(instance_id)
    if instance['customer_id'] != current_user['customer_id']:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Get current storage
    current_size_db = instance['storage_limit']  # e.g., "10G"
    current_size_k8s = k8s_client.convert_storage_to_k8s_format(current_size_db)

    # Validate format
    if not re.match(r'^\d+(Mi|Gi|Ti)$', new_size):
        raise HTTPException(
            status_code=400,
            detail="Invalid size format. Use format like '10Gi', '512Mi', '1Ti'"
        )

    # Derive PVC name
    pvc_name = k8s_client.get_instance_pvc_name(instance_id)

    try:
        # Resize PVC (will raise ValueError if shrinking)
        k8s_client.resize_pvc(pvc_name, new_size, namespace="saasodoo")

        # Update database (convert back to our format)
        new_size_db = new_size.replace('i', '')  # "10Gi" → "10G"
        update_instance_storage_limit(instance_id, new_size_db)

        return {
            "message": "Storage resize initiated",
            "instance_id": instance_id,
            "previous_size": current_size_k8s,
            "new_size": new_size,
            "note": "Resize is in progress. May take a few minutes to complete."
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except K8sException as e:
        raise HTTPException(status_code=500, detail=f"Resize failed: {e}")

@router.get("/{instance_id}/storage/usage")
async def get_instance_storage_usage(
    instance_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get storage usage statistics for instance

    Returns:
        dict with capacity, used, available, percent_used
    """
    instance = get_instance_from_db(instance_id)
    if instance['customer_id'] != current_user['customer_id']:
        raise HTTPException(status_code=403, detail="Not authorized")

    pvc_name = k8s_client.get_instance_pvc_name(instance_id)

    # Get usage (requires implementation in k8s_client)
    usage = k8s_client.get_pvc_usage(pvc_name, namespace="saasodoo")

    return usage
```

---

### 3.5 instance-service/app/tasks/operations.py

#### Update Termination Logic

```python
@celery_app.task(...)
def terminate_instance_task(instance_id: str, delete_data: bool = False):
    """Terminate instance and optionally delete data

    Args:
        instance_id: Instance UUID
        delete_data: If True, immediately delete PVC. If False, mark for deletion.

    Flow:
        1. Scale deployment to 0
        2. Delete deployment
        3. Delete service
        4. Handle PVC based on delete_data flag
        5. Update database status
    """
    logger.info(f"Terminating instance {instance_id} (delete_data={delete_data})")

    try:
        instance = get_instance_from_db(instance_id)
        deployment_name = f"odoo-{instance_id}"
        service_name = f"odoo-{instance_id}-svc"
        pvc_name = k8s_client.get_instance_pvc_name(instance_id)

        # STEP 1: Scale down deployment
        update_instance_status(instance_id, 'terminating', 'Stopping instance')
        k8s_client.scale_deployment(
            deployment_name=deployment_name,
            replicas=0,
            namespace="saasodoo"
        )
        time.sleep(5)  # Wait for graceful shutdown

        # STEP 2: Delete deployment
        k8s_client.delete_deployment(deployment_name, namespace="saasodoo")
        logger.info(f"Deleted deployment: {deployment_name}")

        # STEP 3: Delete service
        k8s_client.delete_service(service_name, namespace="saasodoo")
        logger.info(f"Deleted service: {service_name}")

        # STEP 4: Handle PVC
        if delete_data:
            # IMMEDIATE DELETION (use with caution!)
            logger.warning(f"Permanently deleting PVC: {pvc_name}")
            k8s_client.delete_pvc(pvc_name, namespace="saasodoo", force=True)
        else:
            # SOFT DELETE: Mark for deletion after retention period
            logger.info(f"Marking PVC for deletion: {pvc_name}")
            k8s_client.annotate_pvc(pvc_name, namespace="saasodoo", annotations={
                "saasodoo.io/deleted-at": datetime.utcnow().isoformat(),
                "saasodoo.io/retention-days": "30"  # Keep for 30 days
            })
            # Actual deletion happens via cleanup job

        # STEP 5: Update database
        update_instance_status(instance_id, 'terminated', 'Instance terminated')
        logger.info(f"Instance {instance_id} terminated successfully")

        return {
            "instance_id": instance_id,
            "status": "terminated",
            "data_deleted": delete_data
        }

    except Exception as e:
        logger.error(f"Termination failed for {instance_id}: {e}")
        update_instance_status(instance_id, 'error', f'Termination failed: {e}')
        raise
```

---

## 4. Infrastructure Changes

### 4.1 Remove Shared odoo-instances-pvc

```bash
# Delete old shared PVC (after migration)
kubectl delete pvc odoo-instances-pvc -n saasodoo
```

### 4.2 Update instance-service Deployment

**File**: `infrastructure/services/instance-service/01-deployment.yaml`

```yaml
# REMOVE these volumeMounts:
# - name: odoo-instances
#   mountPath: /mnt/cephfs/odoo_instances

# KEEP only:
volumeMounts:
  - name: odoo-backups
    mountPath: /mnt/cephfs/odoo_backups

# REMOVE these volumes:
# - name: odoo-instances
#   persistentVolumeClaim:
#     claimName: odoo-instances-pvc

# KEEP only:
volumes:
  - name: odoo-backups
    persistentVolumeClaim:
      claimName: odoo-backups-pvc
```

### 4.3 Update instance-worker Deployment

**File**: `infrastructure/services/instance-worker/01-deployment.yaml`

Same changes as instance-service - only keep `odoo-backups` mount.

### 4.4 StorageClass Configuration

Verify `rook-cephfs` supports volume expansion:

```bash
kubectl get storageclass rook-cephfs -o yaml
```

Should have:
```yaml
allowVolumeExpansion: true
```

If not, patch it:
```bash
kubectl patch storageclass rook-cephfs -p '{"allowVolumeExpansion": true}'
```

### 4.5 Delete Old Shared PVC Definition

**File**: `infrastructure/services/instance-service/00-pvcs.yaml`

Remove or comment out `odoo-instances-pvc`:

```yaml
# DELETE THIS:
# ---
# apiVersion: v1
# kind: PersistentVolumeClaim
# metadata:
#   name: odoo-instances-pvc
#   namespace: saasodoo
# spec:
#   ...

# KEEP THIS:
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odoo-backups-pvc
  namespace: saasodoo
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 100Gi
  storageClassName: rook-cephfs
```

---

## 5. Cleanup & Maintenance

### 5.1 Orphaned PVC Cleanup Job

Create scheduled job to clean up orphaned PVCs:

**File**: `infrastructure/services/instance-service/cleanup-cronjob.yaml`

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: pvc-cleanup
  namespace: saasodoo
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: instance-service-sa
          restartPolicy: OnFailure
          containers:
          - name: cleanup
            image: registry.62.171.153.219.nip.io/instance-service:latest
            command:
            - python
            - -c
            - |
              from app.utils.k8s_client import K8sClient
              from app.services.database import DatabaseManager
              from datetime import datetime, timedelta
              import logging

              logger = logging.getLogger(__name__)
              k8s = K8sClient()
              db = DatabaseManager()

              # Get all instance PVCs
              all_pvcs = k8s.list_instance_pvcs(namespace="saasodoo")

              # Get active instances from database
              active_instances = db.get_all_active_instance_ids()
              active_pvc_names = {f"odoo-instance-{iid}" for iid in active_instances}

              # Find orphaned PVCs
              orphaned = set(all_pvcs) - active_pvc_names

              # Check deletion annotations
              retention_cutoff = datetime.utcnow() - timedelta(days=30)

              for pvc_name in orphaned:
                  pvc = k8s.get_pvc(pvc_name, namespace="saasodoo")
                  deleted_at_str = pvc.metadata.annotations.get("saasodoo.io/deleted-at")

                  if deleted_at_str:
                      deleted_at = datetime.fromisoformat(deleted_at_str)
                      if deleted_at < retention_cutoff:
                          logger.info(f"Deleting orphaned PVC: {pvc_name}")
                          k8s.delete_pvc(pvc_name, namespace="saasodoo", force=True)
                  else:
                      logger.warning(f"Found orphaned PVC without deletion timestamp: {pvc_name}")
            env:
            - name: DB_HOST
              valueFrom:
                configMapKeyRef:
                  name: instance-service-config
                  key: DB_HOST
            # ... other env vars ...
```

---

## 6. Migration Steps (Execution Order)

### Phase 1: Code Preparation ✅

1. Implement all code changes in `instance-service`
   - Update `k8s_client.py` with PVC methods
   - Update `provisioning.py` task
   - Update `maintenance.py` tasks
   - Update `operations.py` termination
   - Add storage resize endpoint
2. Update infrastructure manifests
   - Remove shared PVC mounts
   - Update StorageClass
3. Build and push new image:
   ```bash
   docker build -t registry.62.171.153.219.nip.io/instance-service:latest \
     -f services/instance-service/Dockerfile .
   docker push registry.62.171.153.219.nip.io/instance-service:latest
   ```
4. Run unit tests

### Phase 2: Infrastructure Update ✅

1. Verify StorageClass allows expansion:
   ```bash
   kubectl patch storageclass rook-cephfs -p '{"allowVolumeExpansion": true}'
   ```
2. Update deployments:
   ```bash
   kubectl apply -f infrastructure/services/instance-service/01-deployment.yaml
   kubectl apply -f infrastructure/services/instance-worker/01-deployment.yaml
   ```
3. Wait for rollout:
   ```bash
   kubectl rollout status deployment/instance-service -n saasodoo
   kubectl rollout status deployment/instance-worker -n saasodoo
   ```
4. Delete old shared PVC (if no data to preserve):
   ```bash
   kubectl delete pvc odoo-instances-pvc -n saasodoo
   ```

### Phase 3: Testing ✅

1. **Create test instance (10Gi)**
   ```bash
   curl -X POST http://api.62.171.153.219.nip.io/instance/instances \
     -H "Authorization: Bearer $TOKEN" \
     -d '{"plan_id": "test-10g"}'
   ```
   - Verify PVC created: `kubectl get pvc -n saasodoo | grep odoo-instance`
   - Verify pod starts: `kubectl get pods -n saasodoo | grep odoo`
   - Verify data written to PVC

2. **Test backup**
   ```bash
   curl -X POST http://api.62.171.153.219.nip.io/instance/instances/{id}/backup
   ```
   - Check backup job: `kubectl get jobs -n saasodoo`
   - Verify backup created in `/backups`

3. **Test restore**
   ```bash
   curl -X POST http://api.62.171.153.219.nip.io/instance/instances/{id}/restore \
     -d '{"backup_id": "..."}'
   ```

4. **Test storage resize**
   ```bash
   curl -X PATCH http://api.62.171.153.219.nip.io/instance/instances/{id}/storage \
     -d '{"new_size": "20Gi"}'
   ```
   - Verify PVC resized: `kubectl describe pvc odoo-instance-{id} -n saasodoo`
   - Verify pod sees new space: `kubectl exec -n saasodoo {pod} -- df -h`

5. **Test instance deletion**
   ```bash
   curl -X DELETE http://api.62.171.153.219.nip.io/instance/instances/{id}
   ```
   - Verify PVC marked for deletion (annotation)
   - Or verify PVC deleted if `delete_data=true`

### Phase 4: Monitoring ✅

1. Monitor PVC creation/deletion:
   ```bash
   kubectl get pvc -n saasodoo -w
   ```
2. Check for orphaned PVCs:
   ```bash
   kubectl get pvc -n saasodoo -l app=odoo-instance
   ```
3. Monitor storage usage (future: implement metrics)

---

## 7. Edge Cases & Error Handling

### 7.1 PVC Creation Failures

**Scenario**: PVC creation fails (CSI error, quota exceeded, etc.)

**Handling**:
```python
try:
    pvc_name = create_instance_pvc(...)
except K8sException as e:
    update_instance_status(instance_id, 'error', f'Storage allocation failed: {e}')
    # Don't create deployment without PVC
    raise ProvisioningError("Storage allocation failed")
```

### 7.2 Orphaned PVCs

**Scenario**: Instance deleted from database but PVC remains

**Solution**: Cleanup CronJob (see section 5.1)

### 7.3 PVC Deletion Protection

**Scenario**: Accidental instance deletion

**Solution**: Finalizers & soft delete with retention period (30 days)

### 7.4 PVC Resize Limitations

**Limitation**: Kubernetes only supports PVC expansion, not shrinking

**Handling**:
```python
def validate_storage_resize(current_size: str, new_size: str):
    if parse_size_to_bytes(new_size) <= parse_size_to_bytes(current_size):
        raise ValueError("Cannot shrink PVC. Only expansion supported.")
```

### 7.5 Storage Quota Exceeded

**Scenario**: Instance reaches PVC limit

**Handling**:
- Kubernetes automatically enforces quota
- Odoo writes will fail when full
- Emit alert to admin
- Provide self-service resize option via API

---

## 8. Rollback Plan

### If Issues Arise:

1. **Revert code deployment**
   ```bash
   kubectl rollout undo deployment/instance-service -n saasodoo
   kubectl rollout undo deployment/instance-worker -n saasodoo
   ```

2. **Recreate shared PVC if needed**
   ```bash
   kubectl apply -f infrastructure/services/instance-service/00-pvcs.yaml
   ```

3. **Remount in deployments** (revert to previous manifests)

---

## 9. Testing Checklist

- [ ] PVC creation (success case)
- [ ] PVC creation (failure - quota exceeded)
- [ ] Odoo deployment with PVC mount
- [ ] Data persistence (write → restart → read)
- [ ] Backup creation
- [ ] Backup restoration
- [ ] PVC resize (10Gi → 20Gi)
- [ ] PVC resize validation (reject shrink)
- [ ] Instance deletion (PVC cleanup)
- [ ] Orphaned PVC detection
- [ ] Concurrent operations handling
- [ ] Storage full scenario
- [ ] Multiple instances (isolation test)

---

## 10. Post-Migration Validation

```bash
# 1. No shared odoo-instances-pvc
kubectl get pvc -n saasodoo | grep odoo-instances
# Should show only per-instance PVCs

# 2. All instances have dedicated PVCs
kubectl get pvc -n saasodoo -l app=odoo-instance

# 3. Backup jobs work
# Trigger backup via API, check job logs

# 4. Storage enforcement
# Fill instance to quota, verify writes fail gracefully

# 5. Check database consistency
# Verify all active instances have corresponding PVCs in Kubernetes
```

---

## 11. Summary

### Benefits
- ✅ True per-instance isolation
- ✅ Native Kubernetes quota enforcement
- ✅ No special permissions needed (no `SYS_ADMIN` for `setfattr`)
- ✅ Scalable architecture
- ✅ Clean lifecycle management
- ✅ No database schema changes needed (use existing `storage_limit` column)

### Complexity
- More PVCs to manage (one per instance)
- Cleanup jobs for orphaned PVCs
- Retention policy for deleted instances

### Trade-offs
- ❌ Cannot shrink PVCs (Kubernetes limitation)
- ✅ But can delete and recreate with smaller size if needed

---

## Ready to Proceed?

Execute phases in order:
1. Code changes
2. Infrastructure update
3. Testing
4. Monitoring

Each phase should be validated before moving to the next.
