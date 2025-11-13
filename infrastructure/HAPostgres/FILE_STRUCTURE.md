# HAPostgres File Structure

Complete file structure of the PostgreSQL HA cluster configuration.

```
infrastructure/HAPostgres/
├── docker-compose.infra.yml    # Main Docker Swarm stack definition
├── .env.example                 # Environment variables template
├── .gitignore                   # Git ignore rules (excludes .env)
│
├── README.md                    # Complete documentation
├── QUICKSTART.md                # Quick start guide
├── FILE_STRUCTURE.md            # This file
│
├── haproxy/
│   └── haproxy.cfg             # HAProxy load balancer configuration
│
├── pgbouncer/
│   └── pgbouncer.ini           # PgBouncer connection pooler configuration
│
├── patroni/
│   └── (empty - Patroni configured via environment variables)
│
└── scripts/
    ├── setup.sh                # Initial cluster setup (labels, dirs, .env)
    ├── deploy.sh               # Deploy the stack to Swarm
    ├── status.sh               # Check cluster health and status
    └── remove.sh               # Remove stack and optionally clean data
```

## File Purposes

### Core Files

**docker-compose.infra.yml**
- Defines all services (Patroni, etcd, PgBouncer, HAProxy)
- Configures networks (overlay networks for Swarm)
- Sets resource limits and placement constraints
- Environment variable configuration
- Volume mounts and configs

**.env.example**
- Template for environment variables
- Contains all required password placeholders
- Should be copied to `.env` and customized

**.gitignore**
- Ensures `.env` file is never committed
- Excludes backup files and logs

### Documentation

**README.md**
- Complete reference documentation
- Architecture overview
- Detailed setup instructions
- Operations guide
- Troubleshooting section
- Security considerations
- Performance tuning

**QUICKSTART.md**
- 5-minute getting started guide
- Minimal steps to get running
- Essential commands only
- Quick reference

**FILE_STRUCTURE.md**
- This file
- Overview of directory structure
- File purposes

### Configuration Files

**haproxy/haproxy.cfg**
- Load balancer configuration
- Routes traffic to PgBouncer and PostgreSQL
- Health check definitions
- Stats page configuration
- Ports:
  - 6432: PgBouncer pool (main app connection)
  - 5000: PostgreSQL primary (direct admin)
  - 5001: PostgreSQL replicas (read-only)
  - 7000: Stats dashboard

**pgbouncer/pgbouncer.ini**
- Connection pooler configuration
- Pool sizing and limits
- Timeout settings
- Authentication method
- Wildcard database configuration (supports multi-tenancy)
- Session pooling mode (required for Odoo)

### Scripts

**setup.sh**
- Interactive setup wizard
- Labels Swarm nodes for placement
- Creates PostgreSQL data directories
- Generates `.env` from template
- Pre-deployment verification

**deploy.sh**
- Deploys stack to Docker Swarm
- Pre-deployment checks
- Monitors deployment progress
- Verifies cluster health
- Provides connection information
- Shows useful commands

**status.sh**
- Quick cluster health check
- Service status overview
- etcd cluster health
- Patroni cluster status
- PgBouncer pool statistics
- Connection testing
- Resource usage
- Recent events

**remove.sh**
- Safely removes the stack
- Optional volume cleanup
- Optional data directory cleanup
- Optional label removal
- Confirmation prompts to prevent accidents

## Directory Structure on Swarm Nodes

After deployment, each Swarm node will have:

```
/var/lib/patroni/
├── node1/                      # On node labeled patroni=node1
│   ├── base/                   # PostgreSQL database files
│   ├── pg_wal/                 # Write-Ahead Logs
│   ├── pg_stat/                # Statistics
│   └── ...                     # Other PostgreSQL files
│
├── node2/                      # On node labeled patroni=node2
│   └── (same structure)
│
└── node3/                      # On node labeled patroni=node3
    └── (same structure)
```

## Docker Resources Created

### Services
- `saasodoo-db-infra_etcd1`
- `saasodoo-db-infra_etcd2`
- `saasodoo-db-infra_etcd3`
- `saasodoo-db-infra_patroni-node1`
- `saasodoo-db-infra_patroni-node2`
- `saasodoo-db-infra_patroni-node3`
- `saasodoo-db-infra_pgbouncer`
- `saasodoo-db-infra_haproxy`

### Networks
- `saasodoo-db-infra_saasodoo-database-network` (overlay, external)
- `saasodoo-db-infra_patroni-internal` (overlay, internal)
- `saasodoo-db-infra_pgbouncer-backend` (overlay, internal)

### Volumes
- `saasodoo-db-infra_etcd1-data`
- `saasodoo-db-infra_etcd2-data`
- `saasodoo-db-infra_etcd3-data`

### Configs
- `saasodoo-db-infra_haproxy_cfg`
- `saasodoo-db-infra_pgbouncer_ini`

## Configuration Management

All configuration is managed through:

1. **Environment variables** (`.env` file)
   - Passwords and secrets
   - Customizable settings

2. **Docker configs** (mounted read-only)
   - HAProxy configuration
   - PgBouncer configuration
   - Immutable once deployed

3. **Environment variables in docker-compose** (patroni config)
   - PostgreSQL tuning parameters
   - Patroni settings
   - etcd connection strings

## Security Notes

**Files with secrets:**
- `.env` - **NEVER commit to git** (in .gitignore)

**Files safe to commit:**
- All other files (no secrets embedded)
- Configuration templates
- Scripts
- Documentation

**Secrets in Swarm:**
- For production, consider using Docker secrets instead of `.env`
- Secrets are encrypted at rest in Swarm
- Can be rotated without redeploying stack

## Customization Points

**To customize for your deployment:**

1. **docker-compose.infra.yml**
   - Resource limits (CPU, memory)
   - PostgreSQL parameters
   - Service replica counts
   - Network names

2. **haproxy/haproxy.cfg**
   - Connection limits
   - Timeout values
   - Port numbers
   - Stats authentication

3. **pgbouncer/pgbouncer.ini**
   - Pool sizes
   - Connection limits
   - Timeout values
   - Auth method

4. **.env**
   - All passwords
   - Optional environment overrides

## Maintenance Files

After deployment, you may want to add:

```
infrastructure/HAPostgres/
├── backups/                    # Database backups (not in git)
├── logs/                       # Exported logs (not in git)
├── docs/                       # Additional documentation
└── monitoring/                 # Prometheus/Grafana configs (optional)
```

These are not created by default but may be useful for operations.

---

**Last Updated**: 2025-01-13
