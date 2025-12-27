# Complete PVC Migration Plan - All Files

## Overview

**Current**: Shared PVC `/mnt/cephfs/odoo_instances/` with hostPath mounts + broken `setfattr` quotas
**Target**: One PVC per instance with K8s native quota enforcement

---

## Files to Change

1. ✅ `k8s_client.py` - Storage volume methods
2. ✅ `provisioning.py` - Instance creation
3. ✅ `maintenance.py` - Backup/restore
4. ✅ `migration.py` - Database migration
5. ✅ `operations.py` - Instance termination
6. ✅ `routes/instances.py` - Storage info endpoint (optional)
7. ✅ `instance-service/01-deployment.yaml` - Remove shared PVC mount
8. ✅ `instance-worker/01-deployment.yaml` - Remove shared PVC mount
9. ✅ `00-pvcs.yaml` - Delete old shared PVC definition

---

## 1. k8s_client.py

### Add New Methods

```python
def create_instance_pvc(self, pvc_name: str, storage_size: str) -> bool:
    """Create PVC for instance"""
    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            namespace=self.namespace,
            labels={"app": "odoo-instance", "managed-by": "saasodoo"}
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            storage_class_name="rook-cephfs",
            resources=client.V1ResourceRequirements(
                requests={"storage": storage_size}
            )
        )
    )

    self.core_v1.create_namespaced_persistent_volume_claim(
        namespace=self.namespace, body=pvc
    )

    logger.info("Created instance PVC", pvc_name=pvc_name, size=storage_size)
    return True

def delete_pvc(self, pvc_name: str) -> bool:
    """Delete instance PVC"""
    try:
        self.core_v1.delete_namespaced_persistent_volume_claim(
            name=pvc_name, namespace=self.namespace
        )
        logger.info("Deleted PVC", pvc_name=pvc_name)
        return True
    except ApiException as e:
        if e.status == 404:
            logger.warning("PVC not found (already deleted)", pvc_name=pvc_name)
            return True
        raise

def resize_pvc(self, pvc_name: str, new_size: str) -> bool:
    """Resize PVC (expansion only)"""
    pvc = self.core_v1.read_namespaced_persistent_volume_claim(
        name=pvc_name, namespace=self.namespace
    )
    pvc.spec.resources.requests["storage"] = new_size

    self.core_v1.patch_namespaced_persistent_volume_claim(
        name=pvc_name, namespace=self.namespace, body=pvc
    )

    logger.info("Resized PVC", pvc_name=pvc_name, new_size=new_size)
    return True
```

### Update create_odoo_instance Method

**Line 88: Change parameter**
```python
# OLD
def create_odoo_instance(
    self,
    instance_name: str,
    instance_id: str,
    image: str,
    env_vars: Dict[str, str],
    cpu_limit: str = "1",
    memory_limit: str = "2Gi",
    storage_path: str = None,  # ← OLD
    ...

# NEW
def create_odoo_instance(
    self,
    instance_name: str,
    instance_id: str,
    image: str,
    env_vars: Dict[str, str],
    cpu_limit: str = "1",
    memory_limit: str = "2Gi",
    pvc_name: str = None,  # ← NEW
    ...
```

**Line 135-146: Replace hostPath with PVC**
```python
# OLD
volume_mounts = []
volumes = []
if storage_path:
    volume_mounts.append(client.V1VolumeMount(
        name="odoo-data",
        mount_path="/var/lib/odoo"
    ))
    volumes.append(client.V1Volume(
        name="odoo-data",
        host_path=client.V1HostPathVolumeSource(
            path=storage_path,
            type="DirectoryOrCreate"
        )
    ))

# NEW
volume_mounts = []
volumes = []
if pvc_name:
    volume_mounts.append(client.V1VolumeMount(
        name="odoo-data",
        mount_path="/var/lib/odoo"
    ))
    volumes.append(client.V1Volume(
        name="odoo-data",
        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
            claim_name=pvc_name
        )
    ))
```

### Update create_backup_job Method

**Line 605-686: Replace hostPath with PVC for source data**
```python
# OLD
volumes=[
    client.V1Volume(
        name="source-data",
        host_path=client.V1HostPathVolumeSource(
            path=source_path,
            type="Directory"
        )
    ),
    client.V1Volume(
        name="backup-storage",
        host_path=client.V1HostPathVolumeSource(
            path=backup_base_path,
            type="Directory"
        )
    )
]

# NEW - Add instance_pvc_name parameter
def create_backup_job(
    self,
    job_name: str,
    instance_pvc_name: str,  # ← NEW PARAMETER
    backup_file: str,
    backup_base_path: str = "/mnt/cephfs/odoo_backups"
) -> bool:

volumes=[
    client.V1Volume(
        name="source-data",
        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
            claim_name=instance_pvc_name  # ← Use PVC
        )
    ),
    client.V1Volume(
        name="backup-storage",
        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
            claim_name="odoo-backups-pvc"  # ← Shared backups PVC
        )
    )
]
```

**Update volume mounts for backup job**
```python
volume_mounts=[
    client.V1VolumeMount(
        name="source-data",
        mount_path="/data",
        read_only=True
    ),
    client.V1VolumeMount(
        name="backup-storage",
        mount_path="/backup"
    )
]
```

### Update create_restore_job Method

**Line 702-796: Replace hostPath with PVC**
```python
# NEW - Add instance_pvc_name parameter
def create_restore_job(
    self,
    job_name: str,
    instance_pvc_name: str,  # ← NEW PARAMETER
    backup_file: str,
    backup_base_path: str = "/mnt/cephfs/odoo_backups"
) -> bool:

volumes=[
    client.V1Volume(
        name="dest-data",
        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
            claim_name=instance_pvc_name  # ← Use instance PVC
        )
    ),
    client.V1Volume(
        name="backup-storage",
        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
            claim_name="odoo-backups-pvc"  # ← Shared backups PVC
        )
    )
]
```

---

## 2. provisioning.py

### DELETE Function (Line 50-84)
```python
# DELETE THIS ENTIRE FUNCTION
def _create_cephfs_directory_with_quota(path: str, size_limit: str):
    """BROKEN - setfattr doesn't work on PVCs"""
    # ... DELETE ALL CODE ...
```

### Update provision_instance_task (Line 362-395)

**OLD:**
```python
storage_limit = instance.get('storage_limit', '10G')

# Create CephFS directory with quota
cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{db_name}_{instance_id_short}"
_create_cephfs_directory_with_quota(cephfs_path, storage_limit)

# Create K8s instance
result = k8s_client.create_odoo_instance(
    storage_path=cephfs_path,
    ...
)
```

**NEW:**
```python
storage_limit = instance.get('storage_limit', '10G')

# Convert storage to K8s format ("10G" → "10Gi")
k8s_storage_size = storage_limit + 'i' if storage_limit.endswith('G') else storage_limit
pvc_name = f"odoo-instance-{instance_id}"

# Create PVC
logger.info("Creating instance PVC", pvc_name=pvc_name, size=k8s_storage_size)
k8s_client.create_instance_pvc(pvc_name, k8s_storage_size)

# Create K8s instance with PVC
result = k8s_client.create_odoo_instance(
    pvc_name=pvc_name,  # ← Changed from storage_path
    ...
)
```

---

## 3. maintenance.py

### Update Backup Task

**Line ~400 (backup function):**
```python
# OLD
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
source_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

success = k8s_client.create_backup_job(
    job_name=job_name,
    source_path=source_path,  # ← hostPath
    backup_file=backup_filename,
    backup_base_path=BACKUP_BASE_PATH
)

# NEW
instance_id = instance['id'].hex
pvc_name = f"odoo-instance-{instance_id}"

success = k8s_client.create_backup_job(
    job_name=job_name,
    instance_pvc_name=pvc_name,  # ← PVC
    backup_file=backup_filename,
    backup_base_path="/mnt/cephfs/odoo_backups"
)
```

### Update Restore Task

**Line 590-617: DELETE directory creation, use PVC**
```python
# OLD
volume_name = f"odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"

# Get storage limit from instance for CephFS quota
storage_limit = instance.get('storage_limit', '10G')

from app.tasks.provisioning import _create_cephfs_directory_with_quota
_create_cephfs_directory_with_quota(cephfs_path, storage_limit)  # ← DELETE

success = k8s_client.create_restore_job(
    job_name=job_name,
    backup_file=backup_filename,
    dest_path=cephfs_path,  # ← hostPath
    backup_base_path=BACKUP_BASE_PATH
)

# NEW
instance_id = instance['id'].hex
pvc_name = f"odoo-instance-{instance_id}"

# PVC already exists (created during provisioning)
# Just use it directly

success = k8s_client.create_restore_job(
    job_name=job_name,
    instance_pvc_name=pvc_name,  # ← PVC
    backup_file=backup_filename,
    backup_base_path="/mnt/cephfs/odoo_backups"
)
```

---

## 4. migration.py

**Problem**: Lines 206, 321 access CephFS files directly to read/write odoo.conf

**Solution**: Create K8s Job to mount PVC and access config

### Update _create_db_user_on_dedicated_server (Line 197-237)

**OLD:**
```python
# Read existing credentials from odoo.conf
cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
odoo_conf_path = f"{cephfs_path}/conf/odoo.conf"

config = configparser.ConfigParser()
config.read(odoo_conf_path)
```

**NEW - Use kubectl exec or config-reader job:**
```python
# Option 1: Use kubectl exec in pod
deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
k8s_client = KubernetesClient()
pod_name = k8s_client.get_pod_name_for_deployment(deployment_name)

success, output = k8s_client.exec_in_pod(
    pod_name=pod_name,
    command=["cat", "/var/lib/odoo/conf/odoo.conf"]
)

config = configparser.ConfigParser()
config.read_string(output)

# OR Option 2: Create temporary job to read config
# (More complex but works if pod is not running)
```

### Update _update_service_environment (Line 305-372)

**OLD:**
```python
# Update odoo.conf file
cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{instance['database_name']}_{instance['id'].hex[:8]}"
odoo_conf_path = f"{cephfs_path}/conf/odoo.conf"

config = configparser.ConfigParser()
config.read(odoo_conf_path)

config['options']['db_host'] = dedicated['db_host']

with open(odoo_conf_path, 'w') as f:
    config.write(f)
```

**NEW - Use kubectl exec:**
```python
# Use kubectl exec to update odoo.conf inside pod
deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
k8s_client = KubernetesClient()
pod_name = k8s_client.get_pod_name_for_deployment(deployment_name)

# Read current config
success, output = k8s_client.exec_in_pod(
    pod_name=pod_name,
    command=["cat", "/var/lib/odoo/conf/odoo.conf"]
)

# Parse and update
config = configparser.ConfigParser()
config.read_string(output)
config['options']['db_host'] = dedicated['db_host']

# Write back
import io
output_buffer = io.StringIO()
config.write(output_buffer)
new_config_content = output_buffer.getvalue()

# Use kubectl cp or exec to write
k8s_client.exec_in_pod(
    pod_name=pod_name,
    command=["sh", "-c", f"cat > /var/lib/odoo/conf/odoo.conf <<'EOF'\n{new_config_content}\nEOF"]
)
```

---

## 5. operations.py

### Add PVC Deletion on Termination

**Find terminate_instance_task function:**
```python
# OLD
def terminate_instance_task(instance_id: str):
    k8s_client = KubernetesClient()
    instance_name = f"odoo-{instance_id[:8]}"

    # Delete K8s resources
    k8s_client.delete_instance(instance_name)

    # Update database
    update_instance_status(instance_id, 'terminated')

# NEW
def terminate_instance_task(instance_id: str):
    k8s_client = KubernetesClient()
    instance_name = f"odoo-{instance_id[:8]}"
    pvc_name = f"odoo-instance-{instance_id}"

    # Delete K8s resources (deployment, service, ingress)
    k8s_client.delete_instance(instance_name)

    # Delete PVC
    logger.info("Deleting instance PVC", pvc_name=pvc_name)
    k8s_client.delete_pvc(pvc_name)

    # Update database
    update_instance_status(instance_id, 'terminated')
```

---

## 6. routes/instances.py (Optional)

### Add Storage Resize Endpoint

```python
@router.patch("/{instance_id}/storage")
async def update_instance_storage(
    instance_id: str,
    new_size: str = Body(..., description="New size (e.g., '20Gi')"),
    current_user: dict = Depends(get_current_user)
):
    """Resize instance storage (expansion only)"""
    instance = await get_instance_from_db(instance_id)

    # Verify ownership
    if instance['customer_id'] != current_user['customer_id']:
        raise HTTPException(403, "Not authorized")

    # Resize PVC
    pvc_name = f"odoo-instance-{instance_id}"
    k8s_client = KubernetesClient()
    k8s_client.resize_pvc(pvc_name, new_size)

    # Update database
    new_size_db = new_size.replace('i', '')  # "20Gi" → "20G"
    await update_instance_storage_limit(instance_id, new_size_db)

    return {"message": "Storage resize initiated", "new_size": new_size}
```

---

## 7. Infrastructure: instance-service/01-deployment.yaml

**DELETE shared PVC mount:**
```yaml
# OLD - DELETE THIS
volumeMounts:
  - name: odoo-instances
    mountPath: /mnt/cephfs/odoo_instances
  - name: odoo-backups
    mountPath: /mnt/cephfs/odoo_backups

volumes:
  - name: odoo-instances
    persistentVolumeClaim:
      claimName: odoo-instances-pvc
  - name: odoo-backups
    persistentVolumeClaim:
      claimName: odoo-backups-pvc

# NEW - KEEP ONLY
volumeMounts:
  - name: odoo-backups
    mountPath: /mnt/cephfs/odoo_backups

volumes:
  - name: odoo-backups
    persistentVolumeClaim:
      claimName: odoo-backups-pvc
```

---

## 8. Infrastructure: instance-worker/01-deployment.yaml

**Same changes as instance-service** - remove `odoo-instances` mount, keep only `odoo-backups`

---

## 9. Infrastructure: 00-pvcs.yaml

**DELETE old shared PVC:**
```yaml
# DELETE THIS ENTIRE SECTION
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odoo-instances-pvc
  namespace: saasodoo
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 200Gi
  storageClassName: rook-cephfs
```

---

## Deployment Steps

1. **Update code files** (1-6)
2. **Build and push new image:**
   ```bash
   docker build -t registry.62.171.153.219.nip.io/instance-service:latest \
     -f services/instance-service/Dockerfile .
   docker push registry.62.171.153.219.nip.io/instance-service:latest
   ```
3. **Update infrastructure manifests** (7-9)
4. **Apply updated deployments:**
   ```bash
   kubectl apply -f infrastructure/services/instance-service/01-deployment.yaml
   kubectl apply -f infrastructure/services/instance-worker/01-deployment.yaml
   ```
5. **Delete old PVC after rollout:**
   ```bash
   kubectl delete pvc odoo-instances-pvc -n saasodoo
   ```

---

## Testing

1. Create new instance → verify PVC created
2. Check PVC size matches plan
3. Backup instance → verify backup job works with PVC
4. Restore instance → verify restore job works
5. Delete instance → verify PVC deleted
6. Try resizing PVC → verify expansion works

---

## Summary

| File | Lines Changed | What Changes |
|------|--------------|--------------|
| `k8s_client.py` | ~150 lines | Add PVC methods, replace hostPath→PVC |
| `provisioning.py` | ~15 lines | Delete `_create_cephfs_directory_with_quota`, use `create_instance_pvc` |
| `maintenance.py` | ~20 lines | Update backup/restore to use PVC names |
| `migration.py` | ~50 lines | Replace file access with kubectl exec |
| `operations.py` | ~5 lines | Add PVC deletion |
| `routes/instances.py` | ~20 lines | Add resize endpoint (optional) |
| Infrastructure YAMLs | ~20 lines | Remove shared PVC mounts |

**Total**: ~280 lines changed across 9 files

Simple concept: **Replace directory paths with PVC names everywhere**
