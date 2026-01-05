# Deploy Directory

Kubernetes manifests for SaaSOdoo platform applications.

## Structure

```
deploy/
├── 00-namespace.yaml          # saasodoo namespace
├── 00-secrets.example.yaml    # Secrets template (copy to 00-secrets.yaml)
├── 00-shared-config.yaml      # Shared ConfigMap for all services
├── 01-rbac.yaml               # ServiceAccounts and RBAC
│
├── platform/                  # Platform microservices
│   ├── user-service/         # Authentication & user management
│   ├── billing-service/      # KillBill integration & subscriptions
│   ├── instance-service/     # Odoo instance lifecycle API
│   ├── instance-worker/      # Celery workers for instance ops
│   ├── database-service/     # Database pool management API
│   ├── database-worker/      # Celery workers for DB provisioning
│   ├── database-beat/        # Celery beat scheduler
│   ├── notification-service/ # Email & notifications
│   ├── notification-worker/  # Notification workers
│   ├── frontend-service/     # React web application
│   ├── killbill/            # Billing engine (MariaDB + KillBill + Kaui)
│   └── mailhog/             # Email testing (development)
│
└── scripts/
    ├── deploy.sh             # Deploy all manifests
    ├── teardown.sh           # Remove all resources
    ├── build-and-push.sh     # Build and push Docker images
    └── generate-secrets.sh   # Generate secrets file
```

## Quick Start

### 1. Generate Secrets
```bash
# Copy example and fill in values
cp deploy/00-secrets.example.yaml deploy/00-secrets.yaml
# Or use the generator script
./deploy/scripts/generate-secrets.sh
```

### 2. Deploy Platform
```bash
./deploy/scripts/deploy.sh
```

### 3. Check Status
```bash
kubectl get pods -n saasodoo
kubectl get svc -n saasodoo
```

## Service Details

### Platform Services

| Service | Port | Description |
|---------|------|-------------|
| user-service | 8001 | Authentication, user management |
| billing-service | 8004 | KillBill integration, subscriptions |
| instance-service | 8003 | Odoo instance lifecycle API |
| instance-worker | - | Celery workers for provisioning |
| database-service | 8002 | Database pool management |
| database-worker | - | Celery workers for DB ops |
| database-beat | - | Celery beat scheduler |
| notification-service | 5000 | Email and notifications |
| frontend-service | 3000 | React web application |

### Supporting Services

| Service | Port | Description |
|---------|------|-------------|
| killbill | 8080 | Billing engine |
| kaui | 9090 | KillBill admin UI |
| mailhog | 8025 | Email testing (dev) |

## Manifest Structure

Each service directory contains:
```
{service-name}/
├── 00-config.yaml        # ConfigMap (if needed)
├── 01-deployment.yaml    # Kubernetes Deployment
├── 02-service.yaml       # Kubernetes Service
└── 03-ingressroute.yaml  # Traefik IngressRoute (if exposed)
```

## Manual Deployment

```bash
# Foundation
kubectl apply -f deploy/00-namespace.yaml
kubectl apply -f deploy/00-secrets.yaml
kubectl apply -f deploy/00-shared-config.yaml
kubectl apply -f deploy/01-rbac.yaml

# Platform services (order matters for dependencies)
kubectl apply -f deploy/platform/killbill/
kubectl apply -f deploy/platform/user-service/
kubectl apply -f deploy/platform/billing-service/
kubectl apply -f deploy/platform/instance-service/
kubectl apply -f deploy/platform/instance-worker/
kubectl apply -f deploy/platform/database-service/
kubectl apply -f deploy/platform/database-worker/
kubectl apply -f deploy/platform/database-beat/
kubectl apply -f deploy/platform/notification-service/
kubectl apply -f deploy/platform/frontend-service/
```

## Rebuilding Services

```bash
# Build and push image
docker build -t registry.62.171.153.219.nip.io/instance-service:latest \
  -f services/instance-service/Dockerfile .
docker push registry.62.171.153.219.nip.io/instance-service:latest

# Restart deployment
kubectl rollout restart deployment/instance-service -n saasodoo
kubectl rollout status deployment/instance-service -n saasodoo
```

## Environment Variables

Services load configuration in priority order:
1. `shared-config` ConfigMap (lowest priority)
2. Service-specific ConfigMap
3. Service-specific Secret (highest priority)

## Related Directories

- **infrastructure/**: Cluster and infrastructure components
- **services/**: Application source code
- **shared/**: Shared libraries and schemas
