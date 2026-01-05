# RabbitMQ Cluster - High Availability Setup

Production-ready RabbitMQ cluster using the official RabbitMQ Cluster Operator.

## Architecture

**3-Node Cluster:**
```
rabbitmq-server-0 (primary)  ──┐
rabbitmq-server-1 (replica)  ──┼── Quorum queues replicated
rabbitmq-server-2 (replica)  ──┘

Service: rabbitmq.saasodoo.svc.cluster.local:5672
Management: rabbitmq.saasodoo.svc.cluster.local:15672
```

**Features:**
- ✅ Automatic failover (any node can die)
- ✅ Quorum queues properly replicated across 3 nodes
- ✅ CephFS persistent storage (10Gi per node)
- ✅ Prometheus metrics auto-enabled
- ✅ Management UI on all nodes
- ✅ Zero code changes (same service name)

## Prerequisites

- Kubernetes 1.25+
- Storage: `rook-cephfs` StorageClass
- Namespace: `saasodoo`

## Installation

### Step 1: Install RabbitMQ Cluster Operator

```bash
# Install operator (into rabbitmq-system namespace)
kubectl apply -f "https://github.com/rabbitmq/cluster-operator/releases/latest/download/cluster-operator.yml"

# Verify operator is running
kubectl get deployment -n rabbitmq-system rabbitmq-cluster-operator

# Check CRD installed
kubectl get crd rabbitmqclusters.rabbitmq.com
```

### Step 2: Stop Celery Workers

```bash
# Scale down workers to avoid connection issues during migration
kubectl scale deployment instance-worker database-worker database-beat -n saasodoo --replicas=0

# Verify workers stopped
kubectl get pods -n saasodoo | grep worker
```

### Step 3: Remove Old RabbitMQ

```bash
# Delete old StatefulSet
kubectl delete statefulset rabbitmq -n saasodoo

# Delete old service (operator will recreate with same name)
kubectl delete svc rabbitmq -n saasodoo

# Keep old PVC for now (delete after verification)
# kubectl delete pvc rabbitmq-pvc -n saasodoo
```

### Step 4: Deploy RabbitMQ Cluster

```bash
# Create credentials secret
kubectl apply -f 00-secret.yaml

# Deploy 3-node cluster
kubectl apply -f 03-rabbitmq-cluster.yaml

# Watch cluster creation (takes 3-5 minutes)
kubectl get rabbitmqcluster rabbitmq -n saasodoo -w
```

Expected output:
```
NAME       ALLREPLICASREADY   RECONCILESUCCESS   AGE
rabbitmq   False              Unknown            10s
rabbitmq   False              True               30s
rabbitmq   True               True               3m
```

### Step 5: Verify Cluster

```bash
# Check cluster status
kubectl get rabbitmqcluster rabbitmq -n saasodoo

# Check all 3 pods running
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq

# Check service created with correct name
kubectl get svc rabbitmq -n saasodoo

# Check PVCs created
kubectl get pvc -n saasodoo | grep rabbitmq
```

### Step 6: Restart Celery Workers

```bash
# Scale workers back up
kubectl scale deployment instance-worker database-worker database-beat -n saasodoo --replicas=2

# Watch workers connect to new cluster
kubectl logs -n saasodoo -l app.kubernetes.io/name=instance-worker --tail=50 -f
```

Look for: `Connected to amqp://saasodoo:**@rabbitmq:5672/saasodoo`

### Step 7: Verify Quorum Queues

```bash
# Port-forward to management UI
kubectl port-forward -n saasodoo svc/rabbitmq 15672:15672
```

Open browser: http://localhost:15672
- Login: `saasodoo` / `saasodoo123`
- Navigate to **Queues** tab
- Verify queues show:
  - Type: `quorum`
  - Nodes: `3`
  - Leader: One node elected

### Step 8: Cleanup

```bash
# After verifying everything works, delete old PVC
kubectl delete pvc rabbitmq-pvc -n saasodoo

# Archive old manifests
mv ../rabbitmq ../rabbitmq-old-backup
```

## Verification Commands

### Cluster Health

```bash
# Overall cluster status
kubectl get rabbitmqcluster rabbitmq -n saasodoo

# Pod status
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq

# Detailed cluster info
kubectl describe rabbitmqcluster rabbitmq -n saasodoo
```

### Service Endpoint

```bash
# Check service
kubectl get svc rabbitmq -n saasodoo

# Test connection from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n saasodoo -- \
  sh -c "curl -u saasodoo:saasodoo123 http://rabbitmq:15672/api/overview"
```

### Storage

```bash
# Check PVCs
kubectl get pvc -n saasodoo | grep persistence-rabbitmq

# Check PV usage
kubectl exec -it rabbitmq-server-0 -n saasodoo -- df -h /var/lib/rabbitmq
```

### Logs

```bash
# All pods
kubectl logs -n saasodoo -l app.kubernetes.io/name=rabbitmq --tail=100 -f

# Specific pod
kubectl logs -n saasodoo rabbitmq-server-0 --tail=100 -f

# Check for errors
kubectl logs -n saasodoo -l app.kubernetes.io/name=rabbitmq | grep -i error
```

## Testing Failover

```bash
# Delete a pod to test automatic failover
kubectl delete pod rabbitmq-server-0 -n saasodoo

# Watch cluster recover
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq -w

# Celery workers should automatically reconnect
kubectl logs -n saasodoo deployment/instance-worker --tail=50 | grep "Connected to amqp"

# Check quorum queues elected new leader
# Management UI → Queues → Check "Leader" column
```

## Scaling

### Scale Up (Add Nodes)

```bash
# Edit cluster to add more nodes
kubectl patch rabbitmqcluster rabbitmq -n saasodoo --type='merge' -p '{"spec":{"replicas":5}}'

# Watch new nodes join
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq -w
```

### Scale Down (Remove Nodes)

```bash
# Scale down (minimum 3 for quorum queues)
kubectl patch rabbitmqcluster rabbitmq -n saasodoo --type='merge' -p '{"spec":{"replicas":3}}'

# Operator gracefully removes nodes
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq -w
```

## Upgrading RabbitMQ

```bash
# Update image version in cluster spec
kubectl patch rabbitmqcluster rabbitmq -n saasodoo --type='merge' -p '{"spec":{"image":"rabbitmq:4.2.0-management-alpine"}}'

# Operator performs rolling update (zero downtime)
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq -w
```

## Monitoring

### Prometheus Metrics

```bash
# Metrics endpoint (auto-enabled by operator)
kubectl port-forward -n saasodoo svc/rabbitmq 15692:15692

# Scrape metrics
curl http://localhost:15692/metrics
```

### Management UI

```bash
# Port-forward to UI
kubectl port-forward -n saasodoo svc/rabbitmq 15672:15672

# Open browser
open http://localhost:15672
```

**Useful metrics:**
- Queue depth
- Message rates (publish/deliver/ack)
- Connection count
- Channel count
- Memory usage
- Disk usage

## Troubleshooting

### Cluster Not Ready

```bash
# Check operator logs
kubectl logs -n rabbitmq-system deployment/rabbitmq-cluster-operator --tail=100 -f

# Check cluster events
kubectl describe rabbitmqcluster rabbitmq -n saasodoo

# Check pod events
kubectl describe pod rabbitmq-server-0 -n saasodoo
```

### Pods Stuck in Pending

```bash
# Check PVC status
kubectl get pvc -n saasodoo | grep rabbitmq

# Check storage class
kubectl get sc rook-cephfs

# Check node resources
kubectl describe node | grep -A 5 "Allocated resources"
```

### Workers Can't Connect

```bash
# Check service exists
kubectl get svc rabbitmq -n saasodoo

# Check service endpoints
kubectl get endpoints rabbitmq -n saasodoo

# Test from worker pod
kubectl exec -it instance-worker-xxx -n saasodoo -- \
  nc -zv rabbitmq 5672
```

### Quorum Queues Not Replicating

```bash
# Check cluster status in management UI
# All 3 nodes should show as "running"

# Check queue details
# Queues → Click queue name → Check "Node" and "Mirrors" columns

# Force queue sync (if needed)
# Management UI → Queue → "Synchronise" button
```

## Rollback Plan

If issues occur, rollback to old setup:

```bash
# Scale down workers
kubectl scale deployment instance-worker database-worker database-beat --replicas=0 -n saasodoo

# Delete cluster
kubectl delete rabbitmqcluster rabbitmq -n saasodoo

# Restore old StatefulSet
kubectl apply -f ../rabbitmq-old-backup/01-statefulset.yaml
kubectl apply -f ../rabbitmq-old-backup/02-service.yaml

# Scale up workers
kubectl scale deployment instance-worker database-worker database-beat --replicas=2 -n saasodoo
```

## Configuration Reference

### Cluster Spec

- **Replicas:** 3 (minimum for quorum queues)
- **Image:** rabbitmq:4.1.3-management-alpine
- **Storage:** 10Gi per node (rook-cephfs)
- **Resources:** 500m CPU, 1Gi RAM (request) / 1000m CPU, 2Gi RAM (limit)
- **Vhost:** saasodoo
- **Plugins:** management, prometheus, peer_discovery_k8s, shovel

### Service Endpoints

- **AMQP:** `rabbitmq.saasodoo.svc.cluster.local:5672`
- **Management:** `rabbitmq.saasodoo.svc.cluster.local:15672`
- **Prometheus:** `rabbitmq.saasodoo.svc.cluster.local:15692`
- **Inter-node:** `rabbitmq-nodes.saasodoo.svc.cluster.local` (headless)

### Default Credentials

- **Username:** saasodoo
- **Password:** saasodoo123 (change in production!)
- **Vhost:** saasodoo

## Resources

- [RabbitMQ Cluster Operator Docs](https://www.rabbitmq.com/kubernetes/operator/operator-overview)
- [Quorum Queues Guide](https://www.rabbitmq.com/quorum-queues.html)
- [Production Checklist](https://www.rabbitmq.com/production-checklist.html)
- [Monitoring Guide](https://www.rabbitmq.com/monitoring.html)
