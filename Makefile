# Odoo SaaS Kit - Development and Deployment Makefile
.PHONY: help dev-up dev-down dev-logs dev-shell test build prod-deploy swarm-init swarm-deploy

# Default target
help: ## Show this help message
	@echo "Odoo SaaS Kit - Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# =============================================================================
# DEVELOPMENT COMMANDS
# =============================================================================

dev-up: ## Start development environment
	@echo "🚀 Starting development environment..."
	@echo "📋 Ensuring environment file is in place..."
	@copy .env infrastructure\compose\.env > nul 2>&1 || cp .env infrastructure/compose/.env > /dev/null 2>&1 || true
	docker-compose -f infrastructure/compose/docker-compose.dev.yml up -d
	@echo "✅ Development environment started!"
	@echo "   Web App: http://localhost"
	@echo "   Admin: http://admin.localhost"
	@echo "   API Docs: http://api.localhost/docs"
	@echo "   pgAdmin: http://pgadmin.saasodoo.local"

dev-down: ## Stop development environment
	@echo "🛑 Stopping development environment..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml down
	@echo "✅ Development environment stopped!"

dev-restart: ## Restart development environment
	@echo "🔄 Restarting development environment..."
	$(MAKE) dev-down
	$(MAKE) dev-up

dev-logs: ## View development logs
	docker-compose -f infrastructure/compose/docker-compose.dev.yml logs -f

dev-logs-service: ## View logs for specific service (usage: make dev-logs-service SERVICE=web-app)
	docker-compose -f infrastructure/compose/docker-compose.dev.yml logs -f $(SERVICE)

dev-shell: ## Access shell in specific service (usage: make dev-shell SERVICE=web-app)
	docker-compose -f infrastructure/compose/docker-compose.dev.yml exec $(SERVICE) /bin/bash

dev-ps: ## Show running development services
	docker-compose -f infrastructure/compose/docker-compose.dev.yml ps

# =============================================================================
# TESTING COMMANDS
# =============================================================================

test: ## Run all tests
	@echo "🧪 Running all tests..."
	./scripts/test-runner.sh
	@echo "✅ All tests completed!"

test-service: ## Run tests for specific service (usage: make test-service SERVICE=user-service)
	@echo "🧪 Running tests for $(SERVICE)..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml exec $(SERVICE) python -m pytest tests/ -v
	@echo "✅ Tests for $(SERVICE) completed!"

test-integration: ## Run integration tests
	@echo "🧪 Running integration tests..."
	docker-compose -f infrastructure/compose/docker-compose.test.yml up --abort-on-container-exit
	docker-compose -f infrastructure/compose/docker-compose.test.yml down
	@echo "✅ Integration tests completed!"

# =============================================================================
# BUILD COMMANDS
# =============================================================================

build: ## Build all Docker images
	@echo "🔨 Building all Docker images..."
	./scripts/build-all.sh
	@echo "✅ All images built!"

build-service: ## Build specific service image (usage: make build-service SERVICE=web-app)
	@echo "🔨 Building $(SERVICE) image..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml build $(SERVICE)
	@echo "✅ $(SERVICE) image built!"

build-no-cache: ## Build all images without cache
	@echo "🔨 Building all images without cache..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml build --no-cache
	@echo "✅ All images built without cache!"

# =============================================================================
# DATABASE COMMANDS
# =============================================================================

db-test: ## Test database connectivity and setup
	@echo "🧪 Testing database connectivity..."
	python3 shared/configs/postgres/test_connectivity.py --wait
	@echo "✅ Database connectivity test completed!"

db-reset: ## Reset development database
	@echo "🗄️ Resetting development database..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml down -v
	docker-compose -f infrastructure/compose/docker-compose.dev.yml up -d postgres redis
	@echo "⏳ Waiting for database to be ready..."
	sleep 10
	$(MAKE) dev-up
	@echo "✅ Database reset completed!"

db-backup: ## Create database backup
	@echo "💾 Creating database backup..."
	./infrastructure/scripts/backup.sh
	@echo "✅ Database backup completed!"

db-restore: ## Restore database from backup (usage: make db-restore BACKUP_FILE=backup.sql)
	@echo "📥 Restoring database from $(BACKUP_FILE)..."
	docker exec -i $$(docker-compose -f infrastructure/compose/docker-compose.dev.yml ps -q postgres) psql -U odoo_user -d saas_odoo < $(BACKUP_FILE)
	@echo "✅ Database restore completed!"

pgadmin-open: ## Open pgAdmin in browser
	@echo "🌐 Opening pgAdmin in browser..."
	@if [ "$(OS)" = "Windows_NT" ]; then start http://pgadmin.saasodoo.local; else open http://pgadmin.saasodoo.local || xdg-open http://pgadmin.saasodoo.local; fi
	@echo "📝 Login with: admin@saasodoo.local / pgadmin_password_change_me"

pgadmin-reset: ## Reset pgAdmin configuration and data
	@echo "🔄 Resetting pgAdmin configuration..."
	docker-compose -f infrastructure/compose/docker-compose.dev.yml down pgadmin
	docker volume rm saasodoo_pgadmin-data || true
	docker-compose -f infrastructure/compose/docker-compose.dev.yml up -d pgadmin
	@echo "✅ pgAdmin reset completed!"

pgadmin-logs: ## View pgAdmin logs
	docker-compose -f infrastructure/compose/docker-compose.dev.yml logs -f pgadmin

# =============================================================================
# PRODUCTION COMMANDS
# =============================================================================

prod-deploy: ## Deploy to production using Docker Compose
	@echo "🚀 Deploying to production..."
	./infrastructure/scripts/deploy.sh
	@echo "✅ Production deployment completed!"

prod-backup: ## Create production backup
	@echo "💾 Creating production backup..."
	./infrastructure/scripts/backup.sh production
	@echo "✅ Production backup completed!"

prod-restore: ## Restore production from backup
	@echo "📥 Restoring production from backup..."
	./infrastructure/scripts/backup.sh restore $(BACKUP_FILE)
	@echo "✅ Production restore completed!"

prod-logs: ## View production logs
	docker-compose -f infrastructure/compose/docker-compose.prod.yml logs -f

prod-ps: ## Show production services status
	docker-compose -f infrastructure/compose/docker-compose.prod.yml ps

# =============================================================================
# DOCKER SWARM COMMANDS
# =============================================================================

swarm-init: ## Initialize Docker Swarm cluster
	@echo "🐝 Initializing Docker Swarm cluster..."
	./infrastructure/scripts/init-swarm.sh
	@echo "✅ Docker Swarm cluster initialized!"

swarm-deploy: ## Deploy to Docker Swarm
	@echo "🐝 Deploying to Docker Swarm..."
	./infrastructure/scripts/deploy-swarm.sh
	@echo "✅ Swarm deployment completed!"

swarm-scale: ## Scale swarm services (usage: make swarm-scale SERVICE=web-app REPLICAS=3)
	@echo "📈 Scaling $(SERVICE) to $(REPLICAS) replicas..."
	./infrastructure/scripts/scale-services.sh $(SERVICE) $(REPLICAS)
	@echo "✅ Service scaling completed!"

swarm-update: ## Perform rolling update of swarm services
	@echo "🔄 Performing rolling update..."
	./infrastructure/scripts/update-services.sh
	@echo "✅ Rolling update completed!"

swarm-ps: ## Show swarm services status
	docker service ls

swarm-logs: ## View swarm service logs (usage: make swarm-logs SERVICE=web-app)
	docker service logs -f $(SERVICE)

swarm-down: ## Remove swarm stack
	@echo "🛑 Removing swarm stack..."
	docker stack rm odoo-saas
	@echo "✅ Swarm stack removed!"

# =============================================================================
# MIGRATION COMMANDS
# =============================================================================

migrate-to-swarm: ## Migrate from Docker Compose to Swarm
	@echo "🔄 Migrating from Docker Compose to Swarm..."
	./infrastructure/scripts/migrate-to-swarm.sh
	@echo "✅ Migration to Swarm completed!"

validate-stack: ## Validate swarm stack configuration
	@echo "✅ Validating swarm stack configuration..."
	./infrastructure/migration/validate-stack.sh
	@echo "✅ Stack validation completed!"

# =============================================================================
# MONITORING COMMANDS
# =============================================================================

monitoring-up: ## Start monitoring stack
	@echo "📊 Starting monitoring stack..."
	docker-compose -f infrastructure/monitoring/docker-compose.monitoring.yml up -d
	@echo "✅ Monitoring stack started!"
	@echo "   Prometheus: http://monitoring.localhost:9090"
	@echo "   Grafana: http://monitoring.localhost:3000"

monitoring-down: ## Stop monitoring stack
	@echo "📊 Stopping monitoring stack..."
	docker-compose -f infrastructure/monitoring/docker-compose.monitoring.yml down
	@echo "✅ Monitoring stack stopped!"

# =============================================================================
# UTILITY COMMANDS
# =============================================================================

clean: ## Clean up Docker resources
	@echo "🧹 Cleaning up Docker resources..."
	docker system prune -f
	docker volume prune -f
	docker network prune -f
	@echo "✅ Cleanup completed!"

clean-all: ## Clean up all Docker resources including images
	@echo "🧹 Cleaning up all Docker resources..."
	docker system prune -af
	docker volume prune -f
	docker network prune -f
	@echo "✅ Complete cleanup completed!"

setup: ## Initial project setup
	@echo "⚙️ Setting up project..."
	./scripts/dev-setup.sh
	@echo "✅ Project setup completed!"

health-check: ## Check system health
	@echo "🏥 Checking system health..."
	./infrastructure/scripts/health-check.sh
	@echo "✅ Health check completed!"

# =============================================================================
# ENVIRONMENT COMMANDS
# =============================================================================

env-copy: ## Copy .env.example to .env
	@echo "📋 Copying environment template..."
	cp .env.example .env
	@echo "✅ Environment file created! Please edit .env with your values."

env-validate: ## Validate environment configuration
	@echo "✅ Validating environment configuration..."
	@if [ ! -f .env ]; then echo "❌ .env file not found! Run 'make env-copy' first."; exit 1; fi
	@echo "✅ Environment configuration is valid!"

# =============================================================================
# DEVELOPMENT HELPERS
# =============================================================================

install-deps: ## Install development dependencies
	@echo "📦 Installing development dependencies..."
	pip install -r requirements-dev.txt
	@echo "✅ Development dependencies installed!"

format: ## Format code using black and isort
	@echo "🎨 Formatting code..."
	black services/
	isort services/
	@echo "✅ Code formatting completed!"

lint: ## Run code linting
	@echo "🔍 Running code linting..."
	flake8 services/
	pylint services/
	@echo "✅ Code linting completed!"

security-scan: ## Run security scan
	@echo "🔒 Running security scan..."
	bandit -r services/
	@echo "✅ Security scan completed!"

# =============================================================================
# DOCUMENTATION COMMANDS
# =============================================================================

docs-serve: ## Serve documentation locally
	@echo "📚 Serving documentation..."
	mkdocs serve
	@echo "📚 Documentation available at http://localhost:8000"

docs-build: ## Build documentation
	@echo "📚 Building documentation..."
	mkdocs build
	@echo "✅ Documentation built!"

# =============================================================================
# VARIABLES
# =============================================================================

# Default values
SERVICE ?= web-app
REPLICAS ?= 2
BACKUP_FILE ?= backup.sql 