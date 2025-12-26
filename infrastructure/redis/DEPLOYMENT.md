# Redis Cluster Deployment Guide

This guide walks you through deploying the Redis cluster with the Spotahome Redis Operator.

## Architecture Overview

**Before (Single Redis):**
```
[App] --> redis:6379 (single pod, no HA)
```

**After (Redis Cluster with Operator):**
```
[App] --> rfr-redis-cluster:6379 (service pointing to current master)
           ├── Redis Master (rfr-redis-cluster-0)
           ├── Redis Replica 1 (rfr-redis-cluster-1)
           └── Redis Replica 2 (rfr-redis-cluster-2)

[Sentinel Cluster monitors and manages failover]
           ├── Sentinel 1 (rfs-redis-cluster-0)
           ├── Sentinel 2 (rfs-redis-cluster-1)
           └── Sentinel 3 (rfs-redis-cluster-2)
```

## Prerequisites

- Kubernetes cluster running
- `kubectl` access to cluster
- Current Redis instance running (we'll migrate data)

## Deployment Steps

### Step 1: Deploy Redis Operator (One-time, Cluster-wide)

```bash
# Navigate to project root
cd /root/Projects/saasodoo

# Deploy Redis Operator
kubectl apply -f infrastructure/redis-operator/00-namespace.yaml
kubectl apply -f infrastructure/redis-operator/01-crd.yaml
kubectl apply -f infrastructure/redis-operator/02-rbac.yaml
kubectl apply -f infrastructure/redis-operator/03-deployment.yaml

# Verify operator is running
kubectl get pods -n redis-operator
# Expected: redis-operator-xxxxx   1/1   Running

# Check operator logs
kubectl logs -n redis-operator -l app.kubernetes.io/name=redis-operator
```

### Step 2: Deploy RedisFailover CR (Creates the Cluster)

```bash
# Deploy RedisFailover resource
kubectl apply -f infrastructure/redis/03-redisfailover.yaml

# Watch cluster creation (takes 1-2 minutes)
kubectl get redisfailover -n saasodoo -w

# Watch pods being created
kubectl get pods -n saasodoo -l app.kubernetes.io/name=redis-cluster -w
```

**Expected output:**
```
NAME                       READY   STATUS    RESTARTS   AGE
rfr-redis-cluster-0        1/1     Running   0          60s   # Redis Master
rfr-redis-cluster-1        1/1     Running   0          60s   # Redis Replica 1
rfr-redis-cluster-2        1/1     Running   0          60s   # Redis Replica 2
rfs-redis-cluster-0        1/1     Running   0          60s   # Sentinel 1
rfs-redis-cluster-1        1/1     Running   0          60s   # Sentinel 2
rfs-redis-cluster-2        1/1     Running   0          60s   # Sentinel 3
```

### Step 4: Verify Cluster Health

```bash
# Check RedisFailover status
kubectl describe redisfailover redis-cluster -n saasodoo

# Check services created by operator
kubectl get svc -n saasodoo | grep redis
# Expected services:
# rfr-redis-cluster    ClusterIP   <IP>   6379/TCP   # Main Redis service (use this)
# rfs-redis-cluster    ClusterIP   <IP>   26379/TCP  # Sentinel service

# Test Redis connection (no password required)
kubectl run -it --rm redis-test --image=redis:latest --restart=Never -n saasodoo -- \
  redis-cli -h rfr-redis-cluster PING
# Expected: PONG

# Check replication status
kubectl exec -it rfr-redis-cluster-0 -n saasodoo -- \
  redis-cli INFO replication
# Should show: role:master, connected_slaves:2
```

### Step 3: Update Application Configuration

```bash
# Update shared config (already done in manifests)
kubectl apply -f infrastructure/00-shared-config.yaml

# Verify config updated
kubectl get configmap shared-config -n saasodoo -o yaml | grep REDIS_HOST
# Expected: REDIS_HOST: "rfr-redis-cluster.saasodoo.svc.cluster.local"
```

### Step 4: Migrate Data from Old Redis (Optional but Recommended)

If you have important session data or cached data:

```bash
# Option A: Export/Import (Safest)

# 1. Get dump from old Redis
kubectl exec -it redis-0 -n saasodoo -- redis-cli BGSAVE
sleep 5  # Wait for save to complete
kubectl cp saasodoo/redis-0:/data/dump.rdb ./old-redis-dump.rdb

# 2. Copy dump to new Redis master
kubectl cp ./old-redis-dump.rdb saasodoo/rfr-redis-cluster-0:/data/dump.rdb

# 3. Restart new Redis to load dump
kubectl delete pod rfr-redis-cluster-0 -n saasodoo

# 4. Wait for pod to restart and verify data
kubectl wait --for=condition=ready pod/rfr-redis-cluster-0 -n saasodoo --timeout=60s

# Option B: Use redis-cli --rdb (For live migration)
kubectl port-forward -n saasodoo redis-0 6380:6379 &
kubectl port-forward -n saasodoo rfr-redis-cluster-0 6381:6379 &

# Use redis-cli or similar tool to copy data
# (requires redis-cli with --rdb support or redis-dump-load tool)

# Clean up port-forwards
pkill -f "port-forward.*redis"
```

### Step 5: Restart Services to Pick Up New Configuration

```bash
# Restart all services to use new Redis cluster
kubectl rollout restart deployment/user-service -n saasodoo
kubectl rollout restart deployment/instance-service -n saasodoo
kubectl rollout restart deployment/instance-worker -n saasodoo
kubectl rollout restart deployment/billing-service -n saasodoo
kubectl rollout restart deployment/database-service -n saasodoo
kubectl rollout restart deployment/database-worker -n saasodoo

# Watch rollout status
kubectl rollout status deployment/user-service -n saasodoo
kubectl rollout status deployment/instance-service -n saasodoo
kubectl rollout status deployment/billing-service -n saasodoo
```

### Step 6: Verify Services Connect to New Redis

```bash
# Check service logs for Redis connection
kubectl logs -n saasodoo -l app.kubernetes.io/name=user-service --tail=50 | grep -i redis
# Should see: "Redis client initialized successfully"

# Test a service endpoint that uses Redis
POD=$(kubectl get pod -n saasodoo -l app.kubernetes.io/name=user-service -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n saasodoo $POD -- curl -s http://localhost:8001/health
# Should return healthy status

# Check Redis for active connections
kubectl exec -it rfr-redis-cluster-0 -n saasodoo -- \
  redis-cli CLIENT LIST
# Should see multiple connected clients
```

### Step 7: Test Failover (Optional but Recommended)

```bash
# Manually trigger failover to test HA
echo "Deleting master pod to test failover..."
kubectl delete pod rfr-redis-cluster-0 -n saasodoo

# Watch Sentinel promote a replica
kubectl logs -f rfs-redis-cluster-0 -n saasodoo
# Should see: "+switch-master" message

# Verify new master
sleep 10
kubectl exec -it rfr-redis-cluster-1 -n saasodoo -- \
  redis-cli INFO replication | grep role
# One of the replicas should now be master

# Verify services still work
kubectl exec -n saasodoo $POD -- curl -s http://localhost:8001/health
# Should still be healthy
```

### Step 8: Clean Up Old Redis (After Successful Migration)

```bash
# Delete old Redis StatefulSet
kubectl delete statefulset redis -n saasodoo

# Delete old Redis service
kubectl delete service redis -n saasodoo

# Optionally delete old Redis PVC (if no longer needed)
# WARNING: This will delete old Redis data!
# kubectl delete pvc -n saasodoo -l app.kubernetes.io/name=redis

echo "Migration complete! Old Redis removed."
```

## Post-Deployment Verification

```bash
# 1. Check all pods are running
kubectl get pods -n saasodoo | grep redis

# 2. Check services
kubectl get svc -n saasodoo | grep redis

# 3. Verify RedisFailover status
kubectl get redisfailover -n saasodoo

# 4. Test login to your app (uses Redis sessions)
# - Navigate to http://app.62.171.153.219.nip.io
# - Login with test credentials
# - Verify session works

# 5. Check Celery tasks work (uses Redis backend)
# - Create a test instance
# - Verify provisioning task runs

# 6. Monitor Redis metrics (if Prometheus available)
kubectl get svc redis-operator -n redis-operator
# Metrics available at: http://redis-operator.redis-operator:9710/metrics
```

## Rollback (If Issues Occur)

If you encounter issues with the new Redis cluster:

```bash
# 1. Revert ConfigMap changes
kubectl patch configmap shared-config -n saasodoo --type=json -p='[
  {"op": "replace", "path": "/data/REDIS_HOST", "value": "redis.saasodoo.svc.cluster.local"}
]'

# 2. Restart services to reconnect to old Redis
kubectl rollout restart deployment/user-service -n saasodoo
kubectl rollout restart deployment/instance-service -n saasodoo
kubectl rollout restart deployment/billing-service -n saasodoo

# 3. Keep new Redis cluster for investigation
# Don't delete it - troubleshoot the issue

# 4. Check operator logs for issues
kubectl logs -n redis-operator -l app.kubernetes.io/name=redis-operator
```

## Monitoring and Maintenance

### Check Cluster Health Daily

```bash
# Quick health check script
cat << 'EOF' > check-redis-health.sh
#!/bin/bash
echo "=== Redis Cluster Health Check ==="
echo "RedisFailover Status:"
kubectl get redisfailover redis-cluster -n saasodoo

echo -e "\nRedis Pods:"
kubectl get pods -n saasodoo -l app.kubernetes.io/component=redis

echo -e "\nSentinel Pods:"
kubectl get pods -n saasodoo -l app.kubernetes.io/component=sentinel

echo -e "\nReplication Status:"
kubectl exec -it rfr-redis-cluster-0 -n saasodoo -- \
  redis-cli INFO replication 2>/dev/null | grep -E "role|connected_slaves"

echo -e "\nMemory Usage:"
kubectl exec -it rfr-redis-cluster-0 -n saasodoo -- \
  redis-cli INFO memory 2>/dev/null | grep used_memory_human
EOF

chmod +x check-redis-health.sh
./check-redis-health.sh
```

### Backup Strategy

```bash
# Automated daily backups (cron example)
cat << 'EOF' > backup-redis.sh
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="/mnt/cephfs/redis_backups"
mkdir -p "$BACKUP_DIR"

# Trigger RDB save
kubectl exec -n saasodoo rfr-redis-cluster-0 -- \
  redis-cli BGSAVE

sleep 10  # Wait for save to complete

# Copy dump file
kubectl cp saasodoo/rfr-redis-cluster-0:/data/dump.rdb \
  "$BACKUP_DIR/redis-dump-$DATE.rdb"

# Keep only last 7 days
find "$BACKUP_DIR" -name "redis-dump-*.rdb" -mtime +7 -delete

echo "Redis backup completed: $BACKUP_DIR/redis-dump-$DATE.rdb"
EOF

chmod +x backup-redis.sh

# Add to cron (daily at 2 AM)
# 0 2 * * * /path/to/backup-redis.sh
```

## Troubleshooting

See `README.md` for detailed troubleshooting steps.

## Next Steps

- [ ] Monitor cluster performance for 1 week
- [ ] Set up Prometheus metrics collection (optional)
- [ ] Configure automated backups
- [ ] Document runbooks for common operations
- [ ] Update .gitignore to exclude secrets (IMPORTANT!)
