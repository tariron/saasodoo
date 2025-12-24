#!/bin/bash

# Teardown SaaSOdoo from Kubernetes
# This script removes all resources from the saasodoo namespace

set -e

echo "============================================"
echo "Tearing Down SaaSOdoo from Kubernetes"
echo "============================================"

echo ""
echo "WARNING: This will delete all resources in the 'saasodoo' namespace!"
read -p "Are you sure? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Teardown cancelled."
    exit 0
fi

echo ""
echo "Deleting namespace 'saasodoo' and all resources..."
kubectl delete namespace saasodoo --timeout=180s || true

echo ""
echo "Deleting PersistentVolumes..."
kubectl delete pv postgres-data-pv redis-data-pv rabbitmq-data-pv killbill-db-data-pv odoo-instances-pv odoo-backups-pv pgadmin-data-pv --ignore-not-found=true || true

echo ""
echo "============================================"
echo "✓ Teardown completed!"
echo "============================================"
