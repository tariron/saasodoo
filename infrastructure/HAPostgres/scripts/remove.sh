#!/bin/bash

# ============================================================================
# PostgreSQL HA Cluster Removal Script
# ============================================================================
# Removes the HA PostgreSQL stack and optionally cleans up data

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "==========================================================================="
echo "PostgreSQL HA Cluster - Stack Removal"
echo "==========================================================================="
echo ""
echo "⚠️  WARNING: This will remove the HA PostgreSQL stack"
echo ""

# ----------------------------------------------------------------------------
# Check if stack exists
# ----------------------------------------------------------------------------
if ! docker stack ls | grep -q "saasodoo-db-infra"; then
    echo "Stack 'saasodoo-db-infra' is not deployed"
    exit 0
fi

# ----------------------------------------------------------------------------
# Confirm removal
# ----------------------------------------------------------------------------
echo "Current stack services:"
docker stack services saasodoo-db-infra
echo ""

read -p "Remove the stack? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

# ----------------------------------------------------------------------------
# Remove stack
# ----------------------------------------------------------------------------
echo ""
echo "Removing stack..."
docker stack rm saasodoo-db-infra

echo ""
echo "✓ Stack removal initiated"
echo ""
echo "Waiting for services to shut down (this may take 30-60 seconds)..."

# Wait for services to fully stop
for i in {1..30}; do
    REMAINING=$(docker ps -q -f name=saasodoo-db-infra | wc -l)
    if [ "$REMAINING" -eq 0 ]; then
        echo "✓ All services stopped"
        break
    fi
    echo "  $REMAINING containers still running..."
    sleep 2
done

# ----------------------------------------------------------------------------
# Optional: Clean up volumes
# ----------------------------------------------------------------------------
echo ""
echo "Volume cleanup options:"
echo "----------------------"
echo ""
echo "⚠️  WARNING: Deleting volumes will PERMANENTLY DELETE all database data!"
echo ""
echo "Options:"
echo "  1) Keep all data (volumes and data directories)"
echo "  2) Remove Docker volumes only (etcd data)"
echo "  3) Remove everything (Docker volumes + PostgreSQL data directories)"
echo ""

read -p "Choose option (1/2/3): " CLEANUP_OPTION

case $CLEANUP_OPTION in
    1)
        echo "✓ Keeping all data"
        ;;
    2)
        echo ""
        echo "Removing Docker volumes..."
        docker volume rm saasodoo-db-infra_etcd1-data 2>/dev/null || echo "  Volume already removed or not found"
        docker volume rm saasodoo-db-infra_etcd2-data 2>/dev/null || echo "  Volume already removed or not found"
        docker volume rm saasodoo-db-infra_etcd3-data 2>/dev/null || echo "  Volume already removed or not found"
        echo "✓ Docker volumes removed"
        echo ""
        echo "PostgreSQL data directories preserved at:"
        echo "  /var/lib/patroni/node1"
        echo "  /var/lib/patroni/node2"
        echo "  /var/lib/patroni/node3"
        ;;
    3)
        echo ""
        echo "⚠️  FINAL WARNING: This will DELETE ALL DATABASE DATA!"
        read -p "Type 'DELETE ALL DATA' to confirm: " FINAL_CONFIRM

        if [ "$FINAL_CONFIRM" == "DELETE ALL DATA" ]; then
            echo ""
            echo "Removing Docker volumes..."
            docker volume rm saasodoo-db-infra_etcd1-data 2>/dev/null || true
            docker volume rm saasodoo-db-infra_etcd2-data 2>/dev/null || true
            docker volume rm saasodoo-db-infra_etcd3-data 2>/dev/null || true
            echo "✓ Docker volumes removed"

            echo ""
            echo "To remove PostgreSQL data directories, run on each node:"
            echo ""
            echo "On node with patroni=node1:"
            echo "  sudo rm -rf /var/lib/patroni/node1"
            echo ""
            echo "On node with patroni=node2:"
            echo "  sudo rm -rf /var/lib/patroni/node2"
            echo ""
            echo "On node with patroni=node3:"
            echo "  sudo rm -rf /var/lib/patroni/node3"
            echo ""

            read -p "Attempt to remove data directories automatically? (yes/no): " AUTO_REMOVE

            if [ "$AUTO_REMOVE" == "yes" ]; then
                echo ""
                echo "Attempting to remove data directories..."

                # Get node labels
                NODE1=$(docker node ls --filter "label=patroni=node1" --format "{{.Hostname}}" | head -n 1)
                NODE2=$(docker node ls --filter "label=patroni=node2" --format "{{.Hostname}}" | head -n 1)
                NODE3=$(docker node ls --filter "label=patroni=node3" --format "{{.Hostname}}" | head -n 1)

                if [ -n "$NODE1" ]; then
                    echo "Removing data on $NODE1..."
                    ssh "$NODE1" "sudo rm -rf /var/lib/patroni/node1" 2>/dev/null || echo "  ⚠ Failed - please remove manually"
                fi

                if [ -n "$NODE2" ]; then
                    echo "Removing data on $NODE2..."
                    ssh "$NODE2" "sudo rm -rf /var/lib/patroni/node2" 2>/dev/null || echo "  ⚠ Failed - please remove manually"
                fi

                if [ -n "$NODE3" ]; then
                    echo "Removing data on $NODE3..."
                    ssh "$NODE3" "sudo rm -rf /var/lib/patroni/node3" 2>/dev/null || echo "  ⚠ Failed - please remove manually"
                fi

                echo "✓ Data directory removal attempted"
            fi
        else
            echo "Data deletion cancelled - volumes and data directories preserved"
        fi
        ;;
    *)
        echo "Invalid option - keeping all data"
        ;;
esac

# ----------------------------------------------------------------------------
# Optional: Remove node labels
# ----------------------------------------------------------------------------
echo ""
read -p "Remove node labels (patroni, etcd)? (yes/no): " REMOVE_LABELS

if [ "$REMOVE_LABELS" == "yes" ]; then
    echo ""
    echo "Removing node labels..."

    for node in $(docker node ls --format "{{.Hostname}}"); do
        docker node update --label-rm patroni "$node" 2>/dev/null || true
        docker node update --label-rm etcd "$node" 2>/dev/null || true
    done

    echo "✓ Node labels removed"
fi

# ----------------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------------
echo ""
echo "==========================================================================="
echo "Stack Removal Complete"
echo "==========================================================================="
echo ""
echo "The HA PostgreSQL stack has been removed."
echo ""
echo "To redeploy:"
echo "  ./scripts/deploy.sh"
echo ""
echo "==========================================================================="
