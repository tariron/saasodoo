#!/bin/bash

#############################################
# Ceph Cluster Manager Script
# Purpose: Remove and reinstall Ceph cluster
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
MANAGER_IP="10.0.0.2"
CLUSTER_NETWORK="10.0.0.0/22"
CEPHADM_URL="https://download.ceph.com/rpm-reef/el9/noarch/cephadm"

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

remove_ceph_cluster() {
    print_header "Step 1: Removing Existing Ceph Cluster"

    # Check if cephadm exists
    if command -v cephadm &> /dev/null; then
        log_info "Finding existing Ceph clusters..."

        # Get all cluster FSIDs
        FSIDS=$(ls -d /var/lib/ceph/*/config 2>/dev/null | cut -d'/' -f5 || echo "")

        if [ -n "$FSIDS" ]; then
            for FSID in $FSIDS; do
                log_info "Removing cluster with FSID: $FSID"
                cephadm rm-cluster --fsid "$FSID" --force 2>/dev/null || true
            done
            log_success "Cluster(s) removed"
        else
            log_warning "No existing clusters found"
        fi
    else
        log_warning "cephadm not found, skipping cluster removal"
    fi

    # Remove Ceph directories
    log_info "Removing Ceph configuration and data directories..."
    rm -rf /etc/ceph /var/lib/ceph 2>/dev/null || true
    log_success "Directories cleaned"

    # Remove cephadm binary
    log_info "Removing cephadm binary..."
    rm -f /usr/local/bin/cephadm 2>/dev/null || true

    # Remove repository files
    log_info "Removing Ceph repository files..."
    rm -f /etc/apt/sources.list.d/ceph.list 2>/dev/null || true
    rm -f /etc/apt/trusted.gpg.d/ceph.gpg 2>/dev/null || true

    # Remove cephadm package if installed
    if dpkg -l | grep -q cephadm; then
        log_info "Removing cephadm package..."
        apt remove -y cephadm &>/dev/null || true
        apt autoremove -y &>/dev/null || true
    fi

    log_success "Ceph cluster removal complete"
}

install_dependencies() {
    print_header "Step 2: Installing Dependencies"

    log_info "Updating package list..."
    apt update -qq

    log_info "Installing required packages..."
    apt install -y python3 lvm2 podman curl gpg &>/dev/null || apt install -y python3 lvm2 curl gpg &>/dev/null

    log_success "Dependencies installed"
}

install_cephadm() {
    print_header "Step 3: Installing Cephadm"

    log_info "Downloading cephadm from $CEPHADM_URL"
    curl -fsSL "$CEPHADM_URL" -o /usr/local/bin/cephadm
    chmod +x /usr/local/bin/cephadm

    CEPHADM_VERSION=$(/usr/local/bin/cephadm version)
    log_success "cephadm installed: $CEPHADM_VERSION"
}

verify_network() {
    print_header "Step 4: Verifying Network Configuration"

    log_info "Checking if $MANAGER_IP is configured..."
    if ip addr show | grep -q "$MANAGER_IP"; then
        log_success "Manager IP $MANAGER_IP is configured"
    else
        log_error "Manager IP $MANAGER_IP not found on any interface"
        log_error "Please configure the IP first"
        exit 1
    fi

    # Check connectivity to other nodes
    log_info "Testing connectivity to other nodes..."
    for NODE_IP in 10.0.0.1 10.0.0.3; do
        if ping -c 1 -W 2 "$NODE_IP" &>/dev/null; then
            log_success "Node $NODE_IP is reachable"
        else
            log_warning "Node $NODE_IP is NOT reachable (you can add it later)"
        fi
    done
}

bootstrap_cluster() {
    print_header "Step 5: Bootstrapping Ceph Cluster"

    log_info "Starting Ceph bootstrap on $MANAGER_IP with network $CLUSTER_NETWORK"
    log_warning "This may take 5-10 minutes..."

    cephadm bootstrap \
        --mon-ip "$MANAGER_IP" \
        --cluster-network "$CLUSTER_NETWORK" \
        --skip-pull \
        2>&1 | tee /tmp/ceph-bootstrap.log

    log_success "Ceph cluster bootstrapped successfully"
}

display_cluster_info() {
    print_header "Ceph Cluster Information"

    # Get cluster FSID
    FSID=$(ls -d /var/lib/ceph/*/config 2>/dev/null | cut -d'/' -f5 | head -1)

    if [ -z "$FSID" ]; then
        log_error "Could not find cluster FSID"
        return 1
    fi

    echo -e "${GREEN}Cluster ID:${NC} $FSID"
    echo -e "${GREEN}Manager Node:${NC} $MANAGER_IP ($(hostname))"
    echo ""

    # Get dashboard URL and credentials
    if [ -f "/tmp/ceph-bootstrap.log" ]; then
        DASHBOARD_URL=$(grep -oP "URL: \K.*" /tmp/ceph-bootstrap.log | tail -1)
        DASHBOARD_USER=$(grep -oP "User: \K.*" /tmp/ceph-bootstrap.log | tail -1)
        DASHBOARD_PASS=$(grep -oP "Password: \K.*" /tmp/ceph-bootstrap.log | tail -1)

        echo -e "${GREEN}Dashboard URL:${NC} $DASHBOARD_URL"
        echo -e "${GREEN}Username:${NC} $DASHBOARD_USER"
        echo -e "${GREEN}Password:${NC} $DASHBOARD_PASS"
        echo ""
    fi

    # Display SSH public key
    if [ -f "/etc/ceph/ceph.pub" ]; then
        echo -e "${YELLOW}SSH Public Key (add this to nodes 10.0.0.1 and 10.0.0.3):${NC}"
        cat /etc/ceph/ceph.pub
        echo ""
    fi

    # Display cluster status
    echo -e "\n${GREEN}Cluster Status:${NC}"
    cephadm shell -- ceph -s 2>/dev/null || log_warning "Could not get cluster status"
}

save_cluster_info() {
    print_header "Saving Cluster Information"

    INFO_FILE="/root/ceph-cluster-info.txt"

    {
        echo "==================================="
        echo "Ceph Cluster Information"
        echo "Generated: $(date)"
        echo "==================================="
        echo ""

        FSID=$(ls -d /var/lib/ceph/*/config 2>/dev/null | cut -d'/' -f5 | head -1)
        echo "Cluster ID: $FSID"
        echo "Manager Node: $MANAGER_IP ($(hostname))"
        echo ""

        if [ -f "/tmp/ceph-bootstrap.log" ]; then
            echo "Dashboard URL: $(grep -oP "URL: \K.*" /tmp/ceph-bootstrap.log | tail -1)"
            echo "Username: $(grep -oP "User: \K.*" /tmp/ceph-bootstrap.log | tail -1)"
            echo "Password: $(grep -oP "Password: \K.*" /tmp/ceph-bootstrap.log | tail -1)"
            echo ""
        fi

        if [ -f "/etc/ceph/ceph.pub" ]; then
            echo "SSH Public Key (add to other nodes):"
            cat /etc/ceph/ceph.pub
            echo ""
        fi

        echo ""
        echo "==================================="
        echo "Next Steps:"
        echo "==================================="
        echo "1. Copy the SSH public key to nodes 10.0.0.1 and 10.0.0.3:"
        echo "   ssh-copy-id -i /etc/ceph/ceph.pub root@10.0.0.1"
        echo "   ssh-copy-id -i /etc/ceph/ceph.pub root@10.0.0.3"
        echo ""
        echo "2. Add nodes to the cluster:"
        echo "   ceph orch host add node1 10.0.0.1"
        echo "   ceph orch host add node3 10.0.0.3"
        echo ""
        echo "3. Create OSDs (after adding nodes):"
        echo "   ceph orch apply osd --all-available-devices"
        echo ""
        echo "4. Access the dashboard at the URL above"

    } > "$INFO_FILE"

    log_success "Cluster information saved to $INFO_FILE"
}

#############################################
# Main Script
#############################################

main() {
    clear

    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════╗"
    echo "║   Ceph Cluster Manager Script        ║"
    echo "║   Manager Node: $MANAGER_IP         ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"

    check_root

    # Show menu if no arguments provided
    if [ $# -eq 0 ]; then
        echo "Usage: $0 [OPTIONS]"
        echo ""
        echo "Options:"
        echo "  --remove          Remove existing Ceph cluster only"
        echo "  --install         Install new Ceph cluster only"
        echo "  --reinstall       Remove and install (full reinstall)"
        echo "  --help            Show this help message"
        echo ""
        echo "Example: $0 --reinstall"
        exit 0
    fi

    case "$1" in
        --remove)
            remove_ceph_cluster
            log_success "Removal complete"
            ;;
        --install)
            install_dependencies
            install_cephadm
            verify_network
            bootstrap_cluster
            display_cluster_info
            save_cluster_info
            ;;
        --reinstall)
            remove_ceph_cluster
            install_dependencies
            install_cephadm
            verify_network
            bootstrap_cluster
            display_cluster_info
            save_cluster_info

            echo ""
            log_success "Ceph cluster reinstallation complete!"
            log_info "Check /root/ceph-cluster-info.txt for details"
            ;;
        --help)
            echo "Ceph Cluster Manager Script"
            echo ""
            echo "This script helps manage Ceph cluster installation on the manager node."
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --remove          Remove existing Ceph cluster only"
            echo "  --install         Install new Ceph cluster only"
            echo "  --reinstall       Remove and install (full reinstall)"
            echo "  --help            Show this help message"
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
}

main "$@"
