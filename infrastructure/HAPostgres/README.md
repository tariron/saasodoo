# PostgreSQL High Availability Cluster for SaaSOdoo

Production-ready PostgreSQL HA cluster using Patroni, etcd, PgBouncer, and HAProxy on Docker Swarm.

## Architecture Overview

```
Application Services
        ↓
   HAProxy (VIP)
        ↓
   PgBouncer Pool (3 replicas)
        ↓
   Patroni Cluster (3 PostgreSQL nodes)
        ↓
   etcd Cluster (3 nodes)
```

### Components

| Component | Purpose | Replicas | Resources |
|-----------|---------|----------|-----------|
| **Patroni** | PostgreSQL HA orchestration | 3 | 4 CPU, 16GB RAM each |
| **etcd** | Distributed consensus | 3 | 1 CPU, 2GB RAM each |
| **PgBouncer** | Connection pooling | 3 | 2 CPU, 4GB RAM each |
| **HAProxy** | Load balancing | 2 | 1 CPU, 1GB RAM each |

### Key Features

✅ **Automatic Failover** - 10-15 second RTO
✅ **Connection Pooling** - Handle 10,000+ client connections
✅ **Load Balancing** - Distribute traffic across PgBouncer instances
✅ **Read Scaling** - Separate read-only endpoint for replicas
✅ **Split-Brain Protection** - etcd consensus prevents data corruption
✅ **Zero-Downtime Updates** - Rolling updates with no service interruption
✅ **Production-Optimized** - Tuned PostgreSQL parameters for performance

---

## Prerequisites

### Docker Swarm Cluster

- **Minimum**: 3 nodes (1 manager + 2 workers)
- **Recommended**: 3 managers for control plane HA
- **Hardware per node**: 4+ vCPU, 16+ GB RAM, 100+ GB SSD

### Network Requirements

- **Ports**:
  - `6432` - PgBouncer (main application connection)
  - `5000` - PostgreSQL primary (direct admin access)
  - `5001` - PostgreSQL replicas (read-only queries)
  - `7000` - HAProxy stats page
  - `2379-2380` - etcd (internal)
  - `5432` - PostgreSQL (internal)
  - `8008` - Patroni REST API (internal)

### Storage

- **Local SSD recommended** for PostgreSQL data directories
- **No CephFS required** - Patroni handles replication
- **Per node**: `/var/lib/patroni/nodeX` directories with proper permissions

---

## Quick Start

### 1. Initialize Docker Swarm (if not already done)

On the first manager node:

```bash
docker swarm init --advertise-addr <MANAGER-IP>
```

On worker nodes, join the swarm using the token:

```bash
docker swarm join --token <TOKEN> <MANAGER-IP>:2377
```

### 2. Setup Cluster Nodes

Run the setup script on a Swarm manager:

```bash
cd infrastructure/HAPostgres
./scripts/setup.sh
```

This will:
- Label Swarm nodes for Patroni/etcd placement
- Create data directories on each node
- Generate `.env` file from template

### 3. Configure Passwords

Edit the `.env` file and set strong passwords:

```bash
nano .env
```

Generate secure passwords:

```bash
openssl rand -base64 32
```

### 4. Deploy the Stack

```bash
./scripts/deploy.sh
```

This will deploy all services and verify the cluster is healthy.

### 5. Update Application Services

Update your application's `docker-compose.yml` to connect to the HA cluster:

```yaml
services:
  your-app:
    networks:
      - saasodoo-database-network  # Join the database network
    environment:
      POSTGRES_HOST: haproxy
      POSTGRES_PORT: 6432
      # ... other env vars

networks:
  saasodoo-database-network:
    external: true
```

---

## Manual Setup Steps

If you prefer manual setup over using the scripts:

### 1. Label Swarm Nodes

```bash
# List nodes
docker node ls

# Label nodes for placement
docker node update --label-add patroni=node1 <NODE-1-ID>
docker node update --label-add etcd=node1 <NODE-1-ID>

docker node update --label-add patroni=node2 <NODE-2-ID>
docker node update --label-add etcd=node2 <NODE-2-ID>

docker node update --label-add patroni=node3 <NODE-3-ID>
docker node update --label-add etcd=node3 <NODE-3-ID>
```

### 2. Create Data Directories

On each Swarm node, create the Patroni data directory:

**On Node 1:**
```bash
sudo mkdir -p /var/lib/patroni/node1
sudo chown -R 999:999 /var/lib/patroni/node1
```

**On Node 2:**
```bash
sudo mkdir -p /var/lib/patroni/node2
sudo chown -R 999:999 /var/lib/patroni/node2
```

**On Node 3:**
```bash
sudo mkdir -p /var/lib/patroni/node3
sudo chown -R 999:999 /var/lib/patroni/node3
```

> **Note**: `999:999` is the postgres user/group ID inside the Patroni container.

### 3. Configure Environment

```bash
cp .env.example .env
nano .env
```

Set all passwords to strong, unique values.

### 4. Deploy

```bash
docker stack deploy -c docker-compose.infra.yml saasodoo-db-infra
```

---

## Verification & Testing

### Check Stack Status

```bash
docker stack services saasodoo-db-infra
docker stack ps saasodoo-db-infra
```

### Verify etcd Cluster

```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_etcd1) etcdctl member list
```

Expected output: 3 members listed

### Verify Patroni Cluster

```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node) patronictl list
```

Expected output:
```
+ Cluster: saasodoo-cluster ------+----+-----------+
| Member        | Host            | Role    | State   | TL | Lag in MB |
+---------------+-----------------+---------+---------+----+-----------+
| patroni-node1 | patroni-node1:5432 | Leader  | running | 1  |           |
| patroni-node2 | patroni-node2:5432 | Replica | running | 1  | 0         |
| patroni-node3 | patroni-node3:5432 | Replica | running | 1  | 0         |
+---------------+-----------------+---------+---------+----+-----------+
```

### Test Database Connection

Via PgBouncer:

```bash
docker exec -it $(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -1) \
  psql -h localhost -p 6432 -U postgres -d postgres
```

Direct to primary:

```bash
docker exec -it $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  psql -U postgres
```

### View HAProxy Stats

Open in browser: `http://<any-node-ip>:7000/stats`

Default credentials: `admin` / `<HAPROXY_STATS_PASSWORD>`

### Test Failover

Trigger a manual failover:

```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl failover saasodoo-cluster --master patroni-node1 --candidate patroni-node2 --force
```

Verify new primary:

```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node) patronictl list
```

---

## Connection Information

### For Applications

**Primary endpoint (read/write):**
```
Host: haproxy
Port: 6432
Connection: postgresql://username:password@haproxy:6432/database
```

**Direct PostgreSQL primary (admin operations):**
```
Host: haproxy
Port: 5000
```

**Read-only replicas (read scaling):**
```
Host: haproxy
Port: 5001
```

### Connection String Examples

**Python (psycopg2):**
```python
import psycopg2

conn = psycopg2.connect(
    host='haproxy',
    port=6432,
    database='your_db',
    user='your_user',
    password='your_password'
)
```

**Environment Variables (for your application services):**
```bash
POSTGRES_HOST=haproxy
POSTGRES_PORT=6432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

---

## Operations

### View Logs

**Patroni:**
```bash
docker service logs -f saasodoo-db-infra_patroni-node1
```

**PgBouncer:**
```bash
docker service logs -f saasodoo-db-infra_pgbouncer
```

**HAProxy:**
```bash
docker service logs -f saasodoo-db-infra_haproxy
```

**etcd:**
```bash
docker service logs -f saasodoo-db-infra_etcd1
```

### Scale Services

**Scale PgBouncer:**
```bash
docker service scale saasodoo-db-infra_pgbouncer=5
```

**Scale HAProxy:**
```bash
docker service scale saasodoo-db-infra_haproxy=3
```

> **Note**: Patroni should always be 3 replicas (1 per labeled node)

### Update Services

**Update Patroni image:**
```bash
docker service update --image patroni/patroni:3.0.0 saasodoo-db-infra_patroni-node1
docker service update --image patroni/patroni:3.0.0 saasodoo-db-infra_patroni-node2
docker service update --image patroni/patroni:3.0.0 saasodoo-db-infra_patroni-node3
```

Swarm performs rolling updates automatically.

### Manual Failover

**Failover to specific node:**
```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl failover saasodoo-cluster --candidate patroni-node2 --force
```

**Switchover (planned maintenance):**
```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl switchover saasodoo-cluster --master patroni-node1 --candidate patroni-node2
```

### Restart Services

**Restart single service:**
```bash
docker service update --force saasodoo-db-infra_patroni-node1
```

**Restart entire stack:**
```bash
docker stack rm saasodoo-db-infra
# Wait 30 seconds
docker stack deploy -c docker-compose.infra.yml saasodoo-db-infra
```

---

## Backup & Recovery

### Create Backup

**Via pg_basebackup:**
```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  pg_basebackup -h localhost -U postgres -D /tmp/backup -Ft -z -Xs -P
```

**Copy backup out:**
```bash
docker cp <container-id>:/tmp/backup ./backup-$(date +%Y%m%d)
```

### WAL Archiving

Configure in the Patroni environment variables (already set in docker-compose):

```yaml
- PATRONI_POSTGRESQL_PARAMETERS_ARCHIVE_MODE=on
- PATRONI_POSTGRESQL_PARAMETERS_ARCHIVE_COMMAND=test ! -f /backups/wal/%f && cp %p /backups/wal/%f
```

Mount a backup volume to `/backups` on each Patroni node.

### Point-in-Time Recovery (PITR)

1. Stop the cluster
2. Restore base backup to data directory
3. Create `recovery.conf` with restore target
4. Start cluster
5. Patroni re-syncs replicas

---

## Monitoring

### Health Checks

**Patroni REST API:**
```bash
curl http://<node-ip>:8008/health
curl http://<node-ip>:8008/primary
curl http://<node-ip>:8008/replica
curl http://<node-ip>:8008/cluster
```

**PgBouncer Admin Console:**
```bash
docker exec -it $(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -1) \
  psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW POOLS;"
```

**HAProxy Stats Page:**
```
http://<node-ip>:7000/stats
```

### Key Metrics to Monitor

- **Patroni**: Replication lag, failover events, cluster state
- **PgBouncer**: Pool usage (active/waiting clients), connections per database
- **PostgreSQL**: Query performance, connection count, cache hit ratio
- **HAProxy**: Backend health, connection rate, errors

---

## Troubleshooting

### etcd Cluster Won't Form

**Problem**: etcd nodes can't reach each other

**Solution**:
```bash
# Check network connectivity
docker network inspect saasodoo-db-infra_patroni-internal

# Verify DNS resolution
docker exec $(docker ps -q -f name=saasodoo-db-infra_etcd1) ping etcd2

# Check etcd logs
docker service logs saasodoo-db-infra_etcd1
```

### Patroni Won't Initialize

**Problem**: Patroni stuck in initialization

**Causes**:
- etcd not accessible
- Data directory permissions wrong
- Previous PostgreSQL data exists

**Solution**:
```bash
# Check etcd connectivity
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  curl http://etcd1:2379/health

# Check data directory permissions on host
ls -la /var/lib/patroni/node1

# View Patroni logs
docker service logs saasodoo-db-infra_patroni-node1

# If needed, clean data directory and reinitialize
# WARNING: This deletes all data!
docker service scale saasodoo-db-infra_patroni-node1=0
# On the host: sudo rm -rf /var/lib/patroni/node1/*
docker service scale saasodoo-db-infra_patroni-node1=1
```

### PgBouncer Can't Connect

**Problem**: PgBouncer shows connection errors

**Solution**:
```bash
# Check PgBouncer logs
docker service logs saasodoo-db-infra_pgbouncer

# Verify Patroni primary is accessible
docker exec $(docker ps -q -f name=saasodoo-db-infra_pgbouncer) \
  ping patroni-node1

# Check PgBouncer config
docker exec $(docker ps -q -f name=saasodoo-db-infra_pgbouncer) \
  cat /etc/pgbouncer/pgbouncer.ini
```

### Split Brain Detection

**Problem**: Multiple primaries detected

**This should never happen** due to etcd consensus, but if it does:

```bash
# Check cluster state
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node) patronictl list

# Reinitialize problematic replica
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node2) \
  patronictl reinit saasodoo-cluster patroni-node2
```

### Node Failure Recovery

**Scenario**: Physical host dies

**Recovery**:
1. Cluster continues with 2/3 nodes (automatic)
2. Replace failed hardware
3. Label new node:
   ```bash
   docker node update --label-add patroni=node1 <NEW-NODE-ID>
   docker node update --label-add etcd=node1 <NEW-NODE-ID>
   ```
4. Create data directory on new node
5. Service automatically deploys to new node
6. Patroni syncs from current primary

---

## Performance Tuning

### PostgreSQL Parameters

Already optimized for 16GB RAM in `docker-compose.infra.yml`:

- `shared_buffers=4GB` (25% of RAM)
- `effective_cache_size=12GB` (75% of RAM)
- `maintenance_work_mem=1GB`
- `work_mem=10MB` (adjust based on connection count)
- `max_connections=500`

### PgBouncer Tuning

Adjust in `pgbouncer/pgbouncer.ini`:

```ini
default_pool_size = 25        # Connections per database
max_client_conn = 10000       # Total client connections
```

**Rule of thumb**:
```
default_pool_size = max_connections / number_of_databases
```

### HAProxy Tuning

For higher throughput, adjust in `haproxy/haproxy.cfg`:

```
maxconn 20000  # Increase from 10000
```

---

## Security Considerations

### Production Checklist

- [ ] Change all default passwords in `.env`
- [ ] Use strong passwords (32+ characters)
- [ ] Enable TLS for PostgreSQL connections
- [ ] Enable etcd client certificate authentication
- [ ] Restrict network access to database ports
- [ ] Enable HAProxy basic auth for stats page
- [ ] Regular security updates for Docker images
- [ ] Implement network segmentation
- [ ] Enable audit logging
- [ ] Regular backup testing

### Network Isolation

The stack uses separate networks:

- `saasodoo-database-network` - External, for application connections
- `patroni-internal` - Internal, for Patroni/etcd cluster
- `pgbouncer-backend` - Internal, for PgBouncer to PostgreSQL

---

## Maintenance

### Rolling Updates

Update one node at a time to avoid downtime:

```bash
docker service update --force saasodoo-db-infra_patroni-node1
# Wait for node1 to rejoin as replica
docker service update --force saasodoo-db-infra_patroni-node2
# Wait for node2 to rejoin
docker service update --force saasodoo-db-infra_patroni-node3
```

### Planned Downtime

For major maintenance requiring downtime:

```bash
# 1. Put cluster in maintenance mode
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl pause saasodoo-cluster

# 2. Perform maintenance

# 3. Resume cluster
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl resume saasodoo-cluster
```

---

## Cost Estimation

### Infrastructure (AWS Example)

| Resource | Specification | Monthly Cost |
|----------|--------------|--------------|
| 3× EC2 instances | t3.xlarge (4 vCPU, 16 GB) | ~$300 |
| 3× EBS volumes | 100 GB gp3 SSD | ~$30 |
| Data transfer | Internal (negligible) | ~$10 |
| **Total** | | **~$340/month** |

### On-Premises

- Hardware cost amortized
- Primarily power and cooling
- No cloud egress charges

---

## Support & Resources

### Official Documentation

- **Patroni**: https://patroni.readthedocs.io/
- **etcd**: https://etcd.io/docs/
- **PgBouncer**: https://www.pgbouncer.org/
- **HAProxy**: http://www.haproxy.org/

### Useful Commands Reference

```bash
# Cluster status
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node) patronictl list

# Connection test
psql -h haproxy -p 6432 -U postgres -d postgres

# View replication lag
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  psql -U postgres -c "SELECT * FROM pg_stat_replication;"

# PgBouncer stats
docker exec $(docker ps -q -f name=saasodoo-db-infra_pgbouncer) \
  psql -h localhost -p 6432 -U postgres -d pgbouncer -c "SHOW STATS;"
```

---

## License

This configuration is part of the SaaSOdoo project. Adjust as needed for your deployment.

## Contributing

For issues or improvements, please create an issue or pull request in the project repository.

---

**Last Updated**: 2025-01-13
