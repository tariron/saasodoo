# Patroni + Citus High-Availability PostgreSQL Cluster - Production Implementation Guide

**Version**: 2.0
**Last Updated**: 2025-12-02
**Official Versions**: PostgreSQL 17.7 | Patron 4.1.0 | Citus 13.0.1 | etcd 3.7

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Installation Procedure](#installation-procedure)
4. [Initial Cluster Setup (3 Nodes)](#initial-cluster-setup-3-nodes)
5. [Scaling: Adding New Nodes](#scaling-adding-new-nodes)
6. [Read/Write Splitting](#readwrite-splitting)
7. [Operations & Maintenance](#operations--maintenance)
8. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### Production Topology

```
┌────────────────────────────────────────────────────┐
│          HAProxy Load Balancer (Optional)          │
│         Primary: 10.0.0.50 | Backup: 10.0.0.51     │
│   Write Port: 5432 (Primary) | Read Port: 5433 (All)│
└─────────────────────┬──────────────────────────────┘
                      │
         ┌────────────┴────────────┬───────────────┐
         │                         │               │
┌────────▼────────┐   ┌───────────▼──────┐  ┌────▼──────────┐
│   Node 1 (pg1)  │   │  Node 2 (pg2)    │  │ Node 3 (pg3)  │
│   10.0.0.11     │   │   10.0.0.12      │  │  10.0.0.13    │
├─────────────────┤   ├──────────────────┤  ├───────────────┤
│ PostgreSQL 17   │   │ PostgreSQL 17    │  │ PostgreSQL 17 │
│ + Citus 13.0    │   │ + Citus 13.0     │  │ + Citus 13.0  │
│ + Patroni 4.1   │   │ + Patroni 4.1    │  │ + Patroni 4.1 │
│ + etcd 3.7      │   │ + etcd 3.7       │  │ + etcd 3.7    │
│   (Leader)      │   │  (Replica)       │  │  (Replica)    │
└─────────────────┘   └──────────────────┘  └───────────────┘
```

### Key Components

- **PostgreSQL 17.7**: Latest stable database (supports up to PG 18)
- **Patroni 4.1.0**: HA orchestration with automatic failover
- **Citus 13.0.1**: Distributed PostgreSQL extension (supports PG 16-17)
- **etcd 3.7**: Distributed configuration store (DCS)
- **HAProxy**: Load balancer for R/W splitting

---

## Prerequisites

### Hardware Requirements

| Component | Minimum (Dev) | Recommended (Prod) |
|-----------|---------------|-------------------|
| CPU | 4 cores | 8-16 cores |
| RAM | 8 GB | 16-32 GB |
| Disk | 200 GB SSD | 500 GB NVMe SSD |
| Network | 1 Gbps | 10 Gbps |

### Operating System

- **Supported**: Ubuntu 22.04 LTS (recommended), Debian 12, Rocky Linux 9
- **Kernel**: 5.15+
- **User**: postgres (will be created)
- **Python**: 3.8+ (for Patroni)

### Network Configuration

- **Static IP addresses** for all nodes
- **Firewall ports open**:
  - 5432 (PostgreSQL)
  - 8008 (Patroni REST API)
  - 2379 (etcd client)
  - 2380 (etcd peer)
- **DNS resolution** between all nodes
- **NTP synchronized** (critical for etcd)

### Pre-Flight Checks

Run on all nodes:

```bash
# Check Python version
python3 --version  # Should be 3.8+

# Check connectivity between nodes
ping -c 3 10.0.0.11
ping -c 3 10.0.0.12
ping -c 3 10.0.0.13

# Check time sync
timedatectl status  # Should show "System clock synchronized: yes"

# Check disk space
df -h /  # Should have 200GB+ free

# Disable swap (required)
sudo swapoff -a
sudo sed -i '/swap/d' /etc/fstab
```

---

## Installation Procedure

### Directory Structure

Create on all nodes:

```bash
sudo mkdir -p /opt/postgres-ha/{scripts,configs,logs}
sudo mkdir -p /var/lib/postgresql/{17,patroni}
sudo mkdir -p /var/log/{postgresql,patroni,etcd}
sudo mkdir -p /etc/{patroni,etcd}
```

### Step 1: System Preparation (All Nodes)

**File**: `/opt/postgres-ha/scripts/01-prepare-system.sh`

```bash
#!/bin/bash
set -euo pipefail

echo "=== Preparing System for PostgreSQL HA Cluster ==="

# Update system
apt-get update
apt-get upgrade -y

# Install dependencies
apt-get install -y \
    curl wget gnupg2 lsb-release \
    python3-pip python3-dev python3-venv \
    libpq-dev build-essential \
    net-tools vim htop jq \
    acl

# Configure kernel parameters
cat > /etc/sysctl.d/99-postgresql.conf <<EOF
# Memory
vm.swappiness = 1
vm.overcommit_memory = 2
vm.overcommit_ratio = 80
vm.dirty_ratio = 10
vm.dirty_background_ratio = 5

# Network
net.core.somaxconn = 1024
net.ipv4.tcp_max_syn_backlog = 4096
net.ipv4.ip_local_port_range = 10000 65535
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 60
net.ipv4.tcp_keepalive_probes = 3

# Shared memory
kernel.shmmax = 17179869184
kernel.shmall = 4194304
EOF

sysctl -p /etc/sysctl.d/99-postgresql.conf

# Set resource limits
cat > /etc/security/limits.d/postgres.conf <<EOF
postgres soft nofile 65536
postgres hard nofile 65536
postgres soft nproc 8192
postgres hard nproc 8192
postgres soft memlock unlimited
postgres hard memlock unlimited
EOF

echo "✅ System preparation completed"
```

Make executable and run:
```bash
chmod +x /opt/postgres-ha/scripts/01-prepare-system.sh
sudo /opt/postgres-ha/scripts/01-prepare-system.sh
```

### Step 2: Install PostgreSQL 17 (All Nodes)

**File**: `/opt/postgres-ha/scripts/02-install-postgresql.sh`

```bash
#!/bin/bash
set -euo pipefail

POSTGRES_VERSION=17

echo "=== Installing PostgreSQL ${POSTGRES_VERSION} ==="

# Add PostgreSQL APT repository (official PGDG)
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list

apt-get update

# Install PostgreSQL
apt-get install -y \
    postgresql-${POSTGRES_VERSION} \
    postgresql-server-dev-${POSTGRES_VERSION} \
    postgresql-contrib-${POSTGRES_VERSION} \
    postgresql-client-${POSTGRES_VERSION}

# Stop and disable default PostgreSQL (Patroni will manage it)
systemctl stop postgresql
systemctl disable postgresql

# Verify installation
sudo -u postgres psql --version

# Set ownership
chown -R postgres:postgres /var/lib/postgresql
chown -R postgres:postgres /var/log/postgresql

echo "✅ PostgreSQL ${POSTGRES_VERSION} installed successfully"
```

Run:
```bash
chmod +x /opt/postgres-ha/scripts/02-install-postgresql.sh
sudo /opt/postgres-ha/scripts/02-install-postgresql.sh
```

### Step 3: Install Citus Extension (All Nodes)

**File**: `/opt/postgres-ha/scripts/03-install-citus.sh`

```bash
#!/bin/bash
set -euo pipefail

POSTGRES_VERSION=17

echo "=== Installing Citus Extension ==="

# Add Citus repository (official)
curl https://install.citusdata.com/community/deb.sh | bash

# Install Citus for PostgreSQL 17
apt-get install -y postgresql-${POSTGRES_VERSION}-citus-13.0

# Verify installation
sudo -u postgres psql -c "SELECT * FROM pg_available_extensions WHERE name='citus';" | grep citus

if [ $? -eq 0 ]; then
    echo "✅ Citus extension installed successfully"
else
    echo "❌ Citus installation failed"
    exit 1
fi
```

Run:
```bash
chmod +x /opt/postgres-ha/scripts/03-install-citus.sh
sudo /opt/postgres-ha/scripts/03-install-citus.sh
```

### Step 4: Install etcd 3.7 (All Nodes)

**File**: `/opt/postgres-ha/scripts/04-install-etcd.sh`

```bash
#!/bin/bash
set -euo pipefail

ETCD_VERSION="3.7.0"

echo "=== Installing etcd ${ETCD_VERSION} ==="

# Download etcd
ETCD_URL="https://github.com/etcd-io/etcd/releases/download/v${ETCD_VERSION}/etcd-v${ETCD_VERSION}-linux-amd64.tar.gz"
wget -q "${ETCD_URL}" -O /tmp/etcd.tar.gz

# Extract and install
tar -xzf /tmp/etcd.tar.gz -C /tmp
mv /tmp/etcd-v${ETCD_VERSION}-linux-amd64/etcd /usr/local/bin/
mv /tmp/etcd-v${ETCD_VERSION}-linux-amd64/etcdctl /usr/local/bin/
rm -rf /tmp/etcd*

# Create etcd user
useradd -r -s /bin/false etcd || true

# Create directories
mkdir -p /var/lib/etcd/{data,wal}
mkdir -p /etc/etcd
chown -R etcd:etcd /var/lib/etcd
chown -R etcd:etcd /var/log/etcd

# Verify installation
etcd --version
etcdctl version

echo "✅ etcd ${ETCD_VERSION} installed successfully"
```

Run:
```bash
chmod +x /opt/postgres-ha/scripts/04-install-etcd.sh
sudo /opt/postgres-ha/scripts/04-install-etcd.sh
```

### Step 5: Install Patroni 4.1.0 (All Nodes)

**File**: `/opt/postgres-ha/scripts/05-install-patroni.sh`

```bash
#!/bin/bash
set -euo pipefail

PATRONI_VERSION="4.1.0"

echo "=== Installing Patroni ${PATRONI_VERSION} ==="

# Create Python virtual environment (recommended)
python3 -m venv /opt/patroni-venv
source /opt/patroni-venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Patroni with etcd support
# Using psycopg (v3) as recommended for modern PostgreSQL
pip install \
    patroni[etcd3]==${PATRONI_VERSION} \
    psycopg[binary] \
    python-etcd

# Create symlinks for system-wide access
ln -sf /opt/patroni-venv/bin/patroni /usr/local/bin/patroni
ln -sf /opt/patroni-venv/bin/patronictl /usr/local/bin/patronictl

# Create Patroni directories
mkdir -p /etc/patroni
mkdir -p /var/lib/postgresql/patroni
chown -R postgres:postgres /var/lib/postgresql/patroni
chown -R postgres:postgres /var/log/patroni

# Verify installation
patroni --version
patronictl --version

echo "✅ Patroni ${PATRONI_VERSION} installed successfully"
```

Run:
```bash
chmod +x /opt/postgres-ha/scripts/05-install-patroni.sh
sudo /opt/postgres-ha/scripts/05-install-patroni.sh
```

---

## Initial Cluster Setup (3 Nodes)

### Step 1: Configure etcd Cluster

Create configuration for each node:

**Node 1 (10.0.0.11)** - `/etc/etcd/etcd.conf`:

```yaml
name: 'etcd1'
data-dir: /var/lib/etcd/data
wal-dir: /var/lib/etcd/wal

# Listen on all interfaces for client requests
listen-client-urls: 'http://10.0.0.11:2379,http://127.0.0.1:2379'
advertise-client-urls: 'http://10.0.0.11:2379'

# Peer communication
listen-peer-urls: 'http://10.0.0.11:2380'
initial-advertise-peer-urls: 'http://10.0.0.11:2380'

# Cluster configuration
initial-cluster: 'etcd1=http://10.0.0.11:2380,etcd2=http://10.0.0.12:2380,etcd3=http://10.0.0.13:2380'
initial-cluster-state: 'new'
initial-cluster-token: 'saasodoo-etcd-cluster'

# Performance
heartbeat-interval: 100
election-timeout: 1000
max-snapshots: 5
max-wals: 5
quota-backend-bytes: 8589934592  # 8GB

# Logging
log-level: 'info'
log-outputs: ['/var/log/etcd/etcd.log']
```

**Node 2 (10.0.0.12)** - Change:
```yaml
name: 'etcd2'
listen-client-urls: 'http://10.0.0.12:2379,http://127.0.0.1:2379'
advertise-client-urls: 'http://10.0.0.12:2379'
listen-peer-urls: 'http://10.0.0.12:2380'
initial-advertise-peer-urls: 'http://10.0.0.12:2380'
```

**Node 3 (10.0.0.13)** - Change:
```yaml
name: 'etcd3'
listen-client-urls: 'http://10.0.0.13:2379,http://127.0.0.1:2379'
advertise-client-urls: 'http://10.0.0.13:2379'
listen-peer-urls: 'http://10.0.0.13:2380'
initial-advertise-peer-urls: 'http://10.0.0.13:2380'
```

**Create systemd service** - `/etc/systemd/system/etcd.service`:

```ini
[Unit]
Description=etcd key-value store
Documentation=https://etcd.io
After=network.target

[Service]
Type=notify
User=etcd
Group=etcd
Environment="ETCD_UNSUPPORTED_ARCH=arm64"
EnvironmentFile=/etc/etcd/etcd.conf
ExecStart=/usr/local/bin/etcd
Restart=on-failure
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

**Start etcd on all nodes**:

```bash
# On each node
sudo systemctl daemon-reload
sudo systemctl enable etcd
sudo systemctl start etcd

# Check status
sudo systemctl status etcd

# Verify cluster health (run on any node)
ETCDCTL_API=3 etcdctl --endpoints=http://10.0.0.11:2379,http://10.0.0.12:2379,http://10.0.0.13:2379 endpoint health

# Expected output:
# http://10.0.0.11:2379 is healthy: successfully committed proposal: took = 1.234ms
# http://10.0.0.12:2379 is healthy: successfully committed proposal: took = 1.456ms
# http://10.0.0.13:2379 is healthy: successfully committed proposal: took = 1.678ms
```

### Step 2: Configure Patroni

**Node 1 (10.0.0.11)** - `/etc/patroni/patroni.yml`:

```yaml
scope: saasodoo-pg-cluster
namespace: /db/
name: pg1

restapi:
  listen: 10.0.0.11:8008
  connect_address: 10.0.0.11:8008
  authentication:
    username: patroni
    password: 'ChangeThisPassword123!'  # CHANGE THIS!

etcd3:
  hosts:
    - 10.0.0.11:2379
    - 10.0.0.12:2379
    - 10.0.0.13:2379

bootstrap:
  dcs:
    ttl: 30
    loop_wait: 10
    retry_timeout: 10
    maximum_lag_on_failover: 1048576
    master_start_timeout: 300
    synchronous_mode: false
    postgresql:
      use_pg_rewind: true
      use_slots: true
      parameters:
        # Performance tuning
        max_connections: 500
        shared_buffers: 4GB
        effective_cache_size: 12GB
        maintenance_work_mem: 1GB
        checkpoint_completion_target: 0.9
        wal_buffers: 16MB
        default_statistics_target: 100
        random_page_cost: 1.1
        effective_io_concurrency: 200
        work_mem: 8MB
        min_wal_size: 2GB
        max_wal_size: 8GB
        max_worker_processes: 8
        max_parallel_workers_per_gather: 4
        max_parallel_workers: 8
        max_parallel_maintenance_workers: 4

        # Citus extension
        shared_preload_libraries: 'citus'
        citus.node_conninfo: 'sslmode=prefer'

        # Replication
        wal_level: replica
        hot_standby: on
        wal_log_hints: on
        max_wal_senders: 10
        max_replication_slots: 10
        wal_keep_size: 2GB

        # Logging
        log_destination: 'stderr'
        logging_collector: on
        log_directory: '/var/log/postgresql'
        log_filename: 'postgresql-%Y-%m-%d.log'
        log_rotation_age: 1d
        log_rotation_size: 100MB
        log_line_prefix: '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
        log_checkpoints: on
        log_connections: on
        log_disconnections: on
        log_lock_waits: on
        log_min_duration_statement: 1000

  initdb:
    - encoding: UTF8
    - data-checksums
    - locale: en_US.UTF-8

  pg_hba:
    - local all all trust
    - host all all 0.0.0.0/0 md5
    - host all all ::0/0 md5
    - host replication replicator 0.0.0.0/0 md5
    - host replication replicator ::0/0 md5

  users:
    admin:
      password: 'AdminPassword123!'  # CHANGE THIS!
      options:
        - createrole
        - createdb
    replicator:
      password: 'ReplicatorPassword123!'  # CHANGE THIS!
      options:
        - replication

  post_bootstrap: /opt/postgres-ha/scripts/post-bootstrap.sh

postgresql:
  listen: 10.0.0.11:5432
  connect_address: 10.0.0.11:5432
  data_dir: /var/lib/postgresql/17/main
  bin_dir: /usr/lib/postgresql/17/bin
  pgpass: /var/lib/postgresql/.pgpass
  authentication:
    replication:
      username: replicator
      password: 'ReplicatorPassword123!'  # CHANGE THIS!
    superuser:
      username: postgres
      password: 'PostgresPassword123!'  # CHANGE THIS!
    rewind:
      username: replicator
      password: 'ReplicatorPassword123!'  # CHANGE THIS!
  parameters:
    unix_socket_directories: '/var/run/postgresql'

watchdog:
  mode: off  # Set to 'automatic' in production with proper kernel config

tags:
    nofailover: false
    noloadbalance: false
    clonefrom: false
    nosync: false
```

**Node 2 & 3**: Copy the same configuration, but change:
- `name:` (pg2, pg3)
- `restapi.listen:` (10.0.0.12, 10.0.0.13)
- `restapi.connect_address:` (10.0.0.12, 10.0.0.13)
- `postgresql.listen:` (10.0.0.12, 10.0.0.13)
- `postgresql.connect_address:` (10.0.0.12, 10.0.0.13)

**Set permissions**:
```bash
sudo chown postgres:postgres /etc/patroni/patroni.yml
sudo chmod 600 /etc/patroni/patroni.yml
```

### Step 3: Create Post-Bootstrap Script

**File**: `/opt/postgres-ha/scripts/post-bootstrap.sh`

```bash
#!/bin/bash
# This script runs after Patroni bootstraps the cluster
# It creates the Citus extension on all databases

set -euo pipefail

echo "Running post-bootstrap configuration..."

# Wait for PostgreSQL to be ready
sleep 5

# Create Citus extension
sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS citus;"

echo "Post-bootstrap completed successfully"
```

Make executable:
```bash
chmod +x /opt/postgres-ha/scripts/post-bootstrap.sh
```

### Step 4: Create Patroni systemd Service

**File**: `/etc/systemd/system/patroni.service`

```ini
[Unit]
Description=Patroni PostgreSQL HA
Documentation=https://patroni.readthedocs.io/
After=syslog.target network.target etcd.service

[Service]
Type=simple
User=postgres
Group=postgres
ExecStart=/usr/local/bin/patroni /etc/patroni/patroni.yml
ExecReload=/bin/kill -HUP $MAINPID
KillMode=process
TimeoutSec=30
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### Step 5: Start Patroni Cluster

**IMPORTANT**: Start nodes in order!

```bash
# Node 1 (will become leader)
sudo systemctl daemon-reload
sudo systemctl enable patroni
sudo systemctl start patroni

# Wait 30 seconds, then check
sudo systemctl status patroni
patronictl -c /etc/patroni/patroni.yml list

# You should see Node 1 as Leader

# Node 2
sudo systemctl daemon-reload
sudo systemctl enable patroni
sudo systemctl start patroni

# Wait 30 seconds
patronictl -c /etc/patroni/patroni.yml list

# Node 3
sudo systemctl daemon-reload
sudo systemctl enable patroni
sudo systemctl start patroni

# Final check (run on any node)
patronictl -c /etc/patroni/patroni.yml list
```

**Expected output**:
```
+ Cluster: saasodoo-pg-cluster -----+----+-----------+
| Member | Host        | Role    | State   | TL | Lag in MB |
+--------+-------------+---------+---------+----+-----------+
| pg1    | 10.0.0.11   | Leader  | running |  1 |           |
| pg2    | 10.0.0.12   | Replica | running |  1 |         0 |
| pg3    | 10.0.0.13   | Replica | running |  1 |         0 |
+--------+-------------+---------+---------+----+-----------+
```

### Step 6: Configure Citus Coordinator

Connect to the leader node:

```bash
psql -h 10.0.0.11 -U postgres

-- Verify Citus extension
SELECT * FROM citus_version();

-- Add all coordinator nodes
SELECT citus_set_coordinator_host('10.0.0.11', 5432);
SELECT citus_add_node('10.0.0.12', 5432, groupid => 0, noderole => 'secondary');
SELECT citus_add_node('10.0.0.13', 5432, groupid => 0, noderole => 'secondary');

-- Verify nodes
SELECT * FROM citus_get_active_worker_nodes();

-- Create your application databases with Citus
CREATE DATABASE saasodoo_instance;
\c saasodoo_instance
CREATE EXTENSION citus;

-- Repeat for other databases: auth, billing, etc.
```

---

## Scaling: Adding New Nodes

### Procedure for Adding Node 4

**Step 1: Prepare new node**

Run steps 1-5 from Installation Procedure on new node (10.0.0.14).

**Step 2: Configure Patroni on new node**

Create `/etc/patroni/patroni.yml` on node 4:

```yaml
scope: saasodoo-pg-cluster
namespace: /db/
name: pg4  # NEW NAME

restapi:
  listen: 10.0.0.14:8008  # NEW IP
  connect_address: 10.0.0.14:8008
  authentication:
    username: patroni
    password: 'ChangeThisPassword123!'  # Same as cluster

etcd3:
  hosts:
    - 10.0.0.11:2379
    - 10.0.0.12:2379
    - 10.0.0.13:2379

# NO bootstrap section needed - will clone from existing

postgresql:
  listen: 10.0.0.14:5432  # NEW IP
  connect_address: 10.0.0.14:5432
  data_dir: /var/lib/postgresql/17/main
  bin_dir: /usr/lib/postgresql/17/bin
  pgpass: /var/lib/postgresql/.pgpass
  authentication:
    replication:
      username: replicator
      password: 'ReplicatorPassword123!'  # Same as cluster
    superuser:
      username: postgres
      password: 'PostgresPassword123!'  # Same as cluster
    rewind:
      username: replicator
      password: 'ReplicatorPassword123!'  # Same as cluster
  parameters:
    unix_socket_directories: '/var/run/postgresql'

  # Replica bootstrap configuration
  create_replica_methods:
    - basebackup
  basebackup:
    max-rate: 100M
    checkpoint: fast

watchdog:
  mode: off

tags:
    nofailover: false
    noloadbalance: false
    clonefrom: false
    nosync: false
```

**Step 3: Start Patroni on new node**

```bash
# On node 4
sudo systemctl daemon-reload
sudo systemctl enable patroni
sudo systemctl start patroni

# Monitor logs
journalctl -u patroni -f

# You should see: "bootstrapping from leader" and "replica has been created"

# Verify from any node
patronictl -c /etc/patroni/patroni.yml list
```

**Expected output**:
```
+ Cluster: saasodoo-pg-cluster -----+----+-----------+
| Member | Host        | Role    | State   | TL | Lag in MB |
+--------+-------------+---------+---------+----+-----------+
| pg1    | 10.0.0.11   | Leader  | running |  1 |           |
| pg2    | 10.0.0.12   | Replica | running |  1 |         0 |
| pg3    | 10.0.0.13   | Replica | running |  1 |         0 |
| pg4    | 10.0.0.14   | Replica | running |  1 |         0 |
+--------+-------------+---------+---------+----+-----------+
```

**Step 4: Add to Citus cluster**

```bash
psql -h 10.0.0.11 -U postgres

-- Add new coordinator node
SELECT citus_add_node('10.0.0.14', 5432, groupid => 0, noderole => 'secondary');

-- Verify
SELECT * FROM citus_get_active_worker_nodes();
```

**Automation Script** - `/opt/postgres-ha/scripts/add-node.sh`:

```bash
#!/bin/bash
set -euo pipefail

# Usage: ./add-node.sh <new-node-ip> <new-node-name>

NEW_NODE_IP=${1}
NEW_NODE_NAME=${2}
CLUSTER_LEADER="10.0.0.11"

echo "=== Adding new node ${NEW_NODE_NAME} (${NEW_NODE_IP}) to cluster ==="

# 1. SSH to new node and run installation
echo "Step 1: Running installation on ${NEW_NODE_IP}..."
ssh root@${NEW_NODE_IP} 'bash -s' < /opt/postgres-ha/scripts/01-prepare-system.sh
ssh root@${NEW_NODE_IP} 'bash -s' < /opt/postgres-ha/scripts/02-install-postgresql.sh
ssh root@${NEW_NODE_IP} 'bash -s' < /opt/postgres-ha/scripts/03-install-citus.sh
ssh root@${NEW_NODE_IP} 'bash -s' < /opt/postgres-ha/scripts/05-install-patroni.sh

# 2. Generate Patroni config
echo "Step 2: Creating Patroni configuration..."
cat > /tmp/patroni-${NEW_NODE_NAME}.yml <<EOF
scope: saasodoo-pg-cluster
namespace: /db/
name: ${NEW_NODE_NAME}
restapi:
  listen: ${NEW_NODE_IP}:8008
  connect_address: ${NEW_NODE_IP}:8008
  authentication:
    username: patroni
    password: 'ChangeThisPassword123!'
etcd3:
  hosts:
    - 10.0.0.11:2379
    - 10.0.0.12:2379
    - 10.0.0.13:2379
postgresql:
  listen: ${NEW_NODE_IP}:5432
  connect_address: ${NEW_NODE_IP}:5432
  data_dir: /var/lib/postgresql/17/main
  bin_dir: /usr/lib/postgresql/17/bin
  pgpass: /var/lib/postgresql/.pgpass
  authentication:
    replication:
      username: replicator
      password: 'ReplicatorPassword123!'
    superuser:
      username: postgres
      password: 'PostgresPassword123!'
    rewind:
      username: replicator
      password: 'ReplicatorPassword123!'
  parameters:
    unix_socket_directories: '/var/run/postgresql'
  create_replica_methods:
    - basebackup
  basebackup:
    max-rate: 100M
    checkpoint: fast
watchdog:
  mode: off
tags:
    nofailover: false
    noloadbalance: false
    clonefrom: false
    nosync: false
EOF

# 3. Copy config to new node
scp /tmp/patroni-${NEW_NODE_NAME}.yml root@${NEW_NODE_IP}:/etc/patroni/patroni.yml
ssh root@${NEW_NODE_IP} 'chown postgres:postgres /etc/patroni/patroni.yml && chmod 600 /etc/patroni/patroni.yml'

# 4. Copy systemd service
scp /etc/systemd/system/patroni.service root@${NEW_NODE_IP}:/etc/systemd/system/

# 5. Start Patroni
echo "Step 3: Starting Patroni on new node..."
ssh root@${NEW_NODE_IP} 'systemctl daemon-reload && systemctl enable patroni && systemctl start patroni'

# 6. Wait for replication
echo "Step 4: Waiting for node to join cluster (60 seconds)..."
sleep 60

# 7. Verify
patronictl -c /etc/patroni/patroni.yml list

# 8. Add to Citus
echo "Step 5: Adding to Citus cluster..."
psql -h ${CLUSTER_LEADER} -U postgres -c "SELECT citus_add_node('${NEW_NODE_IP}', 5432, groupid => 0, noderole => 'secondary');"

echo "✅ Node ${NEW_NODE_NAME} added successfully!"
```

Make executable:
```bash
chmod +x /opt/postgres-ha/scripts/add-node.sh
```

---

## Read/Write Splitting

### Option 1: HAProxy (Recommended)

**Install HAProxy**:
```bash
apt-get install -y haproxy
```

**Configure** - `/etc/haproxy/haproxy.cfg`:

```
global
    maxconn 10000
    log /dev/log local0
    log /dev/log local1 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    user haproxy
    group haproxy
    daemon

defaults
    mode tcp
    log global
    option tcplog
    option dontlognull
    retries 3
    timeout connect 10s
    timeout client 1h
    timeout server 1h

# Stats interface
listen stats
    mode http
    bind *:7000
    stats enable
    stats uri /
    stats refresh 5s
    stats show-legends
    stats show-node

# Write endpoint (Primary only)
listen postgres_write
    bind *:5432
    mode tcp
    option httpchk GET /primary
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server pg1 10.0.0.11:5432 maxconn 500 check port 8008
    server pg2 10.0.0.12:5432 maxconn 500 check port 8008 backup
    server pg3 10.0.0.13:5432 maxconn 500 check port 8008 backup
    server pg4 10.0.0.14:5432 maxconn 500 check port 8008 backup

# Read endpoint (All nodes)
listen postgres_read
    bind *:5433
    mode tcp
    balance leastconn
    option httpchk GET /replica
    http-check expect status 200
    default-server inter 3s fall 3 rise 2
    server pg1 10.0.0.11:5432 maxconn 500 check port 8008
    server pg2 10.0.0.12:5432 maxconn 500 check port 8008
    server pg3 10.0.0.13:5432 maxconn 500 check port 8008
    server pg4 10.0.0.14:5432 maxconn 500 check port 8008
```

**Start HAProxy**:
```bash
systemctl restart haproxy
systemctl enable haproxy

# Check stats
curl http://localhost:7000
```

### Application Connection Strings

```python
# Write operations (goes to primary)
DATABASE_WRITE_URL = "postgresql://user:pass@haproxy-host:5432/dbname"

# Read operations (load balanced across all)
DATABASE_READ_URL = "postgresql://user:pass@haproxy-host:5433/dbname"
```

---

## Operations & Maintenance

### Common Operations

**Check cluster status**:
```bash
patronictl -c /etc/patroni/patroni.yml list
```

**Manual failover**:
```bash
patronictl -c /etc/patroni/patroni.yml failover
```

**Restart PostgreSQL on a node**:
```bash
patronictl -c /etc/patroni/patroni.yml restart saasodoo-pg-cluster pg2
```

**Reinitialize a failed replica**:
```bash
patronictl -c /etc/patroni/patroni.yml reinit saasodoo-pg-cluster pg3
```

**Check replication lag**:
```bash
psql -h 10.0.0.11 -U postgres -c "SELECT client_addr, state, sync_state, replay_lag FROM pg_stat_replication;"
```

### Monitoring Script

**File**: `/opt/postgres-ha/scripts/cluster-health.sh`

```bash
#!/bin/bash

echo "=== PostgreSQL HA Cluster Health Check ==="
echo "Timestamp: $(date)"
echo ""

echo "1. Patroni Cluster Status:"
patronictl -c /etc/patroni/patroni.yml list
echo ""

echo "2. etcd Cluster Health:"
ETCDCTL_API=3 etcdctl --endpoints=http://10.0.0.11:2379,http://10.0.0.12:2379,http://10.0.0.13:2379 endpoint health
echo ""

echo "3. Replication Lag:"
psql -h 10.0.0.11 -U postgres -t -A -c "SELECT client_addr, state, COALESCE(replay_lag, '0'::interval) as lag FROM pg_stat_replication;" | column -t -s '|'
echo ""

echo "4. Database Sizes:"
psql -h 10.0.0.11 -U postgres -t -A -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database WHERE datname NOT IN ('template0', 'template1') ORDER BY pg_database_size(datname) DESC;" | column -t -s '|'
echo ""

echo "5. Connection Count:"
psql -h 10.0.0.11 -U postgres -t -A -c "SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname ORDER BY count(*) DESC;" | column -t -s '|'
echo ""

echo "✅ Health check completed"
```

---

## Troubleshooting

### Patroni won't start
```bash
# Check logs
journalctl -u patroni -n 100 --no-pager

# Common issues:
# - etcd not reachable
# - PostgreSQL already running
# - Wrong permissions on data directory

# Fix permissions
chown -R postgres:postgres /var/lib/postgresql/17
chmod 700 /var/lib/postgresql/17/main
```

### Split-brain scenario
```bash
# Check which node thinks it's leader
patronictl -c /etc/patroni/patroni.yml list

# If multiple leaders, reinitialize all replicas
patronictl -c /etc/patroni/patroni.yml reinit saasodoo-pg-cluster pg2
patronictl -c /etc/patroni/patroni.yml reinit saasodoo-pg-cluster pg3
```

### High replication lag
```bash
# Check network latency
ping -c 10 10.0.0.12

# Increase wal_keep_size
psql -h 10.0.0.11 -U postgres -c "ALTER SYSTEM SET wal_keep_size = '4GB';"
psql -h 10.0.0.11 -U postgres -c "SELECT pg_reload_conf();"
```

---

## Summary

This guide provides a production-ready PostgreSQL HA cluster with:
- ✅ Automatic failover via Patroni
- ✅ Distributed queries via Citus
- ✅ Easy horizontal scaling (add nodes with one script)
- ✅ Read/write splitting via HAProxy
- ✅ All latest stable versions (2025)

**Next Steps**:
1. Configure SSL/TLS for all connections
2. Set up automated backups (pg_back rest/WAL-G)
3. Add monitoring (Prometheus + Grafana)
4. Test failover scenarios
5. Document disaster recovery procedures

---

**Document Version**: 2.0
**Last Validated**: 2025-12-02
**Maintainer**: SaaSOdoo Infrastructure Team

## Sources

- [PostgreSQL 17 Documentation](https://www.postgresql.org/docs/17/)
- [Patroni 4.1.0 Documentation](https://patroni.readthedocs.io/en/latest/)
- [Citus 13.0 Documentation](https://docs.citusdata.com/)
- [etcd 3.7 Documentation](https://etcd.io/docs/v3.7/)
