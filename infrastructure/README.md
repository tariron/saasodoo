# Infrastructure Directory

Organized infrastructure code and deployment configurations for the SaaSOdoo platform.

## Structure

### images/
Custom Docker images with embedded configurations.

- **postgres/**: PostgreSQL with initialization scripts
  - `Dockerfile`: Custom postgres image
  - `init-scripts/`: Database schemas (auto-run on first start)

- **redis/**: Redis with custom configuration
  - `Dockerfile`: Custom redis image
  - `redis.conf`: Redis configuration file

### networking/
Network infrastructure components.

- **traefik/**: Reverse proxy and SSL termination
  - `static/`: Static configuration
  - `dynamic/`: Dynamic routing rules

### orchestration/
Container orchestration configurations.

- **compose/**: Docker Compose for local development
  - `docker-compose.dev.yml`: Dev environment

- **swarm/**: Docker Swarm for production
  - `docker-compose.ceph.yml`: Production stack with CephFS
  - `.env.swarm`: Environment variables
  - `rebuild-service.sh`: Service rebuild utility

### security/
Security configurations and hardening rules.

### storage/
Storage infrastructure.

- **ceph/**: Distributed filesystem configurations

## Quick Commands

### Deploy to Production (Swarm)
```bash
cd /root/saasodoo
set -a && source infrastructure/orchestration/swarm/.env.swarm && set +a
docker stack deploy -c infrastructure/orchestration/swarm/docker-compose.ceph.yml saasodoo
```

### Rebuild Custom Images
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

### View Services
```bash
docker service ls
docker stack services saasodoo
```

### View Service Logs
```bash
docker service logs saasodoo_<service-name> --tail 100 --follow
```

## Architecture Benefits

**Separation of Concerns**:
- Images: Custom Docker images and build configurations
- Networking: Traefik reverse proxy and routing
- Orchestration: Deployment configurations (dev/prod)
- Security: Hardening scripts and configs
- Storage: Distributed storage setup

**Clear Intent**:
- Development configs in `orchestration/compose/`
- Production configs in `orchestration/swarm/`
- Image definitions separate from deployment configs

**Easy Navigation**:
- All Postgres init scripts in one place
- All Traefik configs organized by static/dynamic
- Clear distinction between deployment types

## Migration from Old Structure

The infrastructure was reorganized on 2025-12-19 to improve clarity and separation of concerns.

**Old Paths → New Paths**:
- `infrastructure/postgres/` → `infrastructure/images/postgres/`
- `infrastructure/redis/` → `infrastructure/images/redis/`
- `infrastructure/compose/` → `infrastructure/orchestration/swarm/`
- `infrastructure/traefik/` → `infrastructure/networking/traefik/`
- `infrastructure/Ceph/` → `infrastructure/storage/ceph/`
- `infrastructure/security-hardening/` → `infrastructure/security/`
- `shared/configs/postgres/` → `infrastructure/images/postgres/init-scripts/`
- `shared/configs/redis.conf` → `infrastructure/images/redis/redis.conf`

All build scripts, documentation, and deployment configs have been updated to reflect the new structure.
