# Admin Service Deployment Order

This document outlines the correct order to deploy admin-service with CNPG integration.

## Important: Integration Guide

**Before deploying, read `INTEGRATION_GUIDE.md`** - it explains what needs to be added to infrastructure files for proper integration.

## Prerequisites

1. CNPG cluster `postgres-cluster` must be running
2. Secret `postgres-cluster-superuser` must exist
3. **CRITICAL:** The `admin_service` role must be added to CNPG cluster (see INTEGRATION_GUIDE.md)

## Step 1: Apply CNPG Resources

```bash
# 1. Create the admin_service role password secret
kubectl apply -f 00-cnpg-secret.yaml

# 2. Create the admin database (CNPG will create database and assign owner)
kubectl apply -f 00-cnpg-database.yaml

# 3. Wait for database to be ready
kubectl wait --for=condition=Ready database/admin -n saasodoo --timeout=60s

# 4. Verify database was created
kubectl get databases.postgresql.cnpg.io -n saasodoo admin
```

## Step 2: Apply Admin Service Config

```bash
# Apply service-specific config and secrets
kubectl apply -f 00-secret.yaml
kubectl apply -f 00-configmap.yaml
```

## Step 3: Initialize Database Tables

```bash
# Run the database initialization job
kubectl apply -f 00-db-init-job.yaml

# Watch the job progress
kubectl logs -n saasodoo job/admin-db-init -f

# Wait for completion
kubectl wait --for=condition=complete --timeout=300s job/admin-db-init -n saasodoo

# Verify tables were created
kubectl exec -n saasodoo postgres-cluster-1 -- \
  psql -U postgres -d admin -c "\dt"
```

## Step 4: Build and Deploy Admin Service

```bash
# Build Docker image
cd /root/Projects/saasodoo
docker build -t registry.109.199.108.243.nip.io/admin-service:latest \
  services/admin-service/

# Push to registry
docker push registry.109.199.108.243.nip.io/admin-service:latest

# Deploy admin-service
kubectl apply -f 01-deployment.yaml
kubectl apply -f 02-service.yaml
kubectl apply -f 03-ingressroute.yaml

# Watch rollout
kubectl rollout status deployment/admin-service -n saasodoo
```

## Step 5: Verify Admin Service

```bash
# Check pods
kubectl get pods -n saasodoo -l app.kubernetes.io/name=admin-service

# Check logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=admin-service --tail=50

# Test health endpoint
kubectl exec -n saasodoo -it \
  $(kubectl get pod -n saasodoo -l app.kubernetes.io/name=admin-service -o jsonpath='{.items[0].metadata.name}') \
  -- wget -qO- http://localhost:8010/health
```

## Step 6: Deploy Admin Frontend

```bash
# Admin frontend should now be able to start since admin-service is running
kubectl delete pod -n saasodoo -l app.kubernetes.io/name=admin-frontend

# Wait for pods to come up
kubectl get pods -n saasodoo -l app.kubernetes.io/name=admin-frontend -w
```

## Step 7: Test

```bash
# Access admin frontend
curl http://admin.109.199.108.243.nip.io/health

# Login with default credentials
# Email: admin@saasodoo.com
# Password: admin123
```

## Integration with Main CNPG Cluster (Optional - for later)

To properly integrate with the main CNPG cluster configuration:

1. Add the admin_service role to `infrastructure/databases/postgres-cnpg/04-cluster.yaml`:
   ```yaml
   spec:
     managed:
       roles:
         - name: admin_service
           ensure: present
           login: true
           passwordSecret:
             name: cnpg-admin-service
   ```

2. Add the admin database to `infrastructure/databases/postgres-cnpg/07-databases.yaml`:
   ```yaml
   ---
   # Admin Database
   apiVersion: postgresql.cnpg.io/v1
   kind: Database
   metadata:
     name: admin
     namespace: saasodoo
   spec:
     cluster:
       name: postgres-cluster
     name: admin
     owner: admin_service
     ensure: present
     extensions:
       - name: uuid-ossp
       - name: pgcrypto
       - name: pg_trgm
   ```

3. Apply the updated files:
   ```bash
   kubectl apply -f infrastructure/databases/postgres-cnpg/04-cluster.yaml
   kubectl apply -f infrastructure/databases/postgres-cnpg/07-databases.yaml
   ```
