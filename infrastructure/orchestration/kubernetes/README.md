# SaaSOdoo Kubernetes Deployment

This directory contains Kubernetes manifests and scripts for deploying SaaSOdoo on Kubernetes (Docker Desktop).

## Directory Structure

```
kubernetes/
├── infrastructure/           # Core infrastructure resources
│   ├── 00-namespace.yaml    # Namespace and labels
│   ├── 01-rbac.yaml         # ServiceAccounts, Roles, RoleBindings
│   ├── secrets/             # ConfigMaps and Secrets
│   ├── storage/             # StorageClass and PersistentVolumes
│   ├── databases/           # PostgreSQL, Redis, RabbitMQ, KillBill
│   └── networking/          # Ingress configuration
├── services/                # Application service deployments
│   ├── user-service/
│   ├── billing-service/
│   ├── instance-service/
│   ├── instance-worker/
│   └── frontend-service/
├── registry/                # Local Docker registry for images
└── scripts/                 # Deployment automation scripts
```

## Prerequisites

1. **Kubernetes in Docker Desktop** (already configured)
2. **kubectl** CLI tool installed
3. **Docker** for building images
4. **NGINX Ingress Controller** installed:
   ```bash
   kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.2/deploy/static/provider/cloud/deploy.yaml
   ```
5. **CephFS mounted** at `/mnt/cephfs` on the host

## Quick Start

### 1. Start Local Registry

```bash
cd infrastructure/orchestration/kubernetes/registry
docker compose -f docker-compose.local-registry.yaml up -d
```

### 2. Build and Push Images

```bash
cd infrastructure/orchestration/kubernetes
./scripts/build-and-push.sh
```

### 3. Deploy to Kubernetes

```bash
./scripts/deploy.sh
```

### 4. Add Hosts to /etc/hosts

```bash
sudo bash -c 'cat >> /etc/hosts << EOF
127.0.0.1 api.saasodoo.local
127.0.0.1 app.saasodoo.local
127.0.0.1 billing.saasodoo.local
127.0.0.1 rabbitmq.saasodoo.local
EOF'
```

## Access Services

- **Frontend**: http://app.saasodoo.local
- **User API**: http://api.saasodoo.local/user
- **Billing API**: http://api.saasodoo.local/billing
- **Instance API**: http://api.saasodoo.local/instance
- **KillBill**: http://billing.saasodoo.local
- **RabbitMQ Management**: http://rabbitmq.saasodoo.local

## Managing the Deployment

### Check Status

```bash
# All pods
kubectl get pods -n saasodoo

# All services
kubectl get services -n saasodoo

# Ingress
kubectl get ingress -n saasodoo

# PVCs
kubectl get pvc -n saasodoo
```

### View Logs

```bash
# User service
kubectl logs -f deployment/user-service -n saasodoo

# Instance worker
kubectl logs -f deployment/instance-worker -n saasodoo

# PostgreSQL
kubectl logs -f statefulset/postgres -n saasodoo
```

### Scale Services

```bash
# Scale user-service to 3 replicas
kubectl scale deployment/user-service --replicas=3 -n saasodoo

# Scale instance-worker to 4 replicas
kubectl scale deployment/instance-worker --replicas=4 -n saasodoo
```

### Update a Service

```bash
# Rebuild and push image
./scripts/build-and-push.sh

# Restart deployment to pull new image
kubectl rollout restart deployment/user-service -n saasodoo
```

### Debug a Pod

```bash
# Get shell in a pod
kubectl exec -it deployment/user-service -n saasodoo -- /bin/bash

# Check environment variables
kubectl exec deployment/user-service -n saasodoo -- env

# Describe pod for events
kubectl describe pod <pod-name> -n saasodoo
```

### Port Forward for Direct Access

```bash
# PostgreSQL
kubectl port-forward svc/postgres-service 5432:5432 -n saasodoo

# Redis
kubectl port-forward svc/redis-service 6379:6379 -n saasodoo

# User Service
kubectl port-forward svc/user-service 8001:8001 -n saasodoo
```

## Teardown

```bash
./scripts/teardown.sh
```

## Key Differences from Docker Swarm

### 1. Orchestration Model
- **Swarm**: `docker-compose.yml` with `deploy` sections
- **Kubernetes**: Separate YAML manifests for each resource type

### 2. Service Discovery
- **Swarm**: Service name directly (e.g., `postgres`)
- **Kubernetes**: Service name + namespace (e.g., `postgres-service.saasodoo.svc.cluster.local`)

### 3. Secrets Management
- **Swarm**: Docker secrets
- **Kubernetes**: Kubernetes Secrets (base64 encoded)

### 4. Instance Management
- **Swarm**: Docker SDK (Docker socket)
- **Kubernetes**: Kubernetes Python Client (in-cluster API)

### 5. Networking
- **Swarm**: Traefik with Docker provider
- **Kubernetes**: NGINX Ingress Controller

### 6. Storage
- **Swarm**: Volume mounts
- **Kubernetes**: PersistentVolumes and PersistentVolumeClaims

### 7. RBAC
- **Swarm**: None (Docker socket access)
- **Kubernetes**: ServiceAccounts, Roles, RoleBindings

## Instance Service Changes

The instance-service now uses the **Kubernetes Python client** instead of the Docker SDK:

- Manages Odoo instances as **Pods** (not containers)
- Uses **ServiceAccounts** with RBAC for API access
- Creates **Services** for instance networking
- Uses **PVCs** for instance storage

See `services/instance-service/app/utils/k8s_client.py` for implementation details.

## Troubleshooting

### Pods stuck in Pending
```bash
kubectl describe pod <pod-name> -n saasodoo
# Check for PVC binding issues or resource constraints
```

### Ingress not working
```bash
# Check NGINX Ingress Controller is running
kubectl get pods -n ingress-nginx

# Check Ingress resource
kubectl describe ingress api-ingress -n saasodoo
```

### Database connection issues
```bash
# Check PostgreSQL is ready
kubectl get pod -l app.kubernetes.io/name=postgres -n saasodoo

# Check service endpoints
kubectl get endpoints postgres-service -n saasodoo
```

### Image pull errors
```bash
# Check local registry is running
docker ps | grep local-k8s-registry

# Push image again
./scripts/build-and-push.sh
```

## Production Considerations

For production deployment, consider:

1. **External Secrets Operator** or **Sealed Secrets** for secret management
2. **Cert-Manager** for TLS certificate automation
3. **Prometheus + Grafana** for monitoring
4. **EFK Stack** (Elasticsearch, Fluentd, Kibana) for logging
5. **Velero** for backup and disaster recovery
6. **Resource Quotas** and **LimitRanges**
7. **Pod Disruption Budgets**
8. **HorizontalPodAutoscaler** for auto-scaling
9. **NetworkPolicies** for network segmentation
10. **Rook-Ceph** for production-grade distributed storage
