# MicroCeph Migration Plan for SaaSodoo

## Overview

This document provides a complete migration plan from local Docker volumes to MicroCeph-backed storage for the SaaSodoo platform. It includes both single-node testing and production 3-node deployment.

**Total Migration Time**:
- Single-node test: 2-3 hours
- Production 3-node: 4-6 hours

---

## Table of Contents

1. [Single-Node Test Setup](#single-node-test-setup)
2. [Production 3-Node Setup](#production-3-node-setup)
3. [Docker Compose Changes](#docker-compose-changes)
4. [Data Migration Steps](#data-migration-steps)
5. [Verification & Testing](#verification--testing)
6. [Rollback Plan](#rollback-plan)

---

## Single-Node Test Setup

### Prerequisites

- Ubuntu 22.04 or 24.04 LTS
- At least 8GB RAM
- 50GB+ free disk space (or dedicated disk)
- Docker and Docker Compose installed

### Step 1: Install MicroCeph on Single Node

```bash
#!/bin/bash
# install-microceph-single.sh
# Single-node MicroCeph installation for testing

set -e

echo "Installing MicroCeph on single node..."

# Install MicroCeph via snap
sudo snap install microceph

# Initialize cluster (single node)
sudo microceph cluster bootstrap

# Check status
sudo microceph status

echo "MicroCeph installed successfully!"
```

### Step 2: Add Storage to MicroCeph

You have two options:

#### Option A: Use a Dedicated Disk (Recommended)

```bash
# List available disks
lsblk

# Add dedicated disk (e.g., /dev/sdb)
# WARNING: This will WIPE the disk!
sudo microceph disk add /dev/sdb
```

#### Option B: Use Loop Device (Testing Only)

```bash
# Create a loop device from a file (for testing without dedicated disk)
sudo mkdir -p /var/snap/microceph/common/data
sudo truncate -s 50G /var/snap/microceph/common/data/osd.img
sudo losetup -f /var/snap/microceph/common/data/osd.img

# Find the loop device created
LOOP_DEVICE=$(losetup -j /var/snap/microceph/common/data/osd.img | cut -d: -f1)
echo "Loop device: $LOOP_DEVICE"

# Add the loop device to MicroCeph
sudo microceph disk add $LOOP_DEVICE
```

### Step 3: Enable CephFS

```bash
# Enable MDS (Metadata Server) for CephFS
sudo microceph enable mds

# Wait a moment for MDS to start
sleep 10

# Enable CephFS filesystem (single node requires special config)
# For single-node testing, we need to allow pool size = 1
sudo ceph osd pool set cephfs.cephfs.meta size 1 --yes-i-really-mean-it
sudo ceph osd pool set cephfs.cephfs.meta min_size 1
sudo ceph osd pool set cephfs.cephfs.data size 1 --yes-i-really-mean-it
sudo ceph osd pool set cephfs.cephfs.data min_size 1

# Verify CephFS is ready
sudo ceph fs status

echo "CephFS enabled for single-node testing!"
```

**Important Note**: Setting `size=1` and `min_size=1` is ONLY for single-node testing. In production with 3 nodes, you'll use `size=3` for replication.

### Step 4: Mount CephFS

```bash
#!/bin/bash
# mount-cephfs-single.sh
# Mount CephFS on single node

set -e

# Create mount point
sudo mkdir -p /mnt/cephfs

# Get the admin key
ADMIN_KEY=$(sudo ceph auth get-key client.admin)

# Create symbolic links for Ceph config (needed for mount command)
sudo ln -sf /var/snap/microceph/current/conf/ceph.conf /etc/ceph/ceph.conf
sudo ln -sf /var/snap/microceph/current/conf/ceph.client.admin.keyring /etc/ceph/ceph.client.admin.keyring

# Mount CephFS
sudo mount -t ceph :/ /mnt/cephfs -o name=admin,secret=$ADMIN_KEY

# Verify mount
df -h /mnt/cephfs

echo "CephFS mounted at /mnt/cephfs"
```

### Step 5: Make Mount Persistent

```bash
# Add to /etc/fstab for automatic mounting on boot
ADMIN_KEY=$(sudo ceph auth get-key client.admin)

# Backup fstab
sudo cp /etc/fstab /etc/fstab.backup.$(date +%Y%m%d_%H%M%S)

# Add mount entry
echo "# MicroCeph CephFS mount" | sudo tee -a /etc/fstab
echo ":/ /mnt/cephfs ceph name=admin,secret=$ADMIN_KEY,noatime,_netdev 0 0" | sudo tee -a /etc/fstab

echo "CephFS mount added to /etc/fstab"
```

### Step 6: Create Volume Directories

```bash
#!/bin/bash
# create-volume-dirs.sh
# Create directories for all SaaSodoo volumes

set -e

VOLUMES=(
    "postgres_data"
    "redis_data"
    "rabbitmq_data"
    "prometheus_data"
    "grafana_data"
    "elasticsearch_data"
    "minio_data"
    "pgadmin_data"
    "odoo_instances"
    "odoo_backups"
    "killbill_db_data"
)

echo "Creating volume directories in CephFS..."

for VOLUME in "${VOLUMES[@]}"; do
    sudo mkdir -p /mnt/cephfs/$VOLUME
    echo "✓ Created /mnt/cephfs/$VOLUME"
done

# Set permissions (Docker needs to write here)
sudo chmod -R 777 /mnt/cephfs/*

echo "All volume directories created!"
```

### Step 7: Verify Single-Node Setup

```bash
#!/bin/bash
# verify-microceph.sh
# Verify MicroCeph is working correctly

set -e

echo "=== MicroCeph Verification ==="

# Check cluster status
echo -e "\n1. Cluster Status:"
sudo microceph status

# Check Ceph health
echo -e "\n2. Ceph Health:"
sudo ceph health

# Check CephFS status
echo -e "\n3. CephFS Status:"
sudo ceph fs status

# Check mount
echo -e "\n4. CephFS Mount:"
df -h /mnt/cephfs

# Test write
echo -e "\n5. Write Test:"
echo "Test data $(date)" | sudo tee /mnt/cephfs/test.txt
cat /mnt/cephfs/test.txt
echo "✓ Write test successful"

# Check directories
echo -e "\n6. Volume Directories:"
ls -la /mnt/cephfs/

echo -e "\n=== Verification Complete ==="
```

---

## Complete Single-Node Test Script

Here's an all-in-one script for single-node testing:

```bash
#!/bin/bash
# single-node-test.sh
# Complete single-node MicroCeph setup and test

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  MicroCeph Single-Node Test Setup     ${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
   exit 1
fi

# 1. Install MicroCeph
echo -e "\n${YELLOW}Step 1: Installing MicroCeph...${NC}"
snap install microceph
microceph cluster bootstrap
echo -e "${GREEN}✓ MicroCeph installed${NC}"

# 2. Add storage (loop device for testing)
echo -e "\n${YELLOW}Step 2: Setting up storage...${NC}"
mkdir -p /var/snap/microceph/common/data
truncate -s 50G /var/snap/microceph/common/data/osd.img
losetup -f /var/snap/microceph/common/data/osd.img
LOOP_DEVICE=$(losetup -j /var/snap/microceph/common/data/osd.img | cut -d: -f1)
echo "Using loop device: $LOOP_DEVICE"
microceph disk add $LOOP_DEVICE
echo -e "${GREEN}✓ Storage added${NC}"

# 3. Enable CephFS
echo -e "\n${YELLOW}Step 3: Enabling CephFS...${NC}"
microceph enable mds
sleep 10
ceph osd pool set cephfs.cephfs.meta size 1 --yes-i-really-mean-it
ceph osd pool set cephfs.cephfs.meta min_size 1
ceph osd pool set cephfs.cephfs.data size 1 --yes-i-really-mean-it
ceph osd pool set cephfs.cephfs.data min_size 1
echo -e "${GREEN}✓ CephFS enabled${NC}"

# 4. Create mount point and symbolic links
echo -e "\n${YELLOW}Step 4: Setting up mount point...${NC}"
mkdir -p /mnt/cephfs
ln -sf /var/snap/microceph/current/conf/ceph.conf /etc/ceph/ceph.conf
ln -sf /var/snap/microceph/current/conf/ceph.client.admin.keyring /etc/ceph/ceph.client.admin.keyring
echo -e "${GREEN}✓ Mount point ready${NC}"

# 5. Mount CephFS
echo -e "\n${YELLOW}Step 5: Mounting CephFS...${NC}"
ADMIN_KEY=$(ceph auth get-key client.admin)
mount -t ceph :/ /mnt/cephfs -o name=admin,secret=$ADMIN_KEY
echo -e "${GREEN}✓ CephFS mounted${NC}"

# 6. Create volume directories
echo -e "\n${YELLOW}Step 6: Creating volume directories...${NC}"
VOLUMES=(
    "postgres_data"
    "redis_data"
    "rabbitmq_data"
    "prometheus_data"
    "grafana_data"
    "elasticsearch_data"
    "minio_data"
    "pgadmin_data"
    "odoo_instances"
    "odoo_backups"
    "killbill_db_data"
)

for VOLUME in "${VOLUMES[@]}"; do
    mkdir -p /mnt/cephfs/$VOLUME
    chmod 777 /mnt/cephfs/$VOLUME
done
echo -e "${GREEN}✓ Volume directories created${NC}"

# 7. Verify setup
echo -e "\n${YELLOW}Step 7: Verifying setup...${NC}"
echo "Cluster status:"
microceph status
echo ""
echo "Ceph health:"
ceph health
echo ""
echo "CephFS mount:"
df -h /mnt/cephfs
echo ""
echo "Test write:"
echo "Test data $(date)" > /mnt/cephfs/test.txt
cat /mnt/cephfs/test.txt

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!                       ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "CephFS is mounted at: /mnt/cephfs"
echo "Volume directories created for all services"
echo ""
echo "Next steps:"
echo "1. Stop your current Docker stack"
echo "2. Use docker-compose.ceph.yml to start services"
echo "3. Verify all services start correctly"
echo ""
```

Save this as `single-node-test.sh` and run:

```bash
sudo bash single-node-test.sh
```

---

## Docker Compose Changes

Now I'll create the updated docker-compose file with CephFS volumes...

---

## Testing with Docker Compose

### Step 1: Stop Current Stack

```bash
cd /home/tariron/Projects/saasodoo
docker compose -f infrastructure/compose/docker-compose.dev.yml down
```

### Step 2: Start with CephFS Volumes

```bash
# Use the new CephFS-enabled compose file
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d
```

### Step 3: Verify Services

```bash
# Check all services are running
docker compose -f infrastructure/compose/docker-compose.ceph.yml ps

# Check logs
docker compose -f infrastructure/compose/docker-compose.ceph.yml logs -f postgres

# Test database
docker exec saasodoo-postgres psql -U odoo_user -d odoo -c "SELECT version();"
```

---

## Production 3-Node Setup

Once single-node testing is successful, here's the production setup:

### Step 1: Install MicroCeph on All 3 Nodes

```bash
# Run on ALL nodes
sudo snap install microceph
```

### Step 2: Bootstrap Cluster on First Node

```bash
# On node1 only
sudo microceph cluster bootstrap

# Get join tokens for other nodes
sudo microceph cluster add node2
sudo microceph cluster add node3
```

### Step 3: Join Other Nodes

```bash
# On node2
sudo microceph cluster join <token_from_node1>

# On node3
sudo microceph cluster join <token_from_node1>
```

### Step 4: Add Disks to All Nodes

```bash
# Run on each node
sudo microceph disk add /dev/sdb
```

### Step 5: Enable CephFS

```bash
# On node1 only
sudo microceph enable mds

# For production, use replica 3 (default)
# No need to change size settings
```

### Step 6: Mount CephFS on All Nodes

```bash
# Run on ALL nodes
sudo mkdir -p /mnt/cephfs
sudo ln -sf /var/snap/microceph/current/conf/ceph.conf /etc/ceph/ceph.conf
sudo ln -sf /var/snap/microceph/current/conf/ceph.client.admin.keyring /etc/ceph/ceph.client.admin.keyring

ADMIN_KEY=$(sudo ceph auth get-key client.admin)
sudo mount -t ceph :/ /mnt/cephfs -o name=admin,secret=$ADMIN_KEY

# Add to fstab on all nodes
echo ":/ /mnt/cephfs ceph name=admin,secret=$ADMIN_KEY,noatime,_netdev 0 0" | sudo tee -a /etc/fstab
```

### Step 7: Create Directories (Once, From Any Node)

```bash
# Run on one node only (data will replicate)
sudo mkdir -p /mnt/cephfs/{postgres_data,redis_data,rabbitmq_data,prometheus_data,grafana_data,elasticsearch_data,minio_data,pgadmin_data,odoo_instances,odoo_backups,killbill_db_data}
sudo chmod -R 777 /mnt/cephfs/*
```

---

## Data Migration Steps

### Option A: Fresh Start (No Data to Migrate)

Simply start with the new docker-compose.ceph.yml file. All services will create fresh data in CephFS.

### Option B: Migrate Existing Data

If you have existing data to preserve:

```bash
#!/bin/bash
# migrate-data.sh
# Migrate existing Docker volumes to CephFS

set -e

echo "Starting data migration..."

VOLUMES=(
    "postgres-data:postgres_data"
    "redis-data:redis_data"
    "rabbitmq-data:rabbitmq_data"
    "prometheus-data:prometheus_data"
    "grafana-data:grafana_data"
    "elasticsearch-data:elasticsearch_data"
    "minio-data:minio_data"
    "pgadmin-data:pgadmin_data"
    "odoo-instances:odoo_instances"
    "odoo-backups:odoo_backups"
    "killbill-db-data:killbill_db_data"
)

for VOLUME_PAIR in "${VOLUMES[@]}"; do
    IFS=':' read -r DOCKER_VOL CEPH_DIR <<< "$VOLUME_PAIR"
    echo "Migrating $DOCKER_VOL to $CEPH_DIR..."

    VOL_PATH=$(docker volume inspect saasodoo_$DOCKER_VOL -f '{{ .Mountpoint }}' 2>/dev/null || echo "")

    if [ -n "$VOL_PATH" ] && [ -d "$VOL_PATH" ]; then
        sudo rsync -avP $VOL_PATH/ /mnt/cephfs/$CEPH_DIR/
        echo "✓ Migrated $DOCKER_VOL"
    else
        echo "⚠ Volume $DOCKER_VOL not found, skipping"
    fi
done

echo "Migration complete!"
```

---

## Verification & Testing

### Quick Verification Checklist

```bash
# 1. Check CephFS is mounted
df -h /mnt/cephfs

# 2. Check Ceph health
sudo ceph health

# 3. Check all directories exist
ls -la /mnt/cephfs/

# 4. Test write/read
echo "Test" | sudo tee /mnt/cephfs/test.txt
cat /mnt/cephfs/test.txt

# 5. Check Docker containers
docker ps

# 6. Test database connection
docker exec saasodoo-postgres psql -U odoo_user -d odoo -c "SELECT version();"

# 7. Test application endpoints
curl http://localhost:8001/health  # user-service
curl http://localhost:8003/health  # instance-service
curl http://localhost:8004/health  # billing-service
```

---

## Rollback Plan

If something goes wrong:

### Step 1: Stop Services

```bash
docker compose -f infrastructure/compose/docker-compose.ceph.yml down
```

### Step 2: Revert to Original Compose File

```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml up -d
```

### Step 3: (Optional) Unmount CephFS

```bash
sudo umount /mnt/cephfs
```

### Step 4: (Optional) Remove MicroCeph

```bash
sudo snap remove microceph --purge
```

---

## Troubleshooting

### Issue: CephFS Mount Fails

```bash
# Check Ceph health
sudo ceph health

# Check MDS status
sudo ceph mds stat

# Check logs
sudo journalctl -u snap.microceph.daemon -f
```

### Issue: Permission Denied in Containers

```bash
# Fix permissions on CephFS directories
sudo chmod -R 777 /mnt/cephfs/*

# Or set specific ownership
sudo chown -R 999:999 /mnt/cephfs/postgres_data  # Postgres UID
```

### Issue: Single-Node Shows HEALTH_WARN

This is expected for single-node with size=1. You'll see:

```
HEALTH_WARN: insufficient standby MDS daemons available
```

This is normal for single-node testing and won't affect functionality.

### Issue: Loop Device Not Persisting After Reboot

Create a systemd service to recreate the loop device on boot:

```bash
sudo tee /etc/systemd/system/microceph-loop.service > /dev/null <<EOF
[Unit]
Description=Setup MicroCeph loop device
Before=snap.microceph.daemon.service

[Service]
Type=oneshot
ExecStart=/sbin/losetup -f /var/snap/microceph/common/data/osd.img
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable microceph-loop.service
```

---

## Performance Tuning (Optional)

### Single-Node Optimizations

```bash
# Disable replication overhead (testing only)
sudo ceph osd pool set cephfs.cephfs.data size 1
sudo ceph osd pool set cephfs.cephfs.meta size 1

# Increase cache size
sudo ceph config set client client_cache_size 536870912  # 512MB
```

### Production Optimizations

```bash
# Enable faster recovery
sudo ceph osd pool set cephfs.cephfs.data pg_autoscale_mode on

# Tune for database workloads
sudo ceph osd pool set cephfs.cephfs.data compression_mode none
```

---

## Next Steps After Successful Test

1. ✅ Single-node test passes
2. ✅ All services start and work correctly
3. ✅ Database connections verified
4. ✅ Application functionality tested
5. 🎯 Plan production 3-node deployment
6. 🎯 Schedule migration window
7. 🎯 Deploy to production

---

## Summary

### Single-Node Test Setup
- Time: 1-2 hours
- Purpose: Validate MicroCeph works with your stack
- Use loop device for storage (no dedicated disk needed)
- Can run on your development machine

### Production 3-Node Setup
- Time: 3-4 hours
- Purpose: High-availability production deployment
- Requires 3 nodes with dedicated disks
- Full replication and fault tolerance

### Docker Changes
- Minimal: Just volume definitions change
- Services remain unchanged
- Same docker-compose commands

---

**Ready to proceed?** Start with the single-node test script above!
