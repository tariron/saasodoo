#!/bin/bash

# ============================================================================
# PostgreSQL HA Cluster Setup Script
# ============================================================================
# This script prepares your Docker Swarm nodes for the HA PostgreSQL cluster
# Run this script on your Swarm manager node

set -e

echo "==========================================================================="
echo "PostgreSQL HA Cluster - Node Setup"
echo "==========================================================================="
echo ""

# ----------------------------------------------------------------------------
# Check if running on Swarm manager
# ----------------------------------------------------------------------------
if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
    echo "ERROR: This node is not part of a Docker Swarm cluster"
    echo "Please initialize or join a Swarm cluster first:"
    echo "  docker swarm init --advertise-addr <MANAGER-IP>"
    exit 1
fi

if ! docker node ls >/dev/null 2>&1; then
    echo "ERROR: This script must be run on a Swarm manager node"
    exit 1
fi

echo "✓ Docker Swarm is active and this is a manager node"
echo ""

# ----------------------------------------------------------------------------
# List available nodes
# ----------------------------------------------------------------------------
echo "Available Swarm nodes:"
echo "---------------------"
docker node ls
echo ""

# ----------------------------------------------------------------------------
# Get node IDs for labeling
# ----------------------------------------------------------------------------
echo "Please provide the node IDs or hostnames for the cluster:"
echo ""

read -p "Enter node ID/hostname for Patroni Node 1 (press Enter for current node): " NODE1
read -p "Enter node ID/hostname for Patroni Node 2: " NODE2
read -p "Enter node ID/hostname for Patroni Node 3: " NODE3

# Use current node if NODE1 is empty
if [ -z "$NODE1" ]; then
    NODE1=$(docker node ls --filter "role=manager" --format "{{.Hostname}}" | head -n 1)
    echo "Using current node: $NODE1"
fi

echo ""
echo "You selected:"
echo "  Patroni/etcd Node 1: $NODE1"
echo "  Patroni/etcd Node 2: $NODE2"
echo "  Patroni/etcd Node 3: $NODE3"
echo ""

read -p "Is this correct? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Setup cancelled"
    exit 0
fi

# ----------------------------------------------------------------------------
# Apply node labels
# ----------------------------------------------------------------------------
echo ""
echo "Applying node labels..."
echo "----------------------"

docker node update --label-add patroni=node1 "$NODE1"
docker node update --label-add etcd=node1 "$NODE1"
echo "✓ Labeled $NODE1 as patroni=node1, etcd=node1"

docker node update --label-add patroni=node2 "$NODE2"
docker node update --label-add etcd=node2 "$NODE2"
echo "✓ Labeled $NODE2 as patroni=node2, etcd=node2"

docker node update --label-add patroni=node3 "$NODE3"
docker node update --label-add etcd=node3 "$NODE3"
echo "✓ Labeled $NODE3 as patroni=node3, etcd=node3"

echo ""
echo "Node labels applied successfully!"
echo ""

# ----------------------------------------------------------------------------
# Create data directories on each node
# ----------------------------------------------------------------------------
echo "Creating Patroni data directories on each node..."
echo "------------------------------------------------"
echo ""
echo "IMPORTANT: The following directories need to be created on each node:"
echo ""
echo "On $NODE1:"
echo "  sudo mkdir -p /var/lib/patroni/node1"
echo "  sudo chown -R 999:999 /var/lib/patroni/node1"
echo ""
echo "On $NODE2:"
echo "  sudo mkdir -p /var/lib/patroni/node2"
echo "  sudo chown -R 999:999 /var/lib/patroni/node2"
echo ""
echo "On $NODE3:"
echo "  sudo mkdir -p /var/lib/patroni/node3"
echo "  sudo chown -R 999:999 /var/lib/patroni/node3"
echo ""

read -p "Would you like to create these directories automatically? (yes/no): " CREATE_DIRS

if [ "$CREATE_DIRS" == "yes" ]; then
    echo ""
    echo "Creating directories on each node..."

    # Create on node1
    docker node ps "$NODE1" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        ssh_host=$(docker node inspect "$NODE1" --format '{{.Description.Hostname}}')
        echo "Creating directory on $NODE1 ($ssh_host)..."
        ssh "$ssh_host" "sudo mkdir -p /var/lib/patroni/node1 && sudo chown -R 999:999 /var/lib/patroni/node1" || echo "  ⚠ Failed - please create manually"
    fi

    # Create on node2
    ssh_host=$(docker node inspect "$NODE2" --format '{{.Description.Hostname}}')
    echo "Creating directory on $NODE2 ($ssh_host)..."
    ssh "$ssh_host" "sudo mkdir -p /var/lib/patroni/node2 && sudo chown -R 999:999 /var/lib/patroni/node2" || echo "  ⚠ Failed - please create manually"

    # Create on node3
    ssh_host=$(docker node inspect "$NODE3" --format '{{.Description.Hostname}}')
    echo "Creating directory on $NODE3 ($ssh_host)..."
    ssh "$ssh_host" "sudo mkdir -p /var/lib/patroni/node3 && sudo chown -R 999:999 /var/lib/patroni/node3" || echo "  ⚠ Failed - please create manually"

    echo ""
    echo "✓ Directory creation complete (check for any errors above)"
else
    echo ""
    echo "⚠ Please create these directories manually on each node before deploying"
fi

# ----------------------------------------------------------------------------
# Create environment file
# ----------------------------------------------------------------------------
echo ""
echo "Setting up environment file..."
echo "-----------------------------"

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "✓ Created .env from .env.example"
        echo ""
        echo "IMPORTANT: Edit the .env file and set secure passwords!"
        echo "  nano .env"
        echo ""
        echo "Generate secure passwords using:"
        echo "  openssl rand -base64 32"
    else
        echo "⚠ .env.example not found - please create .env manually"
    fi
else
    echo "✓ .env file already exists"
fi

# ----------------------------------------------------------------------------
# Verify network connectivity
# ----------------------------------------------------------------------------
echo ""
echo "Verifying network connectivity between nodes..."
echo "----------------------------------------------"

MANAGER_IP=$(docker node inspect self --format '{{.ManagerStatus.Addr}}' | cut -d: -f1)
echo "Manager IP: $MANAGER_IP"
echo ""

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
echo "==========================================================================="
echo "Setup Complete!"
echo "==========================================================================="
echo ""
echo "Node labels have been applied:"
echo "  $NODE1: patroni=node1, etcd=node1"
echo "  $NODE2: patroni=node2, etcd=node2"
echo "  $NODE3: patroni=node3, etcd=node3"
echo ""
echo "Next steps:"
echo "  1. Verify data directories exist on all nodes:"
echo "     /var/lib/patroni/node1 (on $NODE1)"
echo "     /var/lib/patroni/node2 (on $NODE2)"
echo "     /var/lib/patroni/node3 (on $NODE3)"
echo ""
echo "  2. Edit .env and set secure passwords"
echo ""
echo "  3. Deploy the stack:"
echo "     cd infrastructure/HAPostgres"
echo "     ./scripts/deploy.sh"
echo ""
echo "==========================================================================="
