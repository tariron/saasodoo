# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Docker & Environment
- `make dev-up` - Start development environment with all services
- `make dev-down` - Stop development environment
- `make dev-logs` - View all service logs
- `make dev-logs-service SERVICE=user-service` - View specific service logs
- `make dev-shell SERVICE=user-service` - Access service shell
- `make dev-restart` - Restart development environment

### Testing & Quality
- `make test` - Run all tests across services
- `make test-service SERVICE=user-service` - Run tests for specific service
- `make format` - Format code using black and isort
- `make lint` - Run flake8 and pylint code linting
- `make security-scan` - Run bandit security analysis

### Database Operations
- `make db-test` - Test database connectivity using shared/configs/postgres/test_connectivity.py
- `make db-reset` - Reset development database (destroys all data)
- `make pgadmin-open` - Open pgAdmin web interface

### Building & Deployment
- `make build` - Build all Docker images
- `make build-service SERVICE=user-service` - Build specific service image

## Architecture Overview

### Microservices Architecture
This is a multi-tenant SaaS platform for provisioning Odoo instances. The system consists of:

**Core Services (FastAPI)**:
- `user-service` (port 8001) - Authentication & user management with Supabase integration
- `tenant-service` (port 8002) - Tenant management and Docker orchestration  
- `instance-service` (port 8003) - Odoo instance lifecycle management

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