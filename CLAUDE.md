## Architecture Overview

### Microservices Architecture
This is a multi-tenant SaaS platform for provisioning Odoo instances. The system consists of:

**Core Services (FastAPI)**:
#- `user-service` (port 8001) - Authentication & user management with Supabase integration
#- `tenant-service` (port 8002) - Tenant management and Docker orchestration  
#- `instance-service` (port 8003) - Odoo instance lifecycle management

**Infrastructure Services**:
- PostgreSQL with separate databases per service (auth, tenant, instance)
- Redis for caching and sessions
- Traefik as reverse proxy with domain-based routing
- Monitoring stack (Prometheus, Grafana)

### Database Security Model
Each service uses its own database user with specific credentials:
- Services must set `DB_SERVICE_USER` and `DB_SERVICE_PASSWORD` environment variables
- No shared database users - enforced by shared/utils/database.py
- Database schemas are centralized in `shared/schemas/`

### Service Communication
- Services communicate via HTTP APIs
- Shared schemas in `shared/schemas/` for data consistency
- Common utilities in `shared/utils/` (database, logger, security)
- Each service has its own Dockerfile and requirements.txt

### Development Environment
- All services run via docker-compose in `infrastructure/compose/docker-compose.dev.yml`
- Traefik provides routing: `api.localhost/user`, `api.localhost/tenant`, `api.localhost/instance`
- Direct access available on ports 8001-8003 for debugging

## Key Patterns

### FastAPI Service Structure
Each service follows consistent structure:
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
└── tests/
```

### Database Connection Pattern
- Use `shared.utils.database.DatabaseManager` for SQLAlchemy sessions
- Environment variables: `DB_SERVICE_USER`, `DB_SERVICE_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_DB`
- Service-specific database names: `auth`, `tenant`, `instance`

### Error Handling
- Services use FastAPI HTTPException with structured error responses
- Health checks at `/health` and `/health/database` endpoints
- Centralized logging configuration via `shared/utils/logger.py`

## Testing Strategy
- Each service has its own test suite in `tests/` directory
- Use pytest with pytest-asyncio for async testing
- Integration tests via docker-compose test environment
- Database connectivity tests in `shared/configs/postgres/test_connectivity.py`

## Current Development Status
- user-service: Working (authentication, user management)
- tenant-service: Working (tenant CRUD operations)  
- instance-service: Working but has known issues
- Frontend web application: Not yet implemented
- Billing and notification services: Not yet implemented
- use  docker compose -f infrastructure/compose/docker-compose.dev.yml up --build up -d to bring up services

 curl -X POST \
    -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    -H "Content-Type: text/plain" \
    -H "X-Killbill-CreatedBy: admin" \
    -d "http://billing-service:8004/api/billing/webhooks/killbill" \
    "http://localhost:8081/1.0/kb/tenants/userKeyValue/PUSH_NOTIFICATION_CB"
	
    	
	● Here are the commands I used:

  1. Check current KillBill test clock time:
  docker exec saasodoo-killbill curl -s -u admin:password -H "X-Killbill-ApiKey: fresh-tenant" -H "X-Killbill-ApiSecret:
   fresh-secret" http://localhost:8080/1.0/kb/test/clock

  2. Get subscription details (to see end time):
  docker exec saasodoo-killbill curl -s -u admin:password -H "X-Killbill-ApiKey: fresh-tenant" -H "X-Killbill-ApiSecret:
   fresh-secret" "http://localhost:8080/1.0/kb/subscriptions/7b30402a-056c-4c85-8c56-f9b38a23268c" | python3 -m
  json.tool

  3. Advance time to specific date (November 4th, 2025):
  docker exec saasodoo-killbill curl -s -u admin:password -H "X-Killbill-ApiKey: fresh-tenant" -H "X-Killbill-ApiSecret:
   fresh-secret" -X POST "http://localhost:8080/1.0/kb/test/clock?requestedDate=2025-11-04T00:00:00.000Z"

  Provisioning Commands

  # Add tenant (run once after reset)
  docker exec saasodoo-killbill curl -v \
    -X POST \
    -u admin:password \
    -H "Content-Type: application/json" \
    -H "X-Killbill-CreatedBy: admin" \
    -d '{"apiKey":"fresh-tenant","apiSecret":"fresh-secret"}' \
    "http://localhost:8080/1.0/kb/tenants"

  # Upload catalog (using the modified killbill_catalog.xml)
  docker exec saasodoo-killbill curl -v \
    -X POST \
    -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    -H "Content-Type: application/xml" \
    -H "X-Killbill-CreatedBy: admin" \
    -d @/var/tmp/killbill_catalog.xml \
    "http://localhost:8080/1.0/kb/tenants/uploadPluginConfig/killbill-catalog"

  Test Clock Commands

  # Check current KillBill time
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    http://localhost:8080/1.0/kb/test/clock

  # Advance time to specific date
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    -X POST \
    "http://localhost:8080/1.0/kb/test/clock?requestedDate=2026-04-01T02:00:00.000Z"

  # Reset to current system time
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    -X POST \
    "http://localhost:8080/1.0/kb/test/clock?requestedDate=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")"

  Account Commands

  # Get account by external key (customer_id)
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    "http://localhost:8080/1.0/kb/accounts?externalKey=CUSTOMER_ID_HERE" | python3 -m json.tool

  # Get account bundles/subscriptions
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    "http://localhost:8080/1.0/kb/accounts/ACCOUNT_ID_HERE/bundles" | python3 -m json.tool

  Subscription Commands

  # Get subscription details
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    "http://localhost:8080/1.0/kb/subscriptions/SUBSCRIPTION_ID_HERE" | python3 -m json.tool

  # Get subscription with grep filters
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    "http://localhost:8080/1.0/kb/subscriptions/SUBSCRIPTION_ID_HERE" | python3 -m json.tool | grep -E
  "state|cancelledDate|chargedThroughDate|phaseType"

  Bundle Commands

  # Get bundle details
  docker exec saasodoo-killbill curl -s -u admin:password \
    -H "X-Killbill-ApiKey: fresh-tenant" \
    -H "X-Killbill-ApiSecret: fresh-secret" \
    "http://localhost:8080/1.0/kb/bundles/BUNDLE_ID_HERE" | python3 -m json.tool

  Health Check

  # Check KillBill health
  docker exec saasodoo-killbill curl -s http://localhost:8080/1.0/healthcheck

  Database Commands

  # Check instance in database
  docker exec saasodoo-postgres psql -U instance_service -d instance -c \
    "SELECT id, name, status, subscription_id, updated_at FROM instances WHERE id = 'INSTANCE_ID_HERE';"

  Note: The killbill_catalog.xml file is located at infrastructure/killbill/killbill_catalog.xml and needs to be copied
  into the KillBill container before uploading.



docker exec saasodoo-killbill curl -s -u admin:password -H "X-Killbill-ApiKey: fresh-tenant" -H "X-Killbill-ApiSecret:
   fresh-secret" "http://localhost:8080/1.0/kb/tenants/userKeyValue/PUSH_NOTIFICATION_CB"
- never ever do things manually unless told to do so
- always include instance-worker when rebuilding instance-service
- you cannot run sudo commands because you cant, advise me on the command you want me to run
- please be trurhful always