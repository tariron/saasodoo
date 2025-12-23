# Storage and Migration Discussion Summary

**Date:** 2025-12-19
**Context:** Kubernetes migration planning, storage configuration, and code refactoring scope

---

## Table of Contents

1. [Migration Context](#migration-context)
2. [Storage Infrastructure Decisions](#storage-infrastructure-decisions)
3. [Partition Creation](#partition-creation)
4. [Ceph Integration Strategy](#ceph-integration-strategy)
5. [Code Refactoring Scope](#code-refactoring-scope)
6. [Backup Architecture](#backup-architecture)
7. [Next Steps](#next-steps)

---

## Migration Context

### Initial Question
- Reviewed infrastructure restructure alignment with Kubernetes migration plan
- Confirmed intent: **Kubernetes-only migration** (no parallel Docker Swarm)
- Target: RKE2 Kubernetes with Rook-Ceph storage

### Key Clarification
**User requirement:** "at the end i just want kubernetes only no swarm as i will be moving to kubernetes"

**Decision:** Complete migration to Kubernetes, not maintaining parallel systems

---

## Storage Infrastructure Decisions

### Current Cluster Setup
- **3 Contabo VPS nodes:**
  - Node 1: vmi2887101 (10.0.0.1)
  - Node 2: vmi2887102 (10.0.0.2) - Manager
  - Node 3: vmi2887103 (10.0.0.3)

### Contabo Storage Extension Investigation

**Question:** Does Contabo provide `/dev/sdb` devices for Rook-Ceph cluster mode?

**Research Findings:**
- Contabo **does NOT** provide separate attachable block volumes like AWS EBS
- Instead, they offer "Storage Extension" that **increases existing disk size**
- When ordered, `/dev/sda` grows from 150GB → 300GB (not a new `/dev/sdb`)

**Actual Result:**
All 3 nodes now have:
- Disk: `/dev/sda` = 300GB
- Partition: `/dev/sda1` = 149GB (root filesystem)
- **Unused space: ~151GB** (unpartitioned)

### Storage Options Comparison

| Provider | Separate /dev/sdb? | How it Works | Pricing |
|----------|-------------------|--------------|---------|
| **Contabo VPS** | ❌ No | Extends existing /dev/sda disk | ~€1-5/month per extension |
| **OVHcloud** | ✅ Yes | Block Storage volumes appear as /dev/sdb | $0.04-0.08/GB/month |
| **OVHcloud NVMe** | ✅ Yes | Beta (free until Apr 2025) | Free (beta) |

**Decision:** Use Contabo's extended disk space by creating `/dev/sda2` partitions

---

## Partition Creation

### What We Created

**Completed:** Created `/dev/sda2` raw partitions on all 3 nodes

#### Before
```
sda      300G disk
├─sda1   149G part ext4  (root filesystem)
├─sda14    4M part       (BIOS boot)
├─sda15  106M part vfat  (UEFI)
└─sda16  913M part ext4  (boot)
         151G UNUSED
```

#### After
```
sda      300G disk
├─sda1   149G part ext4  (root filesystem)
├─sda2   150G part       (RAW - for Ceph OSD)
├─sda14    4M part
├─sda15  106M part vfat
└─sda16  913M part ext4
```

### Partition Creation Process

**Commands executed on all 3 nodes:**
```bash
# Fix GPT to recognize full disk size
echo 'Fix' | parted /dev/sda ---pretend-input-tty print

# Create partition from free space
parted /dev/sda mkpart primary 161GB 100%
```

**Result:**
- Node 1 (10.0.0.1): `/dev/sda2` 150GB ✅
- Node 2 (10.0.0.2): `/dev/sda2` 150GB ✅
- Node 3 (10.0.0.3): `/dev/sda2` 150GB ✅

**Status:** Unformatted (no filesystem) - perfect for Ceph OSDs

### Storage Capacity Calculation

**Hypothetical Example (10 OSDs × 150GB):**
```
Raw capacity:   10 OSDs × 150GB = 1,500GB
Replication:    3x (data stored on 3 different OSDs)
Usable:         1,500GB ÷ 3 = 500GB
With overhead:  ~450-475GB realistic
```

**Actual Current Setup (3 nodes × 150GB):**
```
Raw capacity:   3 OSDs × 150GB = 450GB
Replication:    3x
Usable:         450GB ÷ 3 = 150GB
With overhead:  ~135-140GB realistic
```

**Comparison to existing:**
- Current Ceph (directory-backed): 86GB available
- New Ceph (with /dev/sda2): ~135-140GB usable
- **Improvement:** +58% more usable space

---

## Ceph Integration Strategy

### Existing Ceph Scripts Analysis

**Scripts found:**
- `infrastructure/storage/ceph/ceph-worker-setup.sh` (248 lines)
- `infrastructure/storage/ceph/ceph-cluster-manager.sh` (334 lines)
- `infrastructure/storage/ceph/ceph-operations.sh` (584 lines)

**Current approach (directory-backed OSDs):**
```bash
# ceph-worker-setup.sh creates loop devices
truncate -s 33G /var/lib/ceph/osd/osd-disk.img
LOOP_DEV=$(losetup -f)
losetup "$LOOP_DEV" /var/lib/ceph/osd/osd-disk.img
```

**What the scripts do beyond loop device creation:**
1. **Install dependencies:** python3, lvm2, podman, chrony
2. **Configure SSH:** Enable root login, prepare for manager's key
3. **Enable time sync:** Critical for Ceph cluster health
4. **Verify network:** Test connectivity to manager node
5. **Create OSD storage:** Loop device (needs modification for /dev/sda2)

### Script Modifications Needed

**Key insight:** Scripts already use `method: raw` in OSD specs, which supports:
- Loop devices (`/dev/loop0`) ← current
- **Raw partitions (`/dev/sda2`)** ← what we need ✅
- Raw disks (`/dev/sdb`) ← ideal future state

**Required changes:**
1. **ceph-worker-setup.sh:** Detect `/dev/sda2` instead of creating loop device
2. **ceph-operations.sh:** Look for `/dev/sda2` instead of loop devices in OSD detection

**OSD spec format (already compatible):**
```yaml
service_type: osd
spec:
  data_devices:
    paths:
      - /dev/sda2  # ← Just use partition path
  method: raw      # ← Already correct!
```

### Rook-Ceph Operator Modes

#### Cluster Mode (Creates New Ceph in Kubernetes)
```yaml
apiVersion: ceph.rook.io/v1
kind: CephCluster
spec:
  storage:
    useAllDevices: false
    devices:
    - name: "/dev/sda2"  # Uses raw partition
```

**What it does:**
1. Scans all nodes for `/dev/sda2`
2. Checks: Is it a block device? Empty? Matches filter?
3. Creates OSD pod on each node with `/dev/sda2`
4. Deploys monitors, managers, MDS automatically
5. Manages entire Ceph lifecycle

**Physical storage:** Data stored on `/dev/sda2` partitions (450GB raw, ~150GB usable with 3x replication)

#### External Mode (Connects to Existing Ceph)
```yaml
apiVersion: ceph.rook.io/v1
kind: CephCluster
spec:
  external:
    enable: true
  mon:
    endpoints:
    - 10.0.0.1:6789
    - 10.0.0.2:6789
    - 10.0.0.3:6789
```

**What it does:**
- Deploys only CSI drivers in Kubernetes
- Connects to existing Ceph monitors
- Pods use PVCs → CSI driver → existing CephFS

### Recommendation: External Mode First

**Reasoning:**
1. Existing Ceph cluster already works (86GB available)
2. No data migration needed
3. `/mnt/cephfs` remains accessible
4. Less risk during initial Kubernetes migration
5. Can migrate to cluster mode later with `/dev/sda2`

**Migration path:**
- **Phase 1:** Use external mode for K8s migration (low risk)
- **Phase 2:** Gradually refactor code for Kubernetes-native storage
- **Phase 3:** Migrate to cluster mode with `/dev/sda2` (better performance)

---

## Code Refactoring Scope

### Files Using `/mnt/cephfs` Directly

**Analysis:**
- 6 files total
- 12 occurrences of `/mnt/cephfs`
- ~2,554 lines across affected files

**Breakdown:**
```
instance-service/app/tasks/provisioning.py  (740 lines)  - 2 occurrences
instance-service/app/tasks/maintenance.py   (1,420 lines) - 4 occurrences
instance-service/app/tasks/migration.py     (394 lines)  - 2 occurrences
instance-service/app/routes/instances.py                  - 1 occurrence
database-service/app/tasks/provisioning.py                - 2 occurrences
database-service/app/main.py                              - 1 occurrence
```

### Current Code Patterns

#### Instance Provisioning
```python
# Create CephFS directory with quota
cephfs_path = f"/mnt/cephfs/odoo_instances/{volume_name}"
os.makedirs(cephfs_path)
setfattr(cephfs_path, "ceph.quota.max_bytes", storage_limit)

# Mount in Docker container
Mount(source=cephfs_path, target='/bitnami/odoo', type='bind')
```

#### Backups
```python
BACKUP_BASE_PATH = "/mnt/cephfs/odoo_backups"
backup_file = f"{BACKUP_BASE_PATH}/active/{customer_id}/{backup_name}.tar.gz"
# Create tar.gz backup
# List backups: os.listdir(f"{BACKUP_BASE_PATH}/active/{customer_id}")
# Restore: extract from backup_file
```

#### Database Migration
```python
cephfs_path = f"/mnt/cephfs/odoo_instances/odoo_data_{db}_{id}"
odoo_conf_path = f"{cephfs_path}/conf/odoo.conf"
# Read/write odoo.conf files
```

### Kubernetes Refactoring Options

#### Option 1: External Mode + hostPath (Minimal Changes)
**Approach:** Mount existing `/mnt/cephfs` into pods
```yaml
volumes:
- name: cephfs
  hostPath:
    path: /mnt/cephfs
    type: Directory
```

**Code changes:** Zero ✅
**Time:** 1-2 days (deployment config only)
**Pros:** Immediate migration, no code risk
**Cons:** Not Kubernetes-native, hostPath is discouraged

#### Option 2: Hybrid Approach (Recommended)
**Phase 1:** Use external mode or hostPath for initial migration
**Phase 2:** Refactor backups only (easiest component)
**Phase 3:** Refactor instance storage over time

**Estimated effort:**
- Backup refactoring: 1-2 days
- Instance storage refactoring: 3-5 days
- Container creation (Docker SDK → K8s API): 5-7 days
- Testing and debugging: 2-3 days
- **Total: 2-3 weeks** spread over multiple sprints

#### Option 3: Full Refactor (Kubernetes-Native)
**Changes required:**

**Instance Provisioning:**
```python
# OLD: Create directory + quota
os.makedirs(cephfs_path)
setfattr(cephfs_path, "ceph.quota.max_bytes", storage_limit)

# NEW: Create PVC via Kubernetes API
from kubernetes import client, config
k8s = client.CoreV1Api()
pvc = client.V1PersistentVolumeClaim(
    metadata=client.V1ObjectMeta(name=volume_name),
    spec=client.V1PersistentVolumeClaimSpec(
        access_modes=["ReadWriteMany"],
        storage_class_name="cephfs",
        resources=client.V1ResourceRequirements(
            requests={"storage": storage_limit}
        )
    )
)
k8s.create_namespaced_persistent_volume_claim("saasodoo", pvc)
```

**Lines to change:** ~500-700 across all files
**Time:** 2-3 weeks full-time
**Risk:** High (architectural change)

---

## Backup Architecture

### Critical Requirements (User Clarification)

**Key point:** Backups need persistent, shared storage for ALL instances

**NOT this:** ❌ Separate backup PVC per instance
```yaml
odoo-instance-123-backup  # NO!
odoo-instance-456-backup  # NO!
```

**YES this:** ✅ Single shared backup storage
```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: odoo-backups-storage  # ONE PVC for all backups
spec:
  accessModes:
  - ReadWriteMany  # Shared across all instance-service pods
  storageClassName: cephfs  # Backed by Rook-Ceph → Ceph cluster
  resources:
    requests:
      storage: 500Gi
```

### Directory Structure (Same as Current)
```
/mnt/cephfs/odoo_backups/  (or /var/backups in K8s)
├── active/
│   ├── customer-001/
│   │   ├── backup-2025-01-15.tar.gz
│   │   └── backup-2025-01-20.tar.gz
│   ├── customer-002/
│   │   └── backup-2025-01-18.tar.gz
│   └── customer-003/
│       └── backup-2025-01-19.tar.gz
└── staging/
```

### Kubernetes Deployment with Backup Access

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: instance-service
spec:
  template:
    spec:
      volumes:
      - name: ceph-backups
        persistentVolumeClaim:
          claimName: odoo-backups-storage

      containers:
      - name: instance-service
        volumeMounts:
        - name: ceph-backups
          mountPath: /mnt/cephfs/odoo_backups  # Can keep same path!
```

### Code Changes for Backups

**Minimal approach:**
```python
# Option 1: No change (mount PVC at same path)
BACKUP_BASE_PATH = "/mnt/cephfs/odoo_backups"

# Option 2: New path (if desired)
BACKUP_BASE_PATH = "/var/backups"

# Everything else stays identical:
backup_file = f"{BACKUP_BASE_PATH}/active/{customer_id}/{backup_name}.tar.gz"
os.makedirs(os.path.dirname(backup_file), exist_ok=True)
# Create, list, restore - all work exactly the same
```

**Effort:** 1 day (create PVC, update deployment, optionally change one constant)

### Storage Flow Confirmation

```
PVC Request (K8s)
      ↓
Rook-Ceph CSI Driver
      ↓
Ceph Cluster (creates CephFS subvolume)
      ↓
Physical Storage (/dev/sda2 partitions)
```

**Confirmed:** PVCs with `storageClassName: cephfs` are backed by Ceph storage ✅

---

## Cross-Service Communication

### Question: Will existing HTTP service-to-service calls work in Kubernetes?

**Answer:** Yes, with no changes needed ✅

**Current (Docker Swarm):**
```python
# Service-to-service HTTP calls
response = requests.post(
    "http://instance-service:8003/api/instance/provision",
    json={"customer_id": customer_id, ...}
)
```

**Kubernetes (ClusterIP Services):**
```python
# Exact same code works!
response = requests.post(
    "http://instance-service:8003/api/instance/provision",
    json={"customer_id": customer_id, ...}
)
```

**Why it works:**
- Kubernetes ClusterIP Services provide same DNS resolution
- Service names stay the same (instance-service, billing-service, etc.)
- Ports stay the same (8001, 8003, 8004, etc.)
- Within same namespace, short names work
- No code changes needed

### Services That Need Code Changes

Only services that **create infrastructure** need refactoring:

1. **instance-service:** Creates Odoo containers
   - Current: Uses Docker SDK (`docker.from_env()`)
   - New: Uses Kubernetes API (`client.AppsV1Api()`)
   - Creates Deployments instead of containers

2. **database-service:** Creates PostgreSQL instances
   - Current: Uses Docker SDK to create Postgres containers
   - New: Uses Kubernetes API to create StatefulSets
   - Creates PVCs for database storage

**Services that DON'T need changes:**
- user-service ✅
- billing-service ✅
- notification-service ✅
- frontend-service ✅

---

## Next Steps

### Immediate Actions

1. **✅ COMPLETED:** Created `/dev/sda2` partitions on all 3 nodes (150GB each)

2. **Decision Point:** Choose Rook-Ceph mode
   - **Option A (Recommended):** External mode → connect to existing Ceph
   - **Option B:** Cluster mode → use new `/dev/sda2` partitions

3. **If choosing cluster mode:**
   - Modify `ceph-worker-setup.sh` to detect `/dev/sda2`
   - Modify `ceph-operations.sh` OSD detection logic
   - Test OSD creation with raw partitions

### Kubernetes Migration Path

#### Week 1-2: RKE2 Cluster Setup
- Install RKE2 on all 3 nodes
- Configure Cilium CNI
- Set up MetalLB for LoadBalancer services
- Deploy Traefik ingress controller

#### Week 3-4: Storage Configuration
**If External Mode:**
- Deploy Rook-Ceph operator
- Configure external cluster connection
- Create StorageClass for CephFS
- Test PVC creation and mounting

**If Cluster Mode:**
- Deploy Rook-Ceph operator
- Configure CephCluster with `/dev/sda2` devices
- Wait for OSD deployment (~30-60 minutes)
- Create CephFS filesystem
- Create StorageClass
- Test PVC creation

#### Week 5-6: Database Migration
- Deploy PostgreSQL StatefulSets
- Migrate platform databases (auth, billing, instance, communication)
- Test database connectivity from pods

#### Week 7-8: Service Deployment
**Phase 1: Services without code changes**
- Deploy user-service
- Deploy billing-service
- Deploy notification-service
- Deploy frontend-service
- Test service-to-service communication

**Phase 2: Services needing refactoring**
- Refactor instance-service (Docker SDK → K8s API)
- Refactor database-service
- Test instance provisioning

#### Week 9-10: Testing and Cutover
- End-to-end testing
- Load testing
- Backup/restore testing
- Documentation updates
- Gradual traffic cutover
- Monitor and stabilize

### Code Refactoring Timeline

**Parallel to infrastructure work:**

**Sprint 1-2 (2 weeks):**
- Set up Kubernetes client libraries
- Create k8s_client.py wrapper
- Refactor backup storage (minimal changes)

**Sprint 3-4 (2 weeks):**
- Refactor instance provisioning logic
- Replace Docker container creation with K8s Deployment creation
- Test with single instance

**Sprint 5-6 (2 weeks):**
- Refactor database-service provisioning
- Update file operation methods
- Complete end-to-end testing

**Sprint 7 (1 week):**
- Bug fixes and edge cases
- Performance optimization
- Documentation

---

## Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Migration approach** | Kubernetes-only (no parallel Swarm) | User requirement for clean migration |
| **Storage backend** | Rook-Ceph | Native K8s integration, existing Ceph expertise |
| **Physical storage** | `/dev/sda2` partitions (150GB × 3) | Contabo doesn't provide separate block devices |
| **Initial Rook mode** | External mode (recommended) | Lower risk, gradual refactoring |
| **Backup storage** | Single shared PVC (500GB) | All backups in one place, organized by customer_id |
| **Cross-service communication** | Keep HTTP/REST (no changes) | Works identically in K8s with ClusterIP services |
| **Code refactoring** | Phased approach (2-3 weeks) | Spread risk, parallel to infrastructure work |

---

## Storage Capacity Summary

### Current State
```
Existing Ceph (directory-backed):
- 99GB raw (3 OSDs)
- 86GB available
- 3.4GB used
```

### After Migration (with /dev/sda2)
```
New Ceph (partition-backed):
- 450GB raw (3 × 150GB OSDs)
- ~135-140GB usable (3x replication)
- ~58% increase in capacity
```

### Future Scaling Options
1. Add more Contabo storage extensions (larger `/dev/sda` → create more partitions)
2. Add more nodes to cluster
3. Migrate to OVHcloud (better block storage options, native `/dev/sdb` devices)

---

## Risk Mitigation

### High-Risk Areas

1. **Instance-service refactoring**
   - Risk: Breaking instance provisioning
   - Mitigation: Thorough testing, gradual rollout, keep Swarm running until stable

2. **Data migration**
   - Risk: Data loss during Ceph cluster transition
   - Mitigation: Use external mode first, backup everything, test restores

3. **Service downtime**
   - Risk: Extended downtime during cutover
   - Mitigation: Parallel environments, gradual traffic shift, rollback plan

### Low-Risk Areas

1. **Cross-service communication** ✅ Works unchanged
2. **Backup storage** ✅ Minimal code changes
3. **User/billing/notification services** ✅ No refactoring needed

---

## References

- Kubernetes Migration Plan: `docs/Plans/KUBERNETES/KUBERNETES_MIGRATION_PLAN_v3_RKE2.md`
- Infrastructure Restructure: `docs/Plans/INFRASTRUCTURE_RESTRUCTURE.md`
- Ceph Scripts: `infrastructure/storage/ceph/`
- Rook-Ceph Documentation: https://rook.io/docs/rook/latest/
- CephFS CSI Driver: https://github.com/ceph/ceph-csi

---

**Document Status:** Draft - Pending final decisions on Rook-Ceph mode and migration timeline
**Last Updated:** 2025-12-19
**Next Review:** Before Week 1 of Kubernetes migration
