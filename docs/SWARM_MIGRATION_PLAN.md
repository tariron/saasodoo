# Docker Swarm Migration Plan for SaasOdoo

## Executive Summary

This document outlines the migration strategy from Docker Compose (development) to Docker Swarm (production) for the SaasOdoo multi-tenant Odoo platform. The migration addresses key challenges around networking, storage, backups, and service orchestration while maintaining the current architecture of one shared PostgreSQL server with separate databases per customer.

---

## Current Architecture

### Service Structure
- **Core Services**: user-service, tenant-service, instance-service (FastAPI)
- **Infrastructure**: PostgreSQL (shared), Redis, Traefik
- **Customer Instances**: One Odoo container per customer
- **Database Model**: One PostgreSQL server, one database per customer (NOT one PostgreSQL container per customer)

### Container Deployment
- Customer containers: `odoo_{database_name}_{instance_id_hex}`
- Created dynamically via Docker SDK in instance-service
- Connected to shared network for database access
- Each has dedicated volume: `odoo_data_{database_name}_{instance_id_hex}`

---

## Key Challenges & Solutions

### 1. **Networking Architecture**

#### Challenge
- Compose uses bridge networks (single-host)
- Swarm needs overlay networks (multi-host)
- Customer containers must reach PostgreSQL service across nodes

#### Solution
**Use attachable overlay network**

```yaml
networks:
  saasodoo-overlay:
    driver: overlay
    attachable: true  # CRITICAL: Allows standalone containers to join
```

**Why this works:**
- Core services (user, tenant, instance) run as Swarm services on overlay network
- Customer Odoo containers (standalone) join same overlay network via `attachable: true`
- DNS resolution works: `postgres` hostname resolves to PostgreSQL service from any node
- No changes needed to database connection strings

**Code Changes Required:**
```python
# provisioning.py:281 - Update container creation
container = client.containers.run(
    f'bitnami/odoo:{odoo_version}',
    name=container_name,
    network='saasodoo-overlay',  # ← Add this
    # ... rest of config
)

# Remove the separate network.connect() call (lines 304-310)
```

---

### 2. **Customer Container Strategy**

#### Challenge
"In Swarm, can I use containers or services for customers?"

#### Solution
**Use standalone containers, NOT Swarm services**

**Reasoning:**
- Swarm services add overhead: health checks, replicas, rolling updates
- Customers don't need service-level orchestration
- Managing 100+ services (one per customer) is inefficient
- Standalone containers are lighter and more direct to control

**Implementation:**
- Customer containers remain standalone Docker containers
- Created via `docker.containers.run()` in instance-service
- Join overlay network via `network='saasodoo-overlay'` parameter
- instance-service runs on manager node with Docker socket access

---

### 3. **Backup Storage Architecture**

#### Challenge
Current backup implementation uses:
- Local path: `/var/lib/odoo/backups`
- Docker volume: `odoo-backups`
- Problem: Volumes are node-local in Swarm

#### Issue Details
```python
# maintenance.py:427-436 - Current backup approach
client.containers.run(
    image="alpine:latest",
    command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
    volumes={
        volume_name: {'bind': '/data', 'mode': 'ro'},  # Customer volume on node-1
        'odoo-backups': {'bind': '/backup', 'mode': 'rw'}  # Backup volume on node-2?
    }
)
# ⚠️ This fails if volumes are on different nodes
```

#### Solution: NFS Shared Storage

**Architecture:**
```
NFS Server (one swarm node or dedicated server)
    └─> /exports/saasodoo-backups
         ↓
All Swarm Nodes mount via NFS
    └─> /mnt/nfs/saasodoo-backups
         ↓
instance-service & celery-workers mount
    └─> /var/lib/odoo/backups → /mnt/nfs/saasodoo-backups
```

**Benefits:**
- ✅ Backups accessible from any node
- ✅ Survives node failures
- ✅ Easy external backup integration (rsync, S3 sync)
- ✅ No code changes to backup logic

**Setup Steps:**

1. **NFS Server Setup** (on one node):
```bash
sudo apt install nfs-kernel-server -y
sudo mkdir -p /exports/saasodoo-backups
sudo chown nobody:nogroup /exports/saasodoo-backups
sudo chmod 777 /exports/saasodoo-backups

# /etc/exports
/exports/saasodoo-backups 10.0.0.0/24(rw,sync,no_subtree_check,no_root_squash)

sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
```

2. **NFS Client Setup** (on all nodes):
```bash
sudo apt install nfs-common -y
sudo mkdir -p /mnt/nfs/saasodoo-backups

# Test mount
sudo mount -t nfs NFS_SERVER_IP:/exports/saasodoo-backups /mnt/nfs/saasodoo-backups

# Permanent mount - /etc/fstab
NFS_SERVER_IP:/exports/saasodoo-backups /mnt/nfs/saasodoo-backups nfs defaults,_netdev 0 0

sudo mount -a
```

3. **Stack Configuration**:
```yaml
services:
  instance-service:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - type: bind
        source: /mnt/nfs/saasodoo-backups
        target: /var/lib/odoo/backups

  celery-worker:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - type: bind
        source: /mnt/nfs/saasodoo-backups
        target: /var/lib/odoo/backups
```

4. **Code Update** (maintenance.py):
```python
# Line 427 - Change from Docker volume to direct path
client.containers.run(
    image="alpine:latest",
    command=f"tar -czf /backup/{backup_name}_data.tar.gz -C /data .",
    volumes={
        volume_name: {'bind': '/data', 'mode': 'ro'},
        BACKUP_ACTIVE_PATH: {'bind': '/backup', 'mode': 'rw'}  # ← Use NFS path
    }
)
```

---

### 4. **Customer Volume Storage**

#### Challenge
Customer Odoo data volumes are node-local by default

#### Options

**Option A: Node Pinning** (Simple, short-term)
```python
# Pin customer containers to specific nodes
container = client.containers.run(
    ...,
    environment={
        "constraint:node.hostname": "swarm-node-2"
    }
)
```
- **Pros**: Simple, no external dependencies
- **Cons**: No redundancy, node failure = data loss (mitigated by backups)

**Option B: Shared Storage** (Production-grade)
- Use NFS/GlusterFS/Ceph for customer volumes
- Containers can run on any node
- **Requires**: Shared filesystem infrastructure

**Recommendation**: Start with Option A (node pinning), migrate to Option B as scale increases.

---

### 5. **Traefik Configuration**

#### Challenge
Traefik must detect customer containers across Swarm nodes

#### Solution
**Enable Swarm Mode in Traefik**

```yaml
services:
  traefik:
    image: traefik:v2.10
    command:
      - --providers.docker.swarmMode=true  # ← Enable Swarm mode
      - --providers.docker.exposedByDefault=false
      - --providers.docker.network=saasodoo-overlay
      - --entrypoints.web.address=:80
    deploy:
      placement:
        constraints: [node.role == manager]  # Needs docker socket
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - saasodoo-overlay
```

**Customer Container Labels** (provisioning.py:293-301):
```python
labels={
    'traefik.enable': 'true',
    f'traefik.http.routers.{container_name}.rule': f'Host(`{subdomain}.yourdomain.com`)',
    f'traefik.http.routers.{container_name}.service': container_name,
    f'traefik.http.services.{container_name}.loadbalancer.server.port': '8069',
    'traefik.docker.network': 'saasodoo-overlay'  # ← Add this
}
```

---

### 6. **Image Registry Requirement**

#### Challenge
Swarm doesn't support `build:` directive - requires pre-built images

#### Solution
**Use Docker Registry**

```bash
# Build images
docker build -t registry.yourdomain.com/saasodoo/user-service:latest services/user-service/
docker build -t registry.yourdomain.com/saasodoo/tenant-service:latest services/tenant-service/
docker build -t registry.yourdomain.com/saasodoo/instance-service:latest services/instance-service/

# Push to registry
docker push registry.yourdomain.com/saasodoo/user-service:latest
docker push registry.yourdomain.com/saasodoo/tenant-service:latest
docker push registry.yourdomain.com/saasodoo/instance-service:latest

# Stack uses registry images
services:
  user-service:
    image: registry.yourdomain.com/saasodoo/user-service:latest
```

**Registry Options:**
- Docker Hub (public/private repos)
- Self-hosted registry (simple: `docker run -d -p 5000:5000 registry:2`)
- Cloud registry (AWS ECR, Google GCR, Azure ACR)

---

### 7. **Docker Event Monitoring Auto-Start**

#### Current Issue
Monitoring requires manual API call to start

#### Solution
**Use Celery Worker Lifecycle Hooks**

**Problem Analysis:**
- Currently: instance-service (FastAPI) calls `monitor_docker_events_task.delay()` on startup
- Issue: Task queues in Celery but no guarantee worker picks it up immediately
- Monitoring thread should live in **worker process**, not FastAPI

**Fix:**

In `app/celery_config.py`:
```python
from celery.signals import worker_ready, worker_shutdown

@worker_ready.connect
def start_monitoring_on_worker_startup(sender, **kwargs):
    """Auto-start monitoring when worker boots"""
    logger.info("Celery worker ready, starting Docker event monitoring")
    from app.tasks.monitoring import _docker_monitor
    _docker_monitor.start_monitoring()

@worker_shutdown.connect
def stop_monitoring_on_worker_shutdown(sender, **kwargs):
    """Stop monitoring on worker shutdown"""
    from app.tasks.monitoring import _docker_monitor
    _docker_monitor.stop_monitoring()
```

In `app/main.py`:
```python
# REMOVE lines 52-65 (monitoring startup code)
# Monitoring now auto-starts in worker, not FastAPI
```

**Result:**
- ✅ Monitoring starts automatically when instance-worker boots
- ✅ No API calls needed
- ✅ Runs in correct process (worker, not FastAPI)
- ✅ Proper lifecycle management

---

## Production Stack Configuration

### Complete docker-compose.prod.yml

```yaml
version: '3.8'

networks:
  saasodoo-overlay:
    driver: overlay
    attachable: true

volumes:
  postgres_data:
  redis_data:

services:
  postgres:
    image: postgres:16
    deploy:
      replicas: 1
      placement:
        constraints: [node.labels.postgres == true]
      restart_policy:
        condition: on-failure
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - saasodoo-overlay
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  redis:
    image: redis:7-alpine
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
    volumes:
      - redis_data:/data
    networks:
      - saasodoo-overlay

  traefik:
    image: traefik:v2.10
    command:
      - --providers.docker.swarmMode=true
      - --providers.docker.exposedByDefault=false
      - --providers.docker.network=saasodoo-overlay
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --api.dashboard=true
    deploy:
      placement:
        constraints: [node.role == manager]
      labels:
        - "traefik.enable=true"
        - "traefik.http.routers.traefik.rule=Host(`traefik.yourdomain.com`)"
        - "traefik.http.routers.traefik.service=api@internal"
        - "traefik.http.services.traefik.loadbalancer.server.port=8080"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - saasodoo-overlay

  user-service:
    image: registry.yourdomain.com/saasodoo/user-service:${VERSION:-latest}
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure
      update_config:
        parallelism: 1
        delay: 10s
    environment:
      DB_SERVICE_USER: ${USER_SERVICE_DB_USER}
      DB_SERVICE_PASSWORD: ${USER_SERVICE_DB_PASSWORD}
      POSTGRES_HOST: postgres
      POSTGRES_DB: auth
    networks:
      - saasodoo-overlay

  tenant-service:
    image: registry.yourdomain.com/saasodoo/tenant-service:${VERSION:-latest}
    deploy:
      replicas: 2
      restart_policy:
        condition: on-failure
      update_config:
        parallelism: 1
        delay: 10s
    environment:
      DB_SERVICE_USER: ${TENANT_SERVICE_DB_USER}
      DB_SERVICE_PASSWORD: ${TENANT_SERVICE_DB_PASSWORD}
      POSTGRES_HOST: postgres
      POSTGRES_DB: tenant
    networks:
      - saasodoo-overlay

  instance-service:
    image: registry.yourdomain.com/saasodoo/instance-service:${VERSION:-latest}
    deploy:
      replicas: 1
      placement:
        constraints: [node.role == manager]
      restart_policy:
        condition: on-failure
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - type: bind
        source: /mnt/nfs/saasodoo-backups
        target: /var/lib/odoo/backups
    environment:
      DB_SERVICE_USER: ${INSTANCE_SERVICE_DB_USER}
      DB_SERVICE_PASSWORD: ${INSTANCE_SERVICE_DB_PASSWORD}
      POSTGRES_HOST: postgres
      POSTGRES_DB: instance
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    networks:
      - saasodoo-overlay

  instance-worker:
    image: registry.yourdomain.com/saasodoo/instance-service:${VERSION:-latest}
    command: celery -A app.celery_config worker --loglevel=info
    deploy:
      replicas: 2
      placement:
        constraints: [node.role == manager]
      restart_policy:
        condition: on-failure
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - type: bind
        source: /mnt/nfs/saasodoo-backups
        target: /var/lib/odoo/backups
    environment:
      DB_SERVICE_USER: ${INSTANCE_SERVICE_DB_USER}
      DB_SERVICE_PASSWORD: ${INSTANCE_SERVICE_DB_PASSWORD}
      POSTGRES_HOST: postgres
      POSTGRES_DB: instance
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      CELERY_BROKER_URL: redis://redis:6379/0
      CELERY_RESULT_BACKEND: redis://redis:6379/0
    networks:
      - saasodoo-overlay
```

---

## Phased Implementation Plan

### Phase 1: Preparation (Week 1)

**Goals**: Set up infrastructure and validate approach

#### Tasks

1. **NFS Server Setup**
   - [ ] Choose NFS server node or dedicated server
   - [ ] Install and configure NFS server
   - [ ] Create backup directory: `/exports/saasodoo-backups`
   - [ ] Configure exports with proper permissions
   - [ ] Test basic NFS functionality

2. **NFS Client Setup**
   - [ ] Install NFS client on all swarm nodes
   - [ ] Create mount points: `/mnt/nfs/saasodoo-backups`
   - [ ] Test manual mounting on all nodes
   - [ ] Configure `/etc/fstab` for permanent mounts
   - [ ] Verify write access from all nodes

3. **Registry Setup**
   - [ ] Choose registry solution (Docker Hub, self-hosted, cloud)
   - [ ] Set up registry if self-hosting
   - [ ] Configure authentication
   - [ ] Test push/pull from all swarm nodes

4. **Swarm Initialization**
   - [ ] Initialize Swarm on manager node: `docker swarm init`
   - [ ] Join worker nodes to swarm
   - [ ] Label nodes appropriately:
     ```bash
     docker node update --label-add postgres=true node-1
     docker node update --label-add odoo-volumes=true node-2
     ```
   - [ ] Verify swarm status: `docker node ls`

**Deliverables:**
- Working NFS shared storage
- Docker Registry operational
- Swarm cluster initialized
- All nodes labeled

---

### Phase 2: Code Updates (Week 2)

**Goals**: Update codebase for Swarm compatibility

#### Tasks

1. **Networking Changes**
   - [ ] Update `provisioning.py` line 281: Add `network='saasodoo-overlay'`
   - [ ] Remove manual network connection (lines 304-310)
   - [ ] Update container labels to include `traefik.docker.network`

2. **Backup Code Updates**
   - [ ] Update `maintenance.py` line 432: Change from Docker volume to NFS path
   - [ ] Update restore code (line 551): Same NFS path change
   - [ ] Test backup/restore locally

3. **Monitoring Auto-Start**
   - [ ] Add worker lifecycle hooks in `celery_config.py`
   - [ ] Remove monitoring startup from `main.py` (lines 52-65)
   - [ ] Test monitoring auto-start with local Celery worker

4. **Stack File Creation**
   - [ ] Create `docker-compose.prod.yml` with Swarm configuration
   - [ ] Define overlay network with `attachable: true`
   - [ ] Configure all services with deployment constraints
   - [ ] Set up Traefik with `swarmMode=true`

5. **Image Build Pipeline**
   - [ ] Create build script for all services
   - [ ] Test image builds
   - [ ] Push images to registry
   - [ ] Verify images are pullable from all nodes

**Deliverables:**
- Updated codebase committed to git
- Production stack file
- Images built and pushed to registry
- Local testing completed

---

### Phase 3: Staging Deployment (Week 3)

**Goals**: Deploy to staging swarm environment and validate

#### Tasks

1. **Initial Deployment**
   - [ ] Deploy stack: `docker stack deploy -c docker-compose.prod.yml saasodoo`
   - [ ] Verify all services start: `docker service ls`
   - [ ] Check service logs: `docker service logs saasodoo_instance-service`
   - [ ] Verify overlay network: `docker network inspect saasodoo_saasodoo-overlay`

2. **Service Validation**
   - [ ] Test user-service health endpoints
   - [ ] Test tenant-service health endpoints
   - [ ] Test instance-service health endpoints
   - [ ] Verify database connectivity from all services
   - [ ] Verify Redis connectivity

3. **Customer Instance Testing**
   - [ ] Provision test customer instance via API
   - [ ] Verify container created and joined overlay network
   - [ ] Test database connectivity from customer container
   - [ ] Verify Traefik routing to customer instance
   - [ ] Test instance start/stop operations

4. **Backup Testing**
   - [ ] Create backup of test instance
   - [ ] Verify backup files on NFS: `ls /mnt/nfs/saasodoo-backups/active/`
   - [ ] Verify backup accessible from all nodes
   - [ ] Test restore operation
   - [ ] Verify restored instance works

5. **Monitoring Validation**
   - [ ] Verify monitoring auto-starts with instance-worker
   - [ ] Check monitoring status: `GET /api/v1/monitoring/status`
   - [ ] Start/stop test instance, verify events detected
   - [ ] Check database status updates
   - [ ] Test manual reconciliation

6. **Multi-Node Testing**
   - [ ] Deploy customer instances on different nodes
   - [ ] Verify cross-node communication
   - [ ] Test Traefik routing across nodes
   - [ ] Simulate node failure, verify service migration

**Deliverables:**
- Fully functional staging environment
- All services passing health checks
- Customer instances working across nodes
- Backup/restore validated
- Monitoring operational

---

### Phase 4: Production Migration (Week 4)

**Goals**: Migrate to production with zero downtime

#### Strategy: Blue-Green Deployment

1. **Pre-Migration**
   - [ ] Set up production swarm cluster (separate from staging)
   - [ ] Configure NFS on production nodes
   - [ ] Set up production registry
   - [ ] Build and push production images with version tags

2. **Database Migration**
   - [ ] Create full backup of production database
   - [ ] Export current customer instance metadata
   - [ ] Prepare migration scripts for data transfer

3. **Parallel Deployment**
   - [ ] Deploy Swarm stack to production cluster (new environment)
   - [ ] Migrate database to new PostgreSQL service
   - [ ] Verify all services healthy
   - [ ] Import customer instance metadata

4. **Customer Instance Recreation**
   - [ ] Script to recreate customer containers in new environment
   - [ ] Migrate customer data volumes to new nodes
   - [ ] For each customer:
     - [ ] Create container in Swarm environment
     - [ ] Restore data from backup
     - [ ] Verify instance accessibility
     - [ ] Update DNS/routing

5. **Traffic Cutover**
   - [ ] Update DNS to point to new Traefik
   - [ ] Monitor traffic shift
   - [ ] Verify customer access
   - [ ] Keep old environment running as fallback

6. **Post-Migration Validation**
   - [ ] Monitor logs for errors
   - [ ] Verify all customer instances accessible
   - [ ] Test provisioning new instances
   - [ ] Test backup/restore
   - [ ] Verify monitoring operational
   - [ ] Load testing

7. **Old Environment Decommission**
   - [ ] Wait 48 hours for stability
   - [ ] Create final backups of old environment
   - [ ] Document any issues encountered
   - [ ] Shut down old environment
   - [ ] Clean up resources

**Rollback Plan:**
- If critical issues detected within first 24 hours
- DNS revert to old environment (5-minute TTL)
- Restore old environment from standby
- Post-mortem to identify issues

**Deliverables:**
- Production running on Swarm
- All customers migrated
- Old environment decommissioned
- Migration documentation

---

### Phase 5: Post-Migration Optimization (Week 5-6)

**Goals**: Optimize and enhance production deployment

#### Tasks

1. **Performance Tuning**
   - [ ] Analyze service resource usage
   - [ ] Adjust CPU/memory limits
   - [ ] Optimize database queries
   - [ ] Tune Celery worker concurrency

2. **Monitoring & Alerting**
   - [ ] Set up Prometheus metrics collection
   - [ ] Configure Grafana dashboards
   - [ ] Implement alerting rules
   - [ ] Set up log aggregation (ELK/Loki)

3. **Backup Automation**
   - [ ] Implement scheduled backup jobs
   - [ ] Set up S3 sync for off-site backups
   - [ ] Test disaster recovery procedures
   - [ ] Document backup retention policies

4. **Scaling Configuration**
   - [ ] Document scaling procedures
   - [ ] Test horizontal scaling (add worker nodes)
   - [ ] Test service scaling (increase replicas)
   - [ ] Implement auto-scaling triggers (optional)

5. **High Availability**
   - [ ] Implement PostgreSQL replication/HA (if needed)
   - [ ] Configure Redis Sentinel (if needed)
   - [ ] Set up health checks and auto-restart
   - [ ] Test failover scenarios

6. **Security Hardening**
   - [ ] Implement secrets management (Docker secrets)
   - [ ] Set up TLS for all services
   - [ ] Configure network policies
   - [ ] Security audit and penetration testing

**Deliverables:**
- Optimized production environment
- Comprehensive monitoring
- Automated backup pipeline
- HA configuration
- Security hardened

---

## Critical Success Factors

### Must-Have Before Migration

1. **NFS Storage Working**
   - All nodes can read/write to NFS
   - Tested with backup operations
   - Failover tested

2. **Registry Accessible**
   - All nodes can pull images
   - Authentication configured
   - Network connectivity verified

3. **Overlay Network Tested**
   - Customer containers can join
   - DNS resolution works
   - Cross-node communication verified

4. **Backup/Restore Validated**
   - Full backup successful
   - Restore successful
   - Data integrity verified

5. **Monitoring Auto-Start Works**
   - Worker lifecycle hooks tested
   - Event detection verified
   - Status updates working

### Rollback Triggers

Immediately rollback if:
- Customer instances unreachable for >5 minutes
- Database corruption detected
- Backup/restore fails
- >10% of customer instances failing
- Critical security vulnerability discovered

---

## Testing Checklist

### Pre-Migration Testing

- [ ] NFS performance testing (throughput, latency)
- [ ] Registry pull performance from all nodes
- [ ] Overlay network bandwidth testing
- [ ] Database connection pool under load
- [ ] Customer instance provisioning (10+ instances)
- [ ] Backup of large instance (>1GB)
- [ ] Restore under load
- [ ] Monitoring with 50+ containers
- [ ] Traefik routing under load (100+ req/s)
- [ ] Node failure simulation
- [ ] Network partition simulation

### Post-Migration Testing

- [ ] All existing customers accessible
- [ ] New customer provisioning works
- [ ] Backup scheduled job executes
- [ ] Monitoring events being captured
- [ ] Logs aggregating properly
- [ ] Metrics being collected
- [ ] Alerts firing correctly
- [ ] Scale-up test (add worker node)
- [ ] Scale-down test (drain node)
- [ ] Rolling update test

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| NFS server failure | Low | High | Set up NFS HA or daily S3 sync |
| Overlay network issues | Medium | High | Extensive pre-testing, fallback to host network |
| Customer data loss | Low | Critical | Multiple backup copies, tested restore |
| Swarm node failure | Medium | Medium | Multi-node setup, service auto-migration |
| Registry unavailable | Low | High | Mirror critical images on nodes |
| Performance degradation | Medium | Medium | Load testing, gradual rollout |
| DNS propagation delay | Low | Medium | Low TTL, parallel running |
| Monitoring not working | Medium | Low | Manual reconciliation fallback |

---

## Maintenance Procedures

### Adding a New Swarm Node

```bash
# On new node
docker swarm join --token <worker-token> <manager-ip>:2377

# On manager
docker node update --label-add odoo-volumes=true node-3

# Set up NFS mount
sudo mount -t nfs NFS_SERVER:/exports/saasodoo-backups /mnt/nfs/saasodoo-backups

# Verify
docker node ls
df -h | grep saasodoo-backups
```

### Updating Service Images

```bash
# Build new version
docker build -t registry.yourdomain.com/saasodoo/instance-service:v1.2.0 .

# Push to registry
docker push registry.yourdomain.com/saasodoo/instance-service:v1.2.0

# Update service (rolling update)
docker service update --image registry.yourdomain.com/saasodoo/instance-service:v1.2.0 saasodoo_instance-service

# Monitor rollout
docker service ps saasodoo_instance-service
```

### Emergency Procedures

**If NFS Fails:**
1. Stop new provisioning
2. Existing instances continue running (local volumes)
3. Backups queue locally until NFS restored
4. Restore NFS or migrate to backup NFS server

**If Swarm Manager Fails:**
1. Promote worker to manager: `docker node promote <node-id>`
2. Update DNS if needed
3. Verify service stability

**If Database Fails:**
1. Stop all services
2. Restore from most recent backup
3. Verify data integrity
4. Restart services
5. Run reconciliation

---

## Conclusion

This migration plan provides a structured, phased approach to moving SaasOdoo from Docker Compose to Docker Swarm. The key architectural decisions—using attachable overlay networks, NFS for backups, standalone containers for customers, and worker lifecycle hooks for monitoring—address all identified challenges while maintaining system integrity.

**Timeline Summary:**
- Week 1: Infrastructure setup
- Week 2: Code updates
- Week 3: Staging validation
- Week 4: Production migration
- Week 5-6: Optimization

**Key Success Metrics:**
- Zero data loss
- <1 hour total downtime
- All customer instances migrated
- Monitoring operational
- Backups working

The phased approach with extensive testing and clear rollback procedures minimizes risk while ensuring a successful migration to a production-ready Swarm deployment.
