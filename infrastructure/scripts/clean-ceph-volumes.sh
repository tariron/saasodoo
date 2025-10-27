#!/bin/bash
# Clean all CephFS-backed volumes for fresh start

set -e

CEPH_MOUNT="/mnt/cephfs"

echo "⚠️  WARNING: This will DELETE all data in CephFS volumes!"
echo "Volumes to be cleaned:"
echo "  - ${CEPH_MOUNT}/postgres_data"
echo "  - ${CEPH_MOUNT}/redis_data"
echo "  - ${CEPH_MOUNT}/rabbitmq_data"
echo "  - ${CEPH_MOUNT}/prometheus_data"
echo "  - ${CEPH_MOUNT}/killbill_db_data"
echo "  - ${CEPH_MOUNT}/odoo_instances"
echo "  - ${CEPH_MOUNT}/odoo_backups"
echo ""
read -p "Are you sure? (y/n): " confirm

if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

echo "🧹 Cleaning CephFS volumes..."

# Stop containers first
echo "Stopping containers..."
docker compose -f infrastructure/compose/docker-compose.ceph.yml down

# Remove Docker volumes first (releases bind mounts)
docker volume rm compose_postgres-data 2>/dev/null || true

# Remove data directories
sudo find ${CEPH_MOUNT}/postgres_data -mindepth 1 -delete
sudo rm -rf ${CEPH_MOUNT}/redis_data/*
sudo rm -rf ${CEPH_MOUNT}/rabbitmq_data/*
sudo rm -rf ${CEPH_MOUNT}/prometheus_data/*
sudo rm -rf ${CEPH_MOUNT}/killbill_db_data/*
sudo rm -rf ${CEPH_MOUNT}/odoo_instances/*
sudo rm -rf ${CEPH_MOUNT}/odoo_backups/*

# Remove remaining Docker volumes (metadata only)
docker volume rm compose_redis-data 2>/dev/null || true
docker volume rm compose_rabbitmq-data 2>/dev/null || true
docker volume rm compose_prometheus-data 2>/dev/null || true
docker volume rm compose_killbill-db-data 2>/dev/null || true
docker volume rm compose_odoo-instances 2>/dev/null || true
docker volume rm compose_odoo-backups 2>/dev/null || true

echo "✅ CephFS volumes cleaned successfully!"
echo "Now you can run: docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d"
