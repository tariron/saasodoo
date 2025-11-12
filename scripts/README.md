# SaaSOdoo Build Scripts

This directory contains scripts for building and managing Docker images for the SaaSOdoo platform.

## Configuration

The scripts automatically read the registry URL from `infrastructure/compose/.env.swarm`:

```bash
# In .env.swarm
BASE_DOMAIN=62.171.153.219.nip.io
DOCKER_REGISTRY=registry.${BASE_DOMAIN}
```

This expands to: `registry.62.171.153.219.nip.io`

## Changing the Registry

To change the registry URL, update the `DOCKER_REGISTRY` variable in `infrastructure/compose/.env.swarm`:

```bash
# For a different domain
BASE_DOMAIN=example.com
DOCKER_REGISTRY=registry.${BASE_DOMAIN}

# Or use a completely different registry
DOCKER_REGISTRY=my-custom-registry.com

# For Docker Hub with namespace
DOCKER_REGISTRY=docker.io/myusername

# For private registries
DOCKER_REGISTRY=private-registry.company.com:5000
```

The scripts will automatically use the updated registry URL.

## Scripts

### 1. build-all.sh

Builds and pushes all services to the registry.

**Usage:**
```bash
# Build all services
./scripts/build-all.sh

# Build all services without cache (clean build)
./scripts/build-all.sh --no-cache
```

**What it builds:**
- Infrastructure: postgres, redis
- Services: user-service, instance-service, instance-worker, billing-service, notification-service, frontend-service

### 2. build-service.sh

Builds and pushes a single service.

**Usage:**
```bash
# Build a specific service
./scripts/build-service.sh <service-name>

# Build without cache
./scripts/build-service.sh <service-name> --no-cache

# Show available services
./scripts/build-service.sh
```

**Available services:**
- `postgres` - PostgreSQL with initialization scripts
- `redis` - Redis with custom configuration
- `user-service` - User authentication and management
- `instance-service` - Odoo instance lifecycle management
- `instance-worker` - Celery worker for instance operations
- `billing-service` - KillBill integration and billing
- `notification-service` - Email and notifications
- `frontend-service` - React frontend application

**Examples:**
```bash
# Build just the billing service
./scripts/build-service.sh billing-service

# Rebuild postgres from scratch
./scripts/build-service.sh postgres --no-cache

# Build and immediately deploy
./scripts/build-service.sh user-service && \
  docker service update --image registry.62.171.153.219.nip.io/compose-user-service:latest saasodoo_user-service
```

## Workflow

### Development Workflow

1. Make changes to service code
2. Build the service:
   ```bash
   ./scripts/build-service.sh <service-name>
   ```
3. Deploy to swarm:
   ```bash
   # Quick update (single service)
   docker service update --image $(grep DOCKER_REGISTRY infrastructure/compose/.env.swarm | cut -d= -f2 | envsubst)/compose-<service-name>:latest saasodoo_<service-name>

   # Or full stack redeploy
   set -a && source infrastructure/compose/.env.swarm && set +a && \
   docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
   ```

### Production Workflow

1. Build all services:
   ```bash
   ./scripts/build-all.sh
   ```
2. Test in staging environment
3. Deploy to production swarm:
   ```bash
   set -a && source infrastructure/compose/.env.swarm && set +a && \
   docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
   ```

## Troubleshooting

### Registry Connection Issues

If you get registry connection errors:

```bash
# Check if registry is running
docker service ls | grep registry

# Check registry logs
docker service logs saasodoo_registry

# Test registry connectivity
curl -v http://registry.62.171.153.219.nip.io/v2/
```

### Build Failures

If builds fail:

```bash
# Clean build without cache
./scripts/build-service.sh <service-name> --no-cache

# Check disk space
df -h

# Clean up old images
docker image prune -a
```

### Permission Issues

If you get permission errors:

```bash
# Ensure scripts are executable
chmod +x scripts/*.sh

# Check Docker permissions
docker info
```

## Image Naming Convention

All images follow this pattern:
```
{DOCKER_REGISTRY}/compose-{service-name}:latest
```

Examples:
- `registry.62.171.153.219.nip.io/compose-postgres:latest`
- `registry.62.171.153.219.nip.io/compose-user-service:latest`
- `registry.62.171.153.219.nip.io/compose-billing-service:latest`

## Notes

- Both `instance-service` and `instance-worker` use the same Dockerfile (`services/instance-service/Dockerfile`) but are tagged as separate images
- Infrastructure services (postgres, redis) use `.` as build context to access `shared/configs/`
- Application services use their service directory as build context
- All scripts automatically push to the registry after successful builds
- Scripts exit on first error to prevent partial builds
