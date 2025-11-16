# Option C: Pure Docker Swarm
## Full Container Orchestration

---

## Overview

This deployment method uses **Docker Swarm for all components**. Everything runs in containers orchestrated by Docker Swarm, including etcd, Patroni, PostgreSQL, PgBouncer, and HAProxy. This is the most modern, container-first approach.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                              │
│                     (Docker Swarm Services)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ user-service │  │billing-svc   │  │instance-svc  │             │
│  │              │  │              │  │              │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                      │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                            │ Docker overlay: saasodoo-network
                            │
          ┌─────────────────▼─────────────────┐
          │     HAProxy (Docker Service)      │
          │     Image: haproxy:3.3-alpine     │
          │     Replicas: 3 (global mode)     │
          │                                   │
          │  Port 5432 → PRIMARY (writes)     │
          │  Port 5433 → REPLICAS (reads)     │
          │  Port 7000 → Stats UI             │
          │                                   │
          │  Networks:                        │
          │  - saasodoo-network (frontend)    │
          │  - db-frontend (to PgBouncer)     │
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
┌─────────▼─────────┐ ┌─────▼─────────┐ ┌───▼───────────┐
│  PgBouncer        │ │  PgBouncer    │ │  PgBouncer    │
│  (Docker)         │ │  (Docker)     │ │  (Docker)     │
│  Server 1         │ │  Server 2     │ │  Server 3     │
│                   │ │               │ │               │
│ Image:            │ │ Image:        │ │ Image:        │
│ pgbouncer/        │ │ pgbouncer/    │ │ pgbouncer/    │
│ pgbouncer:latest  │ │ pgbouncer...  │ │ pgbouncer...  │
│                   │ │               │ │               │
│ Port: 6432        │ │ Port: 6432    │ │ Port: 6432    │
│ Pool mode:        │ │ Pool mode:    │ │ Pool mode:    │
│ transaction       │ │ transaction   │ │ transaction   │
│                   │ │               │ │               │
│ Networks:         │ │ Networks:     │ │ Networks:     │
│ - db-frontend     │ │ - db-frontend │ │ - db-frontend │
│ - db-backend      │ │ - db-backend  │ │ - db-backend  │
│                   │ │               │ │               │
│ Deploy:           │ │ Deploy:       │ │ Deploy:       │
│ mode: global      │ │ mode: global  │ │ mode: global  │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
          │                   │                 │
          │                   │                 │
┌─────────▼─────────┐ ┌───────▼───────┐ ┌───────▼───────┐
│   Spilo           │ │  Spilo        │ │  Spilo        │
│   (Patroni +      │ │  (Patroni +   │ │  (Patroni +   │
│    PostgreSQL)    │ │   PostgreSQL) │ │   PostgreSQL) │
│   Server 1        │ │  Server 2     │ │  Server 3     │
│                   │ │               │ │               │
│ Image:            │ │ Image:        │ │ Image:        │
│ ghcr.io/zalando/  │ │ ghcr.io/      │ │ ghcr.io/      │
│ spilo-17:4.0-p3   │ │ spilo-17...   │ │ spilo-17...   │
│                   │ │               │ │               │
│ Patroni Role:     │ │ Patroni Role: │ │ Patroni Role: │
│ LEADER (PRIMARY)  │ │ REPLICA       │ │ REPLICA       │
│                   │ │               │ │               │
│ PostgreSQL:       │ │ PostgreSQL:   │ │ PostgreSQL:   │
│ Port 5432         │ │ Port 5432     │ │ Port 5432     │
│                   │ │               │ │               │
│ Patroni REST:     │ │ Patroni REST: │ │ Patroni REST: │
│ Port 8008         │ │ Port 8008     │ │ Port 8008     │
│                   │ │               │ │               │
│ Networks:         │ │ Networks:     │ │ Networks:     │
│ - db-backend      │ │ - db-backend  │ │ - db-backend  │
│ - patroni-net     │ │ - patroni-net │ │ - patroni-net │
│                   │ │               │ │               │
│ Placement:        │ │ Placement:    │ │ Placement:    │
│ node.labels.      │ │ node.labels.  │ │ node.labels.  │
│ patroni==node1    │ │ patroni==node2│ │ patroni==node3│
│                   │ │               │ │               │
│ Volumes:          │ │ Volumes:      │ │ Volumes:      │
│ /data/pg/node1    │ │ /data/pg/node2│ │ /data/pg/node3│
│ → /home/postgres/ │ │ → /home/      │ │ → /home/      │
│    pgdata         │ │    postgres/  │ │    postgres/  │
│                   │ │    pgdata     │ │    pgdata     │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
          │                   │                 │
          │ bind mount        │ bind mount      │ bind mount
          │                   │                 │
          ▼                   ▼                 ▼
    /data/postgres/     /data/postgres/   /data/postgres/
        node1/              node2/            node3/
    (LOCAL DISK)        (LOCAL DISK)      (LOCAL DISK)
          │                   │                 │
          │                   │                 │
          └───────────────────┴─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │        etcd Cluster               │
          │        (Docker Services)          │
          │                                   │
          │  ┌────────┐  ┌────────┐  ┌────────┐
          │  │ etcd-1 │  │ etcd-2 │  │ etcd-3 │
          │  │(Docker)│  │(Docker)│  │(Docker)│
          │  │        │  │        │  │        │
          │  │Image:  │  │Image:  │  │Image:  │
          │  │bitnami/│  │bitnami/│  │bitnami/│
          │  │etcd:   │  │etcd:   │  │etcd:   │
          │  │latest  │  │latest  │  │latest  │
          │  │        │  │        │  │        │
          │  │Port:   │  │Port:   │  │Port:   │
          │  │2379    │  │2379    │  │2379    │
          │  │2380    │  │2380    │  │2380    │
          │  │        │  │        │  │        │
          │  │Network:│  │Network:│  │Network:│
          │  │patroni-│  │patroni-│  │patroni-│
          │  │net     │  │net     │  │net     │
          │  │        │  │        │  │        │
          │  │Place:  │  │Place:  │  │Place:  │
          │  │node.   │  │node.   │  │node.   │
          │  │labels. │  │labels. │  │labels. │
          │  │etcd==  │  │etcd==  │  │etcd==  │
          │  │node1   │  │node2   │  │node3   │
          │  │        │  │        │  │        │
          │  │Volume: │  │Volume: │  │Volume: │
          │  │/data/  │  │/data/  │  │/data/  │
          │  │etcd/   │  │etcd/   │  │etcd/   │
          │  │node1   │  │node2   │  │node3   │
          │  └────────┘  └────────┘  └────────┘
          │                                   │
          │  Network: patroni-net (internal)  │
          └───────────────────────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │      CephFS (Optional)            │
          │      /mnt/cephfs/postgres/        │
          │                                   │
          │  - WAL archives                   │
          │  - Backups                        │
          │  - Mounted in Spilo containers    │
          └───────────────────────────────────┘
```

---

## Docker Networks

### 1. **saasodoo-network** (overlay, attachable)
- Application services ↔ HAProxy
- Public-facing connectivity
- Your existing SaaSOdoo network

### 2. **db-frontend** (overlay, internal)
- HAProxy ↔ PgBouncer
- Load balancer to connection pooler

### 3. **db-backend** (overlay, internal)
- PgBouncer ↔ Spilo (PostgreSQL)
- Connection pooler to database

### 4. **patroni-net** (overlay, internal)
- Spilo ↔ etcd
- Patroni cluster coordination
- etcd client communication

---

## Docker Images

### ✅ Verified Available Images (2025)

1. **Spilo (Patroni + PostgreSQL):**
   - Image: `ghcr.io/zalando/spilo-17:4.0-p3`
   - Registry: GitHub Container Registry
   - Includes: PostgreSQL 17, Patroni 3.x, Barman, WAL-G
   - Status: ✅ Actively maintained

2. **etcd:**
   - Image: `bitnami/etcd:latest`
   - Registry: Docker Hub
   - Status: ⚠️ Available but migrating to paid model (Aug 2025)
   - Alternative: github etcd uses gcr.io/etcd-development/etcd as a primary container registry, and quay.io/coreos/etcd as secondary. VER=v3.6.6

3. **PgBouncer:**
   - Image: `pgbouncer/pgbouncer:latest`
   - Registry: Docker Hub (official namespace)
   - Status: ✅ Actively maintained
   - Alternative: `bitnami/pgbouncer:latest`

4. **HAProxy:**
   - Image: `haproxy:3.3-alpine`
   - Registry: Docker Hub (Official Image)
   - Status: ✅ Actively maintained
   - Latest version: 3.3 (Nov 2025)

---

## Docker Stack Compose File Structure

```yaml
version: '3.8'

services:
  # etcd cluster (3 nodes)
  etcd-node1:
    image: bitnami/etcd:latest
    # ... configuration

  etcd-node2:
    image: bitnami/etcd:latest
    # ... configuration

  etcd-node3:
    image: bitnami/etcd:latest
    # ... configuration

  # Spilo (Patroni + PostgreSQL) cluster (3 nodes)
  spilo-node1:
    image: ghcr.io/zalando/spilo-17:4.0-p3
    # ... configuration

  spilo-node2:
    image: ghcr.io/zalando/spilo-17:4.0-p3
    # ... configuration

  spilo-node3:
    image: ghcr.io/zalando/spilo-17:4.0-p3
    # ... configuration

  # PgBouncer (3 instances, global mode)
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    deploy:
      mode: global
    # ... configuration

  # HAProxy (3 instances, global mode)
  haproxy:
    image: haproxy:3.3-alpine
    deploy:
      mode: global
    # ... configuration

networks:
  saasodoo-network:
    external: true  # Your existing network
  db-frontend:
    driver: overlay
    internal: true
  db-backend:
    driver: overlay
    internal: true
  patroni-net:
    driver: overlay
    internal: true

configs:
  haproxy_cfg:
    file: ./configs/haproxy.cfg
  pgbouncer_ini:
    file: ./configs/pgbouncer.ini
```

---

## Node Placement Strategy

### Placement Constraints:

**Purpose:** Pin specific services to specific servers

```yaml
# Server 1 (Manager)
docker node update --label-add etcd=node1 server1
docker node update --label-add patroni=node1 server1

# Server 2 (Worker)
docker node update --label-add etcd=node2 server2
docker node update --label-add patroni=node2 server2

# Server 3 (Worker)
docker node update --label-add etcd=node3 server3
docker node update --label-add patroni=node3 server3
```

**Why needed:**
- etcd nodes must stay on specific servers (cluster membership)
- Spilo nodes must stay on specific servers (data locality)
- PgBouncer/HAProxy can run anywhere (global mode)

---

## Storage Strategy

### Bind Mounts to Local Disk:

```bash
# On each server, create directories
mkdir -p /data/postgres/node1  # or node2, node3
mkdir -p /data/etcd/node1      # or node2, node3
chown -R 999:999 /data/postgres/  # PostgreSQL UID
chown -R 1001:1001 /data/etcd/    # Bitnami etcd UID
```

**In docker-compose:**
```yaml
spilo-node1:
  volumes:
    - /data/postgres/node1:/home/postgres/pgdata

etcd-node1:
  volumes:
    - /data/etcd/node1:/bitnami/etcd
```

**Why bind mounts, not volumes?**
- Explicit control over which server stores which data
- Easier backups (standard filesystem)
- Better performance (no volume driver overhead)
- Predictable location for troubleshooting

---

## Advantages

### ✅ Full Orchestration
- Docker Swarm manages everything
- Automatic container restart
- Automatic rescheduling (within constraints)
- Built-in service discovery (DNS)
- Declarative configuration (one YAML file)

### ✅ Consistency
- Everything is a container
- Same deployment method for all components
- Uniform logging (`docker service logs`)
- Uniform monitoring
- Single management interface

### ✅ Easy Updates
- `docker service update --image <new-image>`
- Rolling updates supported
- Easy rollback
- No SSH to individual servers needed

### ✅ Portability
- Can move to Kubernetes later (similar concepts)
- Can run on any Docker Swarm cluster
- Infrastructure as code (YAML)
- Easy to replicate environments (dev/staging/prod)

### ✅ Developer Friendly
- Local development matches production
- Docker Compose for local, Swarm for production
- Easy onboarding (just Docker knowledge)
- Modern tooling

---

## Disadvantages

### ❌ Image Dependencies
- Reliant on Docker Hub / GHCR availability
- Bitnami etcd changing model (Aug 2025)
- Must trust third-party images
- Image updates require testing

### ❌ Complexity
- More moving parts than bare metal
- Overlay network complexity
- Volume/bind mount management
- Placement constraints required

### ❌ Performance Overhead
- Container runtime overhead (~2-5%)
- Overlay network latency (~1-2ms)
- Volume mount overhead (if using volumes)
- More CPU/RAM used by Docker daemon

### ❌ Debugging Difficulty
- Harder to troubleshoot container issues
- Logs in Docker (not journalctl)
- Can't easily `strace` PostgreSQL
- Network debugging more complex

### ❌ Storage Management
- Bind mounts tied to specific servers
- Volume management complexity
- Data migration requires manual steps
- Backup strategy more complex

---

## Deployment Process

### Phase 1: Prepare Servers
```bash
# On all servers
mkdir -p /data/{postgres,etcd}/node{1,2,3}
chown -R 999:999 /data/postgres
chown -R 1001:1001 /data/etcd
```

### Phase 2: Initialize Swarm
```bash
# On Server 1 (manager)
docker swarm init --advertise-addr <IP>

# On Server 2, 3
docker swarm join --token <TOKEN> <IP>:2377
```

### Phase 3: Label Nodes
```bash
docker node update --label-add etcd=node1 --label-add patroni=node1 server1
docker node update --label-add etcd=node2 --label-add patroni=node2 server2
docker node update --label-add etcd=node3 --label-add patroni=node3 server3
```

### Phase 4: Deploy Stack
```bash
# Single command deploys everything
docker stack deploy -c docker-compose.patroni.yml postgres-ha
```

### Phase 5: Monitor Bootstrap
```bash
# Watch services come up
watch docker service ls

# Check Spilo logs
docker service logs -f postgres-ha_spilo-node1

# Verify Patroni cluster
docker exec $(docker ps -q -f name=spilo-node1) patronictl list
```

---

## Bootstrap Process

### Automatic Initialization:

**What happens when you deploy:**

1. **etcd nodes start** (30-60 seconds)
   - Form cluster automatically
   - Establish quorum

2. **Spilo nodes start** (waiting for etcd)
   - Connect to etcd
   - Race for leader lock
   - First to acquire = PRIMARY

3. **PRIMARY bootstraps** (2-3 minutes)
   - Runs `initdb`
   - Configures replication
   - Starts PostgreSQL
   - Registers in etcd

4. **REPLICAs join** (2-5 minutes each)
   - See leader in etcd
   - Run `pg_basebackup` from PRIMARY
   - Start PostgreSQL in replica mode
   - Begin streaming replication

5. **PgBouncer/HAProxy start** (10-20 seconds)
   - Connect to PostgreSQL cluster
   - Begin accepting connections

**Total bootstrap time: ~5-10 minutes**

---

## Configuration Management

### Using Docker Configs:

```yaml
configs:
  haproxy_cfg:
    file: ./configs/haproxy.cfg
  pgbouncer_ini:
    file: ./configs/pgbouncer.ini

services:
  haproxy:
    configs:
      - source: haproxy_cfg
        target: /usr/local/etc/haproxy/haproxy.cfg
```

**Benefits:**
- Configs versioned with stack
- Immutable (read-only in containers)
- Updated by redeploying stack
- No need to SSH to servers

---

## Failover Behavior

### Container Failure:
```
1. Spilo container (PRIMARY) crashes
   ↓
2. Docker Swarm tries to restart it (10s)
   ↓
3. If restart fails, Patroni detects via etcd
   ↓
4. Patroni promotes REPLICA automatically (10s)
   ↓
5. HAProxy detects new PRIMARY (2s)
   ↓
Total downtime: ~22 seconds
```

### Server Failure:
```
1. Server 1 dies (PRIMARY)
   ↓
2. Docker Swarm marks server as down (30s)
   ↓
3. Patroni detects missing heartbeat (10s)
   ↓
4. Patroni promotes REPLICA on Server 2 (10s)
   ↓
5. HAProxy detects new PRIMARY (2s)
   ↓
6. Docker Swarm tries to reschedule Spilo-node1
   ↓
7. BLOCKED by placement constraint (node.labels.patroni==node1)
   ↓
8. Cluster runs with 2 nodes until Server 1 recovers
   ↓
Total downtime: ~22 seconds
```

**Key Point:** Placement constraints prevent data directory conflicts!

---

## Management Commands

### Service Management:
```bash
# List services
docker service ls

# Scale services (not applicable for Spilo/etcd)
docker service scale postgres-ha_pgbouncer=3

# Update image
docker service update --image haproxy:3.4-alpine postgres-ha_haproxy

# View logs
docker service logs -f postgres-ha_spilo-node1
docker service logs -f postgres-ha_haproxy

# Inspect service
docker service inspect postgres-ha_spilo-node1
```

### Patroni Operations:
```bash
# Access Spilo container
docker exec -it $(docker ps -q -f name=spilo-node1) bash

# Inside container:
patronictl list
patronictl failover
patronictl restart postgres-ha-cluster spilo-node1
```

### PostgreSQL Operations:
```bash
# Connect to PRIMARY
docker exec -it $(docker ps -q -f name=spilo-node1) \
  psql -U postgres

# Check replication
docker exec -it $(docker ps -q -f name=spilo-node1) \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"
```

---

## Monitoring

### Service Health:
```bash
# All services
docker service ls

# Specific service health
docker service ps postgres-ha_spilo-node1 --no-trunc

# Logs
docker service logs postgres-ha_spilo-node1 --since 10m
```

### Patroni REST API:
```bash
# Get Spilo container IP
SPILO_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
  $(docker ps -q -f name=spilo-node1))

# Health checks
curl http://$SPILO_IP:8008/health
curl http://$SPILO_IP:8008/master  # 200 if PRIMARY
```

### HAProxy Stats:
```bash
# Access stats UI
# Visit: http://any-server-ip:7000/stats
```

---

## Use Cases

### ✅ Perfect For:

**Scenario 1: Container-First Organization**
- Everything already in Docker/Kubernetes
- Team familiar with container orchestration
- Modern DevOps practices

**Scenario 2: Multi-Environment Needs**
- Need dev/staging/prod parity
- Frequent environment creation
- Infrastructure as code

**Scenario 3: Cloud-Native Migration**
- Planning Kubernetes migration
- Want Docker Swarm as stepping stone
- Need portable infrastructure

**Scenario 4: Rapid Iteration**
- Frequent updates and changes
- Need easy rollback
- Experimentation encouraged

### ❌ Not Ideal For:

- Production environments with zero Docker expertise
- Maximum performance requirements
- Highly regulated industries (prefer bare metal)
- Environments with no container infrastructure

---

## Estimated Setup Time

**Complete 3-Server Cluster:**
- Swarm initialization: 30 minutes
- Storage preparation: 30 minutes
- Node labeling: 15 minutes
- Stack deployment: 10 minutes
- Bootstrap wait time: 10 minutes
- Testing & validation: 1 hour
- **Total: ~3 hours**

**Much faster than systemd (9 hours) because:**
- No per-server package installation
- No individual service configuration
- One command deploys everything
- Automatic bootstrap

---

## Cost Analysis

### Software:
- All open source: $0

### Infrastructure:
- 3 servers (your existing)
- Docker Engine: FREE
- Docker Swarm: FREE

### Operations:
- Need Docker/container expertise
- Monitoring via Docker tools
- Single update path (docker service update)

---

## Migration Paths

### From Pure systemd:
```
1. Install Docker on all servers
2. Initialize Swarm
3. Dump systemd PostgreSQL data
4. Deploy Docker stack
5. Restore data to Spilo
6. Update application connections
7. Decommission systemd services
```

### To Kubernetes:
```
1. Set up Kubernetes cluster
2. Deploy PostgreSQL Operator (Zalando/Crunchy)
3. Create PostgreSQL cluster in K8s
4. Set up replication from Swarm to K8s
5. Cutover applications
6. Decommission Swarm cluster
```

---

## Next Steps

See the following files:
- **`docker-compose.patroni.yml`** - Complete stack definition
- **`configs/`** - HAProxy and PgBouncer configs
- **`SWARM_DEPLOYMENT_GUIDE.md`** - Step-by-step instructions
- **`SWARM_TROUBLESHOOTING.md`** - Common issues

---

## Summary

**Option C (Pure Docker Swarm)** is the most modern, container-first approach. Everything runs in Docker containers orchestrated by Swarm, providing full automation, easy updates, and infrastructure portability.

**Best for:** Container-first organizations, cloud-native environments, teams with Docker expertise, and scenarios requiring frequent updates and easy scaling.

**Trade-off:** Relies on Docker image availability, adds container runtime overhead, and requires Docker/Swarm expertise. Less suitable for maximum performance or traditional bare-metal operations.
