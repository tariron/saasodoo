# Admin Service CNPG Integration Guide

This guide explains what needs to be added to the existing infrastructure files for proper admin-service integration.

## Overview

The admin-service requires:
1. A dedicated PostgreSQL role: `admin_service`
2. A database: `admin`
3. Tables for admin users, sessions, and audit logs

## Changes Required to Infrastructure Files

### 1. Add admin_service Role to CNPG Cluster

**File:** `/root/Projects/saasodoo/infrastructure/databases/postgres-cnpg/04-cluster.yaml`

**Location:** In the `spec.managed.roles` section (around line 121-165)

**Add this entry:**

```yaml
      # Admin Service Role
      - name: admin_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-admin-service
```

**Full context (add after backup_user, before the backup section):**

```yaml
spec:
  managed:
    roles:
      - name: auth_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-auth-service

      - name: billing_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-billing-service

      - name: instance_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-instance-service

      - name: database_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-database-service

      - name: notification_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-notification-service

      - name: readonly_user
        ensure: present
        login: true
        passwordSecret:
          name: readonly-user-secret

      - name: backup_user
        ensure: present
        login: true
        replication: true
        passwordSecret:
          name: backup-user-secret

      # NEW: Admin Service Role
      - name: admin_service
        ensure: present
        login: true
        passwordSecret:
          name: cnpg-admin-service

  # Backup Configuration (Not configured initially - add later)
  # backup:
  # ...
```

**After adding, apply:**
```bash
kubectl apply -f infrastructure/databases/postgres-cnpg/04-cluster.yaml
```

---

### 2. Add admin Database to CNPG Databases

**File:** `/root/Projects/saasodoo/infrastructure/databases/postgres-cnpg/07-databases.yaml`

**Location:** At the end of the file (after analytics database)

**Add this database definition:**

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

**After adding, apply:**
```bash
kubectl apply -f infrastructure/databases/postgres-cnpg/07-databases.yaml
```

---

## One-Time Patch (Already Applied)

If you don't want to modify the infrastructure files immediately, you can use this one-time kubectl patch:

```bash
# Add admin_service role to cluster
kubectl patch cluster postgres-cluster -n saasodoo --type='json' \
  -p='[{"op": "add", "path": "/spec/managed/roles/-", "value": {"name": "admin_service", "ensure": "present", "login": true, "passwordSecret": {"name": "cnpg-admin-service"}}}]'
```

**Note:** This was already executed during initial setup, so the role exists. But for clean deployments in the future, you should update the infrastructure YAML files.

---

## Secrets Created

The following secrets are managed in `deploy/platform/admin-service/`:

### 1. `cnpg-admin-service` Secret
- **File:** `00-cnpg-secret.yaml`
- **Purpose:** Password for the `admin_service` PostgreSQL role
- **Used by:** CNPG cluster for role management
- **Default password:** `CHANGE_ME_admin_service_password_12345` (⚠️ change in production!)

### 2. `admin-service-secret` Secret
- **File:** `00-secret.yaml`
- **Purpose:** Service credentials including DB password and JWT secret
- **Used by:** admin-service pods for database connection and authentication

**Important:** The `DB_SERVICE_PASSWORD` in `admin-service-secret` must match the password in `cnpg-admin-service`.

---

## Database Resources Created

### 1. Database CRD
- **File:** `00-cnpg-database.yaml`
- **What it does:** Creates the `admin` database with `admin_service` as owner
- **Managed by:** CNPG operator

### 2. Database Tables
- **File:** `00-db-init-job.yaml`
- **What it does:** Creates tables (admin_users, admin_sessions, audit_logs) and initial admin user
- **Runs once:** Job creates schema and default super_admin account

---

## Complete Deployment Sequence

See `DEPLOYMENT_ORDER.md` for the full step-by-step deployment process.

---

## Verification Commands

After making infrastructure changes:

```bash
# Check if admin_service role exists in cluster
kubectl get cluster postgres-cluster -n saasodoo -o jsonpath='{.spec.managed.roles[*].name}' | grep admin_service

# Check if admin database was created
kubectl get databases.postgresql.cnpg.io -n saasodoo admin

# Check database status
kubectl describe database admin -n saasodoo

# Verify tables exist
kubectl exec -n saasodoo postgres-cluster-1 -- \
  psql -U postgres -d admin -c "\dt"

# Check admin_service can connect
kubectl exec -n saasodoo postgres-cluster-1 -- \
  psql -U admin_service -d admin -c "SELECT current_user, current_database();"
```

---

## Cleanup (If Needed)

To remove admin-service integration:

```bash
# Delete admin-service deployment
kubectl delete -f deploy/platform/admin-service/03-ingressroute.yaml
kubectl delete -f deploy/platform/admin-service/02-service.yaml
kubectl delete -f deploy/platform/admin-service/01-deployment.yaml

# Delete admin-frontend
kubectl delete -f deploy/platform/admin-frontend/

# Delete admin database
kubectl delete database admin -n saasodoo

# Remove admin_service role (edit infrastructure files and reapply)
# OR use patch:
kubectl get cluster postgres-cluster -n saasodoo -o json | \
  jq '.spec.managed.roles |= map(select(.name != "admin_service"))' | \
  kubectl apply -f -

# Delete secrets
kubectl delete secret cnpg-admin-service -n saasodoo
kubectl delete secret admin-service-secret -n saasodoo
kubectl delete configmap admin-service-config -n saasodoo

# Delete database init job
kubectl delete job admin-db-init -n saasodoo
```
