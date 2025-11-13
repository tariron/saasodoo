# Quick Start Guide - PostgreSQL HA Cluster

Get your PostgreSQL HA cluster running in 5 minutes.

## Prerequisites

- Docker Swarm cluster (3+ nodes)
- Root/sudo access to each node
- Swarm manager node access

## Steps

### 1. Run Setup Script

```bash
cd infrastructure/HAPostgres
./scripts/setup.sh
```

Follow prompts to:
- Select 3 nodes for the cluster
- Create data directories
- Generate `.env` file

### 2. Set Passwords

```bash
nano .env
```

Replace all `CHANGE_ME_*` values with secure passwords:

```bash
# Quick password generation
openssl rand -base64 32
```

### 3. Deploy

```bash
./scripts/deploy.sh
```

Wait 1-2 minutes for services to start.

### 4. Verify

```bash
# Check cluster status
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node) patronictl list
```

Expected: 1 Leader + 2 Replicas running

### 5. Update Your App

In your application's `docker-compose.yml`:

```yaml
services:
  your-app:
    networks:
      - saasodoo-database-network
    environment:
      POSTGRES_HOST: haproxy
      POSTGRES_PORT: 6432

networks:
  saasodoo-database-network:
    external: true
```

Redeploy your app:

```bash
docker stack deploy -c docker-compose.yml your-app-stack
```

## Done! 🎉

Your app now connects to the HA PostgreSQL cluster.

---

## Quick Commands

**Check Status:**
```bash
docker stack ps saasodoo-db-infra
```

**View Logs:**
```bash
docker service logs -f saasodoo-db-infra_patroni-node1
```

**Connect to Database:**
```bash
docker exec -it $(docker ps -q -f name=saasodoo-db-infra_pgbouncer | head -1) \
  psql -h localhost -p 6432 -U postgres
```

**Test Failover:**
```bash
docker exec $(docker ps -q -f name=saasodoo-db-infra_patroni-node1) \
  patronictl failover saasodoo-cluster --force
```

**HAProxy Stats:**
```
http://<node-ip>:7000/stats
```

---

## Connection Info

**From your applications:**
- Host: `haproxy`
- Port: `6432`
- Connection string: `postgresql://user:pass@haproxy:6432/dbname`

**Direct PostgreSQL access:**
- Primary (read/write): `haproxy:5000`
- Replicas (read-only): `haproxy:5001`

---

## Troubleshooting

**Services not starting?**

Check logs:
```bash
docker service logs saasodoo-db-infra_patroni-node1
```

**Can't connect?**

Verify network:
```bash
docker network ls | grep saasodoo-database-network
```

**Need to restart?**

```bash
docker stack rm saasodoo-db-infra
sleep 30
docker stack deploy -c docker-compose.infra.yml saasodoo-db-infra
```

---

For detailed documentation, see [README.md](./README.md)
