# High Availability PostgreSQL Architecture for SaaSOdoo
## Patroni-based HA with Local Storage

---

## Overview

This document describes the production-ready High Availability PostgreSQL architecture for SaaSOdoo using Patroni for automatic failover, PgBouncer for connection pooling, and HAProxy for intelligent load balancing. **PostgreSQL data is stored on local fast disks (SSD/NVMe) on each server, NOT on CephFS.**

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          APPLICATION LAYER                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ user-service │  │billing-svc   │  │instance-svc  │  │ Odoo         │   │
│  │              │  │              │  │              │  │ Instances    │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │                 │            │
└─────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
          │                 │                 │                 │
          └─────────────────┴─────────────────┴─────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │          HAProxy               │
                    │    (Load Balancer Layer)       │
                    │                                │
                    │  Port 5432 → PRIMARY (Writes)  │
                    │  Port 5433 → REPLICAS (Reads)  │
                    │  Port 7000 → Stats Dashboard   │
                    │                                │
                    │  - Health checks every 2s      │
                    │  - Automatic primary detection │
                    │  - Read/Write splitting        │
                    └───────────────┬────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          │                         │                         │
┌─────────▼─────────┐    ┌──────────▼─────────┐   ┌─────────▼──────────┐
│   PgBouncer-1     │    │   PgBouncer-2      │   │   PgBouncer-3      │
│  (Server 1)       │    │  (Server 2)        │   │  (Server 3)        │
│                   │    │                    │   │                    │
│ - Port: 6432      │    │ - Port: 6432       │   │ - Port: 6432       │
│ - Pool: 10K conn  │    │ - Pool: 10K conn   │   │ - Pool: 10K conn   │
│ - Mode: txn       │    │ - Mode: txn        │   │ - Mode: txn        │
│                   │    │                    │   │                    │
└─────────┬─────────┘    └──────────┬─────────┘   └─────────┬──────────┘
          │                         │                        │
          │                         │                        │
┌─────────▼─────────┐    ┌──────────▼─────────┐   ┌─────────▼──────────┐
│   Patroni-1       │◄───┤   Patroni-2        │◄──┤   Patroni-3        │
│   (Server 1)      │    │   (Server 2)       │   │   (Server 3)       │
│                   │───►│                    │──►│                    │
│  Status: PRIMARY  │    │  Status: REPLICA   │   │  Status: REPLICA   │
│  Role: LEADER     │    │  Role: STANDBY     │   │  Role: STANDBY     │
│                   │    │                    │   │                    │
│  REST API: 8008   │    │  REST API: 8008    │   │  REST API: 8008    │
│                   │    │                    │   │                    │
└─────────┬─────────┘    └──────────┬─────────┘   └─────────┬──────────┘
          │                         │                        │
          │                         │                        │
┌─────────▼─────────┐    ┌──────────▼─────────┐   ┌─────────▼──────────┐
│  PostgreSQL 15    │    │  PostgreSQL 15     │   │  PostgreSQL 15     │
│   (Server 1)      │    │   (Server 2)       │   │   (Server 3)       │
│                   │    │                    │   │                    │
│  Port: 5432       │◄───┤  Port: 5432        │◄──┤  Port: 5432        │
│  Accepts: WRITES  │────┤  Accepts: READS    │───┤  Accepts: READS    │
│                   │    │                    │   │                    │
│  Streaming Repl ──┼───►│  Replication       │   │  Replication       │
│  WAL Sender       │    │  WAL Receiver      │   │  WAL Receiver      │
│                   │    │                    │   │                    │
└─────────┬─────────┘    └──────────┬─────────┘   └─────────┬──────────┘
          │                         │                        │
          │                         │                        │
          │      LOCAL DISK         │      LOCAL DISK        │      LOCAL DISK
          │      (SSD/NVMe)         │      (SSD/NVMe)        │      (SSD/NVMe)
          │                         │                        │
          │   /var/lib/postgresql/  │   /var/lib/postgresql/ │   /var/lib/postgresql/
          │         data/           │         data/          │         data/
          │                         │                        │
          └─────────────────────────┴────────────────────────┘
                                    │
                                    │
          ┌─────────────────────────┴────────────────────────┐
          │                                                   │
          │              CONSENSUS LAYER                      │
          │                                                   │
          │    ┌──────────┐  ┌──────────┐  ┌──────────┐     │
          │    │  etcd-1  │  │  etcd-2  │  │  etcd-3  │     │
          │    │ (Server1)│  │ (Server2)│  │ (Server3)│     │
          │    │          │  │          │  │          │     │
          │    │Port: 2379│  │Port: 2379│  │Port: 2379│     │
          │    │          │  │          │  │          │     │
          │    │ Stores:  │  │ Stores:  │  │ Stores:  │     │
          │    │ - Leader │  │ - Leader │  │ - Leader │     │
          │    │ - Config │  │ - Config │  │ - Config │     │
          │    │ - State  │  │ - State  │  │ - State  │     │
          │    └────┬─────┘  └────┬─────┘  └────┬─────┘     │
          │         └──────────────┴─────────────┘           │
          │              Raft Consensus Protocol             │
          └───────────────────────────────────────────────────┘
                                    │
                                    │
                    ┌───────────────▼────────────────┐
                    │         CephFS (Optional)      │
                    │      /mnt/cephfs/postgres/     │
                    │                                │
                    │  Used ONLY for:                │
                    │  - WAL Archives (backups)      │
                    │  - pg_dump backups             │
                    │  - Point-in-time recovery      │
                    │                                │
                    │  NOT used for live data        │
                    └────────────────────────────────┘
```

---

## Component Breakdown

### 1. Application Layer
**Services:**
- user-service (port 8001)
- billing-service (port 8004)
- instance-service (port 8003)
- notification-service (port 5000)
- Odoo instances (dynamic ports)

**Connection Strategy:**
```python
# Write operations (INSERT, UPDATE, DELETE, CREATE DATABASE)
DATABASE_WRITE_URL = "postgresql://haproxy:5432/database_name"

# Read operations (SELECT, reports, dashboards)
DATABASE_READ_URL = "postgresql://haproxy:5433/database_name"
```

---

### 2. HAProxy - Load Balancer & Routing Layer

**Purpose:**
- Intelligent routing based on operation type (read vs write)
- Automatic detection of current PRIMARY node
- Health checking every 2 seconds
- Connection limiting and queueing

**Ports:**
- **5432** → Routes WRITE queries to PRIMARY only
- **5433** → Routes READ queries to ALL replicas (round-robin)
- **7000** → Statistics dashboard (web UI)

**Health Check Mechanism:**
```bash
# Checks Patroni REST API to determine role
GET http://patroni-node:8008/master    # Returns 200 if PRIMARY
GET http://patroni-node:8008/replica   # Returns 200 if REPLICA
```

**Configuration:**
- Max connections: 10,000 per backend
- Connection timeout: 5 seconds
- Health check interval: 2 seconds
- Failover detection: < 10 seconds

---

### 3. PgBouncer - Connection Pooling Layer

**Purpose:**
- Handle thousands of client connections with minimal PostgreSQL connections
- Connection reuse (reduces overhead)
- Transaction-level pooling

**Why 3 Instances (one per server)?**
- Reduces single point of failure
- HAProxy distributes load across all 3 PgBouncers
- Each PgBouncer manages its local PostgreSQL connection

**Configuration per Instance:**
```ini
[pgbouncer]
pool_mode = transaction              # Most efficient for web apps
max_client_conn = 10000              # Can handle 10K client connections
default_pool_size = 25               # But only use 25 PostgreSQL connections
reserve_pool_size = 5                # Emergency reserve
server_idle_timeout = 600            # 10 minutes
```

**Math:**
- Client connections: 10,000 (from all services)
- PostgreSQL connections: 75 (25 per PgBouncer × 3)
- Efficiency: 133:1 ratio

---

### 4. Patroni - PostgreSQL High Availability Manager

**Purpose:**
- Automatic failover (no manual intervention)
- Leader election using etcd
- Streaming replication management
- Split-brain prevention

**Roles:**

#### PRIMARY (LEADER)
- **Server:** Node elected as leader by etcd
- **State:** Read-write
- **Connections:** Accepts all writes
- **Replication:** Streams WAL to replicas
- **Promotion:** Elected by etcd consensus

#### REPLICA (STANDBY)
- **Server:** All other nodes
- **State:** Read-only
- **Connections:** Accepts reads only
- **Replication:** Receives WAL from primary
- **Promotion:** Can become PRIMARY if leader fails

**Patroni REST API (port 8008):**
```bash
# Check cluster status
GET /cluster

# Check if this node is primary
GET /master       # Returns 200 if primary, 503 if not

# Check if this node is replica
GET /replica      # Returns 200 if replica, 503 if not

# Health check
GET /health       # Returns node health status
```

**Failover Process:**
```
1. Primary fails (Patroni detects missed heartbeat after 10s)
2. etcd marks primary as unavailable
3. Patroni triggers leader election
4. Replica with least lag is promoted (5-10s)
5. Other replicas automatically follow new primary
6. HAProxy detects new primary via health checks (2s)
7. Total downtime: 15-30 seconds
```

---

### 5. PostgreSQL - Database Server

**Version:** PostgreSQL 15 (official Docker image)

**Storage Strategy:**
```
Server 1: /var/lib/postgresql/data → Local SSD/NVMe
Server 2: /var/lib/postgresql/data → Local SSD/NVMe
Server 3: /var/lib/postgresql/data → Local SSD/NVMe
```

**Replication Configuration:**

**PRIMARY Settings:**
```ini
# postgresql.conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
hot_standby = on
archive_mode = on
archive_command = 'cp %p /mnt/cephfs/postgres/wal_archive/%f'
```

**REPLICA Settings:**
```ini
# postgresql.conf (same as primary)
hot_standby = on
hot_standby_feedback = on
```

**Replication Slots:**
- Patroni automatically manages replication slots
- One slot per replica
- Prevents WAL deletion before replica catches up

**Streaming Replication:**
```
PRIMARY → REPLICA1: Asynchronous streaming (< 100ms lag typical)
PRIMARY → REPLICA2: Asynchronous streaming (< 100ms lag typical)
```

---

### 6. etcd - Distributed Consensus Layer

**Purpose:**
- Store cluster state (who is primary?)
- Leader election for Patroni
- Distributed configuration store
- Prevent split-brain scenarios

**Why 3 Nodes?**
- Quorum requires (N/2) + 1 = 2 nodes minimum
- Tolerates 1 node failure
- Odd number prevents split votes

**Data Stored:**
```json
{
  "/service/saasodoo-cluster/leader": "patroni-node1",
  "/service/saasodoo-cluster/members/patroni-node1": {
    "role": "master",
    "state": "running",
    "timeline": 1
  },
  "/service/saasodoo-cluster/members/patroni-node2": {
    "role": "replica",
    "state": "running",
    "timeline": 1
  }
}
```

**Ports:**
- **2379** → Client API (Patroni connects here)
- **2380** → Peer communication (etcd cluster sync)

**Network Requirements:**
- Low latency between nodes (< 10ms recommended)
- Consistent connectivity (avoid NAT/firewalls between etcd nodes)

---

### 7. CephFS - Backup Storage Only

**Role:** Archive and backup storage (NOT live data)

**What's stored on CephFS:**
```
/mnt/cephfs/postgres/
├── wal_archive/           # WAL files for point-in-time recovery
│   ├── 000000010000000000000001
│   ├── 000000010000000000000002
│   └── ...
├── backups/               # pg_dump backups
│   ├── daily/
│   ├── weekly/
│   └── monthly/
└── basebackups/           # pg_basebackup files
    └── 2025-11-14/
```

**Why NOT use CephFS for live data?**
- ❌ Network latency (adds 5-20ms to every query)
- ❌ Single writer limitation (PostgreSQL needs exclusive access)
- ❌ IOPS limitations compared to local NVMe
- ❌ PostgreSQL fsync() performance issues over network FS

**Benefits of local storage:**
- ✅ 10-100x faster IOPS
- ✅ Sub-millisecond latency
- ✅ No network overhead
- ✅ Better PostgreSQL performance

---

## Network Architecture

### Networks:

1. **saasodoo-network** (overlay, attachable)
   - Application services ↔ HAProxy
   - Public-facing network

2. **patroni-internal** (overlay, internal)
   - Patroni ↔ etcd communication
   - PostgreSQL ↔ Patroni REST API
   - No external access

3. **pgbouncer-backend** (overlay, internal)
   - PgBouncer ↔ PostgreSQL connections
   - No external access

### Security:
- Application layer ONLY sees HAProxy
- PostgreSQL ports NOT exposed to external network
- etcd NOT accessible from outside cluster
- PgBouncer isolated to backend network

---

## Performance Characteristics

### Throughput:
- **Single node capacity:** ~10,000 TPS (transactions per second)
- **Read scalability:** 3x (reads distributed across 3 nodes)
- **Write capacity:** Same as single node (writes go to PRIMARY only)

### Latency:
- **Read queries:** 1-5ms (local node)
- **Write queries:** 2-10ms (must go to PRIMARY)
- **Replication lag:** < 100ms typical, < 1s worst case

### Connection Capacity:
- **Without PgBouncer:** 300-500 connections max
- **With PgBouncer:** 10,000+ connections supported
- **SaaSOdoo requirement:** ~1,000 connections (5 services + 100 Odoo instances)

### Failover Time:
- **Detection:** 10 seconds (Patroni heartbeat timeout)
- **Election:** 5-10 seconds (etcd consensus)
- **Promotion:** 2-5 seconds (pg_ctl promote)
- **HAProxy detection:** 2 seconds (health check interval)
- **Total downtime:** 15-30 seconds

---

## Failure Scenarios

### Scenario 1: PRIMARY PostgreSQL crashes
```
1. Patroni detects failure (10s)
2. etcd triggers leader election
3. REPLICA with least lag promoted (10s)
4. HAProxy detects new primary (2s)
5. Applications resume writes
Total: ~22 seconds downtime
```

### Scenario 2: Server 1 (PRIMARY) dies completely
```
1. Patroni on Server1 stops responding (10s)
2. etcd declares Server1 dead
3. Patroni on Server2 or Server3 promoted (10s)
4. HAProxy reroutes traffic (2s)
5. Applications continue
Total: ~22 seconds downtime
```

### Scenario 3: etcd node fails (1 of 3)
```
1. etcd cluster still has quorum (2 of 3 nodes)
2. Patroni continues normal operation
3. No downtime
4. Failed etcd node can rejoin later
```

### Scenario 4: etcd cluster loses quorum (2 of 3 fail)
```
1. Patroni cannot determine leader
2. PRIMARY continues serving (does NOT stop)
3. Failover BLOCKED until etcd quorum restored
4. Manual intervention required
```

### Scenario 5: Network partition (split-brain)
```
1. etcd detects partition
2. Partition with quorum keeps PRIMARY
3. Partition without quorum = all nodes become read-only
4. Split-brain prevented ✅
```

---

## Monitoring & Observability

### Key Metrics to Monitor:

**PostgreSQL:**
- Replication lag (should be < 1 second)
- Connection count per database
- Transaction rate (TPS)
- Query performance (slow queries)
- WAL generation rate

**Patroni:**
- Cluster state (healthy/degraded)
- Leader election events
- Failover count
- Replication status

**PgBouncer:**
- Active connections
- Waiting connections
- Pool utilization
- Transaction rate

**HAProxy:**
- Backend server status
- Request rate per backend
- Error rate
- Health check failures

**etcd:**
- Leader elections
- Latency between nodes
- Disk fsync duration

### Monitoring Endpoints:

```bash
# Patroni REST API
curl http://patroni-node1:8008/cluster
curl http://patroni-node1:8008/patroni

# HAProxy stats
http://haproxy:7000/stats

# PgBouncer stats
psql -h pgbouncer -p 6432 -U admin -d pgbouncer -c "SHOW STATS"

# PostgreSQL replication status
psql -h primary -c "SELECT * FROM pg_stat_replication"
```

---

## Backup Strategy

### 1. Continuous WAL Archiving
```bash
# Automatic via PostgreSQL archive_command
archive_command = 'cp %p /mnt/cephfs/postgres/wal_archive/%f'
```

### 2. Daily Base Backups
```bash
# Cron job on one of the replicas
0 2 * * * pg_basebackup -h replica -D /mnt/cephfs/postgres/basebackups/$(date +\%Y-\%m-\%d) -Ft -z -P
```

### 3. Logical Backups (per database)
```bash
# For critical platform databases
0 3 * * * pg_dump -h replica auth > /mnt/cephfs/postgres/backups/daily/auth-$(date +\%Y-\%m-\%d).sql
```

### Recovery Scenarios:

**Scenario A: Lost all 3 PostgreSQL nodes (disaster)**
```bash
# Restore from base backup + WAL archive
pg_basebackup restore + replay WAL files
Recovery time: 1-4 hours depending on size
```

**Scenario B: Corrupted database**
```bash
# Restore specific database from pg_dump
dropdb corrupted_db && createdb corrupted_db
psql corrupted_db < backup.sql
Recovery time: 5-30 minutes
```

**Scenario C: Accidental DELETE query**
```bash
# Point-in-time recovery using WAL
pg_restore with target time before DELETE
Recovery time: 30-60 minutes
```

---

## Cost-Benefit Analysis

### What You Get:
✅ 99.95%+ uptime (< 5 minutes downtime per month)
✅ Automatic failover (15-30 second recovery)
✅ Read scalability (3x read capacity)
✅ Zero data loss (synchronous replication optional)
✅ Load balancing across 3 servers
✅ Connection pooling (10,000+ connections)
✅ Point-in-time recovery capability

### What It Costs:
❌ Complexity (9 components vs 1 PostgreSQL)
❌ 3x hardware cost (3 servers vs 1)
❌ Operational overhead (monitoring, maintenance)
❌ Setup time (2-3 weeks to get right)
❌ Requires DevOps expertise

### When It's Worth It:
✅ 100+ paying customers
✅ Downtime = lost revenue
✅ Multi-tenant SaaS with SLAs
✅ Heavy database load
✅ Need read scalability

### When It's NOT Worth It:
❌ MVP/testing phase
❌ < 50 customers
❌ Single PostgreSQL can handle load
❌ Manual failover acceptable

---

## Next Steps

See the following files in this directory:

1. **`docker-compose.patroni.yml`** - Complete Docker Swarm stack definition
2. **`CONFIG_FILES.md`** - Configuration files for all components
3. **`DEPLOYMENT_GUIDE.md`** - Step-by-step deployment instructions
4. **`FAILOVER_PLAYBOOK.md`** - Manual and automatic failover procedures
5. **`MONITORING_GUIDE.md`** - Monitoring setup and dashboards
6. **`TROUBLESHOOTING.md`** - Common issues and solutions

---

## Summary

This architecture provides production-grade PostgreSQL High Availability for SaaSOdoo using:

- **Patroni** for automatic failover
- **etcd** for distributed consensus
- **PgBouncer** for connection pooling
- **HAProxy** for load balancing
- **Local SSD/NVMe storage** for performance
- **CephFS** for backups only

Expected uptime: **99.95%+** with automatic recovery in under 30 seconds.
