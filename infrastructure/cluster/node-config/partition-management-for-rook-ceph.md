# Partition Management for Rook-Ceph

Guide for creating raw partitions for Rook-Ceph OSD storage on Contabo VPS.

**CRITICAL:** New partitions must remain **unformatted** (no filesystem) for Rook-Ceph.

## Prerequisites

- Access to Contabo Control Panel
- VNC access or SSH to rescue system
- Backup of important data

## Boot into Rescue Mode (Contabo)

1. Log into Contabo Customer Control Panel
2. Go to your VPS → **Manage** → **Rescue System**
3. Boot into rescue mode
4. Connect via VNC or SSH

---

## Scenario 1: Split Existing Partition (Shrink Root to Create sda2)

Use this when you need to carve out space from an existing root partition.

### Example: 300GB disk → 100GB root + 200GB for Ceph

```bash
# 1. Check current layout
fdisk -l /dev/sda
lsblk

# 2. Run filesystem check (REQUIRED before resize)
e2fsck -f /dev/sda1

# 3. Shrink filesystem to MINIMUM size (safest approach)
#    This avoids unit mismatch issues between resize2fs and parted
resize2fs -M /dev/sda1

# 4. Resize partition to desired size
#    IMPORTANT: Use GiB (not GB) to match resize2fs binary units
#    Or use a safe buffer (107GB > 100GiB)
parted /dev/sda resizepart 1 107GB

# 5. Create new RAW partition with remaining space (NO FILESYSTEM)
parted /dev/sda mkpart primary 107GB 100%

# 6. Expand filesystem back to fill the resized partition
resize2fs /dev/sda1

# 7. Verify layout
fdisk -l /dev/sda
lsblk -f    # sda2 should show NO fstype
```

### Unit Reference (CRITICAL)
| Tool | Unit | Meaning |
|------|------|---------|
| resize2fs | G | GiB (binary): 1G = 1024^3 = 1.074 GB |
| parted | GB | GB (decimal): 1GB = 1000^3 bytes |
| parted | GiB | GiB (binary): 1GiB = 1024^3 bytes |

**Always use `GiB` in parted when working with resize2fs, or shrink to minimum first.**

---

## Scenario 2: Add Partition from Increased Disk Space

Use this when you've upgraded your VPS and have additional unallocated space.

### Example: Disk expanded from 300GB to 500GB, create sda2 with new 200GB

```bash
# 1. Check current layout and see unallocated space
fdisk -l /dev/sda
parted /dev/sda print free

# 2. Create new RAW partition in unallocated space (NO FILESYSTEM)
#    Find where current partitions end and start from there
parted /dev/sda mkpart primary <START> 100%

# Example if sda1 ends at 300GB:
parted /dev/sda mkpart primary 300GB 100%

# 3. Verify - sda2 should have NO filesystem
fdisk -l /dev/sda
lsblk -f
```

### Alternative: Using fdisk

```bash
# 1. Start fdisk
fdisk /dev/sda

# 2. Inside fdisk:
n           # New partition
p           # Primary
2           # Partition number 2
<Enter>     # Default start (first available sector)
<Enter>     # Default end (use all remaining space)
w           # Write changes and exit

# 3. Verify
fdisk -l /dev/sda
lsblk -f    # sda2 should show NO fstype
```

---

## Scenario 3: Merge Partitions Back (Remove sda2, Expand Root)

Use this to reclaim Ceph partition space back to root.

**WARNING:** All data on sda2 will be lost. Remove from Ceph cluster first!

```bash
# 1. Ensure sda2 is not in use by Ceph
#    On the k8s cluster: remove OSD from Ceph first

# 2. Check current layout
fdisk -l /dev/sda

# 3. Delete the second partition
parted /dev/sda rm 2

# 4. Expand root partition to use all space
parted /dev/sda resizepart 1 100%

# 5. Expand filesystem to fill partition
resize2fs /dev/sda1

# 6. Verify
fdisk -l /dev/sda
df -h /
```

---

## Verification Commands

After any partition operation, verify the setup:

```bash
# Check partition table
fdisk -l /dev/sda

# Check filesystems (Ceph partition should show blank FSTYPE)
lsblk -f

# Expected output for Ceph-ready partition:
# NAME    FSTYPE LABEL           MOUNTPOINTS
# sda1    ext4   cloudimg-rootfs /
# sda2                                        <-- NO filesystem = ready for Ceph
```

---

## Troubleshooting

### Boot failure after resize

**Cause:** Filesystem larger than partition (unit mismatch)

**Fix:**
```bash
# In rescue mode:
# 1. Delete the new partition
parted /dev/sda rm 2

# 2. Expand root partition back
parted /dev/sda resizepart 1 100%

# 3. Fix filesystem
e2fsck -f /dev/sda1

# 4. Retry with correct procedure (use -M flag)
```

### "Overlapping partitions" error

**Cause:** Trying to expand partition into space occupied by another partition

**Fix:** Delete the blocking partition first with `parted /dev/sda rm <number>`

### e2fsck shows errors about blocks outside partition

**Cause:** Filesystem extends beyond partition boundary

**Fix:**
```bash
# 1. Delete extra partitions
parted /dev/sda rm 2

# 2. Expand partition to cover filesystem
parted /dev/sda resizepart 1 100%

# 3. Now run e2fsck
e2fsck -f /dev/sda1
```

---

## Notes for Rook-Ceph

- Partitions for Rook-Ceph must be **raw** (no filesystem)
- Rook will automatically format with BlueStore
- Label partitions for easy identification: `parted /dev/sda name 2 ceph-osd`
- Minimum recommended OSD size: 10GB (100GB+ recommended for production)
