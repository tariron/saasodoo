# Option B: Hybrid - systemd Core + Docker Utilities
## Best of Both Worlds

---

## Overview

This deployment method uses **systemd for critical database components** (etcd, Patroni, PostgreSQL) and **Docker Swarm for utility services** (PgBouncer, HAProxy). This combines the stability of bare-metal deployment with the flexibility of container orchestration.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                              │
│                     (Docker Containers)                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ user-service │  │billing-svc   │  │instance-svc  │             │
│  │              │  │              │  │              │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                      │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
                            │ Docker overlay network (saasodoo-network)
                            │
╔═════════════════════════════════════════════════════════════════════╗
║               DOCKER SWARM LAYER (Utility Services)                 ║
╚═════════════════════════════════════════════════════════════════════╝
          │
          ┌─────────────────▼─────────────────┐
          │     HAProxy (Docker Service)      │
          │     Replicas: 3 (one per node)    │
          │                                   │
          │  Image: haproxy:3.3-alpine        │
          │  Port 5432 → PRIMARY (writes)     │
          │  Port 5433 → REPLICAS (reads)     │
          │  Port 7000 → Stats UI             │
          │                                   │
          │  Deploy mode: global              │
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
│ Mode: transaction │ │ Mode: trans.. │ │ Mode: trans.. │
│                   │ │               │ │               │
│ Connects to:      │ │ Connects to:  │ │ Connects to:  │
│ localhost:5432    │ │ localhost:5432│ │ localhost:5432│
│ (systemd layer)   │ │ (systemd...)  │ │ (systemd...)  │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
          │                   │                 │
          │ host network      │ host network    │ host network
          │ (talks to         │                 │
          │  systemd layer)   │                 │
          │                   │                 │
╔═════════▼═══════════════════▼═════════════════▼═════════════════════╗
║               SYSTEMD LAYER (Critical Database Core)                ║
╚═════════════════════════════════════════════════════════════════════╝
          │                   │                 │
┌─────────▼─────────┐ ┌───────▼───────┐ ┌───────▼───────┐
│   Patroni         │ │  Patroni      │ │  Patroni      │
│   (systemd)       │ │  (systemd)    │ │  (systemd)    │
│   Server 1        │ │  Server 2     │ │  Server 3     │
│                   │ │               │ │               │
│ Role: LEADER      │ │ Role: REPLICA │ │ Role: REPLICA │
│ REST API: 8008    │ │ REST API:8008 │ │ REST API:8008 │
│                   │ │               │ │               │
│ Service:          │ │ Service:      │ │ Service:      │
│ patroni.service   │ │ patroni.svc   │ │ patroni.svc   │
│                   │ │               │ │               │
│ Config:           │ │ Config:       │ │ Config:       │
│ /etc/patroni/     │ │ /etc/patroni/ │ │ /etc/patroni/ │
│ patroni.yml       │ │ patroni.yml   │ │ patroni.yml   │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
          │                   │                 │
┌─────────▼─────────┐ ┌───────▼───────┐ ┌───────▼───────┐
│  PostgreSQL 15    │ │ PostgreSQL 15 │ │ PostgreSQL 15 │
│  (systemd)        │ │ (systemd)     │ │ (systemd)     │
│  Server 1         │ │ Server 2      │ │ Server 3      │
│                   │ │               │ │               │
│ Port: 5432        │ │ Port: 5432    │ │ Port: 5432    │
│ Role: PRIMARY     │ │ Role: STANDBY │ │ Role: STANDBY │
│                   │ │               │ │               │
│ Managed by:       │ │ Managed by:   │ │ Managed by:   │
│ Patroni           │ │ Patroni       │ │ Patroni       │
│                   │ │               │ │               │
│ Data:             │ │ Data:         │ │ Data:         │
│ /var/lib/         │ │ /var/lib/     │ │ /var/lib/     │
│ postgresql/15/    │ │ postgresql/   │ │ postgresql/   │
│ main              │ │ 15/main       │ │ 15/main       │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
          │                   │                 │
          │   LOCAL DISK      │   LOCAL DISK    │   LOCAL DISK
          │   (ext4/xfs)      │   (ext4/xfs)    │   (ext4/xfs)
          │                   │                 │
          └───────────────────┴─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │        etcd Cluster               │
          │        (systemd)                  │
          │                                   │
          │  ┌────────┐  ┌────────┐  ┌────────┐
          │  │ etcd-1 │  │ etcd-2 │  │ etcd-3 │
          │  │ Server1│  │ Server2│  │ Server3│
          │  │        │  │        │  │        │
          │  │Port:   │  │Port:   │  │Port:   │
          │  │2379    │  │2379    │  │2379    │
          │  │2380    │  │2380    │  │2380    │
          │  │        │  │        │  │        │
          │  │Service:│  │Service:│  │Service:│
          │  │etcd.   │  │etcd.   │  │etcd.   │
          │  │service │  │service │  │service │
          │  │        │  │        │  │        │
          │  │Data:   │  │Data:   │  │Data:   │
          │  │/var/lib│  │/var/lib│  │/var/lib│
          │  │/etcd/  │  │/etcd/  │  │/etcd/  │
          │  └────────┘  └────────┘  └────────┘
          │                                   │
          └───────────────────────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │      CephFS (Optional)            │
          │      /mnt/cephfs/postgres/        │
          │                                   │
          │  - WAL archives                   │
          │  - Backups                        │
          └───────────────────────────────────┘
```

---

## Layer Separation

### **Systemd Layer** (Critical - Bare Metal)
```
Components:
├── etcd (consensus)
├── Patroni (HA manager)
└── PostgreSQL (database)

Why systemd:
✅ Maximum stability
✅ No Docker image dependencies
✅ Direct control over critical components
✅ Better performance (no container overhead)
✅ Easier troubleshooting for database issues
```

### **Docker Swarm Layer** (Utilities - Containers)
```
Components:
├── HAProxy (load balancer)
└── PgBouncer (connection pooler)

Why Docker:
✅ Easy deployment and updates
✅ Built-in service discovery
✅ Automatic restart and rescheduling
✅ Easy to replace/upgrade
✅ Less critical (can restart without data loss)
```

---

## The Integration Point

### How They Communicate:

**PgBouncer → PostgreSQL:**
```yaml
# PgBouncer runs in Docker with --network host
# This allows it to access localhost:5432 (systemd PostgreSQL)

pgbouncer:
  image: pgbouncer/pgbouncer
  network_mode: host  # ← Key: Access host network
  environment:
    DATABASE_URL: postgresql://localhost:5432/postgres
```

**HAProxy → Patroni:**
```yaml
# HAProxy health checks Patroni REST API on host
# Patroni runs on host (systemd) at localhost:8008

haproxy:
  image: haproxy:3.3-alpine
  network_mode: host  # ← Access Patroni on localhost:8008
  # HAProxy checks: http://localhost:8008/master
```

**Application → HAProxy:**
```yaml
# Applications connect to HAProxy via Docker overlay network
# HAProxy is exposed on the swarm network

user-service:
  environment:
    DATABASE_URL: postgresql://haproxy:5432/auth
  networks:
    - saasodoo-network  # ← Connects to HAProxy service
```

---

## Advantages

### ✅ Stability Where It Matters
- Critical database components on bare metal
- PostgreSQL performance not impacted by Docker
- etcd stability (no container restart issues)
- Patroni directly manages PostgreSQL (no Docker layer)

### ✅ Flexibility Where It Helps
- HAProxy easy to update (docker service update)
- PgBouncer easy to scale (docker service scale)
- Utility restarts don't affect database
- Easy rollback for utilities

### ✅ No Image Concerns for Database
- PostgreSQL, Patroni, etcd from OS packages
- Only HAProxy and PgBouncer use Docker images
- HAProxy is official and stable
- PgBouncer has multiple maintained options

### ✅ Best Performance
- PostgreSQL on bare metal (no volume overhead)
- Direct disk I/O
- No container network overhead for database
- PgBouncer and HAProxy are lightweight (container overhead minimal)

### ✅ Easier Operations
- Database troubleshooting uses standard Linux tools
- Docker only for utilities (simpler)
- Clear separation of concerns
- systemd for critical, Docker for convenience

### ✅ Gradual Migration Path
- Start with systemd database cluster
- Add Docker utilities later
- Or vice versa: migrate utilities to Docker first
- Easy to change your mind

---

## Disadvantages

### ❌ Two Management Paradigms
- systemd commands for database layer
- docker commands for utility layer
- Need to know both systems
- Different logging mechanisms

### ❌ Network Complexity
- Docker containers need `host` network mode
- Or use complex network configurations
- Application → Docker → systemd path
- More potential points of failure

### ❌ Setup Complexity
- Must set up both systemd and Docker Swarm
- More configuration files
- More moving parts
- Requires understanding of both systems

### ❌ Monitoring Complexity
- systemd services: `journalctl`
- Docker services: `docker service logs`
- Need to monitor two layers
- Different health check mechanisms

---

## Installation Process

### Phase 1: Initialize Docker Swarm
```bash
# On Server 1 (manager)
docker swarm init --advertise-addr <SERVER1_IP>

# On Server 2 and 3
docker swarm join --token <TOKEN> <SERVER1_IP>:2377
```

### Phase 2: Install systemd Layer (All Servers)
```bash
# On each server
apt install -y postgresql-15 etcd python3-pip
pip3 install patroni[etcd]

# Configure etcd
./scripts/configure-etcd.sh

# Configure Patroni
./scripts/configure-patroni.sh

# Start services
systemctl start etcd
systemctl start patroni
```

### Phase 3: Deploy Docker Layer (Manager)
```bash
# From manager node
docker stack deploy -c docker-compose.utilities.yml db-utils
```

### Phase 4: Verify
```bash
# Check systemd layer
patronictl -c /etc/patroni/patroni.yml list
systemctl status patroni

# Check Docker layer
docker service ls
docker service ps db-utils_haproxy
docker service ps db-utils_pgbouncer
```

---

## File Structure

```
Server 1, 2, 3:

├── /etc/                              # systemd layer config
│   ├── default/etcd
│   ├── patroni/patroni.yml
│   └── systemd/system/patroni.service
│
├── /var/lib/                          # systemd layer data
│   ├── etcd/
│   └── postgresql/15/main/
│
└── infrastructure/HAPostgres/         # Docker layer config
    ├── docker-compose.utilities.yml   # HAProxy + PgBouncer
    ├── configs/
    │   ├── haproxy.cfg
    │   └── pgbouncer.ini
    └── scripts/
        ├── 1-install-systemd-layer.sh
        ├── 2-deploy-docker-layer.sh
        └── 3-verify-integration.sh
```

---

## Docker Compose for Utilities Layer

```yaml
version: '3.8'

services:
  # PgBouncer - Connection Pooling
  pgbouncer:
    image: pgbouncer/pgbouncer:latest
    network_mode: host  # Access systemd PostgreSQL on localhost
    environment:
      DATABASE_URL: postgresql://postgres:password@localhost:5432/postgres
      POOL_MODE: transaction
      MAX_CLIENT_CONN: 10000
      DEFAULT_POOL_SIZE: 25
    volumes:
      - ./configs/pgbouncer.ini:/etc/pgbouncer/pgbouncer.ini:ro
    deploy:
      mode: global  # One per server
      restart_policy:
        condition: any
        delay: 5s

  # HAProxy - Load Balancing
  haproxy:
    image: haproxy:3.3-alpine
    network_mode: host  # Access Patroni REST API on localhost
    volumes:
      - ./configs/haproxy.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    deploy:
      mode: global  # One per server
      restart_policy:
        condition: any
        delay: 5s
```

---

## Use Cases

### ✅ Perfect For:

**Scenario 1: Existing systemd PostgreSQL**
- You already have PostgreSQL on systemd
- Want to add HA without full Docker migration
- Gradual modernization approach

**Scenario 2: Risk-Averse Migration**
- Want to try containers without affecting database
- Keep database on stable systemd
- Containerize utilities first

**Scenario 3: Performance-Critical Workloads**
- Need maximum database performance
- But want orchestration for utilities
- Best of both worlds

**Scenario 4: Mixed Infrastructure**
- Some services in Docker (your microservices)
- Some on systemd (legacy/critical)
- Need them to work together

### ❌ Not Ideal For:

- Pure container environments
- Kubernetes migrations
- Minimal operational complexity requirement
- Small teams (two systems to manage)

---

## Failover Behavior

### Database Layer (systemd):
```
1. PRIMARY PostgreSQL dies (systemd)
2. Patroni detects and triggers failover
3. New PRIMARY promoted (systemd)
4. Automatic - NO Docker involvement
5. Downtime: ~22 seconds
```

### Utility Layer (Docker):
```
1. PgBouncer container dies
2. Docker Swarm restarts it (~10s)
3. Connects to PostgreSQL (still running)
4. Minimal disruption

1. HAProxy container dies
2. Docker Swarm restarts it (~10s)
3. Re-detects Patroni PRIMARY
4. Routes traffic correctly
```

**Key Benefit:** Database failover is independent of Docker Swarm health!

---

## Management Commands

### systemd Layer:
```bash
# Patroni
patronictl -c /etc/patroni/patroni.yml list
systemctl restart patroni

# PostgreSQL (via Patroni)
patronictl -c /etc/patroni/patroni.yml restart node1

# etcd
systemctl status etcd
etcdctl endpoint health
```

### Docker Layer:
```bash
# Services
docker service ls
docker service logs db-utils_haproxy
docker service scale db-utils_pgbouncer=3

# Update utilities
docker service update --image pgbouncer/pgbouncer:latest db-utils_pgbouncer
docker service update --image haproxy:3.3-alpine db-utils_haproxy
```

---

## Monitoring

### systemd Layer:
```bash
# Patroni
curl http://localhost:8008/health
patronictl list

# PostgreSQL
psql -h localhost -p 5432 -c "SELECT * FROM pg_stat_replication;"

# Logs
journalctl -u patroni -f
journalctl -u etcd -f
```

### Docker Layer:
```bash
# HAProxy
curl http://localhost:7000/stats
docker service logs db-utils_haproxy -f

# PgBouncer
psql -h localhost -p 6432 -U pgbouncer pgbouncer -c "SHOW STATS;"
docker service logs db-utils_pgbouncer -f
```

---

## Network Flow

```
┌──────────────────────────────────────────────┐
│ Application (Docker container)               │
│   DATABASE_URL=postgresql://haproxy:5432/db  │
└──────────────┬───────────────────────────────┘
               │ Docker overlay network
               ↓
┌──────────────────────────────────────────────┐
│ HAProxy (Docker, network_mode: host)         │
│   Listens on: 0.0.0.0:5432, 0.0.0.0:5433    │
└──────────────┬───────────────────────────────┘
               │ localhost (same host)
               ↓
┌──────────────────────────────────────────────┐
│ PgBouncer (Docker, network_mode: host)       │
│   Connects to: localhost:5432                │
└──────────────┬───────────────────────────────┘
               │ localhost (same host)
               ↓
┌──────────────────────────────────────────────┐
│ PostgreSQL (systemd)                         │
│   Listens on: 0.0.0.0:5432                   │
│   Managed by: Patroni (systemd)              │
└──────────────────────────────────────────────┘
```

---

## Estimated Setup Time

**Per Server:**
- systemd layer: 2 hours
- Docker Swarm init: 15 minutes
- Docker layer deployment: 30 minutes
- Integration testing: 45 minutes
- **Total per server: ~3.5 hours**

**Complete 3-Server Cluster:**
- systemd setup: 6 hours
- Docker setup: 2 hours
- Testing: 2 hours
- **Total: ~10 hours**

---

## Cost Analysis

### Software:
- All open source: $0

### Infrastructure:
- 3 servers (your existing)
- Docker Engine: FREE
- Docker Swarm: FREE (built into Docker)

### Operations:
- Need skills in both systemd AND Docker
- More complex monitoring setup
- Two update paths to manage

---

## Migration Paths

### From Pure systemd:
```
1. Install Docker Engine on all servers
2. Initialize Swarm
3. Deploy HAProxy + PgBouncer to Docker
4. Update application connections
5. Test
6. Remove systemd HAProxy/PgBouncer (if installed)
```

### From Pure Docker:
```
1. Set up systemd PostgreSQL cluster
2. Dump data from Docker PostgreSQL
3. Restore to systemd PostgreSQL
4. Keep HAProxy + PgBouncer in Docker
5. Update PgBouncer to connect to systemd PostgreSQL
6. Test
7. Remove Docker PostgreSQL
```

### To Pure Docker:
```
1. Deploy Spilo (Patroni + PostgreSQL) in Docker
2. Set up replication from systemd to Docker
3. Cutover
4. Remove systemd layer
```

---

## Next Steps

See the following files:
- **`docker-compose.utilities.yml`** - Docker Swarm stack for utilities
- **`systemd-configs/`** - systemd configuration templates
- **`HYBRID_DEPLOYMENT_GUIDE.md`** - Step-by-step instructions
- **`HYBRID_TROUBLESHOOTING.md`** - Integration issues

---

## Summary

**Option B (Hybrid)** combines systemd stability for the database core with Docker Swarm flexibility for utilities. It offers maximum database performance and stability while retaining container orchestration benefits for supporting services.

**Best for:** Organizations wanting gradual modernization, performance-critical database workloads, or mixed infrastructure environments.

**Trade-off:** More complex to set up and manage, but offers the best of both worlds for risk-averse deployments.
