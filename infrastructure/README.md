# Infrastructure Directory

Kubernetes-based infrastructure for the SaaSOdoo multi-tenant platform.

## Structure

### Core Configuration Files
- **00-namespace.yaml**: Kubernetes namespace definition
- **00-configmap.yaml**: Platform-wide configuration
- **00-secrets.yaml**: Sensitive credentials (not in git)
- **00-secrets.example.yaml**: Template for secrets
- **01-rbac.yaml**: Role-based access control for service accounts

### images/
Custom Docker images with embedded configurations.

- **postgres/**: PostgreSQL with initialization scripts
  - `Dockerfile`: Custom postgres image
  - `init-scripts/`: Database schemas (auto-run on first start)

- **redis/**: Redis with custom configuration
  - `Dockerfile`: Custom redis image
  - `redis.conf`: Redis configuration file

### Infrastructure Components

#### postgres/
Platform PostgreSQL StatefulSet with database schemas and init scripts.
- Hosts platform databases: auth, billing, instance, communication
- Maintains db_servers table for pool management

#### redis/
Redis StatefulSet for session storage, caching, and Celery result backend.

#### rabbitmq/
RabbitMQ StatefulSet for Celery task queues.
- Queues: provisioning, operations, maintenance, monitoring

#### killbill/
Billing engine infrastructure.
- **mariadb/**: KillBill database StatefulSet
- **killbill/**: KillBill server Deployment
- **kaui/**: KillBill admin UI Deployment

#### kubernetes-dashboard/
Kubernetes web UI for cluster management.

#### registry/
Container registry infrastructure.
- Kubernetes manifests for registry Deployment
- Local registry docker-compose for development

### networking/
Network infrastructure components.

- **metallb/**: Load balancer for bare-metal Kubernetes
  - IP address pool configuration
  - L2 advertisement settings

- **traefik/**: Kubernetes-native Traefik ingress controller
  - CRDs (Custom Resource Definitions)
  - RBAC permissions
  - Deployment and Service manifests
  - IngressRoute configurations

### services/
Platform microservices Kubernetes manifests.

- **user-service/**: Authentication and user management
- **instance-service/**: Odoo instance lifecycle management API
- **instance-worker/**: Celery workers for instance operations
- **database-service/**: Database pool management API
- **database-worker/**: Celery workers for database provisioning
- **database-beat/**: Celery beat scheduler
- **billing-service/**: KillBill integration and subscriptions
- **notification-service/**: Email and notifications
- **frontend-service/**: React web application
- **mailhog/**: Email testing (development)

Each service directory contains:
- `00-rbac.yaml`: Service account and permissions (if needed)
- `01-deployment.yaml`: Kubernetes Deployment
- `02-service.yaml`: Kubernetes Service
- `03-ingressroute.yaml`: Traefik routing (if exposed)

### scripts/
Deployment and management scripts.

- **deploy.sh**: Deploy all Kubernetes manifests
- **build-and-push.sh**: Build and push service images
- **teardown.sh**: Remove all resources

### security/
Security configurations and hardening rules.

### storage/
Storage infrastructure.

- **ceph/**: CephFS distributed filesystem configurations
- **00-storageclass.yaml**: Kubernetes StorageClass definitions
- **01-persistent-volumes.yaml**: PersistentVolume configurations

## Quick Commands

### Deploy Entire Platform
```bash
cd /root/Projects/saasodoo

# Deploy all manifests
./infrastructure/scripts/deploy.sh

# Or manually:
kubectl apply -f infrastructure/00-namespace.yaml
kubectl apply -f infrastructure/00-secrets.yaml
kubectl apply -f infrastructure/00-configmap.yaml
kubectl apply -f infrastructure/01-rbac.yaml
kubectl apply -f infrastructure/storage/
kubectl apply -f infrastructure/networking/
kubectl apply -f infrastructure/postgres/
kubectl apply -f infrastructure/redis/
kubectl apply -f infrastructure/rabbitmq/
kubectl apply -f infrastructure/killbill/
kubectl apply -f infrastructure/services/
```

### Build and Push Service Images
```bash
# Build all services
./infrastructure/scripts/build-and-push.sh

# Or build specific service:
docker build -t registry.62.171.153.219.nip.io/instance-service:latest \
  -f services/instance-service/Dockerfile .
docker push registry.62.171.153.219.nip.io/instance-service:latest
```

### Rebuild Custom Infrastructure Images
```bash
# Postgres
docker build -t registry.62.171.153.219.nip.io/compose-postgres:latest \
  -f infrastructure/images/postgres/Dockerfile .
docker push registry.62.171.153.219.nip.io/compose-postgres:latest

# Redis
docker build -t registry.62.171.153.219.nip.io/compose-redis:latest \
  -f infrastructure/images/redis/Dockerfile .
docker push registry.62.171.153.219.nip.io/compose-redis:latest
```

### Check Platform Status
```bash
# All pods
kubectl get pods -n saasodoo

# All services
kubectl get svc -n saasodoo

# Check specific service
kubectl logs -n saasodoo -l app.kubernetes.io/name=instance-service --tail=100
```

### Teardown
```bash
./infrastructure/scripts/teardown.sh
```

## Architecture Benefits

**Kubernetes-Native**:
- Declarative infrastructure as code
- Self-healing and auto-restart
- Resource management and limits
- Rolling updates with zero downtime

**Separation of Concerns**:
- Infrastructure components: postgres, redis, rabbitmq, killbill
- Platform services: user, instance, billing, notification
- Networking: Traefik ingress with IngressRoutes
- Storage: CephFS persistent volumes
- Images: Custom build configurations

**Clear Organization**:
- All manifests in logical directories
- Root config files for namespace, secrets, RBAC
- Service-specific manifests grouped by service
- Scripts for common operations

## Migration from Docker Swarm

This infrastructure was migrated from Docker Swarm to Kubernetes on 2025-12-26.

**Key Changes**:
- Removed `infrastructure/orchestration/swarm/` directory
- Moved from `infrastructure/orchestration/kubernetes/` to `infrastructure/`
- Replaced Swarm Traefik config with Kubernetes IngressRoutes
- Updated all deployment scripts and documentation

**Old Structure**:
```
infrastructure/orchestration/
├── kubernetes/  # Nested directory
└── swarm/       # Docker Swarm configs
```

**New Structure**:
```
infrastructure/  # Kubernetes manifests at root
├── services/
├── postgres/
├── redis/
└── ...
```

All build scripts, deployment workflows, and documentation have been updated for Kubernetes-only deployment.
