#!/bin/bash

#############################################
# Ceph Worker Node Setup Script
# Purpose: Prepare worker nodes for Ceph cluster
# Run this on: 10.0.0.1 and 10.0.0.3
# Author: Claude Code
# Date: 2025-11-03
#############################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
OSD_SIZE_GB=33  # 33GB per node (100GB total / 3 nodes)
OSD_PATH="/var/lib/ceph/osd/ceph-osd-0"

#############################################
# Functions
#############################################

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "\n${GREEN}=================================${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}=================================${NC}\n"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

get_node_ip() {
    NODE_IP=$(ip addr show eth1 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d'/' -f1 || echo "")
    if [ -z "$NODE_IP" ]; then
        log_error "Could not detect IP on eth1 (private network)"
        exit 1
    fi
    echo "$NODE_IP"
}

#############################################
# Main Setup Functions
#############################################

cleanup_old_setup() {
    print_header "Step 0: Cleaning Up Old Setup"

    # Detach any existing loop devices
    log_info "Checking for existing loop devices..."
    EXISTING_LOOP=$(losetup -a | grep osd-disk.img | cut -d: -f1 || echo "")
    if [ -n "$EXISTING_LOOP" ]; then
        log_info "Detaching existing loop device: $EXISTING_LOOP"
        losetup -d "$EXISTING_LOOP" || true
    fi

    # Remove old OSD directory
    if [ -d "/var/lib/ceph/osd/ceph-osd-0" ]; then
        log_info "Removing old OSD directory..."
        rm -rf /var/lib/ceph/osd/ceph-osd-0
    fi

    # Remove old OSD image file
    if [ -f "/var/lib/ceph/osd/osd-disk.img" ]; then
        log_info "Removing old OSD image file..."
        rm -f /var/lib/ceph/osd/osd-disk.img
    fi

    # Remove from rc.local
    if [ -f /etc/rc.local ] && grep -q "osd-disk.img" /etc/rc.local; then
        log_info "Removing from /etc/rc.local..."
        sed -i '/osd-disk.img/d' /etc/rc.local
    fi

    log_success "Cleanup complete"
}

install_dependencies() {
    print_header "Step 1: Installing Dependencies"

    log_info "Updating package list..."
    apt update -qq

    log_info "Installing required packages..."
    apt install -y python3 lvm2 podman curl gpg chrony &>/dev/null || apt install -y python3 lvm2 curl gpg chrony &>/dev/null

    # Ensure time sync is enabled
    log_info "Enabling time synchronization..."
    systemctl enable --now systemd-timesyncd || systemctl enable --now chrony || true

    log_success "Dependencies installed"
}

configure_ssh() {
    print_header "Step 2: Configuring SSH Access"

    # Ensure SSH directory exists
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh

    # Ensure authorized_keys exists
    touch /root/.ssh/authorized_keys
    chmod 600 /root/.ssh/authorized_keys

    # Configure SSH to allow root login
    if ! grep -q "^PermitRootLogin yes" /etc/ssh/sshd_config; then
        log_info "Enabling SSH root login..."
        sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
        systemctl reload sshd
    fi

    log_success "SSH configured"
    log_warning "Manager node will add its SSH key automatically"
}

create_osd_storage() {
    print_header "Step 3: Creating OSD Storage (Loop Device)"

    # Create directory for OSD files
    mkdir -p /var/lib/ceph/osd

    log_info "Creating ${OSD_SIZE_GB}GB sparse file for OSD..."
    truncate -s ${OSD_SIZE_GB}G /var/lib/ceph/osd/osd-disk.img

    log_info "Setting up loop device..."
    # Find free loop device
    LOOP_DEV=$(losetup -f)

    # Attach file to loop device
    losetup "$LOOP_DEV" /var/lib/ceph/osd/osd-disk.img

    log_success "Loop device created: $LOOP_DEV"
    log_info "Backed by file: /var/lib/ceph/osd/osd-disk.img (${OSD_SIZE_GB}GB)"

    # Make it persistent across reboots
    log_info "Adding to /etc/rc.local for persistence..."
    if [ ! -f /etc/rc.local ]; then
        cat > /etc/rc.local << 'RCEOF'
#!/bin/bash
exit 0
RCEOF
        chmod +x /etc/rc.local
    fi

    # Add losetup command if not already there
    if ! grep -q "osd-disk.img" /etc/rc.local; then
        sed -i '/^exit 0/i losetup -f /var/lib/ceph/osd/osd-disk.img || true' /etc/rc.local
    fi

    log_info "Loop device: $LOOP_DEV"
}

verify_network() {
    print_header "Step 4: Verifying Network Configuration"

    NODE_IP=$(get_node_ip)
    log_success "Node IP on private network: $NODE_IP"

    # Test connectivity to manager
    log_info "Testing connectivity to manager node (10.0.0.2)..."
    if ping -c 2 -W 2 10.0.0.2 &>/dev/null; then
        log_success "Manager node (10.0.0.2) is reachable"
    else
        log_error "Cannot reach manager node at 10.0.0.2"
        exit 1
    fi
}

display_summary() {
    print_header "Worker Node Setup Complete"

    NODE_IP=$(get_node_ip)
    HOSTNAME=$(hostname)
    LOOP_DEV=$(losetup -a | grep osd-disk.img | cut -d: -f1 | head -1)

    echo -e "${GREEN}Node Information:${NC}"
    echo -e "  Hostname: $HOSTNAME"
    echo -e "  Private IP: $NODE_IP"
    echo -e "  Loop Device: $LOOP_DEV"
    echo -e "  OSD File: /var/lib/ceph/osd/osd-disk.img"
    echo -e "  OSD Size: ${OSD_SIZE_GB}GB"
    echo ""
    echo -e "${YELLOW}Next Steps:${NC}"
    echo -e "  1. Run this script on the other worker node (if not done yet)"
    echo -e "  2. On the manager node (10.0.0.2), run: ${GREEN}./ceph-manager-orchestration.sh${NC}"
    echo ""
    echo -e "${BLUE}The manager will:${NC}"
    echo -e "  - Copy SSH keys to this node"
    echo -e "  - Add this node to the Ceph cluster"
    echo -e "  - Deploy OSDs on this node"
    echo -e "  - Configure CephFS"
    echo ""
}

#############################################
# Main Script
#############################################

main() {
    clear

    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════╗"
    echo "║   Ceph Worker Node Setup Script      ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"

    check_root

    NODE_IP=$(get_node_ip)
    log_info "Detected node IP: $NODE_IP"

    cleanup_old_setup
    install_dependencies
    configure_ssh
    create_osd_storage
    verify_network
    display_summary

    log_success "Worker node is ready for Ceph cluster!"
}

main "$@"
