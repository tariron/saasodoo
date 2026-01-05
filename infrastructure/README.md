# Infrastructure Directory

Kubernetes infrastructure components for the SaaSOdoo multi-tenant platform.

## Structure

```
infrastructure/
├── cluster/                    # Cluster configuration & hardening
│   ├── node-config/           # RKE2/K3s node configuration
│   ├── helm-configs/          # HelmChartConfig overrides
│   ├── resource-management/   # LimitRange, ResourceQuota
│   ├── resilience/            # PodDisruptionBudgets
│   ├── security/              # Pod Security Standards, Network Policies
│   ├── addons/                # Control plane add-ons
│   │   └── cert-manager/      # TLS certificate management
│   └── scripts/               # Cluster setup scripts
│
├── networking/                 # Network infrastructure
│   ├── metallb/               # Bare-metal load balancer
│   └── traefik/               # Ingress controller
│
├── storage/                    # Storage infrastructure
│   ├── rook/                  # Rook operator for Ceph
│   └── ceph/                  # CephFS configuration
│
├── databases/                  # Database infrastructure
│   ├── postgres-cnpg/         # CloudNativePG PostgreSQL cluster
│   ├── redis/                 # Redis for caching & sessions
│   └── rabbitmq/              # RabbitMQ message broker
│
├── monitoring/                 # Observability stack
│   ├── prometheus/            # Metrics collection
│   ├── grafana/               # Dashboards
│   ├── kube-state-metrics/    # Cluster state metrics
│   └── metrics-server/        # Resource metrics for HPA
│
├── registry/                   # Container registry
│
├── tools/                      # Supporting tools
│   ├── kubernetes-dashboard/  # Cluster web UI
│   └── rancher/               # Cluster management
│
└── images/                     # Custom Docker images
    └── postgres/              # Custom PostgreSQL image
```

## Deployment Order

### Phase 1: Cluster Setup
```bash
# Apply cluster hardening configs
kubectl apply -f infrastructure/cluster/resource-management/
kubectl apply -f infrastructure/cluster/security/
kubectl apply -f infrastructure/cluster/resilience/
kubectl apply -f infrastructure/cluster/addons/cert-manager/
```

### Phase 2: Storage & Networking
```bash
kubectl apply -f infrastructure/storage/rook/
kubectl apply -f infrastructure/networking/metallb/
kubectl apply -f infrastructure/networking/traefik/
```

### Phase 3: Databases
```bash
kubectl apply -f infrastructure/databases/postgres-cnpg/
kubectl apply -f infrastructure/databases/redis/
kubectl apply -f infrastructure/databases/rabbitmq/
```

### Phase 4: Monitoring
```bash
kubectl apply -f infrastructure/monitoring/
```

### Phase 5: Applications
See `deploy/` directory for application manifests.

## Component Details

### cluster/
Cluster-level configurations that apply to all nodes:
- **node-config/**: RKE2/K3s configuration files and setup instructions
- **helm-configs/**: HelmChartConfig CRDs for RKE2 component customization
- **resource-management/**: Default resource limits and namespace quotas
- **resilience/**: PodDisruptionBudgets for HA components
- **security/**: Pod Security Standards, fail2ban configs
- **addons/**: Lightweight control plane add-ons (cert-manager, etc.)

### networking/
- **metallb/**: L2 load balancer for bare-metal (IP pool: 62.171.153.219)
- **traefik/**: Kubernetes-native ingress with IngressRoute CRDs

### storage/
- **rook/**: Rook-Ceph operator for distributed storage
- **ceph/**: CephFS filesystem and StorageClass definitions

### databases/
- **postgres-cnpg/**: HA PostgreSQL via CloudNativePG operator (3 replicas)
- **redis/**: Redis for sessions, caching, Celery backend
- **rabbitmq/**: RabbitMQ cluster for Celery task queues

### monitoring/
- **prometheus/**: Metrics scraping and alerting
- **grafana/**: Visualization dashboards
- **kube-state-metrics/**: Cluster object metrics
- **metrics-server/**: Resource metrics for kubectl top and HPA

### tools/
Optional management tools:
- **kubernetes-dashboard/**: Web UI for cluster management
- **rancher/**: Multi-cluster management (optional)

## Quick Commands

### Check Infrastructure Status
```bash
# All infrastructure pods
kubectl get pods -n saasodoo -l app.kubernetes.io/part-of=infrastructure

# Database status
kubectl get clusters.postgresql.cnpg.io -n saasodoo
kubectl get pods -n saasodoo -l app.kubernetes.io/name=redis
kubectl get pods -n saasodoo -l app.kubernetes.io/name=rabbitmq

# Storage status
kubectl get cephcluster -n rook-ceph
kubectl get sc
```

### View Logs
```bash
# PostgreSQL primary
kubectl logs -n saasodoo -l cnpg.io/cluster=postgres-cluster,role=primary

# Traefik
kubectl logs -n saasodoo -l app.kubernetes.io/name=traefik
```

## Related Directories

- **deploy/**: Application manifests (platform services)
- **services/**: Application source code
- **shared/**: Shared libraries and schemas
