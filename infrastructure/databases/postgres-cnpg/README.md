# CloudNativePG - PostgreSQL HA Cluster

Production-ready PostgreSQL cluster using CloudNativePG operator for the SaaSOdoo platform.

## Architecture

```
postgres-cluster-0 (primary)   ──┐
postgres-cluster-1 (standby)   ──┼── Synchronous replication
postgres-cluster-2 (standby)   ──┘
         │
         ▼
┌─────────────────────────────────┐
│  PgBouncer Pooler (2 replicas)  │
│  Transaction pooling mode       │
└─────────────────────────────────┘
         │
         ▼
Service: postgres-cluster-pooler-rw.saasodoo.svc.cluster.local:5432
```

**Features:**
- 3 PostgreSQL instances (1 primary + 2 synchronous standbys)
- Automatic failover (< 30 seconds)
- PgBouncer connection pooling (transaction mode)
- Declarative database management via Database CRDs
- Managed roles with Kubernetes secrets
- CephFS persistent storage (20Gi)
- Prometheus metrics auto-enabled

## Files

```
postgres-cnpg/
├── 00-secrets.yaml               # CNPG managed role secrets (gitignored)
├── 01-operator.yaml              # Operator installation reference
├── 04-cluster.yaml               # Main CNPG Cluster manifest
├── 06-init-scripts-configmap.yaml # SQL init scripts ConfigMap
├── 07-databases.yaml             # Database CRDs (auth, billing, etc.)
├── 08-schema-job.yaml            # Schema initialization Job
├── 10-pgbouncer-pooler.yaml      # PgBouncer connection pooler
├── README.md                     # This file
└── init-scripts/                 # SQL schema files
    ├── 04-auth-schema.sql
    ├── 04-billing-schema.sql
    ├── 04-instance-schema.sql
    ├── 04-communication-schema.sql
    ├── 04-analytics-schema.sql
    ├── 05-plan-entitlements.sql
    ├── 06-database-service-schema.sql
    └── 07-add-db-type-to-plan-entitlements.sql
```

## Prerequisites

- Kubernetes 1.25+
- 3+ nodes (for pod anti-affinity)
- Storage: `rook-cephfs` StorageClass
- Namespace: `saasodoo` (must exist)
- Resources: 2Gi+ memory, 1000m+ CPU per node

## Installation

### Step 1: Install CloudNativePG Operator

```bash
# Install operator (creates cnpg-system namespace)
kubectl apply --server-side -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.28/releases/cnpg-1.28.0.yaml

# Wait for operator to be ready
kubectl wait --for=condition=Available --timeout=300s \
  deployment/cnpg-controller-manager -n cnpg-system

# Verify CRDs installed
kubectl get crds | grep postgresql.cnpg.io
```

### Step 2: Deploy Secrets

```bash
cd infrastructure/postgres-cnpg

# Create managed role secrets
kubectl apply -f 00-secrets.yaml

# Verify secrets created
kubectl get secrets -n saasodoo | grep cnpg-
```

### Step 3: Deploy PostgreSQL Cluster

```bash
# Deploy cluster
kubectl apply -f 04-cluster.yaml

# Watch cluster creation (takes 3-5 minutes)
kubectl get cluster postgres-cluster -n saasodoo -w

# Wait for cluster to be ready
kubectl wait --for=condition=Ready --timeout=600s \
  cluster/postgres-cluster -n saasodoo
```

Expected output:
```
NAME               AGE   INSTANCES   READY   STATUS                     PRIMARY
postgres-cluster   30s   3           1       Setting up primary         postgres-cluster-1
postgres-cluster   1m    3           2       Creating replica           postgres-cluster-1
postgres-cluster   3m    3           3       Cluster in healthy state   postgres-cluster-1
```

### Step 4: Create Databases

```bash
# Apply database CRDs
kubectl apply -f 07-databases.yaml

# Verify databases created
kubectl get database -n saasodoo
```

Expected output:
```
NAME            AGE   CLUSTER            READY
auth            10s   postgres-cluster   True
billing         10s   postgres-cluster   True
instance        10s   postgres-cluster   True
communication   10s   postgres-cluster   True
analytics       10s   postgres-cluster   True
```

### Step 5: Initialize Schemas

```bash
# Apply init scripts ConfigMap
kubectl apply -f 06-init-scripts-configmap.yaml

# Run schema initialization Job
kubectl apply -f 08-schema-job.yaml

# Watch Job completion
kubectl get job cnpg-schema-init -n saasodoo -w

# Check Job logs
kubectl logs -n saasodoo job/cnpg-schema-init
```

### Step 6: Enable PgBouncer Pooler

```bash
# Deploy PgBouncer pooler
kubectl apply -f 10-pgbouncer-pooler.yaml

# Wait for pooler to be ready
kubectl get pooler -n saasodoo -w

# Verify pooler pods running
kubectl get pods -n saasodoo -l cnpg.io/poolerName=postgres-cluster-pooler-rw
```

### Step 7: Update Platform Configuration

Ensure `infrastructure/00-shared-config.yaml` uses the pooler endpoint:

```yaml
POSTGRES_HOST: "postgres-cluster-pooler-rw.saasodoo.svc.cluster.local"
POSTGRES_PORT: "5432"
```

Then apply and restart services:

```bash
kubectl apply -f ../00-shared-config.yaml

kubectl rollout restart deployment \
  user-service billing-service instance-service instance-worker \
  notification-service -n saasodoo
```

### Step 8: Verify Installation

```bash
# Check all components
kubectl get cluster,pooler,database -n saasodoo

# Check pods
kubectl get pods -n saasodoo -l cnpg.io/cluster=postgres-cluster

# Test service health
curl -s http://api.62.171.153.219.nip.io/user/health
curl -s http://api.62.171.153.219.nip.io/billing/health
curl -s http://api.62.171.153.219.nip.io/instance/health
```

## Verification Commands

### Cluster Health

```bash
# Overall cluster status
kubectl get cluster postgres-cluster -n saasodoo

# Pod status with roles
kubectl get pods -n saasodoo -L role -l cnpg.io/cluster=postgres-cluster

# Detailed cluster info
kubectl describe cluster postgres-cluster -n saasodoo
```

### Database Verification

```bash
# Get primary pod
PRIMARY=$(kubectl get pods -n saasodoo \
  -l cnpg.io/cluster=postgres-cluster,role=primary \
  -o jsonpath='{.items[0].metadata.name}')

# List databases
kubectl exec -n saasodoo $PRIMARY -- psql -U postgres -c '\l'

# List users
kubectl exec -n saasodoo $PRIMARY -- psql -U postgres -c '\du'

# Check tables in auth database
kubectl exec -n saasodoo $PRIMARY -- psql -U postgres -d auth -c '\dt'
```

### Replication Status

```bash
# Check replication (should show 2 sync standbys)
kubectl exec -n saasodoo $PRIMARY -- psql -U postgres -c \
  "SELECT application_name, state, sync_state,
   pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS lag_bytes
   FROM pg_stat_replication;"
```

### PgBouncer Status

```bash
# Port-forward to pooler
kubectl port-forward -n saasodoo svc/postgres-cluster-pooler-rw 6432:5432 &

# Check pools (connect as pgbouncer admin)
PGPASSWORD=$(kubectl get secret -n saasodoo postgres-cluster-superuser \
  -o jsonpath='{.data.password}' | base64 -d) \
  psql -h localhost -p 6432 -U postgres pgbouncer -c "SHOW POOLS;"

# Check stats
PGPASSWORD=$(kubectl get secret -n saasodoo postgres-cluster-superuser \
  -o jsonpath='{.data.password}' | base64 -d) \
  psql -h localhost -p 6432 -U postgres pgbouncer -c "SHOW STATS;"
```

## Operations

### Manual Failover (Switchover)

```bash
# Promote a specific standby to primary
kubectl cnpg promote postgres-cluster postgres-cluster-2 -n saasodoo

# Or use annotation
kubectl annotate cluster postgres-cluster -n saasodoo \
  cnpg.io/primaryUpdateMethod=switchover
```

### Rolling Restart

```bash
# Rolling restart all instances
kubectl cnpg restart postgres-cluster -n saasodoo

# Restart only primary
kubectl cnpg restart postgres-cluster --primary -n saasodoo
```

### Scaling Instances

```bash
# Scale to 5 instances
kubectl patch cluster postgres-cluster -n saasodoo \
  --type='merge' -p '{"spec":{"instances":5}}'

# Scale down to 2 instances (minimum for sync replication)
kubectl patch cluster postgres-cluster -n saasodoo \
  --type='merge' -p '{"spec":{"instances":2}}'
```

### Re-run Schema Initialization

If you need to re-run the schema job:

```bash
# Delete old job
kubectl delete job cnpg-schema-init -n saasodoo

# Re-apply
kubectl apply -f 08-schema-job.yaml

# Watch logs
kubectl logs -n saasodoo job/cnpg-schema-init -f
```

## Monitoring

### Prometheus Metrics

CloudNativePG exports metrics automatically:

```bash
# Check PodMonitor
kubectl get podmonitor -n saasodoo

# Key metrics:
# - cnpg_pg_stat_replication_lag_bytes
# - cnpg_pg_database_size_bytes
# - cnpg_pg_stat_database_xact_commit
# - cnpg_pg_settings_max_connections
```

### Connection Count

```bash
kubectl exec -n saasodoo $PRIMARY -- psql -U postgres -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
```

## Troubleshooting

### Cluster Not Ready

```bash
# Check cluster events
kubectl get events -n saasodoo --field-selector involvedObject.name=postgres-cluster

# Check operator logs
kubectl logs -n cnpg-system -l app.kubernetes.io/name=cloudnative-pg --tail=100

# Check pod logs
kubectl logs -n saasodoo $PRIMARY --tail=100
```

### Pod Scheduling Issues

```bash
# Check pod events
kubectl describe pod -n saasodoo -l cnpg.io/cluster=postgres-cluster

# Verify anti-affinity (pods should be on different nodes)
kubectl get pods -n saasodoo -l cnpg.io/cluster=postgres-cluster -o wide
```

### Service Connection Failures

```bash
# Check pooler service
kubectl get svc postgres-cluster-pooler-rw -n saasodoo

# Test connection from debug pod
kubectl run -n saasodoo psql-test --rm -it --restart=Never \
  --image=postgres:18-alpine \
  --env="PGPASSWORD=$(kubectl get secret -n saasodoo postgres-cluster-superuser -o jsonpath='{.data.password}' | base64 -d)" \
  -- psql -h postgres-cluster-pooler-rw -U postgres -c "SELECT version();"
```

### Database CRD Not Creating

```bash
# Check database status
kubectl describe database auth -n saasodoo

# Check operator can connect
kubectl logs -n cnpg-system -l app.kubernetes.io/name=cloudnative-pg | grep -i database
```

## Configuration Reference

### Cluster Spec

- **Instances:** 3 (1 primary + 2 sync standbys)
- **PostgreSQL:** 18.1
- **Storage:** 20Gi per instance (rook-cephfs)
- **Sync Replicas:** min=1, max=2
- **Resources:** 1Gi RAM, 500m CPU (request) / 2Gi RAM, 1000m CPU (limit)

### Databases

| Database | Owner | Description |
|----------|-------|-------------|
| auth | auth_service | User authentication |
| billing | billing_service | Subscription & billing |
| instance | instance_service | Odoo instance management |
| communication | notification_service | Notifications |
| analytics | analytics_service | Platform analytics |

### Service Endpoints

- **Primary (via pooler):** `postgres-cluster-pooler-rw.saasodoo.svc.cluster.local:5432`
- **Primary (direct):** `postgres-cluster-rw.saasodoo.svc.cluster.local:5432`
- **Read replicas:** `postgres-cluster-ro.saasodoo.svc.cluster.local:5432`

### Managed Roles

| Role | Secret | Permissions |
|------|--------|-------------|
| auth_service | cnpg-auth-service | Full access to auth DB |
| billing_service | cnpg-billing-service | Full access to billing DB |
| instance_service | cnpg-instance-service | Full access to instance DB |
| database_service | cnpg-database-service | Full access to instance DB |
| readonly_user | cnpg-readonly-user | SELECT on all DBs |
| backup_user | cnpg-backup-user | Replication + backup |

## Cleanup

To completely remove the PostgreSQL cluster:

```bash
# Delete cluster (this deletes all data!)
kubectl delete cluster postgres-cluster -n saasodoo

# Delete databases
kubectl delete database --all -n saasodoo

# Delete pooler
kubectl delete pooler postgres-cluster-pooler-rw -n saasodoo

# Delete secrets
kubectl delete secret -n saasodoo -l app.kubernetes.io/name=postgres

# Delete ConfigMap
kubectl delete configmap cnpg-init-scripts -n saasodoo

# Delete schema Job
kubectl delete job cnpg-schema-init -n saasodoo

# Uninstall operator (optional)
kubectl delete -f \
  https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.28/releases/cnpg-1.28.0.yaml
```

## Resources

- [CloudNativePG Documentation](https://cloudnative-pg.io/documentation/1.28/)
- [CloudNativePG GitHub](https://github.com/cloudnative-pg/cloudnative-pg)
- [PostgreSQL 18 Documentation](https://www.postgresql.org/docs/18/)
- [PgBouncer Documentation](https://www.pgbouncer.org/config.html)
