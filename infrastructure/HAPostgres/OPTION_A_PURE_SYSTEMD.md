# Option A: Pure systemd - Bare Metal Deployment
## Zero Docker Dependencies

---

## Overview

This deployment method uses **NO Docker containers**. All components run as native Linux services managed by systemd. This is the most traditional, stable, and production-proven approach for PostgreSQL High Availability.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ user-service │  │billing-svc   │  │instance-svc  │             │
│  │ (Docker)     │  │ (Docker)     │  │ (Docker)     │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘             │
│         │                 │                 │                      │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          └─────────────────┴─────────────────┘
                            │
          ┌─────────────────▼─────────────────┐
          │         HAProxy (systemd)         │
          │       Server 1, 2, 3              │
          │                                   │
          │  - Port 5432 → PRIMARY (writes)  │
          │  - Port 5433 → REPLICAS (reads)  │
          │  - Port 7000 → Stats UI          │
          │                                   │
          │  Service: haproxy.service         │
          │  Config: /etc/haproxy/haproxy.cfg│
          └─────────────────┬─────────────────┘
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
┌─────────▼─────────┐ ┌─────▼─────────┐ ┌───▼───────────┐
│   PgBouncer       │ │  PgBouncer    │ │  PgBouncer    │
│   (systemd)       │ │  (systemd)    │ │  (systemd)    │
│   Server 1        │ │  Server 2     │ │  Server 3     │
│                   │ │               │ │               │
│ Port: 6432        │ │ Port: 6432    │ │ Port: 6432    │
│ Service:          │ │ Service:      │ │ Service:      │
│ pgbouncer.service │ │ pgbouncer...  │ │ pgbouncer...  │
│ Config:           │ │ Config:       │ │ Config:       │
│ /etc/pgbouncer/   │ │ /etc/pgb...   │ │ /etc/pgb...   │
└─────────┬─────────┘ └───────┬───────┘ └───────┬───────┘
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
│ patroni.service   │ │ patroni...    │ │ patroni...    │
│ Config:           │ │ Config:       │ │ Config:       │
│ /etc/patroni/     │ │ /etc/pat...   │ │ /etc/pat...   │
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
│ Service:          │ │ Service:      │ │ Service:      │
│ (managed by       │ │ (managed by   │ │ (managed by   │
│  Patroni)         │ │  Patroni)     │ │  Patroni)     │
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
          │                                   │
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
          │  │Config: │  │Config: │  │Config: │
          │  │/etc/   │  │/etc/   │  │/etc/   │
          │  │default/│  │default/│  │default/│
          │  │etcd    │  │etcd    │  │etcd    │
          │  └────────┘  └────────┘  └────────┘
          │                                   │
          │  Data: /var/lib/etcd/             │
          └───────────────────────────────────┘
                            │
                            │
          ┌─────────────────▼─────────────────┐
          │      CephFS (Optional)            │
          │      /mnt/cephfs/postgres/        │
          │                                   │
          │  - WAL archives (backups)         │
          │  - pg_dump backups                │
          │  - Point-in-time recovery         │
          └───────────────────────────────────┘
```

---

## Components

### 1. **etcd (Consensus Layer)**
- **What:** Distributed key-value store for cluster coordination
- **Installation:** OS package (`apt install etcd` or `yum install etcd`)
- **Service:** `etcd.service`
- **Configuration:** `/etc/default/etcd` or `/etc/etcd/etcd.conf`
- **Data:** `/var/lib/etcd/`
- **Ports:** 2379 (client), 2380 (peer)

### 2. **Patroni (HA Manager)**
- **What:** PostgreSQL cluster manager, handles failover
- **Installation:** Python package (`pip3 install patroni[etcd]`)
- **Service:** `patroni.service` (custom unit file)
- **Configuration:** `/etc/patroni/patroni.yml`
- **Logs:** `journalctl -u patroni -f`
- **REST API:** Port 8008

### 3. **PostgreSQL (Database)**
- **What:** PostgreSQL database server
- **Installation:** OS package (`apt install postgresql-15`)
- **Managed by:** Patroni (Patroni starts/stops PostgreSQL)
- **Configuration:** Managed by Patroni via `/etc/patroni/patroni.yml`
- **Data:** `/var/lib/postgresql/15/main/`
- **Port:** 5432

### 4. **PgBouncer (Connection Pooler)**
- **What:** Connection pooling to reduce PostgreSQL overhead
- **Installation:** OS package (`apt install pgbouncer`)
- **Service:** `pgbouncer.service`
- **Configuration:** `/etc/pgbouncer/pgbouncer.ini`
- **Port:** 6432

### 5. **HAProxy (Load Balancer)**
- **What:** Routes traffic to PRIMARY (writes) or REPLICAs (reads)
- **Installation:** OS package (`apt install haproxy`)
- **Service:** `haproxy.service`
- **Configuration:** `/etc/haproxy/haproxy.cfg`
- **Stats UI:** Port 7000
- **Ports:** 5432 (writes), 5433 (reads)

---

## Installation Method

### Package Sources

**Ubuntu/Debian:**
```bash
# Add PostgreSQL repository
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list

# Install all components
apt update
apt install -y \
    postgresql-15 \
    etcd \
    pgbouncer \
    haproxy \
    python3-pip \
    python3-psycopg2

# Install Patroni via pip
pip3 install patroni[etcd]
```

**RHEL/CentOS:**
```bash
# Add PostgreSQL repository
yum install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-8-x86_64/pgdg-redhat-repo-latest.noarch.rpm

# Install all components
yum install -y \
    postgresql15-server \
    etcd \
    pgbouncer \
    haproxy \
    python3-pip \
    python3-psycopg2

# Install Patroni
pip3 install patroni[etcd]
```

---

## Deployment Process

### Phase 1: Install Packages (All Servers)
```bash
# Run on Server 1, 2, 3
./scripts/1-install-packages.sh
```

### Phase 2: Configure etcd Cluster (All Servers)
```bash
# Run on each server with different NODE_NAME
./scripts/2-configure-etcd.sh NODE_NAME=etcd1 NODE_IP=192.168.1.10
```

### Phase 3: Configure Patroni (All Servers)
```bash
# Run on each server
./scripts/3-configure-patroni.sh NODE_NAME=node1 NODE_IP=192.168.1.10
```

### Phase 4: Start Services (All Servers)
```bash
# Start in order
systemctl start etcd
systemctl start patroni
systemctl start pgbouncer
systemctl start haproxy
```

### Phase 5: Verify Cluster
```bash
# Check Patroni cluster status
patronictl -c /etc/patroni/patroni.yml list

# Check etcd health
etcdctl endpoint health

# Test connectivity
psql -h localhost -p 5432 -U postgres
```

---

## File Structure

```
Server 1, 2, 3:
├── /etc/
│   ├── default/
│   │   └── etcd                          # etcd configuration
│   ├── patroni/
│   │   ├── patroni.yml                   # Patroni configuration
│   │   └── .pgpass                       # PostgreSQL passwords
│   ├── pgbouncer/
│   │   ├── pgbouncer.ini                 # PgBouncer configuration
│   │   └── userlist.txt                  # User authentication
│   ├── haproxy/
│   │   └── haproxy.cfg                   # HAProxy configuration
│   └── systemd/system/
│       └── patroni.service               # Patroni systemd unit
├── /var/lib/
│   ├── etcd/                             # etcd data
│   └── postgresql/15/main/               # PostgreSQL data
├── /var/log/
│   ├── postgresql/                       # PostgreSQL logs
│   ├── pgbouncer/                        # PgBouncer logs
│   └── haproxy.log                       # HAProxy logs
└── /usr/local/bin/
    └── patroni                           # Patroni binary (from pip)
```

---

## Advantages

### ✅ Maximum Stability
- No container runtime overhead
- Direct OS service management
- Standard Linux tooling
- Proven deployment method

### ✅ Zero Image Concerns
- All packages from official repositories
- No Docker Hub dependencies
- No deprecated images
- Predictable update path

### ✅ Performance
- No containerization overhead
- Direct disk I/O (no volume mounts)
- Native networking (no overlay networks)
- Full control over resource allocation

### ✅ Simplicity
- Standard systemd services
- Familiar Linux administration
- Standard logging (`journalctl`)
- Standard monitoring (systemd status)

### ✅ Security
- OS-level security updates
- No Docker daemon required
- Standard firewall rules (iptables/firewalld)
- SELinux/AppArmor support

### ✅ Operations
- Standard backup tools
- Standard monitoring (Nagios, Zabbix, etc.)
- Standard configuration management (Ansible, Chef, Puppet)
- Well-documented troubleshooting

---

## Disadvantages

### ❌ Manual Installation
- Must SSH to each server
- Run installation scripts on each
- More initial setup time
- Configuration files on each server

### ❌ No Orchestration
- systemd handles restarts on same server only
- If server dies, manual intervention required
- No automatic rescheduling to another server
- Must manually start services after reboot

### ❌ Updates
- Must update each server individually
- OS package updates require testing
- Patroni updates via pip (manual)
- Configuration drift risk

### ❌ Scaling
- Adding new nodes requires manual setup
- No declarative configuration
- More operational overhead

---

## Use Cases

### ✅ Perfect For:
- Traditional infrastructure teams
- Environments with no Docker
- Maximum stability requirements
- Long-term production deployments
- Regulated industries (banking, healthcare)
- Teams familiar with systemd/Linux administration

### ❌ Not Ideal For:
- Container-first environments
- Rapid scaling requirements
- Teams without Linux expertise
- Ephemeral infrastructure
- Frequent redeployments

---

## Failover Behavior

### Automatic Failover
```
1. PRIMARY (Server 1) dies
   ↓
2. Patroni on Server 1 stops heartbeat to etcd (10s)
   ↓
3. etcd declares Server 1 dead
   ↓
4. Patroni on Server 2 or 3 promoted automatically (10s)
   ↓
5. HAProxy detects new PRIMARY via health checks (2s)
   ↓
6. Total downtime: ~22 seconds
```

**Key Point:** Patroni handles automatic failover even with systemd deployment!

### Server Recovery
```
# When Server 1 comes back online:
systemctl start etcd
systemctl start patroni

# Patroni automatically:
# - Detects existing cluster
# - Joins as REPLICA
# - Syncs data from current PRIMARY
# - Becomes available for reads
```

---

## Management Commands

### Patroni Operations
```bash
# Check cluster status
patronictl -c /etc/patroni/patroni.yml list

# Manual failover
patronictl -c /etc/patroni/patroni.yml failover

# Restart PostgreSQL on a node
patronictl -c /etc/patroni/patroni.yml restart node1

# Reload configuration
patronictl -c /etc/patroni/patroni.yml reload node1
```

### Service Management
```bash
# Start/stop services
systemctl start patroni
systemctl stop patroni
systemctl restart pgbouncer
systemctl reload haproxy

# Check status
systemctl status patroni
systemctl status pgbouncer
systemctl status haproxy
systemctl status etcd

# View logs
journalctl -u patroni -f
journalctl -u pgbouncer -f
journalctl -u haproxy -f
```

### PostgreSQL Operations
```bash
# Connect to PRIMARY (writes)
psql -h localhost -p 5432 -U postgres

# Connect to REPLICA (reads) via HAProxy
psql -h localhost -p 5433 -U postgres

# Check replication status
psql -h localhost -p 5432 -U postgres -c "SELECT * FROM pg_stat_replication;"
```

---

## Monitoring

### Key Metrics

**Patroni:**
```bash
# REST API health check
curl http://localhost:8008/health
curl http://localhost:8008/master  # Returns 200 if PRIMARY
curl http://localhost:8008/replica # Returns 200 if REPLICA

# Cluster status
patronictl -c /etc/patroni/patroni.yml list
```

**PostgreSQL:**
```bash
# Replication lag
psql -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_lag;"

# Connection count
psql -c "SELECT count(*) FROM pg_stat_activity;"

# Database size
psql -c "SELECT pg_size_pretty(pg_database_size('postgres'));"
```

**PgBouncer:**
```bash
# Connection stats
psql -h localhost -p 6432 -U pgbouncer pgbouncer -c "SHOW STATS;"
psql -h localhost -p 6432 -U pgbouncer pgbouncer -c "SHOW POOLS;"
```

**HAProxy:**
```bash
# Stats page
curl http://localhost:7000/stats

# Backend status
echo "show stat" | socat stdio /var/run/haproxy.sock
```

---

## Backup Strategy

### Continuous WAL Archiving
```bash
# Configured in Patroni (patroni.yml)
archive_mode: on
archive_command: 'cp %p /mnt/cephfs/postgres/wal_archive/%f'
```

### Daily Base Backups
```bash
# Cron job on one REPLICA
0 2 * * * pg_basebackup -h localhost -D /backups/$(date +\%Y-\%m-\%d) -Ft -z -P
```

### Logical Backups
```bash
# Per-database dumps
0 3 * * * pg_dump -h localhost auth > /backups/auth-$(date +\%Y-\%m-\%d).sql
```

---

## Estimated Setup Time

**Per Server:**
- Installation: 30 minutes
- Configuration: 45 minutes
- Testing: 30 minutes
- **Total per server: ~2 hours**

**Complete 3-Server Cluster:**
- Setup: 6 hours
- Testing & validation: 2 hours
- Documentation: 1 hour
- **Total: ~9 hours**

---

## Cost Analysis

### Software Costs
- PostgreSQL: FREE (open source)
- Patroni: FREE (open source)
- etcd: FREE (open source)
- PgBouncer: FREE (open source)
- HAProxy: FREE (open source)
- **Total: $0**

### Operational Costs
- 3 servers (your existing infrastructure)
- No Docker licensing
- No orchestrator overhead
- Standard Linux administration

---

## Migration Path

### From Single PostgreSQL
```
1. Install Patroni on existing server (becomes Server 1)
2. Let Patroni manage existing PostgreSQL
3. Add Server 2 as replica
4. Add Server 3 as replica
5. Add PgBouncer + HAProxy
6. Update application connection strings
7. Test failover
```

### To Kubernetes (Future)
```
1. Deploy PostgreSQL Operator (Zalando/Crunchy)
2. Create logical dump of all databases
3. Restore to Kubernetes PostgreSQL
4. Cutover application connections
5. Decommission systemd cluster
```

---

## Next Steps

See the following files:
- **`systemd-configs/`** - All configuration templates
- **`systemd-scripts/`** - Installation and setup scripts
- **`SYSTEMD_DEPLOYMENT_GUIDE.md`** - Step-by-step instructions
- **`SYSTEMD_TROUBLESHOOTING.md`** - Common issues and solutions

---

## Summary

**Option A (Pure systemd)** is the most stable, traditional, and production-proven method for deploying PostgreSQL High Availability. It requires no Docker, uses standard OS packages, and is managed entirely through systemd.

**Best for:** Production environments, traditional infrastructure teams, maximum stability requirements, and long-term deployments.

**Trade-off:** More manual setup initially, but significantly more stable and easier to operate long-term.
