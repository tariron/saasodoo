# Infrastructure Directory Restructure Plan

**Created**: 2025-12-18
**Status**: Proposed
**Goal**: Reorganize infrastructure/ directory for better clarity and separation of concerns

## Current Infrastructure Structure

```
infrastructure/
├── Ceph/                      # Ceph storage configs
├── compose/                   # Docker Compose files (deployment configs)
│   ├── docker-compose.ceph.yml
│   ├── docker-compose.dev.yml (if exists)
│   └── .env.swarm
├── postgres/                  # Custom postgres Dockerfile
│   └── Dockerfile
├── redis/                     # Custom redis Dockerfile
│   └── Dockerfile
├── security-hardening/        # Security configs
├── swarm/                     # Docker Swarm configs (if exists)
└── traefik/                   # Traefik reverse proxy configs
    └── dynamic/

shared/configs/
├── postgres/                  # DB init scripts (*.sql)
└── redis.conf                 # Redis configuration
```

## Issues

1. **Mixed concerns**: Deployment configs (compose/) mixed with infrastructure code
2. **Scattered configs**: Postgres init scripts in shared/, Dockerfile in infrastructure/
3. **Flat structure**: No logical grouping (networking, storage, orchestration, images)
4. **Inconsistent naming**: "Ceph" vs lowercase elsewhere

## Proposed New Structure

```
infrastructure/
├── images/                           # NEW: Custom Docker images
│   ├── postgres/
│   │   ├── Dockerfile               # Updated paths
│   │   └── init-scripts/            # Moved from shared/configs/postgres/
│   │       ├── 01-create-databases.sql
│   │       ├── 02-auth-schema.sql
│   │       ├── 03-instance-schema.sql
│   │       ├── 04-billing-schema.sql
│   │       ├── 05-communication-schema.sql
│   │       └── 06-database-service-schema.sql
│   └── redis/
│       ├── Dockerfile               # Updated paths
│       └── redis.conf               # Moved from shared/configs/
├── networking/                       # NEW: Network infrastructure
│   └── traefik/
│       ├── static/                   # Static config
│       └── dynamic/                  # Dynamic routing rules
├── orchestration/                    # NEW: Container orchestration
│   ├── compose/                      # Docker Compose for dev
│   │   └── docker-compose.dev.yml (if exists)
│   └── swarm/                        # Docker Swarm for production
│       ├── docker-compose.ceph.yml  # Updated paths
│       └── .env.swarm
├── security/                         # RENAMED: security-hardening → security
│   └── (existing security configs)
└── storage/                          # NEW: Storage infrastructure
    └── ceph/                         # Lowercase for consistency
        └── (existing Ceph configs)
```

---

## Step-by-Step Migration Plan

### Step 1: Create New Directory Structure
**Risk**: None
**Time**: 1 minute

```bash
cd /root/saasodoo/infrastructure

mkdir -p images/postgres/init-scripts
mkdir -p images/redis
mkdir -p networking/traefik/static
mkdir -p networking/traefik/dynamic
mkdir -p orchestration/compose
mkdir -p orchestration/swarm
mkdir -p storage/ceph
```

**Verification**: `tree infrastructure/ -L 3 -d` or `find infrastructure/ -type d | sort`

---

### Step 2: Move and Update Postgres Files
**Risk**: Low (not actively building)
**Time**: 3 minutes

```bash
cd /root/saasodoo

# Move postgres init scripts
cp -r shared/configs/postgres/* infrastructure/images/postgres/init-scripts/

# Move postgres Dockerfile
cp infrastructure/postgres/Dockerfile infrastructure/images/postgres/
```

Now **update** `infrastructure/images/postgres/Dockerfile`:

**OLD**:
```dockerfile
FROM postgres:18-alpine

# Copy initialization scripts
COPY shared/configs/postgres/ /docker-entrypoint-initdb.d/
```

**NEW**:
```dockerfile
FROM postgres:18-alpine

# Copy initialization scripts
COPY infrastructure/images/postgres/init-scripts/ /docker-entrypoint-initdb.d/
```

**Verification**:
```bash
cat infrastructure/images/postgres/Dockerfile
ls infrastructure/images/postgres/init-scripts/*.sql
```

---

### Step 3: Move and Update Redis Files
**Risk**: Low (not actively building)
**Time**: 2 minutes

```bash
cd /root/saasodoo

# Move redis config
cp shared/configs/redis.conf infrastructure/images/redis/

# Move redis Dockerfile
cp infrastructure/redis/Dockerfile infrastructure/images/redis/
```

Now **update** `infrastructure/images/redis/Dockerfile`:

**OLD**:
```dockerfile
FROM redis:8.4-rc1-alpine

# Copy redis configuration
COPY shared/configs/redis.conf /etc/redis/redis.conf
```

**NEW**:
```dockerfile
FROM redis:8.4-rc1-alpine

# Copy redis configuration
COPY infrastructure/images/redis/redis.conf /etc/redis/redis.conf
```

**Verification**:
```bash
cat infrastructure/images/redis/Dockerfile
ls infrastructure/images/redis/redis.conf
```

---

### Step 4: Move Traefik Configurations
**Risk**: Low
**Time**: 2 minutes

```bash
cd /root/saasodoo/infrastructure

# Move Traefik dynamic configs
cp -r traefik/dynamic/* networking/traefik/dynamic/ 2>/dev/null || true

# Move any other Traefik files to static
cp traefik/*.yml networking/traefik/static/ 2>/dev/null || true
cp traefik/*.yaml networking/traefik/static/ 2>/dev/null || true
```

**Verification**:
```bash
ls networking/traefik/dynamic/
ls networking/traefik/static/
```

---

### Step 5: Move Orchestration Configs
**Risk**: Medium (active deployment files)
**Time**: 2 minutes

```bash
cd /root/saasodoo/infrastructure

# Move Swarm production configs
cp compose/docker-compose.ceph.yml orchestration/swarm/
cp compose/.env.swarm orchestration/swarm/

# Move Compose dev configs (if exists)
if [ -f compose/docker-compose.dev.yml ]; then
  cp compose/docker-compose.dev.yml orchestration/compose/
fi

# Move any other swarm configs
if [ -d swarm ]; then
  cp -r swarm/* orchestration/swarm/ 2>/dev/null || true
fi
```

**Verification**:
```bash
ls orchestration/swarm/docker-compose.ceph.yml
ls orchestration/swarm/.env.swarm
```

---

### Step 6: Move Storage Configs
**Risk**: Low
**Time**: 1 minute

```bash
cd /root/saasodoo/infrastructure

# Move Ceph configs
if [ -d Ceph ]; then
  cp -r Ceph/* storage/ceph/ 2>/dev/null || true
elif [ -d ceph ]; then
  cp -r ceph/* storage/ceph/ 2>/dev/null || true
fi
```

**Verification**: `ls storage/ceph/`

---

### Step 7: Rename Security Directory
**Risk**: None
**Time**: 1 minute

```bash
cd /root/saasodoo/infrastructure

if [ -d security-hardening ] && [ ! -d security ]; then
  cp -r security-hardening security
fi
```

**Verification**: `ls security/`

---

### Step 8: Update Docker Compose File Paths (CRITICAL)
**Risk**: High (breaks deployment if incorrect)
**Time**: 10 minutes

Edit `infrastructure/orchestration/swarm/docker-compose.ceph.yml`:

**Change 1 - Postgres build context and Dockerfile**:
```yaml
# Find the postgres service section
postgres:
  # OLD
  build:
    context: ../../
    dockerfile: infrastructure/postgres/Dockerfile

  # NEW
  build:
    context: ../../../
    dockerfile: infrastructure/images/postgres/Dockerfile
```

**Change 2 - Redis build context and Dockerfile**:
```yaml
# Find the redis service section
redis:
  # OLD
  build:
    context: ../../
    dockerfile: infrastructure/redis/Dockerfile

  # NEW
  build:
    context: ../../../
    dockerfile: infrastructure/images/redis/Dockerfile
```

**Change 3 - Remove any volume mounts for init scripts** (since they're now in the image):
```yaml
# postgres service - REMOVE this if it exists:
volumes:
  - ../../shared/configs/postgres:/docker-entrypoint-initdb.d:ro
```

**Verification**:
```bash
grep -n "infrastructure/postgres" infrastructure/orchestration/swarm/docker-compose.ceph.yml
grep -n "infrastructure/redis" infrastructure/orchestration/swarm/docker-compose.ceph.yml
grep -n "shared/configs" infrastructure/orchestration/swarm/docker-compose.ceph.yml
```

---

### Step 9: Update Build Scripts
**Risk**: Low
**Time**: 5 minutes

Update `scripts/build-all.sh` and `scripts/build-service.sh`:

**Find and replace**:
- `infrastructure/compose/` → `infrastructure/orchestration/swarm/`
- `infrastructure/postgres/Dockerfile` → `infrastructure/images/postgres/Dockerfile`
- `infrastructure/redis/Dockerfile` → `infrastructure/images/redis/Dockerfile`

**Verification**:
```bash
grep "infrastructure/" scripts/*.sh
```

---

### Step 10: Build New Images (Test)
**Risk**: Medium (tests if Dockerfiles work)
**Time**: 5 minutes

```bash
cd /root/saasodoo

# Test postgres image build
docker build -t test-postgres -f infrastructure/images/postgres/Dockerfile .

# Test redis image build
docker build -t test-redis -f infrastructure/images/redis/Dockerfile .

# Clean up test images
docker rmi test-postgres test-redis
```

**Verification**: Both builds should complete without errors

**If builds fail**: Check COPY paths in Dockerfiles match the actual file locations

---

### Step 11: Update CLAUDE.md Documentation
**Risk**: None
**Time**: 5 minutes

Update `/root/saasodoo/CLAUDE.md`:

**Find and replace all occurrences**:
- `infrastructure/compose/docker-compose.dev.yml` → `infrastructure/orchestration/compose/docker-compose.dev.yml`
- `infrastructure/compose/docker-compose.ceph.yml` → `infrastructure/orchestration/swarm/docker-compose.ceph.yml`
- `infrastructure/compose/.env.swarm` → `infrastructure/orchestration/swarm/.env.swarm`

**Add documentation for new structure** in the Architecture section

**Verification**: Search for "infrastructure/compose" to ensure all references updated

---

### Step 12: Update devops-engineer Skill
**Risk**: None
**Time**: 5 minutes

Update `.claude/skills/devops-engineer/SKILL.md`:

**Find and replace**:
- All `infrastructure/compose/` → `infrastructure/orchestration/swarm/`
- Update "Rebuild and Redeploy Service" section with new Dockerfile paths
- Update directory structure documentation

**Verification**: Search for old paths to ensure all updated

---

### Step 13: Test Deployment (CRITICAL)
**Risk**: High
**Time**: 15 minutes

**Create backup first**:
```bash
docker stack rm saasodoo
sleep 10
```

**Rebuild custom images** with new structure:
```bash
cd /root/saasodoo

# Build postgres with new structure
docker build -t registry.62.171.153.219.nip.io/compose-postgres:latest \
  -f infrastructure/images/postgres/Dockerfile .

# Build redis with new structure
docker build -t registry.62.171.153.219.nip.io/compose-redis:latest \
  -f infrastructure/images/redis/Dockerfile .

# Push to registry
docker push registry.62.171.153.219.nip.io/compose-postgres:latest
docker push registry.62.171.153.219.nip.io/compose-redis:latest
```

**Deploy stack**:
```bash
set -a && source infrastructure/orchestration/swarm/.env.swarm && set +a
docker stack deploy -c infrastructure/orchestration/swarm/docker-compose.ceph.yml saasodoo
```

**Verification**:
```bash
# Wait for services to start
sleep 30

# Check all services
docker service ls

# Check health endpoints
curl http://api.62.171.153.219.nip.io/instance/health
curl http://api.62.171.153.219.nip.io/billing/health
curl http://api.62.171.153.219.nip.io/user/health

# Check postgres logs
docker service logs saasodoo_postgres --tail 20

# Check redis logs
docker service logs saasodoo_redis --tail 20
```

**Success criteria**:
- All services show 1/1 replicas
- Health endpoints respond
- No errors in postgres/redis logs about missing files

---

### Step 14: Remove Old Directories (After Successful Test)
**Risk**: None (only after Step 13 succeeds)
**Time**: 2 minutes

**ONLY run this after Step 13 is completely successful**:

```bash
cd /root/saasodoo

# Remove old infrastructure directories
rm -rf infrastructure/postgres
rm -rf infrastructure/redis
rm -rf infrastructure/compose
rm -rf infrastructure/traefik
rm -rf infrastructure/swarm 2>/dev/null || true
rm -rf infrastructure/Ceph 2>/dev/null || true
rm -rf infrastructure/ceph 2>/dev/null || true
rm -rf infrastructure/security-hardening 2>/dev/null || true

# Remove postgres scripts from shared (now in images)
rm -rf shared/configs/postgres

# Remove redis.conf from shared (now in images)
rm shared/configs/redis.conf
```

**Verification**:
```bash
ls infrastructure/
# Should only show: images/ networking/ orchestration/ security/ storage/

ls shared/configs/
# Should NOT show postgres/ or redis.conf
```

---

### Step 15: Create Infrastructure README
**Risk**: None
**Time**: 3 minutes

Create `infrastructure/README.md`:

```markdown
# Infrastructure Directory

Organized infrastructure code and deployment configurations.

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
```

---

## Rollback Strategy

### If Steps 1-9 Fail (Before Testing)
Simply use the old paths - nothing has been changed in active deployment:
```bash
# Deploy using old structure
set -a && source infrastructure/compose/.env.swarm && set +a
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

### If Step 10 (Image Build) Fails
Fix Dockerfile COPY paths - the paths in Dockerfiles must match actual file locations.

Common issues:
- COPY path doesn't match where files actually are
- Build context is wrong (should be project root: `/root/saasodoo`)

### If Step 13 (Deployment) Fails

1. **Redeploy with old structure**:
   ```bash
   set -a && source infrastructure/compose/.env.swarm && set +a
   docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
   ```

2. **Restore old images** (if new ones are broken):
   ```bash
   # Pull old working images from registry
   docker pull registry.62.171.153.219.nip.io/compose-postgres:latest
   docker pull registry.62.171.153.219.nip.io/compose-redis:latest
   ```

3. **Check logs** to identify issue:
   ```bash
   docker service logs saasodoo_postgres
   docker service logs saasodoo_redis
   ```

---

## Success Criteria

- ✅ New directory structure created
- ✅ Dockerfiles updated with correct COPY paths
- ✅ Images build successfully with new structure
- ✅ Stack deploys with new compose file paths
- ✅ All services healthy (1/1 replicas)
- ✅ Health endpoints respond
- ✅ No errors in service logs
- ✅ Old directories removed
- ✅ Documentation updated

---

## Estimated Time

- **Steps 1-9** (Setup & Updates): 30 minutes
- **Step 10** (Image Testing): 5 minutes
- **Steps 11-12** (Documentation): 10 minutes
- **Step 13** (Deployment Test): 15 minutes
- **Steps 14-15** (Cleanup): 5 minutes
- **Buffer**: 10 minutes

**Total**: 60-75 minutes

**Recommendation**: Execute during maintenance window. Keep old structure until Step 13 succeeds.
