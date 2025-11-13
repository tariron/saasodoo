#!/bin/bash

# ============================================================================
# PostgreSQL HA Cluster Status Script
# ============================================================================
# Quick cluster health check and status overview

set -e

echo "==========================================================================="
echo "PostgreSQL HA Cluster - Status Check"
echo "==========================================================================="
echo ""

# ----------------------------------------------------------------------------
# Check if stack is deployed
# ----------------------------------------------------------------------------
if ! docker stack ls | grep -q "saasodoo-db-infra"; then
    echo "❌ Stack 'saasodoo-db-infra' is not deployed"
    echo ""
    echo "Deploy with: ./scripts/deploy.sh"
    exit 1
fi

echo "✓ Stack is deployed"
echo ""

# ----------------------------------------------------------------------------
# Service Status
# ----------------------------------------------------------------------------
echo "Service Status:"
echo "---------------"
docker stack services saasodoo-db-infra
echo ""

# ----------------------------------------------------------------------------
# etcd Cluster Health
# ----------------------------------------------------------------------------
echo "etcd Cluster Health:"
echo "-------------------"
ETCD_CONTAINER=$(docker ps -q -f name=saasodoo-db-infra_etcd1 | head -n 1)
if [ -n "$ETCD_CONTAINER" ]; then
    docker exec "$ETCD_CONTAINER" etcdctl member list 2>/dev/null || echo "⚠ etcd not responding"
else
    echo "⚠ etcd containers not found"
fi
echo ""

# ----------------------------------------------------------------------------
# Patroni Cluster Status
# ----------------------------------------------------------------------------
echo "Patroni Cluster Status:"
echo "----------------------"
PATRONI_CONTAINER=$(docker ps -q -f name=saasodoo-db-infra_patroni-node | head -n 1)
if [ -n "$PATRONI_CONTAINER" ]; then
    docker exec "$PATRONI_CONTAINER" patronictl list 2>/dev/null || echo "⚠ Patroni not responding"
else
    echo "⚠ Patroni containers not found"
fi
echo ""

# ----------------------------------------------------------------------------
# PgBouncer Status
# ----------------------------------------------------------------------------
echo "PgBouncer Pool Status:"
echo "---------------------"
PGBOUNCER_CONTAINER=$(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -n 1)
if [ -n "$PGBOUNCER_CONTAINER" ]; then
    docker exec "$PGBOUNCER_CONTAINER" psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;" 2>/dev/null || echo "⚠ PgBouncer not responding"
else
    echo "⚠ PgBouncer containers not found"
fi
echo ""

# ----------------------------------------------------------------------------
# Connection Test
# ----------------------------------------------------------------------------
echo "Connection Test:"
echo "---------------"
if [ -n "$PGBOUNCER_CONTAINER" ]; then
    if docker exec "$PGBOUNCER_CONTAINER" psql -h localhost -p 6432 -U postgres -d postgres -c "SELECT version();" >/dev/null 2>&1; then
        echo "✓ Successfully connected to PostgreSQL via PgBouncer"
    else
        echo "❌ Failed to connect to PostgreSQL via PgBouncer"
    fi
else
    echo "⚠ Cannot test connection - no PgBouncer container found"
fi
echo ""

# ----------------------------------------------------------------------------
# Resource Usage
# ----------------------------------------------------------------------------
echo "Resource Usage (top 5 containers):"
echo "----------------------------------"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    $(docker ps -q -f name=saasodoo-db-infra) | head -n 6
echo ""

# ----------------------------------------------------------------------------
# Recent Events
# ----------------------------------------------------------------------------
echo "Recent Service Events (last 10):"
echo "--------------------------------"
docker stack ps saasodoo-db-infra --format "table {{.Name}}\t{{.CurrentState}}\t{{.Error}}" | head -n 11
echo ""

# ----------------------------------------------------------------------------
# Quick Commands
# ----------------------------------------------------------------------------
echo "==========================================================================="
echo "Quick Commands:"
echo "==========================================================================="
echo ""
echo "View logs:"
echo "  docker service logs -f saasodoo-db-infra_patroni-node1"
echo ""
echo "Connect to database:"
echo "  docker exec -it \$(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -1) \\"
echo "    psql -h localhost -p 6432 -U postgres"
echo ""
echo "HAProxy stats:"
echo "  http://\$(docker node inspect self --format '{{.Status.Addr}}'):7000/stats"
echo ""
echo "Test failover:"
echo "  docker exec \$(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \\"
echo "    patronictl failover saasodoo-cluster --force"
echo ""
echo "==========================================================================="
