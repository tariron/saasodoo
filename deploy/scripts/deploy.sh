#!/bin/bash
# Layered Kubernetes Deployment Script for SaaSOdoo
# This script deploys the entire platform in a specific order to ensure dependencies are met

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEPLOY_ROOT="$PROJECT_ROOT/deploy"
INFRA_ROOT="$PROJECT_ROOT/infrastructure"

echo "========================================="
echo "SaaSOdoo Kubernetes Deployment"
echo "========================================="
echo "Project Root: $PROJECT_ROOT"
echo "Deploy Manifests: $DEPLOY_ROOT"
echo "Infrastructure: $INFRA_ROOT"
echo ""

# Layer 0: Foundation (Namespaces, Secrets, RBAC)
echo "Layer 0: Foundation (Namespaces, Secrets, RBAC)"
echo "-----------------------------------------------------"
kubectl apply -f "$DEPLOY_ROOT/00-namespace.yaml"
kubectl apply -f "$DEPLOY_ROOT/00-secrets.yaml"
kubectl apply -f "$DEPLOY_ROOT/00-shared-config.yaml"
kubectl apply -f "$DEPLOY_ROOT/01-rbac.yaml"
echo "Layer 0 complete"
echo ""

# Layer 1: Storage
echo "Layer 1: Storage"
echo "-----------------------------------------------------"
kubectl apply -f "$INFRA_ROOT/storage/00-storageclass.yaml" 2>/dev/null || true
echo "Layer 1 complete"
echo ""

# Layer 2: Networking (MetalLB + Traefik)
echo "Layer 2: Networking (MetalLB + Traefik)"
echo "-----------------------------------------------------"
echo "  Applying MetalLB..."
kubectl apply -f "$INFRA_ROOT/networking/metallb/" 2>/dev/null || true
echo "  Installing Traefik CRDs..."
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.0/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml 2>/dev/null || true
echo "  Waiting for CRDs..."
sleep 5
kubectl apply -f "$INFRA_ROOT/networking/traefik/"
echo "  Waiting for Traefik..."
kubectl wait --for=condition=available --timeout=120s deployment/traefik -n saasodoo 2>/dev/null || true
echo "Layer 2 complete"
echo ""

# Layer 3: Databases (PostgreSQL, Redis, RabbitMQ)
echo "Layer 3: Databases (PostgreSQL, Redis, RabbitMQ)"
echo "-----------------------------------------------------"
# PostgreSQL (CNPG)
echo "  Deploying CloudNativePG PostgreSQL..."
kubectl apply -f "$INFRA_ROOT/databases/postgres-cnpg/"
echo "  Waiting for PostgreSQL cluster..."
kubectl wait --for=condition=ready --timeout=300s cluster/postgres-cluster -n saasodoo 2>/dev/null || true

# Redis
echo "  Deploying Redis..."
kubectl apply -f "$INFRA_ROOT/databases/redis/"
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=redis -n saasodoo 2>/dev/null || true

# RabbitMQ
echo "  Deploying RabbitMQ..."
kubectl apply -f "$INFRA_ROOT/databases/rabbitmq/"
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=rabbitmq -n saasodoo 2>/dev/null || true
echo "Layer 3 complete"
echo ""

# Layer 4: Platform Services
echo "Layer 4: Platform Services"
echo "-----------------------------------------------------"

# KillBill (MariaDB + KillBill + Kaui)
echo "  Deploying KillBill stack..."
kubectl apply -f "$DEPLOY_ROOT/platform/killbill/"
kubectl wait --for=condition=available --timeout=300s deployment/killbill -n saasodoo 2>/dev/null || true

# User Service
echo "  Deploying user-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/user-service/"
kubectl wait --for=condition=available --timeout=120s deployment/user-service -n saasodoo 2>/dev/null || true

# Billing Service
echo "  Deploying billing-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/billing-service/"
kubectl wait --for=condition=available --timeout=120s deployment/billing-service -n saasodoo 2>/dev/null || true

# Instance Service & Worker
echo "  Deploying instance-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/instance-service/"
kubectl apply -f "$DEPLOY_ROOT/platform/instance-worker/"
kubectl wait --for=condition=available --timeout=120s deployment/instance-service -n saasodoo 2>/dev/null || true
kubectl wait --for=condition=available --timeout=120s deployment/instance-worker -n saasodoo 2>/dev/null || true

# Database Service & Worker
echo "  Deploying database-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/database-service/"
kubectl apply -f "$DEPLOY_ROOT/platform/database-worker/"
kubectl apply -f "$DEPLOY_ROOT/platform/database-beat/"
kubectl wait --for=condition=available --timeout=120s deployment/database-service -n saasodoo 2>/dev/null || true

# Notification Service
echo "  Deploying notification-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/notification-service/"
kubectl apply -f "$DEPLOY_ROOT/platform/notification-worker/" 2>/dev/null || true
kubectl wait --for=condition=available --timeout=120s deployment/notification-service -n saasodoo 2>/dev/null || true

# Frontend Service
echo "  Deploying frontend-service..."
kubectl apply -f "$DEPLOY_ROOT/platform/frontend-service/"
kubectl wait --for=condition=available --timeout=120s deployment/frontend-service -n saasodoo 2>/dev/null || true

# MailHog (Development)
echo "  Deploying mailhog..."
kubectl apply -f "$DEPLOY_ROOT/platform/mailhog/" 2>/dev/null || true

echo "Layer 4 complete"
echo ""

# Deployment Summary
echo "========================================="
echo "DEPLOYMENT COMPLETE"
echo "========================================="
echo ""
echo "Check status:"
echo "  kubectl get pods -n saasodoo"
echo "  kubectl get svc -n saasodoo"
echo ""
echo "Access URLs (via Traefik):"
echo "  - Frontend:    http://app.62.171.153.219.nip.io"
echo "  - API:         http://api.62.171.153.219.nip.io"
echo "  - KillBill:    http://billing.62.171.153.219.nip.io"
echo "  - Kaui Admin:  http://billing-admin.62.171.153.219.nip.io"
echo ""
