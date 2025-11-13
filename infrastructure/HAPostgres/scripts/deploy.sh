#!/bin/bash

# ============================================================================
# PostgreSQL HA Cluster Deployment Script
# ============================================================================
# This script deploys the HA PostgreSQL cluster to Docker Swarm

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "==========================================================================="
echo "PostgreSQL HA Cluster - Deployment"
echo "==========================================================================="
echo ""

# ----------------------------------------------------------------------------
# Pre-deployment checks
# ----------------------------------------------------------------------------
echo "Running pre-deployment checks..."
echo "-------------------------------"

# Check if Docker Swarm is active
if ! docker info 2>/dev/null | grep -q "Swarm: active"; then
    echo "❌ ERROR: Docker Swarm is not active"
    echo "Please initialize or join a Swarm cluster first"
    exit 1
fi
echo "✓ Docker Swarm is active"

# Check if running on manager node
if ! docker node ls >/dev/null 2>&1; then
    echo "❌ ERROR: This script must be run on a Swarm manager node"
    exit 1
fi
echo "✓ Running on Swarm manager node"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found"
    echo "Please copy .env.example to .env and configure passwords"
    exit 1
fi
echo "✓ .env file exists"

# Check if node labels are set
NODE_LABELS=$(docker node ls --format "{{.Hostname}}: {{.Labels}}" | grep -E "patroni|etcd" | wc -l)
if [ "$NODE_LABELS" -lt 3 ]; then
    echo "⚠ WARNING: Node labels may not be properly configured"
    echo "Expected at least 3 nodes with patroni/etcd labels"
    echo ""
    docker node ls --format "table {{.Hostname}}\t{{.Labels}}"
    echo ""
    read -p "Continue anyway? (yes/no): " CONTINUE
    if [ "$CONTINUE" != "yes" ]; then
        echo "Deployment cancelled"
        exit 0
    fi
else
    echo "✓ Node labels configured"
fi

# Check if data directories exist (best effort check)
echo ""
echo "⚠ Please verify that data directories exist on all nodes:"
echo "  /var/lib/patroni/node1"
echo "  /var/lib/patroni/node2"
echo "  /var/lib/patroni/node3"
echo ""
read -p "Have you verified data directories exist? (yes/no): " VERIFIED
if [ "$VERIFIED" != "yes" ]; then
    echo "Please create data directories first using setup.sh"
    exit 0
fi

echo ""
echo "✓ Pre-deployment checks passed"
echo ""

# ----------------------------------------------------------------------------
# Deployment confirmation
# ----------------------------------------------------------------------------
echo "Deployment Configuration:"
echo "------------------------"
echo "Stack name: saasodoo-db-infra"
echo "Compose file: docker-compose.infra.yml"
echo ""
echo "Services to be deployed:"
echo "  - etcd cluster (3 nodes)"
echo "  - Patroni cluster (3 PostgreSQL nodes)"
echo "  - PgBouncer (3 replicas)"
echo "  - HAProxy (2 replicas)"
echo ""

read -p "Deploy the stack now? (yes/no): " DEPLOY
if [ "$DEPLOY" != "yes" ]; then
    echo "Deployment cancelled"
    exit 0
fi

# ----------------------------------------------------------------------------
# Deploy the stack
# ----------------------------------------------------------------------------
echo ""
echo "Deploying stack..."
echo "-----------------"

docker stack deploy -c docker-compose.infra.yml saasodoo-db-infra

echo ""
echo "✓ Stack deployment initiated"
echo ""

# ----------------------------------------------------------------------------
# Wait for services to start
# ----------------------------------------------------------------------------
echo "Waiting for services to start (this may take 1-2 minutes)..."
echo "-----------------------------------------------------------"
echo ""

sleep 10

# Monitor service status
for i in {1..24}; do
    echo "Check $i/24..."
    docker stack services saasodoo-db-infra
    echo ""

    # Check if all services are running
    RUNNING=$(docker stack services saasodoo-db-infra --format "{{.Replicas}}" | grep -v "0/" | wc -l)
    TOTAL=$(docker stack services saasodoo-db-infra | tail -n +2 | wc -l)

    if [ "$RUNNING" -eq "$TOTAL" ]; then
        echo "✓ All services are running!"
        break
    fi

    if [ "$i" -eq 24 ]; then
        echo "⚠ Services are still starting. Check status with:"
        echo "  docker stack services saasodoo-db-infra"
        echo "  docker service logs saasodoo-db-infra_<service_name>"
        break
    fi

    sleep 5
done

# ----------------------------------------------------------------------------
# Verify etcd cluster
# ----------------------------------------------------------------------------
echo ""
echo "Verifying etcd cluster..."
echo "------------------------"

sleep 5

ETCD_CONTAINER=$(docker ps -q -f name=saasodoo-db-infra_etcd1 | head -n 1)
if [ -n "$ETCD_CONTAINER" ]; then
    echo "etcd cluster members:"
    docker exec "$ETCD_CONTAINER" etcdctl member list 2>/dev/null || echo "⚠ etcd not ready yet"
else
    echo "⚠ etcd containers not found yet"
fi

# ----------------------------------------------------------------------------
# Verify Patroni cluster
# ----------------------------------------------------------------------------
echo ""
echo "Verifying Patroni cluster..."
echo "---------------------------"

sleep 5

PATRONI_CONTAINER=$(docker ps -q -f name=saasodoo-db-infra_patroni-node | head -n 1)
if [ -n "$PATRONI_CONTAINER" ]; then
    echo "Patroni cluster status:"
    docker exec "$PATRONI_CONTAINER" patronictl list 2>/dev/null || echo "⚠ Patroni not ready yet - cluster is initializing"
else
    echo "⚠ Patroni containers not found yet"
fi

# ----------------------------------------------------------------------------
# Connection information
# ----------------------------------------------------------------------------
echo ""
echo "==========================================================================="
echo "Deployment Complete!"
echo "==========================================================================="
echo ""
echo "Connection Information:"
echo "----------------------"
echo ""
echo "Applications should connect to:"
echo "  Host: haproxy"
echo "  Port: 6432"
echo "  Connection string: postgresql://user:password@haproxy:6432/dbname"
echo ""
echo "Alternative direct connections:"
echo "  PostgreSQL Primary: haproxy:5000"
echo "  PostgreSQL Replicas (read-only): haproxy:5001"
echo ""
echo "Management URLs:"
echo "  HAProxy Stats: http://<any-node-ip>:7000/stats"
echo "  Patroni API: http://<any-node-ip>:8008/cluster"
echo ""
echo "Useful Commands:"
echo "---------------"
echo ""
echo "Check stack status:"
echo "  docker stack ps saasodoo-db-infra"
echo ""
echo "Check service logs:"
echo "  docker service logs saasodoo-db-infra_patroni-node1"
echo "  docker service logs saasodoo-db-infra_pgbouncer"
echo "  docker service logs saasodoo-db-infra_haproxy"
echo ""
echo "Check Patroni cluster:"
echo "  docker exec \$(docker ps -q -f name=saasodoo-db-infra_patroni-node1) patronictl list"
echo ""
echo "Connect to PostgreSQL via PgBouncer:"
echo "  docker exec -it \$(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -1) \\"
echo "    psql -h localhost -p 6432 -U postgres -d postgres"
echo ""
echo "Test failover:"
echo "  docker exec \$(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \\"
echo "    patronictl failover saasodoo-cluster"
echo ""
echo "==========================================================================="
echo ""
echo "⚠ IMPORTANT: Update your application services to use:"
echo "  POSTGRES_HOST=haproxy"
echo "  POSTGRES_PORT=6432"
echo ""
echo "Your application stack must join the 'saasodoo-database-network' network"
echo "==========================================================================="
