# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SaaSOdoo is a multi-tenant SaaS platform for provisioning and managing Odoo ERP instances with integrated billing (KillBill), containerized orchestration, and distributed storage (CephFS).

## Architecture

### Microservices Structure
- **user-service** (port 8001) - Authentication & user management
- **instance-service** (port 8003) - Odoo instance lifecycle management with Celery workers
- **billing-service** (port 8004) - KillBill integration & subscription management
- **notification-service** (port 5000) - Email & communication
- **frontend-service** (port 3000) - React web application

### Key Infrastructure Components
- **PostgreSQL** - Single server hosting multiple databases:
  - Platform databases: `auth`, `billing`, `instance`, `communication`
  - Per-instance databases: `odoo_{customer_id}_{instance_id_short}`
- **Redis** - Session storage, caching, Celery result backend
- **RabbitMQ** - Celery task queues (provisioning, operations, maintenance, monitoring)
- **KillBill + MariaDB** - Billing engine with webhooks driving instance lifecycle
- **Traefik** - Reverse proxy with domain-based routing
- **CephFS** - Distributed storage at `/mnt/cephfs` for Odoo instance data

### Service Communication Pattern
- Services communicate via HTTP/REST APIs
- Shared utilities in `shared/utils/` (database, logger, security, redis)
- Shared schemas in `shared/schemas/` for data consistency
- Event-driven: KillBill webhooks trigger instance lifecycle changes
- Background tasks: Celery workers handle async instance operations

## Development Commands

### Start Development Environment
```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml up --build -d
```

### Stop Environment
```bash
docker compose -f infrastructure/compose/docker-compose.dev.yml down
```

### View Logs
```bash
# All services
docker compose -f infrastructure/compose/docker-compose.dev.yml logs -f

# Specific service
docker compose -f infrastructure/compose/docker-compose.dev.yml logs -f user-service

# Instance worker (Celery)
docker compose -f infrastructure/compose/docker-compose.dev.yml logs -f instance-worker
```

### Rebuild Specific Service
```bash
# Always rebuild instance-worker when rebuilding instance-service
docker compose -f infrastructure/compose/docker-compose.dev.yml up --build -d instance-service instance-worker
```

### Run Tests
```bash
# Service-specific tests
docker exec saasodoo-user-service pytest tests/
docker exec saasodoo-billing-service pytest tests/

# Database connectivity test
docker exec saasodoo-postgres python3 /docker-entrypoint-initdb.d/test_connectivity.py
```

### Access Service Health Endpoints
```bash
curl http://localhost:8001/health          # user-service
curl http://localhost:8003/health          # instance-service
curl http://localhost:8004/health          # billing-service
```

## Database Architecture

### Service-Specific User Pattern
Each service MUST set environment variables:
- `DB_SERVICE_USER` - Dedicated database user (e.g., `auth_service`, `billing_service`)
- `DB_SERVICE_PASSWORD` - Service-specific password

This is enforced by `shared/utils/database.py:DatabaseManager._build_database_url()` which raises ValueError if not set.

### Database Query Commands
```bash
# Check instance record
docker exec saasodoo-postgres psql -U instance_service -d instance -c \
  "SELECT id, name, status, subscription_id, billing_status FROM instances WHERE id = 'INSTANCE_ID';"

# Check user sessions
docker exec saasodoo-postgres psql -U auth_service -d auth -c \
  "SELECT customer_id, created_at, last_used FROM user_sessions WHERE customer_id = 'USER_ID';"
```

## KillBill Billing Integration

### Essential KillBill Commands

#### Check KillBill Health
```bash
docker exec saasodoo-killbill curl -s http://localhost:8080/1.0/healthcheck
```

#### View Subscription Details
```bash
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/subscriptions/SUBSCRIPTION_ID" | python3 -m json.tool
```

#### Check Account by External Key (customer_id)
```bash
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/accounts?externalKey=CUSTOMER_ID" | python3 -m json.tool
```

#### Test Clock Manipulation (Dev/Test Mode Only)
```bash
# Check current KillBill time
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  http://localhost:8080/1.0/kb/test/clock

# Advance time to trigger subscription events
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  -X POST "http://localhost:8080/1.0/kb/test/clock?requestedDate=2026-04-01T00:00:00.000Z"
```

### KillBill Webhook Flow
1. KillBill fires webhook to `http://billing-service:8004/api/billing/webhooks/killbill`
2. Billing-service processes event (`SUBSCRIPTION_CREATION`, `SUBSCRIPTION_CANCEL`, `INVOICE_PAYMENT_SUCCESS`, etc.)
3. Billing-service calls instance-service API to update instance status
4. Instance-service queues Celery task for provisioning/termination

## Instance Service & Celery Workers

### Celery Task Queues
- `instance_provisioning` - New instance creation (CPU-intensive, ~30-60s)
- `instance_operations` - Start/stop/restart (5-45s)
- `instance_maintenance` - Backups, updates, scaling
- `instance_monitoring` - Health checks, metrics collection

### Instance Lifecycle States
**Status**: `creating` → `starting` → `running` → `stopped` | `paused` | `terminated` | `error`
**Billing Status**: `trial` → `payment_required` → `paid` | `overdue` | `suspended`

### Important Celery Configuration
- **No automatic retries**: `task_max_retries=0` (manual admin retry only)
- **Task time limit**: 30 minutes hard, 25 minutes soft
- **Worker prefetch**: 1 task per worker at a time (`worker_prefetch_multiplier=1`)
- **Task acknowledgment**: After completion (`task_acks_late=True`)

## FastAPI Service Structure Pattern

Each service follows this structure:
```
services/{service-name}/
├── app/
│   ├── main.py           # FastAPI app with lifespan manager
│   ├── models/           # SQLAlchemy models
│   ├── routes/           # API route handlers
│   ├── services/         # Business logic
│   └── utils/            # Service-specific utilities
├── Dockerfile
├── requirements.txt
└── tests/                # pytest with pytest-asyncio
```

## Storage & CephFS

### CephFS Mount Point
`/mnt/cephfs` - Shared across instance-service and instance-worker

### Directory Structure
```
/mnt/cephfs/odoo_instances/
└── odoo_data_{db_name}_{instance_id}/
    ├── addons/
    ├── filestore/
    └── sessions/
```

### Quota Management
Quotas set via `setfattr -n ceph.quota.max_bytes` for per-instance limits

## Service URLs (Development)

### API Endpoints
- `http://api.localhost/user` - user-service
- `http://api.localhost/instance` - instance-service
- `http://api.localhost/billing` - billing-service
- `http://localhost:8001/docs` - user-service OpenAPI docs
- `http://localhost:8003/docs` - instance-service OpenAPI docs
- `http://localhost:8004/docs` - billing-service OpenAPI docs

### Admin Interfaces
- `http://localhost:8080` - Traefik dashboard
- `http://localhost:9090` - Kaui (KillBill admin UI) - admin/password
- `http://localhost:3000` - Frontend application

## Known Issues & Patterns

### Critical Security Patterns
- **Session invalidation**: Logout MUST delete session from `user_sessions` table (see ISSUES_LOG.md #001)
- **Database users**: Each service MUST use service-specific credentials, never shared admin user
- **Trial eligibility**: Always use backend API (`GET /api/billing/trial-eligibility/{customer_id}`) as single source of truth

### Trial Logic System
The platform implements a "trial invisibility" pattern where users ineligible for trials never see any trial-related UI or messaging.

**Business Rules:**
- One trial per customer (lifetime limit)
- Customers with active paid subscriptions cannot get trials
- Trial eligibility checked via backend API (single source of truth)
- Frontend transforms plan data based on eligibility
- Ineligible users see only paid pricing, no trial badges/warnings

**Implementation:**
- **Backend**: `TrialEligibilityService` (`services/billing-service/app/services/trial_eligibility_service.py`)
- **API Endpoint**: `GET /api/billing/trial-eligibility/{customer_id}`
- **Redis Locking**: Prevents race conditions during trial creation
- **Error Handling**: Fail closed (deny trials on system errors)
- **Frontend**: Plan transformation in `CreateInstance.tsx` removes trial info for ineligible users

**Trial Duration:**
- Production plans: 14 days (configurable via `DEFAULT_TRIAL_DAYS`)
- Test plans: 1 day

**Environment Variables:**
```bash
DEFAULT_TRIAL_DAYS=14
TRIAL_ELIGIBILITY_FAIL_BEHAVIOR=closed
TRIAL_WARNING_DAYS=7,3,1
TRIAL_MONITORING_ENABLED=true
```

**Key Files:**
- Backend service: `services/billing-service/app/services/trial_eligibility_service.py`
- Backend routes: `services/billing-service/app/routes/trial.py`
- Shared schemas: `shared/schemas/billing.py` (TrialEligibilityResponse)
- Frontend types: `frontend/src/types/billing.ts`
- Frontend API: `frontend/src/utils/api.ts` (getTrialEligibility)
- Frontend page: `frontend/src/pages/CreateInstance.tsx` (transformPlanForDisplay)

### Docker Access Method
Instance-service and instance-worker use the **Docker SDK for Python** (`docker==7.1.0`) to manage Odoo containers via `DockerClientWrapper` (in `app/utils/docker_client.py`).

**Current Setup (Dev)**: Unix socket
- Connection: `DOCKER_HOST=unix:///var/run/docker.sock`
- Requires: Socket mounted as volume in docker-compose
- Security concern: Requires docker group GID or root privileges

**Production Alternative**: TCP with TLS
- Connection: `DOCKER_HOST=tcp://docker-host:2376` (TLS) or `tcp://docker-host:2375` (unencrypted)
- Benefits: No socket mount, no GID issues, network-accessible, certificate-based auth
- Recommended for Docker Swarm/Kubernetes deployments

### Rebuild Requirement
When modifying instance-service, ALWAYS rebuild instance-worker as well since they share the same codebase.

### No Manual Operations
Do not perform manual operations unless explicitly requested. Follow automated workflows.

### Sudo Restrictions
Cannot run sudo commands. If sudo is needed, inform the user and suggest the command to run.

## Code Style Preferences

- Be concise when discussing code; only provide extensive code when explicitly requested
- Be truthful always; admit uncertainties
- Avoid verbosity during discussions unless implementation is requested

## Documentation References

See `docs/` directory for:
- `SAASODOO_PROJECT_SUMMARY.md` - Complete technical architecture
- `ISSUES_LOG.md` - Known issues and resolutions
- `DOCKER_SWARM_MIGRATION_PLAN.md` - Production deployment guide
- `KUBERNETES_MIGRATION_PLAN.md` - Future Kubernetes migration
