# Redis High-Availability Cluster

Spotahome Redis Operator managing a Redis cluster with Sentinel for automatic failover.

## Architecture

**Topology:** 1 Master + 2 Replicas + 3 Sentinels

```
┌────────────────────────────────────────────────┐
│ Spotahome Redis Operator (redis-operator ns)  │
│ Manages RedisFailover custom resources        │
└────────────────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
┌───────▼────────┐         ┌────────▼─────────┐
│ Redis Pods (3) │         │ Sentinel Pods (3)│
│ StatefulSet    │         │ Deployment       │
│ ─────────────  │         │ ──────────────   │
│ • rfr-...-0   │         │ • rfs-...-xxxxx  │
│ • rfr-...-1   │         │ • rfs-...-yyyyy  │
│ • rfr-...-2   │         │ • rfs-...-zzzzz  │
└────────────────┘         └──────────────────┘
        │                           │
┌───────▼────────┐         ┌────────▼─────────┐
│ No Service     │         │ Service          │
│ (DNS via       │         │ rfs-redis-cluster│
│  StatefulSet)  │         │ port: 26379      │
└────────────────┘         └──────────────────┘
```

## Installation

### Step 1: Deploy Redis Operator (One-time, Cluster-wide)

```bash
# Deploy operator components in order
kubectl apply -f 00-operator-namespace.yaml
kubectl apply -f 01-operator-crd.yaml
kubectl apply -f 02-operator-rbac.yaml
kubectl apply -f 03-operator-deployment.yaml

# Verify operator is running
kubectl get pods -n redis-operator
kubectl logs -n redis-operator -l app.kubernetes.io/name=redis-operator
```

**Operator Version:** `quay.io/spotahome/redis-operator:v1.2.4`

### Step 2: Deploy Redis Cluster (saasodoo namespace)

```bash
# Create RedisFailover cluster
kubectl apply -f 04-cluster.yaml

# Watch cluster creation
kubectl get pods -n saasodoo | grep redis

# Verify cluster is ready
kubectl exec -n saasodoo rfr-redis-cluster-0 -- redis-cli INFO replication
```

## Application Connection

**IMPORTANT:** Applications MUST connect via Sentinel for automatic failover support.

### Environment Variables

```yaml
# Sentinel configuration (REQUIRED)
REDIS_SENTINEL_ENABLED: "true"
REDIS_SENTINEL_HOST: "rfs-redis-cluster.saasodoo.svc.cluster.local"
REDIS_SENTINEL_PORT: "26379"
REDIS_SENTINEL_MASTER: "mymaster"
REDIS_DB: "0"

# Fallback direct connection (not used when Sentinel enabled)
REDIS_HOST: "redis-master.saasodoo.svc.cluster.local"
REDIS_PORT: "6379"
```

### Python (Redis-py with Sentinel)

```python
from redis.sentinel import Sentinel

# Connect to Sentinel
sentinel = Sentinel([
    ('rfs-redis-cluster.saasodoo.svc.cluster.local', 26379)
])

# Get master client (automatically discovers current master)
master = sentinel.master_for('mymaster', socket_timeout=5.0, db=0, decode_responses=True)
master.set('key', 'value')

# Get slave client (for read operations)
slave = sentinel.slave_for('mymaster', socket_timeout=5.0, db=0, decode_responses=True)
value = slave.get('key')
```

### Celery Configuration

```python
import os

def _get_redis_backend_url():
    """Build Redis backend URL with Sentinel support"""
    use_sentinel = os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true"

    if use_sentinel:
        # Sentinel backend URL format: sentinel://host:port
        # Master name and db go in transport_options, NOT in URL
        sentinel_host = os.getenv("REDIS_SENTINEL_HOST", "rfs-redis-cluster.saasodoo.svc.cluster.local")
        sentinel_port = os.getenv("REDIS_SENTINEL_PORT", "26379")
        return f"sentinel://{sentinel_host}:{sentinel_port}"
    else:
        # Direct connection fallback
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = os.getenv("REDIS_PORT", "6379")
        db = os.getenv("REDIS_DB", "0")
        return f"redis://{redis_host}:{redis_port}/{db}"

# Create Celery app
celery_app = Celery("myapp", backend=_get_redis_backend_url())

# Configure Sentinel transport options
if os.getenv("REDIS_SENTINEL_ENABLED", "true").lower() == "true":
    celery_app.conf.result_backend_transport_options = {
        'master_name': os.getenv("REDIS_SENTINEL_MASTER", "mymaster"),
        'db': int(os.getenv("REDIS_DB", "0"))
    }
```

## Failover Behavior

1. **Master Failure:** Sentinels detect master is down after 5 seconds
2. **Quorum:** At least 2 out of 3 sentinels must agree
3. **Promotion:** A replica is promoted to master
4. **Client Reconnection:** Applications using Sentinel automatically connect to new master
5. **Recovery:** Failed master becomes replica when it comes back online

**Total Failover Time:** ~15 seconds (vs 30+ seconds with manual intervention)

## Configuration

### Redis Settings (04-cluster.yaml)

- **Replicas:** 3 (1 master + 2 replicas)
- **CPU:** 100m-1000m per pod
- **Memory:** 256Mi-1Gi per pod
- **Max Memory:** 512MB (allkeys-lru eviction)
- **Persistence:** RDB + AOF enabled
- **Authentication:** Disabled (no password)

### Sentinel Settings

- **Replicas:** 3 (quorum of 2)
- **Down-after-milliseconds:** 5000 (5s to declare master down)
- **Failover-timeout:** 10000 (10s failover timeout)
- **Parallel-syncs:** 1 (sync 1 replica at a time)

## Monitoring

### Check Cluster Status

```bash
# Get RedisFailover status
kubectl get redisfailover redis-cluster -n saasodoo

# Get all Redis pods
kubectl get pods -n saasodoo -l app.kubernetes.io/name=redis-cluster

# Check which pod is master
kubectl get pods -n saasodoo -l redisfailovers-role=master

# Check replication status
kubectl exec -n saasodoo rfr-redis-cluster-0 -- redis-cli INFO replication
```

### Check Sentinel

```bash
# Get Sentinel master address
kubectl exec -n saasodoo rfs-redis-cluster-<pod> -- \
  redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster

# Get all Sentinel info
kubectl exec -n saasodoo rfs-redis-cluster-<pod> -- \
  redis-cli -p 26379 SENTINEL masters
```

### Check Operator

```bash
# Operator logs
kubectl logs -n redis-operator -l app.kubernetes.io/name=redis-operator --tail=100 -f

# Operator status
kubectl get pods -n redis-operator
```

## Testing Failover

```bash
# 1. Check current master
kubectl get pods -n saasodoo -l redisfailovers-role=master

# 2. Delete master pod to trigger failover
kubectl delete pod <master-pod-name> -n saasodoo

# 3. Watch Sentinel promote a replica (takes ~15 seconds)
kubectl logs -n saasodoo rfs-redis-cluster-<pod> -f

# 4. Verify new master
kubectl get pods -n saasodoo -l redisfailovers-role=master
kubectl exec -n saasodoo rfr-redis-cluster-1 -- redis-cli INFO replication | grep role
```

## Troubleshooting

### Operator Issues

```bash
# Check operator logs
kubectl logs -n redis-operator -l app.kubernetes.io/name=redis-operator --tail=100

# Check CRD is installed
kubectl get crd | grep redisfailover

# Check operator has proper RBAC
kubectl get clusterrole redis-operator
kubectl get clusterrolebinding redis-operator
```

### Cluster Issues

```bash
# Check RedisFailover resource
kubectl describe redisfailover redis-cluster -n saasodoo

# Check Redis pods
kubectl get pods -n saasodoo -l app.kubernetes.io/name=redis-cluster
kubectl logs -n saasodoo rfr-redis-cluster-0

# Check Sentinel pods
kubectl get pods -n saasodoo -l app.kubernetes.io/component=sentinel
kubectl logs -n saasodoo rfs-redis-cluster-<pod>
```

### Connection Issues

```bash
# Test Sentinel connection
kubectl run -it --rm redis-test --image=redis:7-alpine --restart=Never -n saasodoo -- \
  redis-cli -h rfs-redis-cluster.saasodoo.svc.cluster.local -p 26379 \
  SENTINEL get-master-addr-by-name mymaster

# Test direct Redis connection
kubectl exec -n saasodoo rfr-redis-cluster-0 -- redis-cli ping

# Check services
kubectl get svc -n saasodoo | grep redis
kubectl get endpoints rfs-redis-cluster -n saasodoo
```

## Files in This Directory

- `00-operator-namespace.yaml` - Namespace for Redis Operator
- `01-operator-crd.yaml` - RedisFailover CustomResourceDefinition
- `02-operator-rbac.yaml` - ServiceAccount, ClusterRole, ClusterRoleBinding for operator
- `03-operator-deployment.yaml` - Redis Operator deployment
- `04-cluster.yaml` - RedisFailover custom resource (creates the cluster)
- `DEPLOYMENT.md` - Detailed deployment notes
- `SUMMARY.md` - Technical summary
- `README.md` - This file

## Resources Created

### By Operator Deployment
- Namespace: `redis-operator`
- CRD: `redisfailovers.databases.spotahome.com`
- ServiceAccount: `redis-operator`
- ClusterRole: `redis-operator`
- ClusterRoleBinding: `redis-operator`
- Deployment: `redis-operator` (1 replica)
- Service: `redis-operator` (metrics on port 9710)

### By RedisFailover CR
- StatefulSet: `rfr-redis-cluster` (3 pods)
- Deployment: `rfs-redis-cluster` (3 sentinel pods)
- Service: `rfs-redis-cluster` (Sentinel service, port 26379)
- Headless Service: Automatically created by StatefulSet for DNS

## Uninstall

```bash
# Delete Redis cluster
kubectl delete -f 04-cluster.yaml

# Delete operator (if no other Redis clusters)
kubectl delete -f 03-operator-deployment.yaml
kubectl delete -f 02-operator-rbac.yaml
kubectl delete -f 01-operator-crd.yaml
kubectl delete -f 00-operator-namespace.yaml
```

## References

- [Spotahome Redis Operator](https://github.com/spotahome/redis-operator)
- [Redis Sentinel Documentation](https://redis.io/docs/management/sentinel/)
- [Python Redis Sentinel](https://redis-py.readthedocs.io/en/stable/connections.html#redis.sentinel.Sentinel)
- [Celery Redis Sentinel](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
