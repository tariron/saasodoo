# Admin Service Deployment Guide

## Overview

Admin Service is the Backend-for-Frontend (BFF) for the SaaSOdoo Admin Tool. It aggregates data from user-service, instance-service, billing-service, and database-service, providing a unified API for admin operations with comprehensive audit logging.

**Port:** 8010
**Database:** `admin` (PostgreSQL)
**User:** `admin_service`

---

## Prerequisites

1. **Secrets Generated**
   ```bash
   # Generate DB password
   openssl rand -base64 32

   # Generate JWT secret
   openssl rand -hex 32
   ```

2. **Update Secret Manifest**
   Edit `00-secret.yaml` and replace placeholders with generated values.

3. **Postgres Superuser Secret**
   Ensure `postgres-superuser` secret exists in `saasodoo` namespace (required by db-init job).

---

## Deployment Steps

### Step 1: Apply Secrets & Config

```bash
kubectl apply -f 00-secret.yaml
kubectl apply -f 00-configmap.yaml
```

### Step 2: Initialize Database

```bash
# Apply database init job
kubectl apply -f 00-db-init-job.yaml

# Watch job progress
kubectl logs -n saasodoo job/admin-db-init -f

# Wait for completion
kubectl wait --for=condition=complete --timeout=300s job/admin-db-init -n saasodoo

# Verify database and tables created
kubectl exec -n saasodoo postgres-cluster-1 -- psql -U postgres -d admin -c "\dt"
kubectl exec -n saasodoo postgres-cluster-1 -- psql -U postgres -d admin -c "SELECT email, role FROM admin_users;"
```

Expected output:
- Tables: `admin_users`, `admin_sessions`, `audit_logs`
- User: `admin@saasodoo.com` (super_admin)

### Step 3: Build and Push Docker Image

```bash
# Build image
docker build -t registry.109.199.108.243.nip.io/admin-service:latest \
  services/admin-service/

# Push to registry
docker push registry.109.199.108.243.nip.io/admin-service:latest
```

### Step 4: Deploy Admin Service

```bash
# Apply all manifests
kubectl apply -f 01-deployment.yaml
kubectl apply -f 02-service.yaml
kubectl apply -f 03-ingressroute.yaml

# Watch rollout
kubectl rollout status deployment/admin-service -n saasodoo

# Check pods
kubectl get pods -n saasodoo -l app.kubernetes.io/name=admin-service
```

### Step 5: Verify Deployment

```bash
# Check pod logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=admin-service --tail=50

# Port-forward and test
kubectl port-forward -n saasodoo svc/admin-service 8010:8010

# Test health endpoint
curl http://localhost:8010/health

# Expected response:
# {"status":"healthy","service":"admin-service","database":"connected"}

# Test docs
curl http://localhost:8010/docs
```

### Step 6: Test via Ingress

```bash
# Test via Traefik ingress
curl http://admin.109.199.108.243.nip.io/api/health

# Access API docs
# Open browser: http://admin.109.199.108.243.nip.io/api/docs
```

---

## Configuration

### Environment Variables

Loaded from (in order):
1. `shared-config` ConfigMap (platform-wide settings)
2. `admin-service-config` ConfigMap (service-specific)
3. `admin-service-secret` Secret (credentials)

**Key Variables:**
- `DB_SERVICE_USER=admin_service`
- `DB_SERVICE_PASSWORD` (from secret)
- `DB_NAME=admin`
- `ADMIN_JWT_SECRET` (from secret)
- Service URLs via Kubernetes DNS

### Database Connection

Admin service uses dedicated `admin_service` user with least-privilege permissions:
- `admin_users`: SELECT, INSERT, UPDATE
- `admin_sessions`: SELECT, INSERT, DELETE
- `audit_logs`: SELECT, INSERT (append-only)

---

## Troubleshooting

### Database Init Job Fails

```bash
# Check job logs
kubectl logs -n saasodoo job/admin-db-init

# Common issues:
# - postgres-superuser secret not found
# - PostgreSQL not ready
# - admin_service password mismatch

# Re-run job (delete and re-create)
kubectl delete job/admin-db-init -n saasodoo
kubectl apply -f 00-db-init-job.yaml
```

### Pod CrashLoopBackOff

```bash
# Check logs
kubectl logs -n saasodoo <pod-name>

# Common issues:
# - DB_SERVICE_PASSWORD not set (check secret applied)
# - Cannot connect to database (check admin DB exists)
# - ADMIN_JWT_SECRET not set

# Verify secrets
kubectl get secret admin-service-secret -n saasodoo -o yaml
```

### Health Check Failing

```bash
# Exec into pod
kubectl exec -it -n saasodoo <pod-name> -- bash

# Test database connection
python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect('$DATABASE_URL').close())"

# Check if port is listening
netstat -tlnp | grep 8010
```

### Cannot Access via Ingress

```bash
# Check IngressRoute
kubectl get ingressroute -n saasodoo admin-service -o yaml

# Check Traefik routes
kubectl logs -n kube-system -l app.kubernetes.io/name=traefik --tail=100 | grep admin

# Test service directly
kubectl run curl --image=curlimages/curl -it --rm -- \
  curl http://admin-service.saasodoo.svc.cluster.local:8010/health
```

---

## Maintenance

### Rebuild and Redeploy

```bash
# Rebuild image
docker build -t registry.109.199.108.243.nip.io/admin-service:latest services/admin-service/
docker push registry.109.199.108.243.nip.io/admin-service:latest

# Restart deployment (pulls new image)
kubectl rollout restart deployment/admin-service -n saasodoo
kubectl rollout status deployment/admin-service -n saasodoo
```

### View Audit Logs

```bash
# Connect to admin database
kubectl exec -it -n saasodoo postgres-cluster-1 -- psql -U admin_service -d admin

# Query recent audit logs
SELECT
  a.created_at,
  u.email as admin,
  a.action,
  a.target_type,
  a.target_id
FROM audit_logs a
JOIN admin_users u ON u.id = a.admin_user_id
ORDER BY a.created_at DESC
LIMIT 20;
```

### Clean Up Expired Sessions

```bash
# Sessions auto-expire after 15 minutes
# Manual cleanup (if needed):
kubectl exec -it -n saasodoo postgres-cluster-1 -- psql -U admin_service -d admin \
  -c "DELETE FROM admin_sessions WHERE expires_at < NOW();"
```

---

## Default Credentials

⚠️ **IMPORTANT:** Default admin credentials are set during database initialization. Contact the system administrator or check the deployment logs for initial access details. Change credentials immediately after first login.

---

## Scaling

```bash
# Scale replicas
kubectl scale deployment/admin-service -n saasodoo --replicas=3

# Check status
kubectl get deployment admin-service -n saasodoo
```

---

## Uninstall

```bash
# Delete all resources
kubectl delete -f 03-ingressroute.yaml
kubectl delete -f 02-service.yaml
kubectl delete -f 01-deployment.yaml
kubectl delete -f 00-configmap.yaml
kubectl delete -f 00-secret.yaml
kubectl delete job/admin-db-init -n saasodoo

# Drop database (optional - DESTRUCTIVE)
kubectl exec -n saasodoo postgres-cluster-1 -- psql -U postgres \
  -c "DROP DATABASE IF EXISTS admin;"
kubectl exec -n saasodoo postgres-cluster-1 -- psql -U postgres \
  -c "DROP USER IF EXISTS admin_service;"
```
