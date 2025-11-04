#!/bin/bash

#############################################
# Ceph Operations Script
# Purpose: Day-to-day Ceph cluster management
# Run on: Manager node (10.0.0.2)
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
OSD_PATH="/var/lib/ceph/osd/ceph-osd-0"
CEPHFS_MOUNT="/mnt/cephfs"
FS_NAME="saasodoo_fs"

# Odoo platform required directories
ODOO_DIRS=(
    "postgres_data"
    "redis_data"
    "rabbitmq_data"
    "prometheus_data"
    "killbill_db_data"
    "odoo_instances"
    "odoo_backups"
)

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

check_ceph() {
    if ! command -v cephadm &> /dev/null; then
        log_error "cephadm not found. Please run ceph-cluster-manager.sh first"
        exit 1
    fi

    if ! cephadm shell -- ceph -s &>/dev/null; then
        log_error "Ceph cluster is not running"
        exit 1
    fi
}

#############################################
# Command Functions
#############################################

add_node() {
    local NODE_IP=$1

    if [ -z "$NODE_IP" ]; then
        log_error "Usage: $0 add-node <ip>"
        exit 1
    fi

    print_header "Adding Node: $NODE_IP"

    # Check connectivity
    log_info "Testing connectivity to $NODE_IP..."
    if ! ping -c 2 -W 2 "$NODE_IP" &>/dev/null; then
        log_error "Cannot reach $NODE_IP"
        exit 1
    fi

    # Copy SSH key
    log_info "Copying SSH key to $NODE_IP..."
    if [ ! -f "/etc/ceph/ceph.pub" ]; then
        log_error "SSH key not found at /etc/ceph/ceph.pub"
        exit 1
    fi

    log_warning "Please enter the SSH password for root@$NODE_IP"

    # Use manual method since ssh-copy-id has issues with ceph keys
    cat /etc/ceph/ceph.pub | ssh -o StrictHostKeyChecking=no "root@$NODE_IP" \
        'mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys' || {
        log_error "Failed to copy SSH key to $NODE_IP"
        exit 1
    }

    # Test SSH connection
    log_info "Testing SSH connection..."
    if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 "root@$NODE_IP" "echo 'SSH OK'" &>/dev/null; then
        log_error "SSH connection failed"
        exit 1
    fi

    # Get hostname from node
    NODE_HOSTNAME=$(ssh -o StrictHostKeyChecking=no "root@$NODE_IP" "hostname" 2>/dev/null)
    log_info "Node hostname: $NODE_HOSTNAME"

    # Check if node already exists
    if cephadm shell -- ceph orch host ls --format json 2>/dev/null | grep -q "$NODE_IP"; then
        log_warning "Node $NODE_IP already in cluster"
    else
        log_info "Adding $NODE_HOSTNAME ($NODE_IP) to cluster..."
        cephadm shell -- ceph orch host add "$NODE_HOSTNAME" "$NODE_IP" || {
            log_error "Failed to add node to cluster"
            exit 1
        }
        log_success "Node added to cluster"

        # Wait for node to be ready
        log_info "Waiting for node to be ready (10 seconds)..."
        sleep 10
    fi

    # Add OSD automatically - find loop device on node
    log_info "Detecting loop device on $NODE_HOSTNAME..."
    LOOP_DEV=$(ssh -o StrictHostKeyChecking=no "root@$NODE_IP" "losetup -a | grep osd-disk.img | cut -d: -f1 | head -1" 2>/dev/null || echo "")

    if [ -n "$LOOP_DEV" ]; then
        log_info "Found loop device: $LOOP_DEV"
        log_info "Adding OSD on $NODE_HOSTNAME..."
        cephadm shell -- ceph orch daemon add osd "${NODE_HOSTNAME}:${LOOP_DEV}" || {
            log_warning "Failed to add OSD (it might already exist)"
        }
    else
        log_warning "No loop device found on $NODE_HOSTNAME. Run worker setup script first."
    fi

    log_success "Node $NODE_IP added successfully!"
    log_info "OSD will be available in ~30 seconds"
}

remove_node() {
    local NODE_HOSTNAME=$1

    if [ -z "$NODE_HOSTNAME" ]; then
        log_error "Usage: $0 remove-node <hostname>"
        exit 1
    fi

    print_header "Removing Node: $NODE_HOSTNAME"

    log_warning "This will remove the node and its OSDs from the cluster"
    read -p "Are you sure? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        log_info "Cancelled"
        exit 0
    fi

    log_info "Draining node..."
    cephadm shell -- ceph orch host drain "$NODE_HOSTNAME" || true

    log_info "Waiting for data migration (30 seconds)..."
    sleep 30

    log_info "Removing node from cluster..."
    cephadm shell -- ceph orch host rm "$NODE_HOSTNAME" --force || {
        log_error "Failed to remove node"
        exit 1
    }

    log_success "Node $NODE_HOSTNAME removed"
}

add_osd() {
    local NODE_HOSTNAME=$1

    if [ -z "$NODE_HOSTNAME" ]; then
        log_error "Usage: $0 add-osd <hostname>"
        exit 1
    fi

    print_header "Adding OSD on: $NODE_HOSTNAME"

    # Get node IP
    NODE_IP=$(cephadm shell -- ceph orch host ls 2>/dev/null | grep "^$NODE_HOSTNAME" | awk '{print $2}')

    if [ -z "$NODE_IP" ]; then
        log_error "Could not find IP for $NODE_HOSTNAME. Is node in cluster?"
        exit 1
    fi

    # Find loop device on target node
    log_info "Detecting loop device on $NODE_HOSTNAME ($NODE_IP)..."

    # Check if this is the local node
    LOCAL_IP=$(ip addr show eth1 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d'/' -f1)

    if [ "$NODE_IP" == "$LOCAL_IP" ]; then
        # Local node - no SSH needed
        LOOP_DEV=$(losetup -a | grep osd-disk.img | cut -d: -f1 | head -1 || echo "")
    else
        # Remote node - use SSH
        LOOP_DEV=$(ssh -o StrictHostKeyChecking=no "root@$NODE_IP" "losetup -a | grep osd-disk.img | cut -d: -f1 | head -1" 2>/dev/null || echo "")
    fi

    if [ -z "$LOOP_DEV" ]; then
        log_error "No loop device found on $NODE_HOSTNAME"
        log_error "Run worker setup script on that node first"
        exit 1
    fi

    log_info "Found loop device: $LOOP_DEV"
    log_info "Creating OSD spec for raw mode..."

    # Create a unique service ID based on hostname
    SERVICE_ID="osd-${NODE_HOSTNAME}"

    # Apply OSD spec via stdin (works with loop devices in raw mode)
    log_info "Applying OSD configuration..."
    cat <<EOF | cephadm shell -- ceph orch apply -i -
service_type: osd
service_id: ${SERVICE_ID}
placement:
  hosts:
    - ${NODE_HOSTNAME}
spec:
  data_devices:
    paths:
      - ${LOOP_DEV}
  method: raw
EOF

    if [ $? -ne 0 ]; then
        log_error "Failed to apply OSD spec"
        exit 1
    fi

    log_success "OSD spec applied for $NODE_HOSTNAME using $LOOP_DEV"
    log_info "OSD deployment started, will be ready in ~60 seconds"
    log_info "Check status with: ./ceph-operations.sh list-osds"
}

setup_cephfs() {
    print_header "Setting up CephFS Filesystem"

    # Check if MDS is deployed
    log_info "Deploying MDS (Metadata Servers)..."
    cephadm shell -- ceph orch apply mds "$FS_NAME" --placement="3" || {
        log_warning "MDS deployment initiated"
    }

    log_info "Waiting for MDS to start (60 seconds)..."
    sleep 60

    # Check if filesystem already exists
    if cephadm shell -- ceph fs ls 2>/dev/null | grep -q "$FS_NAME"; then
        log_warning "Filesystem $FS_NAME already exists"
    else
        log_info "Creating CephFS volume: $FS_NAME"
        cephadm shell -- ceph fs volume create "$FS_NAME" || {
            log_error "Failed to create CephFS volume"
            exit 1
        }
        log_success "CephFS filesystem created"
    fi

    # Wait for filesystem to be ready
    log_info "Waiting for filesystem to be ready (30 seconds)..."
    sleep 30

    # Show filesystem status
    log_info "Filesystem status:"
    cephadm shell -- ceph fs status "$FS_NAME"

    log_success "CephFS setup complete"
}

mount_cephfs() {
    local NODE_IP=$1

    if [ -z "$NODE_IP" ]; then
        # Mount on local manager node
        print_header "Mounting CephFS on Manager Node"
        mount_cephfs_local
    else
        # Mount on remote worker node
        print_header "Mounting CephFS on: $NODE_IP"
        mount_cephfs_remote "$NODE_IP"
    fi
}

mount_cephfs_local() {
    # Install ceph-common
    log_info "Installing ceph-common package..."
    apt install -y ceph-common &>/dev/null || {
        log_warning "Could not install ceph-common"
    }

    # Create mount point
    mkdir -p "$CEPHFS_MOUNT"

    # Check if already mounted
    if mountpoint -q "$CEPHFS_MOUNT"; then
        log_warning "$CEPHFS_MOUNT is already mounted"
        return
    fi

    # Get monitor addresses with ports (v1 protocol)
    MON_ADDRS=$(cephadm shell -- ceph mon dump 2>/dev/null | grep "mon\." | grep -oP 'v1:\K[0-9.]+:[0-9]+' | paste -sd,)
    log_info "Monitor addresses: $MON_ADDRS"

    # Get admin keyring
    ADMIN_KEY=$(cephadm shell -- ceph auth get-key client.admin 2>/dev/null)

    if [ -z "$ADMIN_KEY" ]; then
        log_error "Could not get admin key"
        exit 1
    fi

    # Mount CephFS
    log_info "Mounting CephFS at $CEPHFS_MOUNT..."
    mount -t ceph "${MON_ADDRS}:/" "$CEPHFS_MOUNT" -o "name=admin,secret=$ADMIN_KEY" || {
        log_error "Failed to mount CephFS"
        exit 1
    }

    # Add to fstab
    log_info "Adding to /etc/fstab..."
    FSTAB_ENTRY="${MON_ADDRS}:/ ${CEPHFS_MOUNT} ceph name=admin,secret=${ADMIN_KEY},noatime,_netdev 0 0"

    if ! grep -q "$CEPHFS_MOUNT" /etc/fstab; then
        echo "$FSTAB_ENTRY" >> /etc/fstab
    fi

    log_success "CephFS mounted at $CEPHFS_MOUNT"
}

mount_cephfs_remote() {
    local NODE_IP=$1

    # Get mount info - extract monitor addresses with ports (v1 protocol)
    MON_ADDRS=$(cephadm shell -- ceph mon dump 2>/dev/null | grep "mon\." | grep -oP 'v1:\K[0-9.]+:[0-9]+' | paste -sd,)
    ADMIN_KEY=$(cephadm shell -- ceph auth get-key client.admin 2>/dev/null)

    log_info "Copying Ceph configuration to $NODE_IP..."

    # Copy ceph config and keyring to remote node
    scp -o StrictHostKeyChecking=no /etc/ceph/ceph.conf "root@$NODE_IP:/tmp/ceph.conf" || {
        log_error "Failed to copy ceph.conf"
        exit 1
    }

    scp -o StrictHostKeyChecking=no /etc/ceph/ceph.client.admin.keyring "root@$NODE_IP:/tmp/ceph.client.admin.keyring" || {
        log_error "Failed to copy keyring"
        exit 1
    }

    log_info "Mounting CephFS on $NODE_IP..."

    ssh -o StrictHostKeyChecking=no "root@$NODE_IP" bash <<EOF
        set -e

        # Install ceph-common
        apt update -qq && apt install -y ceph-common &>/dev/null || true

        # Create /etc/ceph directory
        mkdir -p /etc/ceph

        # Move config files
        mv /tmp/ceph.conf /etc/ceph/ceph.conf
        mv /tmp/ceph.client.admin.keyring /etc/ceph/ceph.client.admin.keyring
        chmod 600 /etc/ceph/ceph.client.admin.keyring

        # Create mount point
        mkdir -p $CEPHFS_MOUNT

        # Mount if not already mounted
        if ! mountpoint -q $CEPHFS_MOUNT; then
            mount -t ceph "${MON_ADDRS}:/" "$CEPHFS_MOUNT" -o "name=admin,secret=$ADMIN_KEY" || exit 1

            # Add to fstab
            if ! grep -q "$CEPHFS_MOUNT" /etc/fstab; then
                echo "${MON_ADDRS}:/ ${CEPHFS_MOUNT} ceph name=admin,secret=${ADMIN_KEY},noatime,_netdev 0 0" >> /etc/fstab
            fi
        fi

        echo "Mounted successfully"
EOF

    if [ $? -eq 0 ]; then
        log_success "CephFS mounted on $NODE_IP"
    else
        log_error "Failed to mount on $NODE_IP"
        exit 1
    fi
}

setup_odoo_storage() {
    print_header "Setting up Odoo Storage Directories"

    # Ensure CephFS is mounted locally
    if ! mountpoint -q "$CEPHFS_MOUNT"; then
        log_error "$CEPHFS_MOUNT is not mounted. Run: $0 mount-cephfs"
        exit 1
    fi

    log_info "Creating Odoo directories in $CEPHFS_MOUNT..."

    for DIR in "${ODOO_DIRS[@]}"; do
        DIR_PATH="${CEPHFS_MOUNT}/${DIR}"

        if [ -d "$DIR_PATH" ]; then
            log_info "✓ $DIR (exists)"
        else
            log_info "Creating $DIR..."
            mkdir -p "$DIR_PATH"
            chmod 755 "$DIR_PATH"
        fi
    done

    log_success "All Odoo directories created"

    # List directories
    echo ""
    log_info "Created directories:"
    ls -lah "$CEPHFS_MOUNT/" | grep -E "$(IFS=\|; echo "${ODOO_DIRS[*]}")" || true
}

show_status() {
    print_header "Ceph Cluster Status"

    log_info "Cluster Health:"
    cephadm shell -- ceph health detail

    echo ""
    log_info "Cluster Status:"
    cephadm shell -- ceph -s

    echo ""
    log_info "Storage Usage:"
    cephadm shell -- ceph df

    if mountpoint -q "$CEPHFS_MOUNT"; then
        echo ""
        log_info "CephFS Mount:"
        df -h "$CEPHFS_MOUNT"
    fi
}

list_nodes() {
    print_header "Cluster Nodes"

    cephadm shell -- ceph orch host ls
}

list_osds() {
    print_header "OSD Status"

    log_info "OSD Tree:"
    cephadm shell -- ceph osd tree

    echo ""
    log_info "OSD Stats:"
    cephadm shell -- ceph osd stat
}

show_help() {
    echo -e "${BLUE}Ceph Operations Script${NC}"
    echo ""
    echo "Usage: $0 <command> [arguments]"
    echo ""
    echo -e "${GREEN}Node Management:${NC}"
    echo "  add-node <ip>           Add worker node to cluster (prompts for SSH password)"
    echo "  remove-node <hostname>  Remove node from cluster"
    echo "  list-nodes              List all nodes in cluster"
    echo ""
    echo -e "${GREEN}Storage Management:${NC}"
    echo "  add-osd <hostname>      Add OSD storage to a node"
    echo "  list-osds               Show OSD status and topology"
    echo "  setup-cephfs            Create CephFS filesystem (one-time)"
    echo "  mount-cephfs [ip]       Mount CephFS (local if no IP, remote if IP given)"
    echo "  setup-odoo-storage      Create Odoo directories on CephFS"
    echo ""
    echo -e "${GREEN}Monitoring:${NC}"
    echo "  status                  Show cluster health and status"
    echo "  help                    Show this help message"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo "  $0 add-node 10.0.0.1              # Add worker node"
    echo "  $0 setup-cephfs                   # Setup filesystem"
    echo "  $0 mount-cephfs                   # Mount on manager"
    echo "  $0 mount-cephfs 10.0.0.1          # Mount on worker"
    echo "  $0 setup-odoo-storage             # Create Odoo dirs"
    echo "  $0 status                         # Check cluster"
    echo ""
}

#############################################
# Main Script
#############################################

main() {
    local COMMAND=$1
    shift || true

    # Don't check root/ceph for help command
    if [ "$COMMAND" == "help" ] || [ "$COMMAND" == "--help" ] || [ "$COMMAND" == "-h" ]; then
        show_help
        exit 0
    fi

    check_root
    check_ceph

    case "$COMMAND" in
        add-node)
            add_node "$@"
            ;;
        remove-node)
            remove_node "$@"
            ;;
        add-osd)
            add_osd "$@"
            ;;
        setup-cephfs)
            setup_cephfs
            ;;
        mount-cephfs)
            mount_cephfs "$@"
            ;;
        setup-odoo-storage)
            setup_odoo_storage
            ;;
        status)
            show_status
            ;;
        list-nodes)
            list_nodes
            ;;
        list-osds)
            list_osds
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            log_error "No command specified"
            echo ""
            show_help
            exit 1
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
