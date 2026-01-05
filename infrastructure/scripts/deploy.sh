#!/bin/bash
# Layered Kubernetes Deployment Script for SaaSOdoo
# This script deploys the entire platform in a specific order to ensure dependencies are met

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "SaaSOdoo Kubernetes Deployment"
echo "========================================="
echo "Kubernetes Manifests: $K8S_ROOT"
echo ""

# Layer 0: Foundation (Namespaces, Secrets, Storage)
echo "📦 LAYER 0: Foundation (Namespaces, Secrets, Storage)"
echo "-----------------------------------------------------"
kubectl apply -f "$K8S_ROOT/infrastructure/00-namespace.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/00-secrets.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/00-configmap.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/01-rbac.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/storage/00-storageclass.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/storage/01-persistent-volumes.yaml"
echo "✅ Layer 0 complete"
echo ""

# Layer 1: Networking (Traefik)
echo "📦 LAYER 1: Networking (Traefik v3)"
echo "-----------------------------------------------------"
echo "  Installing official Traefik v3.0 CRDs..."
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.0/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
echo "⏳ Waiting for CRDs to be established..."
sleep 5
kubectl apply -f "$K8S_ROOT/infrastructure/networking/traefik/01-rbac.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/networking/traefik/02-configmap.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/networking/traefik/03-deployment.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/networking/traefik/04-service.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/networking/traefik/05-dashboard.yaml"
echo "⏳ Waiting for Traefik to be ready..."
kubectl wait --for=condition=available --timeout=120s deployment/traefik -n saasodoo
echo "✅ Layer 1 complete"
echo ""

# Layer 2: Image Building (Manual Step)
echo "📦 LAYER 2: Custom Image Building"
echo "-----------------------------------------------------"
echo "⚠️  MANUAL STEP REQUIRED:"
echo "   Run: $SCRIPT_DIR/build-and-push.sh"
echo "   This builds and pushes custom images (saasodoo-postgres, saasodoo-redis)"
echo ""
read -p "Have you run build-and-push.sh? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Please run build-and-push.sh first, then re-run this script"
    exit 1
fi
echo "✅ Layer 2 confirmed"
echo ""

# Layer 3: Infrastructure (Postgres, Redis, RabbitMQ)
echo "📦 LAYER 3: Infrastructure (Databases & Message Queue)"
echo "-----------------------------------------------------"
# PostgreSQL
kubectl apply -f "$K8S_ROOT/infrastructure/postgres/01-pvc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/postgres/02-configmap.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/postgres/03-statefulset.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/postgres/04-service.yaml"

# Redis
kubectl apply -f "$K8S_ROOT/infrastructure/redis/01-pvc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/redis/02-configmap.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/redis/03-statefulset.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/redis/04-service.yaml"

# RabbitMQ
kubectl apply -f "$K8S_ROOT/infrastructure/rabbitmq/01-pvc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/rabbitmq/02-configmap.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/rabbitmq/03-statefulset.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/rabbitmq/04-service.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/rabbitmq/05-ingressroute.yaml"

echo "⏳ Waiting for infrastructure to be ready..."
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=postgres -n saasodoo
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=redis -n saasodoo
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=rabbitmq -n saasodoo
echo "✅ Layer 3 complete"
echo ""

# Layer 4: Application Stack (KillBill & Microservices)
echo "📦 LAYER 4: Application Stack (KillBill & Services)"
echo "-----------------------------------------------------"

# KillBill (MariaDB + KillBill + Kaui)
echo "  Deploying KillBill stack..."
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/01-mariadb-pvc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/02-mariadb-sts.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/03-mariadb-svc.yaml"
kubectl wait --for=condition=ready --timeout=180s pod -l app.kubernetes.io/name=killbill-db -n saasodoo
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/04-killbill-deploy.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/05-killbill-svc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/06-killbill-route.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/07-kaui-deploy.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/08-kaui-svc.yaml"
kubectl apply -f "$K8S_ROOT/infrastructure/killbill/09-kaui-route.yaml"
echo "  ⏳ Waiting for KillBill to be ready..."
kubectl wait --for=condition=available --timeout=300s deployment/killbill -n saasodoo

# Microservices
echo "  Deploying microservices..."

# User Service
kubectl apply -f "$K8S_ROOT/services/user-service/"
kubectl wait --for=condition=available --timeout=120s deployment/user-service -n saasodoo

# Billing Service
kubectl apply -f "$K8S_ROOT/services/billing-service/"
kubectl wait --for=condition=available --timeout=120s deployment/billing-service -n saasodoo

# Instance Service & Worker
kubectl apply -f "$K8S_ROOT/services/instance-service/00-pvcs.yaml"
kubectl apply -f "$K8S_ROOT/services/instance-service/01-deployment.yaml"
kubectl apply -f "$K8S_ROOT/services/instance-service/02-service.yaml"
kubectl apply -f "$K8S_ROOT/services/instance-service/03-ingressroute.yaml"
kubectl apply -f "$K8S_ROOT/services/instance-worker/"
kubectl wait --for=condition=available --timeout=120s deployment/instance-service -n saasodoo
kubectl wait --for=condition=available --timeout=120s deployment/instance-worker -n saasodoo

# Notification Service
kubectl apply -f "$K8S_ROOT/services/notification-service/"
kubectl wait --for=condition=available --timeout=120s deployment/notification-service -n saasodoo

# Database Service & Worker
kubectl apply -f "$K8S_ROOT/services/database-service/"
kubectl apply -f "$K8S_ROOT/services/database-worker/"
kubectl wait --for=condition=available --timeout=120s deployment/database-service -n saasodoo
kubectl wait --for=condition=available --timeout=120s deployment/database-worker -n saasodoo

# Frontend Service
kubectl apply -f "$K8S_ROOT/services/frontend-service/"
kubectl wait --for=condition=available --timeout=120s deployment/frontend-service -n saasodoo

# MailHog
kubectl apply -f "$K8S_ROOT/services/mailhog/"
kubectl wait --for=condition=available --timeout=60s deployment/mailhog -n saasodoo

echo "✅ Layer 4 complete"
echo ""

# Deployment Summary
echo "========================================="
echo "✅ DEPLOYMENT COMPLETE"
echo "========================================="
echo ""
echo "Access URLs:"
echo "  - Frontend:           http://app.saasodoo.local"
echo "  - API (User):         http://api.saasodoo.local/user"
echo "  - API (Billing):      http://api.saasodoo.local/billing"
echo "  - API (Instance):     http://api.saasodoo.local/instance"
echo "  - API (Database):     http://api.saasodoo.local/database"
echo "  - Traefik Dashboard:  http://localhost:8080/dashboard/"
echo "  - KillBill:           http://billing.saasodoo.local"
echo "  - Kaui Admin:         http://billing-admin.saasodoo.local"
echo "  - RabbitMQ:           http://rabbitmq.saasodoo.local"
echo "  - MailHog:            http://mail.saasodoo.local"
echo ""
echo "Next Steps:"
echo "  1. Add these entries to /etc/hosts:"
echo "       127.0.0.1 api.saasodoo.local"
echo "       127.0.0.1 app.saasodoo.local"
echo "       127.0.0.1 billing.saasodoo.local"
echo "       127.0.0.1 billing-admin.saasodoo.local"
echo "       127.0.0.1 rabbitmq.saasodoo.local"
echo "       127.0.0.1 mail.saasodoo.local"
echo "       127.0.0.1 notification.saasodoo.local"
echo "  2. Check pod status: kubectl get pods -n saasodoo"
echo "  3. Check services: kubectl get svc -n saasodoo"
echo ""
