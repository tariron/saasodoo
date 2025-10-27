#!/bin/bash
#
# MicroCeph Single-Node Setup Script for SaaSodoo Testing
# Based on official MicroCeph documentation
#
# This script automates the complete setup of MicroCeph on a single node
#
# Requirements:
# - Ubuntu 22.04 or 24.04 LTS
# - At least 8GB RAM
# - Root access
#
# Usage: sudo bash setup-microceph-single-node.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
MOUNT_POINT="/mnt/cephfs"
FS_NAME="cephfs"

# Volume directories for SaaSodoo
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

# Print banner
echo -e "${GREEN}"
echo "========================================"
echo "  MicroCeph Single-Node Setup          "
echo "========================================"
echo -e "${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}Error: This script must be run as root${NC}"
   echo "Usage: sudo bash $0"
   exit 1
fi

# Check OS version
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo -e "${BLUE}Detected OS: $NAME $VERSION_ID${NC}"
fi

# Step 0: Clean up any existing broken MicroCeph installation
echo -e "\n${YELLOW}Step 0/7: Checking for existing MicroCeph installation...${NC}"
if snap list 2>/dev/null | grep -q microceph; then
    echo -e "${YELLOW}Found existing MicroCeph installation${NC}"
    read -p "Do you want to remove it and start fresh? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Unmounting CephFS if mounted...${NC}"
        umount "$MOUNT_POINT" 2>/dev/null || true

        echo -e "${YELLOW}Removing MicroCeph with --purge...${NC}"
        snap remove --purge microceph

        echo -e "${YELLOW}Cleaning up mount point...${NC}"
        rm -rf "$MOUNT_POINT"

        echo -e "${GREEN}✓ Cleanup complete${NC}"
        echo -e "${BLUE}Note: /etc/ceph symlinks will be recreated automatically${NC}"
    else
        echo -e "${BLUE}Keeping existing installation${NC}"
    fi
else
    echo -e "${BLUE}No existing MicroCeph installation found${NC}"
fi

# Step 1: Install MicroCeph
echo -e "\n${YELLOW}Step 1/7: Installing MicroCeph...${NC}"
if snap list 2>/dev/null | grep -q microceph; then
    echo -e "${BLUE}MicroCeph already installed${NC}"
else
    snap install microceph
    echo -e "${GREEN}✓ MicroCeph installed${NC}"
fi

# Hold updates
echo "Preventing auto-updates..."
snap refresh --hold microceph

# Step 2: Bootstrap cluster
echo -e "\n${YELLOW}Step 2/7: Bootstrapping cluster...${NC}"
if microceph status &>/dev/null; then
    echo -e "${BLUE}Cluster already bootstrapped${NC}"
else
    microceph cluster bootstrap
    echo -e "${GREEN}✓ Cluster bootstrapped${NC}"
fi

# Create /etc/ceph directory and symlinks (needed for ceph commands)
echo "Setting up /etc/ceph configuration symlinks..."
mkdir -p /etc/ceph
ln -sf /var/snap/microceph/current/conf/ceph.conf /etc/ceph/ceph.conf
ln -sf /var/snap/microceph/current/conf/ceph.client.admin.keyring /etc/ceph/ceph.client.admin.keyring
echo -e "${GREEN}✓ Configuration symlinks created${NC}"

# Step 3: Add storage
echo -e "\n${YELLOW}Step 3/7: Adding storage (3x 4GB OSDs)...${NC}"
if microceph status | grep -q "Disks: [1-9]"; then
    echo -e "${BLUE}Storage already configured${NC}"
else
    # Add 3 loop-backed OSDs of 4GB each (official recommendation)
    microceph disk add loop,4G,3
    echo -e "${GREEN}✓ Storage added${NC}"
fi

# Wait for OSDs to be up
echo "Waiting for OSDs to be ready..."
sleep 5

# Step 4: Create CephFS filesystem
echo -e "\n${YELLOW}Step 4/7: Creating CephFS filesystem...${NC}"
if ceph fs ls 2>/dev/null | grep -q "$FS_NAME"; then
    echo -e "${BLUE}CephFS filesystem '$FS_NAME' already exists${NC}"
else
    # Create filesystem using volume method
    ceph fs volume create "$FS_NAME"
    echo "Waiting for filesystem to be ready..."
    sleep 5
    echo -e "${GREEN}✓ CephFS filesystem created${NC}"
fi

# Verify MDS is active
echo "Checking MDS status..."
MDS_STATUS=$(ceph mds stat)
echo "$MDS_STATUS"

if echo "$MDS_STATUS" | grep -q "up:active"; then
    echo -e "${GREEN}✓ MDS is active${NC}"
else
    echo -e "${YELLOW}Waiting for MDS to become active...${NC}"
    sleep 10
    ceph mds stat
fi

# Step 5: Install ceph-common and setup mount
echo -e "\n${YELLOW}Step 5/7: Installing mount dependencies...${NC}"

# Install ceph-common for mount helper
if ! dpkg -l | grep -q "^ii  ceph-common"; then
    echo "Installing ceph-common package..."
    apt-get update -qq
    apt-get install -y ceph-common
    echo -e "${GREEN}✓ ceph-common installed${NC}"
else
    echo -e "${BLUE}ceph-common already installed${NC}"
fi

# Load ceph kernel module
if ! lsmod | grep -q "^ceph"; then
    echo "Loading ceph kernel module..."
    modprobe ceph || {
        echo -e "${RED}Failed to load ceph kernel module${NC}"
        echo "Your kernel may not support Ceph (common in WSL)."
        exit 1
    }
    echo -e "${GREEN}✓ ceph module loaded${NC}"
else
    echo -e "${BLUE}ceph module already loaded${NC}"
fi

# Step 6: Setup mount point
echo -e "\n${YELLOW}Step 6/7: Setting up mount point...${NC}"

# Create mount directory
mkdir -p "$MOUNT_POINT"

echo -e "${GREEN}✓ Mount point configured${NC}"

# Step 7: Mount CephFS
echo -e "\n${YELLOW}Step 7/7: Mounting CephFS...${NC}"

# Check if already mounted
if mountpoint -q "$MOUNT_POINT"; then
    echo -e "${BLUE}CephFS already mounted at $MOUNT_POINT${NC}"
else
    # Get admin key
    ADMIN_KEY=$(ceph auth get-key client.admin)

    echo "Mounting CephFS..."
    # Mount with filesystem name
    mount -t ceph :/ "$MOUNT_POINT" -o name=admin,secret="$ADMIN_KEY",fs="$FS_NAME"
    echo -e "${GREEN}✓ CephFS mounted at $MOUNT_POINT${NC}"
fi

# Verify mount
echo ""
df -h "$MOUNT_POINT" | grep cephfs

# Step 8: Create volume directories
echo -e "\n${YELLOW}Creating volume directories...${NC}"

for VOLUME in "${VOLUMES[@]}"; do
    VOLUME_PATH="$MOUNT_POINT/$VOLUME"

    if [ -d "$VOLUME_PATH" ]; then
        echo "  ⚬ $VOLUME (exists)"
    else
        mkdir -p "$VOLUME_PATH"
        chmod 777 "$VOLUME_PATH"
        echo "  ✓ $VOLUME (created)"
    fi
done

echo -e "${GREEN}✓ All volume directories created${NC}"

# Final verification
echo -e "\n${YELLOW}Running final verification...${NC}"

# Test write
TEST_FILE="$MOUNT_POINT/.test_write_$(date +%s).txt"
echo "Test write at $(date)" > "$TEST_FILE"
if [ -f "$TEST_FILE" ]; then
    rm "$TEST_FILE"
    echo -e "${GREEN}✓ Write test successful${NC}"
else
    echo -e "${RED}✗ Write test failed${NC}"
    exit 1
fi

# Print summary
echo -e "\n${GREEN}========================================"
echo "  Setup Complete!                     "
echo "========================================${NC}"
echo ""
echo -e "${BLUE}Cluster Status:${NC}"
microceph status
echo ""
echo -e "${BLUE}Ceph Health:${NC}"
ceph health
echo ""
echo -e "${BLUE}CephFS Status:${NC}"
ceph fs status "$FS_NAME"
echo ""
echo -e "${BLUE}Mount:${NC}"
df -h "$MOUNT_POINT" | grep cephfs
echo ""
echo -e "${GREEN}Next Steps:${NC}"
echo "1. cd /home/tariron/Projects/saasodoo"
echo "2. docker compose -f infrastructure/compose/docker-compose.dev.yml down"
echo "3. docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d"
echo "4. docker compose -f infrastructure/compose/docker-compose.ceph.yml ps"
echo ""
echo -e "${YELLOW}Volume directories created at:${NC} $MOUNT_POINT/"
ls -la "$MOUNT_POINT/"
echo ""
