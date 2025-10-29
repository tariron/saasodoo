# Docker Swarm Migration Plan - Fresh Deployment

## Executive Summary

Migrate the SaaS Odoo platform from Docker Compose to Docker Swarm to enable multi-node orchestration, high availability, and automatic service recovery. This plan assumes a **clean, fresh deployment** with no existing data migration required.

**Key Changes:**
- Each Odoo instance becomes a single-replica Docker Swarm service
- Service naming: `odoo-{database_name}-{instance_id_hex[:8]}`
- Database tracking: `service_id` and `service_name` (replacing `container_id` and `container_name`)
- Network: Overlay network for multi-node communication
- Orchestration: Swarm handles scheduling, health checks, and auto-restart

---

## Architecture Changes

### Current (Docker Compose)
- Each Odoo instance = standalone container
- Container naming: `odoo_{database_name}_{instance_id_hex}`
- Bridge network: `saasodoo-network`
- Direct container API operations (`client.containers.*`)
- Manual restart/recovery

### Target (Docker Swarm)
- Each Odoo instance = single-replica service
- Service naming: `odoo-{database_name}-{instance_id_hex}`
- Overlay network: `saasodoo-network` (attachable)
- Service API operations (`client.services.*`)
- Automatic task restart/rescheduling by Swarm

---

## Phase 1: Infrastructure Setup (2 hours)

### 1.1 Initialize Docker Swarm

**On manager node:**
```bash
docker swarm init
```

**Output:**
- Swarm initialized
- Manager node elected
- Join token generated (save for adding worker nodes later)

**Verification:**
```bash
docker node ls
```

**Deliverable:** Single-node Swarm cluster active

---

### 1.2 Create Overlay Network

**Create network:**
```bash
docker network create \
  --driver overlay \
  --attachable \
  saasodoo-network
```

**Why attachable?** Allows standalone containers (debugging) to connect to overlay network.

**Verification:**
```bash
docker network ls | grep saasodoo-network
docker network inspect saasodoo-network
```

**Deliverable:** Overlay network for service-to-service communication

---

### 1.3 Verify CephFS Storage

**Check mount:**
```bash
ls -la /mnt/cephfs
df -h | grep cephfs
```

**Test quota management:**
```bash
# Create test directory
mkdir -p /mnt/cephfs/test_quota

# Set 10GB quota
setfattr -n ceph.quota.max_bytes -v 10737418240 /mnt/cephfs/test_quota

# Verify quota
getfattr -n ceph.quota.max_bytes /mnt/cephfs/test_quota

# Cleanup
rm -rf /mnt/cephfs/test_quota
```

**Create required directories:**
```bash
cd /mnt/cephfs
mkdir -p postgres_data redis_data rabbitmq_data prometheus_data \
         odoo_instances odoo_backups killbill_db_data
```

**Set permissions:**
```bash
chmod -R 755 /mnt/cephfs/*
```

**Deliverable:** CephFS storage verified and directories created

---

### 1.4 Update Traefik Configuration

**File:** `infrastructure/traefik/traefik.yml`

**Add Swarm mode to Docker provider:**
```yaml
providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    swarmMode: true  # ADD THIS LINE
    network: saasodoo-network
```

**Verification:** Will be confirmed after Traefik service deployed in Phase 7

**Deliverable:** Traefik configured for Swarm service discovery

---

## Phase 2: Database Schema Updates (1 hour)

### 2.1 Update Instance Model

**File:** `services/instance-service/app/models/instance.py`

**Changes at lines 206-208:**

**OLD:**
```python
# Container information
container_id: Optional[str] = Field(None, description="Docker container ID")
container_name: Optional[str] = Field(None, description="Docker container name")
```

**NEW:**
```python
# Service information (Swarm)
service_id: Optional[str] = Field(None, description="Docker service ID")
service_name: Optional[str] = Field(None, description="Docker service name")
```

**Why remove container fields?** Fresh deployment - no backward compatibility needed.

**Database creation:** SQLAlchemy will create the correct schema on first run.

**Deliverable:** Instance model reflects Swarm service architecture

---

## Phase 3: Core Service Code Updates (2 days)

### 3.1 Update `docker_client.py`

**File:** `services/instance-service/app/utils/docker_client.py`

**Changes:**

#### Update Service Pattern (Line 26)
```python
# OLD
self.container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')

# NEW
self.service_pattern = re.compile(r'^odoo-([^-]+)-([a-f0-9]{8})$')
```

#### Add Service Methods
**New methods to add:**
1. `get_service(service_name)` - Get service by name
2. `get_service_by_label(label_key, label_value)` - Label-based lookup
3. `get_service_status(service_name)` - Get task states
4. `start_service(service_name, timeout)` - Scale to 1 replica
5. `stop_service(service_name, timeout)` - Scale to 0 replicas
6. `restart_service(service_name, timeout)` - Force update tasks
7. `get_service_logs(service_name, tail)` - Service logs
8. `list_saasodoo_services()` - List all Odoo services
9. `service_health_check(service_name)` - Check task health
10. `update_service_resources(service_name, cpu_limit, memory_bytes)` - Update resources

**Replace container-based methods** with service equivalents:
- `get_container()` → `get_service()`
- `list_saasodoo_containers()` → `list_saasodoo_services()`
- `get_container_status()` → `get_service_status()`
- `container_health_check()` → `service_health_check()`
- `update_container_resources()` → `update_service_resources()`

**Key differences:**
- Services have tasks (containers running in a service)
- Check task state: `task['Status']['State']` (running, failed, etc.)
- Get task IP: `task['NetworksAttachments'][0]['Addresses'][0]`
- Scaling: `service.update(mode={'Replicated': {'Replicas': N}})`

**Deliverable:** Docker wrapper supports Swarm service operations

---

### 3.2 Update `provisioning.py`

**File:** `services/instance-service/app/tasks/provisioning.py`

**Key function:** `_deploy_odoo_container()` (Line 309)

#### Change Service Name (Line 315)
```python
# OLD
container_name = f"odoo_{instance['database_name']}_{instance['id'].hex[:8]}"

# NEW
service_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"
```

#### Replace Container Creation with Service Creation (Line 372)
**OLD:** `client.containers.run(...)`

**NEW:** `client.services.create(...)`

**Key parameters:**
- `image`: Odoo image
- `name`: Service name
- `env`: Environment variables (dict, not list)
- `resources`: `docker.types.Resources(cpu_limit=int, mem_limit=int)`
- `mode`: `docker.types.ServiceMode('replicated', replicas=1)`
- `mounts`: `[docker.types.Mount(target='/bitnami/odoo', source=volume_name, type='volume')]`
- `networks`: `['saasodoo-network']`
- `labels`: Traefik routing + metadata
- `restart_policy`: `docker.types.RestartPolicy(condition='any')`

**Wait for task to start:**
```python
await asyncio.sleep(5)  # Give Swarm time to schedule
service.reload()
tasks = service.tasks()
running_task = next((t for t in tasks if t['Status']['State'] == 'running'), None)
```

**Extract task information:**
```python
internal_ip = running_task['NetworksAttachments'][0]['Addresses'][0].split('/')[0]
container_id = running_task['Status']['ContainerStatus']['ContainerID'][:12]
```

**Return dict fields:**
```python
return {
    'service_id': service.id,
    'service_name': service_name,
    'internal_ip': internal_ip,
    'internal_url': f'http://{internal_ip}:8069',
    'external_url': f'http://{subdomain}.saasodoo.local',
    'admin_password': generated_password
}
```

#### Update Network Info Function (Line 461)
**Function:** `_update_instance_network_info()`

**OLD:**
```python
UPDATE instances
SET container_id = $1, container_name = $2,
    internal_url = $3, external_url = $4, updated_at = $5
WHERE id = $6
```

**NEW:**
```python
UPDATE instances
SET service_id = $1, service_name = $2,
    internal_url = $3, external_url = $4, updated_at = $5
WHERE id = $6
```

**Deliverable:** New instances deploy as Swarm services

---

### 3.3 Update `lifecycle.py`

**File:** `services/instance-service/app/tasks/lifecycle.py`

#### Start Workflow (Line 305)
**Function:** `_start_docker_container()` → `_start_docker_service()`

**Logic:**
1. Get service by name
2. Check current replica count
3. Scale to 1: `service.update(mode={'Replicated': {'Replicas': 1}})`
4. Wait for task state = 'running' (60s timeout)
5. Extract task network info
6. Return service details

**If service not found:** Re-provision (call `_deploy_odoo_service()`)

#### Stop Workflow (Line 371)
**Function:** `_stop_docker_container()` → `_stop_docker_service()`

**Logic:**
1. Get service by name
2. Scale to 0: `service.update(mode={'Replicated': {'Replicas': 0}})`
3. No waiting needed (Swarm handles graceful shutdown)

#### Restart Workflow (Line 266)
**Function:** `_restart_docker_container()` → `_restart_docker_service()`

**Logic:**
1. Get service by name
2. Force update: `service.force_update()`
3. Wait for new task to reach 'running' state (60s timeout)
4. Extract task network info
5. Return service details

#### Unpause Workflow (Line 406)
**Remove entirely** - Swarm doesn't support pause/unpause operations.

**Alternative:** Map unpause action to start operation (scale to 1).

**Deliverable:** Lifecycle operations work with Swarm services

---

### 3.4 Update `monitoring.py`

**File:** `services/instance-service/app/tasks/monitoring.py`

**Changes:**

**Replace container health checks with service task checks:**
- Query service tasks: `service.tasks()`
- Check task states: `task['Status']['State']`
- Compare `DesiredState` vs `CurrentState`
- Detect unhealthy tasks (desired=running, current=failed)

**Update health check logic:**
- Service is healthy if: has running task, task uptime > 10s
- Service is unhealthy if: no tasks, task failed, task pending too long

**Deliverable:** Health monitoring works with Swarm services

---

### 3.5 Update `maintenance.py`

**File:** `services/instance-service/app/tasks/maintenance.py`

**Changes:**

**Orphan detection:**
1. List all services: `client.services.list(filters={'label': 'saasodoo.instance.id'})`
2. Extract instance IDs from labels
3. Query database for matching instances
4. Remove services without database records: `service.remove()`

**Deliverable:** Orphan cleanup works with Swarm services

---

### 3.6 Update `routes/instances.py`

**File:** `services/instance-service/app/routes/instances.py`

**Changes:**

**Suspension logic (Line 1141-1168):**
- Update service name pattern: `service_name = f"odoo-{instance.database_name}-{str(instance.id).replace('-', '')[:8]}"`
- Replace `client.containers.get()` with `client.services.get()`
- Replace `container.stop()` with `service.update(mode={'Replicated': {'Replicas': 0}})`

**Resource scaling (Line 1302-1371):**
- Use `instance.service_name` instead of `instance.container_name`
- Call `docker_client.update_service_resources()` instead of `update_container_resources()`
- Update response to include `service_name`

**API responses:**
- Include `service_id` and `service_name` in instance response models
- Remove references to `container_id` and `container_name`

**Deliverable:** Instance routes work with Swarm services

---

### 3.7 Update `routes/monitoring.py`

**File:** `services/instance-service/app/routes/monitoring.py`

**Changes:**

**Health check endpoint (Line 217):**
- Call `docker_client.service_health_check()` instead of `container_health_check()`
- Use `service_name` from database

**Status endpoint (Line 245-284):**
- Change path parameter from `container_name` to `service_name`
- Call `get_service_info()` instead of `get_container_info()`
- Return task state information

**Sync endpoint (Line 358-396):**
- Change path parameter to `service_name`
- Use `is_saasodoo_service()` instead of `is_saasodoo_container()`
- Extract metadata from service labels (not name pattern)

**Deliverable:** Monitoring endpoints work with Swarm services

---

## Phase 4: Convert docker-compose.ceph.yml to Swarm Stack (4 hours)

### 4.1 Add Deploy Sections to All Services

**Stateful services** (postgres, redis, rabbitmq, killbill-db):
```yaml
deploy:
  replicas: 1
  placement:
    constraints:
      - node.role == manager
  restart_policy:
    condition: any
    delay: 5s
    max_attempts: 3
  update_config:
    parallelism: 1
    delay: 10s
```

**Stateless services** (user-service, instance-service, instance-worker, billing-service, notification-service, frontend-service):
```yaml
deploy:
  replicas: 1
  restart_policy:
    condition: any
    delay: 5s
  update_config:
    parallelism: 1
    delay: 10s
```

**Traefik** (special case - needs access to Docker socket):
```yaml
deploy:
  replicas: 1
  placement:
    constraints:
      - node.role == manager
  restart_policy:
    condition: any
```

**Monitoring services** (prometheus, mailhog):
```yaml
deploy:
  replicas: 1
  restart_policy:
    condition: any
```

**KillBill and Kaui:**
```yaml
deploy:
  replicas: 1
  restart_policy:
    condition: any
    delay: 10s
```

---

### 4.2 Update Network Configuration

**File:** `infrastructure/compose/docker-compose.ceph.yml`

**Line 597-600 (networks section):**

**OLD:**
```yaml
networks:
  saasodoo-network:
    driver: bridge
    name: saasodoo-network
```

**NEW:**
```yaml
networks:
  saasodoo-network:
    driver: overlay
    attachable: true
    name: saasodoo-network
```

**Why attachable?** Allows debugging - can connect standalone containers to the network.

---

### 4.3 Remove Container Names

**Remove all `container_name:` directives from services.**

Swarm manages task naming automatically:
- Task format: `{stack_name}_{service_name}.{replica_number}.{task_id}`
- Example: `saasodoo_postgres.1.abc123def456`

**Services to update:**
- traefik (line 7)
- postgres (line 28)
- redis (line 60)
- rabbitmq (line 82)
- prometheus (line 110)
- mailhog (line 133)
- killbill-db (line 148)
- killbill (line 168)
- kaui (line 223)
- user-service (line 268)
- instance-service (line 329)
- instance-worker (line 401)
- billing-service (line 452)
- frontend-service (line 516)
- notification-service (line 539)

---

### 4.4 Update Volume Definitions

**No changes needed** - CephFS bind mounts work in Swarm mode.

Volumes already configured correctly:
```yaml
volumes:
  postgres-data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /mnt/cephfs/postgres_data
```

---

### 4.5 Update Port Mappings (Optional)

**Consider:** In Swarm mode, published ports are load-balanced across all nodes.

**For development (single node):** Keep existing port mappings.

**For production (multi-node):** Use ingress routing or host mode:
```yaml
ports:
  - target: 8001
    published: 8001
    mode: host  # Binds to specific node IP, not load-balanced
```

---

## Phase 5: Testing Strategy (1 day)

### 5.1 Unit Tests

**Test service creation:**
```python
def test_create_service():
    # Mock docker.services.create()
    # Verify correct parameters passed
    # Assert service_id returned
```

**Test service scaling:**
```python
def test_start_service():
    # Mock service.update(mode={'Replicated': {'Replicas': 1}})
    # Verify scaling to 1 replica

def test_stop_service():
    # Mock service.update(mode={'Replicated': {'Replicas': 0}})
    # Verify scaling to 0 replicas
```

**Test force update:**
```python
def test_restart_service():
    # Mock service.force_update()
    # Verify new task created
```

---

### 5.2 Integration Tests

**Create instance:**
```bash
# POST to instance API
curl -X POST http://api.localhost/instance/instances \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test-instance",
    "database_name": "testdb",
    "admin_email": "admin@test.com",
    ...
  }'

# Verify service created
docker service ls | grep odoo-

# Verify Traefik routing
curl http://testdb.saasodoo.local
```

**Lifecycle operations:**
```bash
# Stop instance
curl -X POST http://api.localhost/instance/instances/{id}/stop

# Verify service scaled to 0
docker service ps odoo-{id} --format "{{.DesiredState}}"

# Start instance
curl -X POST http://api.localhost/instance/instances/{id}/start

# Verify service scaled to 1
docker service ps odoo-{id} --filter "desired-state=running"

# Restart instance
curl -X POST http://api.localhost/instance/instances/{id}/restart

# Verify new task created
docker service ps odoo-{id} --no-trunc
```

---

### 5.3 Load Tests

**Create 10 instances concurrently:**
```bash
for i in {1..10}; do
  curl -X POST http://api.localhost/instance/instances \
    -H "Content-Type: application/json" \
    -d "{...}" &
done
wait
```

**Verify:**
- All services created: `docker service ls | grep odoo- | wc -l`
- All services have 1/1 replicas
- Traefik routes all instances correctly
- CephFS quotas applied to all volumes

**Measure:**
- Service creation time (should be < 5 minutes)
- Resource allocation (CPU/memory limits enforced)
- Network connectivity (ping between services)

---

### 5.4 Failure Scenarios

**Test 1: Kill service task**
```bash
# Get task container ID
CONTAINER_ID=$(docker ps -q -f label=com.docker.swarm.service.name=odoo-abc12345)

# Kill container
docker kill $CONTAINER_ID

# Verify Swarm auto-restarts within 30s
docker service ps odoo-abc12345
```

**Test 2: Service with bad configuration**
```bash
# Create service with invalid image
# Verify provisioning fails gracefully
# Verify instance status = ERROR
# Verify cleanup removes failed service
```

**Test 3: Network partition (multi-node only)**
```bash
# Block traffic between nodes
# Verify tasks rescheduled to healthy nodes
# Restore network
# Verify cluster converges
```

**Test 4: CephFS quota reached**
```bash
# Fill instance volume to quota limit
# Verify writes fail
# Verify instance doesn't crash
# Verify error reported to user
```

---

## Phase 6: Documentation Updates (4 hours)

### 6.1 Update CLAUDE.md

**Add Swarm architecture section:**
```markdown
## Docker Swarm Architecture

This platform uses Docker Swarm for orchestration:
- **Manager node:** Schedules services, maintains cluster state
- **Worker nodes:** Run service tasks (containers)
- **Overlay network:** saasodoo-network for service communication
- **Service per instance:** Each Odoo instance = single-replica service
```

**Update development setup:**
```markdown
## Development Setup

1. Initialize Swarm:
   ```bash
   docker swarm init
   ```

2. Create overlay network:
   ```bash
   docker network create --driver overlay --attachable saasodoo-network
   ```

3. Deploy stack:
   ```bash
   docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
   ```

4. Verify services:
   ```bash
   docker stack services saasodoo
   ```
```

**Update command reference:**
```markdown
## Common Commands

### Stack Management
- Deploy: `docker stack deploy -c docker-compose.ceph.yml saasodoo`
- Remove: `docker stack rm saasodoo`
- List services: `docker stack services saasodoo`
- List tasks: `docker stack ps saasodoo`

### Service Management
- List: `docker service ls`
- Inspect: `docker service inspect saasodoo_instance-service`
- Logs: `docker service logs -f saasodoo_instance-service`
- Scale: `docker service scale saasodoo_instance-service=2`
- Update: `docker service update --force saasodoo_instance-service`

### Odoo Instance Services
- List: `docker service ls --filter label=saasodoo.instance.id`
- Inspect: `docker service inspect odoo-abc12345`
- Logs: `docker service logs -f odoo-abc12345`
- Tasks: `docker service ps odoo-abc12345`
```

**Update service naming convention:**
```markdown
## Instance Naming Convention

- **Service name:** `odoo-{database_name}-{instance_id_hex[:8]}`
- **Example:** `odoo-mycompany-a1b2c3d4` for database `mycompany` and instance UUID `a1b2c3d4-5678-90ab-cdef-1234567890ab`
- **Why this pattern?** Database name is already unique (used as subdomain), combined with instance ID provides strong uniqueness guarantee
- **Labels:**
  - `saasodoo.instance.id`: Full instance UUID
  - `saasodoo.instance.name`: Instance display name
  - `saasodoo.customer.id`: Customer UUID
```

---

### 6.2 Developer Documentation

**Create:** `docs/SWARM_DEVELOPER_GUIDE.md`

**Contents:**
- How to view service logs
- How to inspect service tasks
- How to access task containers for debugging
- How to test Swarm locally (single-node)
- How to add worker nodes
- Common debugging scenarios
- Troubleshooting guide

**Example sections:**

**Viewing Service Logs:**
```markdown
## Viewing Logs

### Platform service logs:
```bash
docker service logs -f saasodoo_instance-service
docker service logs --tail 100 saasodoo_billing-service
```

### Odoo instance logs:
```bash
docker service logs -f odoo-abc12345
```

### Specific task logs:
```bash
# Get task ID
docker service ps odoo-abc12345

# View task logs
docker logs {task_container_id}
```
```

**Accessing Containers:**
```markdown
## Debugging Containers

### Find task container:
```bash
# Get container ID for service
CONTAINER_ID=$(docker ps -q -f label=com.docker.swarm.service.name=odoo-abc12345)

# Exec into container
docker exec -it $CONTAINER_ID bash
```

### Quick access:
```bash
docker exec -it $(docker ps -q -f label=com.docker.swarm.service.name=odoo-abc12345) bash
```
```

---

### 6.3 Operations Documentation

**Create:** `docs/SWARM_OPERATIONS_GUIDE.md`

**Contents:**
- Swarm cluster management
- Adding/removing nodes
- Backup and recovery procedures
- Rolling updates for platform services
- Monitoring cluster health
- Security best practices
- Disaster recovery

**Create:** `docs/SWARM_TROUBLESHOOTING.md`

**Contents:**
- Service won't start
- Tasks in pending state
- Network connectivity issues
- Volume mount problems
- Node failures
- Swarm split-brain scenarios
- Performance issues

---

## Phase 7: Deployment Process (2 hours)

### 7.1 Pre-Deployment Checklist

Infrastructure:
- [ ] Docker Swarm initialized (`docker swarm init`)
- [ ] Overlay network created (`docker network create --driver overlay --attachable saasodoo-network`)
- [ ] CephFS mounted at `/mnt/cephfs` on all nodes
- [ ] Required CephFS directories created
- [ ] CephFS quota management tested

Configuration:
- [ ] Traefik config updated with `swarmMode: true`
- [ ] `.env` file configured with all required variables
- [ ] All secrets/credentials generated

Code:
- [ ] Database model updated (service_id/service_name fields)
- [ ] All instance-service code updated
- [ ] docker-compose.ceph.yml converted to stack format
- [ ] All code committed and pushed

Testing:
- [ ] Unit tests passing
- [ ] Integration tests written
- [ ] Load tests prepared

---

### 7.2 Deployment Steps

**Step 1: Initialize Swarm**
```bash
docker swarm init
docker node ls  # Verify manager elected
```

**Step 2: Create Overlay Network**
```bash
docker network create --driver overlay --attachable saasodoo-network
docker network ls | grep saasodoo-network
```

**Step 3: Prepare CephFS**
```bash
cd /mnt/cephfs
mkdir -p postgres_data redis_data rabbitmq_data prometheus_data \
         odoo_instances odoo_backups killbill_db_data
chmod -R 755 .
```

**Step 4: Deploy Stack**
```bash
cd /home/tariron/Projects/saasodoo
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

**Step 5: Monitor Deployment**
```bash
# Watch services come up
watch docker stack services saasodoo

# Check for errors
docker service ls | grep "0/1"
docker service logs saasodoo_postgres
```

**Step 6: Wait for Health Checks**
```bash
# All services should show 1/1 replicas
docker stack services saasodoo

# Verify postgres ready
docker service logs saasodoo_postgres | grep "ready to accept connections"

# Verify KillBill ready
docker service logs saasodoo_killbill | grep "started successfully"
```

**Step 7: Verify Database Schema**
```bash
# Connect to postgres
docker exec -it $(docker ps -q -f label=com.docker.swarm.service.name=saasodoo_postgres) bash

# Inside container
psql -U instance_service -d instance

# Check schema
\d instances

# Verify service_id and service_name columns exist
SELECT column_name FROM information_schema.columns
WHERE table_name = 'instances' AND column_name IN ('service_id', 'service_name');

# Exit
\q
exit
```

---

### 7.3 Post-Deployment Verification

**1. Verify all services running:**
```bash
docker stack services saasodoo
# All services should show 1/1 replicas
```

**2. Check service health:**
```bash
# Postgres
docker service logs saasodoo_postgres --tail 50

# Redis
docker exec $(docker ps -q -f label=com.docker.swarm.service.name=saasodoo_redis) redis-cli ping

# RabbitMQ
curl http://rabbitmq.localhost/

# KillBill
curl http://billing.localhost/1.0/healthcheck
```

**3. Verify Traefik routing:**
```bash
# Access Traefik dashboard
curl http://traefik.localhost/dashboard/

# Check service discovery
curl http://traefik.localhost/api/http/services
```

**4. Create test instance:**
```bash
# Register user (if needed)
curl -X POST http://auth.localhost/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!",
    "first_name": "Test",
    "last_name": "User"
  }'

# Login to get token
TOKEN=$(curl -X POST http://auth.localhost/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!"
  }' | jq -r '.access_token')

# Create instance
curl -X POST http://api.localhost/instance/instances \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Instance",
    "database_name": "testdb",
    "admin_email": "admin@test.com",
    "odoo_version": "17",
    "instance_type": "development",
    "billing_status": "trial"
  }'
```

**5. Verify instance service created:**
```bash
# List Odoo services
docker service ls --filter label=saasodoo.instance.id

# Check service status (example: odoo-testdb-a1b2c3d4)
docker service ps odoo-testdb-{instance_id_hex}

# Check service logs
docker service logs odoo-testdb-{instance_id_hex}
```

**6. Test Traefik routing to instance:**
```bash
# Wait for Odoo to start (may take 2-3 minutes)
curl -I http://testdb.saasodoo.local

# Should return 200 or 303 (Odoo redirect)
```

**7. Test lifecycle operations:**
```bash
# Get instance ID from create response
INSTANCE_ID="..."

# Stop instance
curl -X POST http://api.localhost/instance/instances/$INSTANCE_ID/stop \
  -H "Authorization: Bearer $TOKEN"

# Verify service scaled to 0
docker service ls --filter label=saasodoo.instance.id=$INSTANCE_ID

# Start instance
curl -X POST http://api.localhost/instance/instances/$INSTANCE_ID/start \
  -H "Authorization: Bearer $TOKEN"

# Verify service scaled to 1
docker service ls --filter label=saasodoo.instance.id=$INSTANCE_ID
```

**8. Verify billing integration:**
```bash
# Check KillBill webhook registered
docker exec $(docker ps -q -f label=com.docker.swarm.service.name=saasodoo_killbill) \
  curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  http://localhost:8080/1.0/kb/tenants/userKeyValue/PUSH_NOTIFICATION_CB
```

**9. Check monitoring:**
```bash
# Prometheus targets
curl http://prometheus.localhost/api/v1/targets

# Grafana (if configured)
curl http://grafana.localhost/
```

**10. Verify email notifications:**
```bash
# Access MailHog
curl http://mail.localhost/

# Should show emails sent during instance creation
```

---

## Phase 8: Rollback Plan

### Scenario 1: Service-Level Issues

**Problem:** Single service failing (e.g., instance-service)

**Solution:**
```bash
# Stop problematic service
docker service scale saasodoo_instance-service=0

# Review logs
docker service logs saasodoo_instance-service --tail 200

# Fix code/config

# Redeploy service
docker service update --force saasodoo_instance-service

# Or rebuild and update
docker service update --image {new_image} saasodoo_instance-service
```

---

### Scenario 2: Stack-Level Issues

**Problem:** Multiple services failing, need clean restart

**Solution:**
```bash
# Remove entire stack
docker stack rm saasodoo

# Wait for cleanup (30-60 seconds)
docker service ls  # Should be empty

# Fix docker-compose.ceph.yml

# Redeploy
docker stack deploy -c infrastructure/compose/docker-compose.ceph.yml saasodoo
```

---

### Scenario 3: Critical Failure - Leave Swarm

**Problem:** Swarm mode causing critical issues, need to revert to Compose

**Solution:**
```bash
# 1. Stop all services
docker stack rm saasodoo

# 2. Leave Swarm
docker swarm leave --force

# 3. Revert code changes
git checkout main  # Or last working commit
git revert {swarm_migration_commits}

# 4. Recreate bridge network
docker network create saasodoo-network

# 5. Deploy with Compose
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d

# 6. Verify services
docker compose -f infrastructure/compose/docker-compose.ceph.yml ps
```

**Note:** This requires reverting code changes that removed container_id/container_name fields.

---

### Scenario 4: Partial Rollback

**Problem:** Want to keep platform services in Swarm, but revert Odoo instance deployment

**Solution:**
1. Keep platform services running in Swarm
2. Revert only instance-service code to container-based operations
3. Update database schema to restore container_id/container_name
4. Deploy instance-service update

**Not recommended** - better to fully commit to Swarm or fully rollback.

---

## Timeline Estimate

| Phase | Duration | Person-Days |
|-------|----------|-------------|
| Phase 1: Infrastructure Setup | 2 hours | 0.25 |
| Phase 2: Database Schema | 1 hour | 0.125 |
| Phase 3: Core Code Updates | 16 hours | 2.0 |
| Phase 4: Compose to Stack | 4 hours | 0.5 |
| Phase 5: Testing | 8 hours | 1.0 |
| Phase 6: Documentation | 4 hours | 0.5 |
| Phase 7: Deployment | 2 hours | 0.25 |
| **Total** | **37 hours** | **~4.6 days** |

**Assumes:** Single developer, full-time work, no major blockers.

---

## Key Success Metrics

### Performance
- [ ] Service creation time: < 5 minutes per instance
- [ ] Service start time: < 30 seconds (from API call to task running)
- [ ] Service stop time: < 10 seconds
- [ ] Auto-recovery time: < 30 seconds after task failure

### Reliability
- [ ] Services auto-restart on failure (Swarm orchestration)
- [ ] Health checks detect task failures within 60 seconds
- [ ] Failed tasks rescheduled automatically

### Functionality
- [ ] Traefik routes all instance domains correctly
- [ ] CPU/Memory limits enforced on services
- [ ] CephFS quotas prevent instances exceeding storage limits
- [ ] All API endpoints work (backward compatible)
- [ ] Billing integration functional (KillBill webhooks)
- [ ] Email notifications sent correctly

### Operational
- [ ] Service logs accessible via `docker service logs`
- [ ] Service status visible via `docker service ps`
- [ ] Orphan cleanup removes services without DB records
- [ ] Monitoring dashboards show service metrics

---

## Risk Mitigation

| Risk | Impact | Probability | Mitigation Strategy |
|------|--------|-------------|---------------------|
| Swarm learning curve | High | Medium | Start with single-node Swarm, extensive testing before multi-node |
| CephFS not available on nodes | High | Low | Verify mount on all nodes before deployment, have NFS fallback |
| Service networking issues | Medium | Medium | Keep overlay network attachable for debugging, test connectivity |
| Traefik routing failures | High | Low | Test label-based routing extensively, keep direct port access |
| Performance degradation | Medium | Low | Benchmark before/after, have Compose config as fallback |
| Volume mount inconsistencies | High | Low | Standardize CephFS paths across all nodes, test mounts |
| Task scheduling delays | Low | Medium | Monitor task placement, optimize resource requests |
| Split-brain scenarios | High | Very Low | Single-node deployment initially, add workers carefully |

---

## Files Modified Summary

### New Files (3)
1. `DOCKER_SWARM_MIGRATION_PLAN.md` - This document
2. `docs/SWARM_DEVELOPER_GUIDE.md` - Developer reference
3. `docs/SWARM_OPERATIONS_GUIDE.md` - Operations manual
4. `docs/SWARM_TROUBLESHOOTING.md` - Troubleshooting guide

### Modified Infrastructure Files (2)
1. `infrastructure/compose/docker-compose.ceph.yml` - Add deploy sections, change network to overlay
2. `infrastructure/traefik/traefik.yml` - Enable swarmMode

### Modified Instance Service Files (7)
1. `services/instance-service/app/models/instance.py` - Update to service_id/service_name
2. `services/instance-service/app/utils/docker_client.py` - Add service methods
3. `services/instance-service/app/tasks/provisioning.py` - Service creation logic
4. `services/instance-service/app/tasks/lifecycle.py` - Service lifecycle operations
5. `services/instance-service/app/tasks/monitoring.py` - Service health checks
6. `services/instance-service/app/tasks/maintenance.py` - Service cleanup
7. `services/instance-service/app/routes/instances.py` - Update suspension/scaling
8. `services/instance-service/app/routes/monitoring.py` - Service monitoring endpoints

### Modified Documentation Files (1)
1. `CLAUDE.md` - Update with Swarm commands and architecture

**Total: 16 files**

---

## Post-Migration Enhancements (Future)

### Phase 9: Multi-Node Deployment
- Add worker nodes to Swarm cluster
- Configure node labels for workload placement
- Test cross-node networking
- Implement node affinity rules

### Phase 10: High Availability
- PostgreSQL streaming replication (primary + replica)
- Redis Sentinel for cache HA
- RabbitMQ clustering
- Multi-replica Traefik

### Phase 11: Security Hardening
- Implement Docker secrets for credentials
- Enable TLS for service communication
- Implement service mesh (Traefik Mesh)
- Network segmentation (separate overlay networks)

### Phase 12: Observability
- Distributed tracing (Jaeger)
- Centralized logging (ELK/Loki)
- Service metrics (Prometheus exporters)
- Custom Grafana dashboards

### Phase 13: Autoscaling
- Horizontal pod autoscaling for platform services
- Dynamic instance provisioning based on demand
- Resource quota management per customer
- Cost optimization strategies

---

## Conclusion

This migration plan transitions the SaaS Odoo platform from Docker Compose to Docker Swarm, enabling multi-node orchestration, automatic failure recovery, and simplified operations. The primary architectural change is replacing direct container management with Swarm service management in the instance-service.

**Key Benefits:**
- **Automatic recovery:** Swarm restarts failed tasks without manual intervention
- **Simplified deployment:** Single `docker stack deploy` command
- **Better resource management:** Service-level resource constraints
- **Built-in health checks:** Swarm monitors task health automatically
- **Multi-node ready:** Easy to add worker nodes for horizontal scaling

**Migration Approach:**
- Fresh deployment (no data migration)
- Clean database schema with service fields
- Backward compatible API (frontend/billing unchanged)
- Comprehensive testing strategy
- Clear rollback procedures

**Estimated Timeline:** ~4-5 working days for complete migration and testing.
