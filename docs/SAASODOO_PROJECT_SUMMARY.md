# SaaSOdoo Platform - Comprehensive Technical Summary

## Executive Overview

SaaSOdoo is a multi-tenant SaaS platform designed to provision, manage, and bill Odoo ERP instances on-demand. The platform operates as a distributed microservices architecture with automated billing integration, container orchestration, and comprehensive monitoring capabilities. This document provides technical specifications for infrastructure planning and Docker Swarm deployment.

---

## 1. Platform Architecture

### 1.1 Microservices Overview

The platform consists of **five core microservices** built with FastAPI/Flask:

1. **User Service** (Port 8001) - Authentication & user management
2. **Instance Service** (Port 8003) - Odoo instance lifecycle management
3. **Billing Service** (Port 8004) - Subscription & payment management with KillBill integration
4. **Notification Service** (Port 5000) - Email & communication management
5. **Frontend Service** (Port 3000) - React-based web application

### 1.2 Service Communication Pattern

- **API Gateway**: Traefik reverse proxy routes requests to microservices based on path/domain
- **Inter-service Communication**: HTTP/REST APIs over internal Docker network
- **Event-Driven Architecture**: KillBill webhooks trigger instance lifecycle events
- **Asynchronous Processing**: Celery workers handle long-running instance operations

### 1.3 Critical Architectural Note: Shared PostgreSQL Server

**IMPORTANT**: All Odoo instances share a **single PostgreSQL server** but each has a **dedicated database**. This is a critical design decision for resource efficiency and manageability:

- **Platform Databases** (microservices metadata):
  - `auth` - User accounts, authentication tokens
  - `billing` - Billing metadata, plan entitlements
  - `instance` - Instance records, configurations
  - `communication` - Notification logs, email templates

- **Customer Instance Databases** (one per Odoo instance):
  - `odoo_customer123_abc12345` - Customer 123's Odoo ERP database
  - `odoo_customer456_def67890` - Customer 456's Odoo ERP database
  - Each database is fully isolated with dedicated connection credentials
  - Database naming pattern: `odoo_{customer_id}_{instance_id_short}`

**Implications for Scaling**:
- PostgreSQL server must handle 100-10,000+ databases
- Connection pooling critical (PgBouncer recommended at scale)
- Database-level resource quotas not enforced (rely on container limits)
- Backup strategy must handle incremental backups per database
- At extreme scale (5,000+ instances), consider sharding PostgreSQL server by customer ID ranges

---

## 2. Complete Docker Compose Architecture

Below is the full `docker-compose.dev.yml` that defines all services, their interconnections, and configurations. This provides a complete view of the deployment structure:

```yaml
version: '3.8'

services:
  # ===== REVERSE PROXY & LOAD BALANCER =====
  traefik:
    image: traefik:v3.0
    container_name: saasodoo-traefik
    restart: unless-stopped
    ports:
      - "80:80"        # HTTP ingress
      - "8080:8080"    # Traefik dashboard
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ../traefik/traefik.yml:/etc/traefik/traefik.yml:ro
    networks:
      - saasodoo-network

  # ===== CORE INFRASTRUCTURE =====

  # Shared PostgreSQL for ALL databases (platform + customer instances)
  postgres:
    image: postgres:15-alpine
    container_name: saasodoo-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      # Platform databases created by init scripts
      POSTGRES_MULTIPLE_DATABASES: auth,billing,instance,communication
      # Service-specific credentials
      POSTGRES_AUTH_SERVICE_PASSWORD: ${POSTGRES_AUTH_SERVICE_PASSWORD}
      POSTGRES_BILLING_SERVICE_PASSWORD: ${POSTGRES_BILLING_SERVICE_PASSWORD}
      POSTGRES_INSTANCE_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ../../shared/configs/postgres:/docker-entrypoint-initdb.d
    networks:
      - saasodoo-network
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Redis for caching and Celery backend
  redis:
    image: redis:7-alpine
    container_name: saasodoo-redis
    restart: unless-stopped
    command: redis-server /etc/redis/redis.conf
    volumes:
      - redis-data:/data
      - ../../shared/configs/redis.conf:/etc/redis/redis.conf:ro
    networks:
      - saasodoo-network
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s

  # RabbitMQ for Celery task queues
  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: saasodoo-rabbitmq
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
      RABBITMQ_DEFAULT_VHOST: saasodoo
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    networks:
      - saasodoo-network
    ports:
      - "5672:5672"   # AMQP
      - "15672:15672" # Management UI
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
      interval: 10s

  # ===== BILLING INFRASTRUCTURE (KillBill) =====

  # KillBill MariaDB (separate from main PostgreSQL)
  killbill-db:
    image: killbill/mariadb:0.24
    container_name: saasodoo-killbill-db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: killbill
    volumes:
      - killbill-db-data:/var/lib/mysql
    networks:
      - saasodoo-network
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect"]
      interval: 10s

  # KillBill Billing Engine
  killbill:
    image: killbill/killbill:0.24.15
    container_name: saasodoo-killbill
    restart: unless-stopped
    environment:
      KILLBILL_DAO_URL: jdbc:mysql://killbill-db:3306/killbill
      KILLBILL_DAO_USER: root
      KILLBILL_DAO_PASSWORD: killbill
      KILLBILL_SERVER_MULTITENANT: true
      KILLBILL_USERNAME: ${KILLBILL_USERNAME}
      KILLBILL_PASSWORD: ${KILLBILL_PASSWORD}
      KILLBILL_API_KEY: ${KILLBILL_API_KEY}
      KILLBILL_API_SECRET: ${KILLBILL_API_SECRET}
      KILLBILL_NOTIFICATION_URL: http://billing-service:8004/api/billing/webhooks/killbill
      KILLBILL_SERVER_TEST_MODE: true  # Enables clock manipulation
    networks:
      - saasodoo-network
    depends_on:
      killbill-db:
        condition: service_healthy
    ports:
      - "8081:8080"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/1.0/healthcheck"]
      interval: 30s
      start_period: 180s

  # Kaui Admin UI for KillBill
  kaui:
    image: killbill/kaui:latest
    container_name: saasodoo-kaui
    restart: unless-stopped
    environment:
      KAUI_KILLBILL_URL: http://killbill:8080
      KAUI_KILLBILL_API_KEY: ${KILLBILL_API_KEY}
      KAUI_KILLBILL_API_SECRET: ${KILLBILL_API_SECRET}
      KAUI_CONFIG_DAO_URL: jdbc:mysql://killbill-db:3306/kaui
      KAUI_CONFIG_DAO_USER: root
      KAUI_CONFIG_DAO_PASSWORD: killbill
      KAUI_ROOT_USERNAME: admin
      KAUI_ROOT_PASSWORD: password
    networks:
      - saasodoo-network
    depends_on:
      killbill:
        condition: service_healthy
    ports:
      - "9090:8080"

  # ===== MICROSERVICES =====

  # User Service - Authentication & User Management
  user-service:
    build:
      context: ../../services/user-service
      dockerfile: Dockerfile
    container_name: saasodoo-user-service
    restart: unless-stopped
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: auth
      DB_SERVICE_USER: ${POSTGRES_AUTH_SERVICE_USER}
      DB_SERVICE_PASSWORD: ${POSTGRES_AUTH_SERVICE_PASSWORD}
      REDIS_HOST: redis
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
    volumes:
      - ../../shared:/app/shared:ro
    networks:
      - saasodoo-network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "8001:8001"
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"]
      interval: 30s

  # Instance Service - Odoo Instance Lifecycle Management
  instance-service:
    build:
      context: ../../services/instance-service
      dockerfile: Dockerfile
    container_name: saasodoo-instance-service
    restart: unless-stopped
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: instance
      DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER}
      DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD}
      REDIS_HOST: redis
      DOCKER_HOST: unix:///var/run/docker.sock
    volumes:
      - ../../shared:/app/shared:ro
      - /var/run/docker.sock:/var/run/docker.sock  # Docker orchestration
      - odoo-backups:/var/lib/odoo/backups
      - /mnt/cephfs:/mnt/cephfs:rw  # CephFS for instance storage
    networks:
      - saasodoo-network
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    ports:
      - "8003:8003"

  # Instance Worker - Celery Background Tasks
  instance-worker:
    build:
      context: ../../services/instance-service
      dockerfile: Dockerfile
    container_name: saasodoo-instance-worker
    restart: unless-stopped
    command: celery -A app.celery_config worker --loglevel=info --queues=instance_provisioning,instance_operations,instance_maintenance,instance_monitoring
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: instance
      DB_SERVICE_USER: ${POSTGRES_INSTANCE_SERVICE_USER}
      DB_SERVICE_PASSWORD: ${POSTGRES_INSTANCE_SERVICE_PASSWORD}
      POSTGRES_USER: ${POSTGRES_USER}  # Admin for creating instance databases
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      REDIS_HOST: redis
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      DOCKER_HOST: unix:///var/run/docker.sock
    volumes:
      - ../../shared:/app/shared:ro
      - /var/run/docker.sock:/var/run/docker.sock
      - odoo-backups:/var/lib/odoo/backups
      - /mnt/cephfs:/mnt/cephfs:rw
    networks:
      - saasodoo-network
    depends_on:
      postgres:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy

  # Billing Service - KillBill Integration & Subscription Management
  billing-service:
    build:
      context: ../../services/billing-service
      dockerfile: Dockerfile
    container_name: saasodoo-billing-service
    restart: unless-stopped
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_DB: billing
      DB_SERVICE_USER: ${POSTGRES_BILLING_SERVICE_USER}
      DB_SERVICE_PASSWORD: ${POSTGRES_BILLING_SERVICE_PASSWORD}
      KILLBILL_URL: ${KILLBILL_URL}
      KILLBILL_API_KEY: ${KILLBILL_API_KEY}
      KILLBILL_API_SECRET: ${KILLBILL_API_SECRET}
      KILLBILL_USERNAME: ${KILLBILL_USERNAME}
      KILLBILL_PASSWORD: ${KILLBILL_PASSWORD}
      REDIS_HOST: redis
    volumes:
      - ../../shared:/app/shared:ro
    networks:
      - saasodoo-network
    depends_on:
      postgres:
        condition: service_healthy
      killbill:
        condition: service_healthy
    ports:
      - "8004:8004"

  # Notification Service - Email & Communication
  notification-service:
    build:
      context: ../../services/notification-service
      dockerfile: Dockerfile
    container_name: saasodoo-notification-service
    restart: unless-stopped
    environment:
      SMTP_HOST: mailhog
      SMTP_PORT: 1025
      SMTP_USE_TLS: false
      DEFAULT_FROM_EMAIL: noreply@saasodoo.local
      DB_DATABASE_URL: postgresql://notification_service:${POSTGRES_NOTIFICATION_PASSWORD}@postgres:5432/communication
    volumes:
      - ../../shared:/app/shared:ro
    networks:
      - saasodoo-network
    depends_on:
      postgres:
        condition: service_healthy
      mailhog:
        condition: service_started

  # Frontend Service - React Web Application
  frontend-service:
    build:
      context: ../../services/frontend-service
      dockerfile: Dockerfile
    container_name: saasodoo-frontend
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - BASE_DOMAIN=${BASE_DOMAIN}
    networks:
      - saasodoo-network

  # ===== MONITORING & OBSERVABILITY =====

  prometheus:
    image: prom/prometheus:latest
    container_name: saasodoo-prometheus
    volumes:
      - ../monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus-data:/prometheus
    networks:
      - saasodoo-network

  grafana:
    image: grafana/grafana:latest
    container_name: saasodoo-grafana
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana-data:/var/lib/grafana
    networks:
      - saasodoo-network

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.8.0
    container_name: saasodoo-elasticsearch
    environment:
      - discovery.type=single-node
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    volumes:
      - elasticsearch-data:/usr/share/elasticsearch/data
    networks:
      - saasodoo-network

  kibana:
    image: docker.elastic.co/kibana/kibana:8.8.0
    container_name: saasodoo-kibana
    environment:
      ELASTICSEARCH_HOSTS: http://elasticsearch:9200
    networks:
      - saasodoo-network
    depends_on:
      - elasticsearch

  # ===== DEVELOPMENT TOOLS =====

  mailhog:
    image: mailhog/mailhog:latest
    container_name: saasodoo-mailhog
    networks:
      - saasodoo-network

  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: saasodoo-pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@saasodoo.local
      PGADMIN_DEFAULT_PASSWORD: admin
    volumes:
      - pgadmin-data:/var/lib/pgadmin
    networks:
      - saasodoo-network
    depends_on:
      - postgres

  minio:
    image: minio/minio:latest
    container_name: saasodoo-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY}
    volumes:
      - minio-data:/data
    networks:
      - saasodoo-network

networks:
  saasodoo-network:
    driver: bridge
    name: saasodoo-network

volumes:
  postgres-data:     # Shared PostgreSQL data (all databases)
  redis-data:
  rabbitmq-data:
  killbill-db-data:
  prometheus-data:
  grafana-data:
  elasticsearch-data:
  minio-data:
  pgadmin-data:
  odoo-backups:
```

**Key Architectural Highlights from Docker Compose**:

1. **Single PostgreSQL Container** - Hosts 4 platform databases + 1 database per Odoo instance (scales to thousands of databases)
2. **Instance Worker** - Has PostgreSQL admin credentials to create new databases for each Odoo instance
3. **CephFS Mount** - `/mnt/cephfs` shared across instance-service and instance-worker for distributed storage
4. **Docker Socket Mount** - instance-service and instance-worker manage Docker containers via `/var/run/docker.sock`
5. **Service Dependencies** - Explicit healthcheck-based startup ordering (e.g., billing-service waits for KillBill)
6. **Network Isolation** - All services on `saasodoo-network` bridge network with service discovery by name

---

## 3. Core Business Functionality

### 3.1 Customer Journey - New User Signup

1. **Account Creation**
   - User registers via frontend (user-service)
   - Account created in PostgreSQL auth database
   - Session established in Redis

2. **Plan Selection**
   - User browses available plans (starter, professional, enterprise)
   - Plans stored in KillBill catalog with pricing, trials, and resource limits
   - Each plan defines: CPU cores, RAM, storage, and billing cycle

3. **Trial Instance Provisioning**
   - User selects plan with trial period (e.g., 14-day free trial)
   - Billing-service creates KillBill account and subscription
   - KillBill fires `SUBSCRIPTION_CREATION` webhook (actionType=EFFECTIVE)
   - Billing-service webhook handler:
     - Validates trial eligibility (one trial per customer)
     - Calls instance-service to create instance record
     - Triggers Celery provisioning task
   - Instance-worker (Celery):
     - Creates PostgreSQL database for Odoo
     - Provisions Docker container with resource limits
     - Mounts CephFS storage with quota
     - Initializes Odoo with customer configuration
     - Configures Traefik routing for subdomain access
   - Instance becomes accessible at `{subdomain}.saasodoo.com`

4. **Trial Period**
   - Instance runs with status `billing_status=trial`
   - User can access full functionality during trial
   - KillBill tracks trial expiration date

5. **Trial-to-Paid Transition**
   - Trial expires, KillBill fires `SUBSCRIPTION_PHASE` webhook (phaseType=EVERGREEN)
   - Instance `billing_status` updated to `payment_required`
   - Invoice generated automatically by KillBill
   - User receives notification email

6. **Payment & Instance Activation**
   - User adds payment method and pays first invoice
   - KillBill fires `INVOICE_PAYMENT_SUCCESS` webhook
   - Billing-service verifies payment and updates instance to `billing_status=paid`
   - Instance transitions to running paid subscription

### 3.2 Customer Journey - Active Subscription Management

#### Plan Upgrades/Downgrades
1. User selects new plan from frontend
2. Billing-service calls KillBill to change subscription plan
3. KillBill fires `SUBSCRIPTION_CHANGE` webhook (actionType=EFFECTIVE)
4. Instance-service applies new resource limits:
   - CPU/memory updated live via Docker API (zero downtime)
   - Storage quota updated via CephFS setfattr
5. User receives upgrade confirmation email

#### Recurring Billing
1. KillBill generates monthly/annual invoice automatically
2. `INVOICE_CREATION` webhook fires → customer receives invoice email
3. Payment processor charges customer
4. `INVOICE_PAYMENT_SUCCESS` webhook → instance remains active
5. If payment fails:
   - `INVOICE_PAYMENT_FAILED` webhook fires
   - Instance immediately suspended (container stopped, status=PAUSED)
   - User receives payment failure notification
6. If invoice becomes overdue (configurable grace period):
   - `INVOICE_OVERDUE` webhook fires
   - Instance suspension confirmed
   - Escalation emails sent

#### Subscription Cancellation
1. User requests cancellation via frontend
2. Billing-service calls KillBill cancel API with `END_OF_TERM` policy
3. KillBill fires `SUBSCRIPTION_CANCEL` webhook (actionType=REQUESTED)
   - Cancellation recorded, instance continues running
   - User receives cancellation confirmation email with end date
4. At end of billing period:
   - `SUBSCRIPTION_CANCEL` webhook (actionType=EFFECTIVE)
   - Instance terminated (container stopped, status=TERMINATED)
   - Any unpaid invoices written off (debt forgiven)
   - User receives termination notification with backup instructions
5. Instance data retained for 30 days for reactivation

#### Instance Reactivation
1. User requests reactivation of terminated instance
2. Frontend calls billing-service to create new subscription
3. New subscription metadata includes `target_instance_id` and `reactivation=true`
4. Payment required upfront (no new trial)
5. Upon payment:
   - Instance status changes from TERMINATED → STOPPED → RUNNING
   - Existing container/data restarted with new subscription_id
   - User receives reactivation success email

### 3.3 Instance Lifecycle States

**Provisioning Status**: `pending` → `provisioning` → `ready` → `terminated`

**Billing Status**: `trial` → `payment_required` → `paid` | `overdue` | `suspended`

**Instance Status**:
- `creating` - Initial provisioning
- `starting` - Container booting
- `running` - Active and accessible
- `stopping` - Graceful shutdown
- `stopped` - Container halted but can restart
- `paused` - Suspended due to billing issues
- `terminated` - Permanently shut down, awaiting cleanup
- `error` - Provisioning/runtime failure

---

## 4. Infrastructure Components

### 4.1 Core Infrastructure Services

#### PostgreSQL (Port 5432)
- **Image**: `postgres:15-alpine`
- **Purpose**: Primary data store for ALL microservices AND all Odoo instances
- **Critical Architecture**: Single PostgreSQL server hosting thousands of databases
- **Platform Databases** (4 databases):
  - `auth` - User accounts, sessions, authentication
  - `billing` - Billing metadata, plan entitlements
  - `instance` - Instance records, configurations, status
  - `communication` - Notification logs, email templates
- **Customer Instance Databases** (one per Odoo instance):
  - `odoo_{customer_id}_{instance_id_short}` - Dedicated Odoo ERP database per instance
  - Example: `odoo_cust789_abc12345` for customer 789's instance
  - Each database fully isolated with unique credentials
  - **Database Count Scaling**: 100 instances = 104 databases, 1,000 instances = 1,004 databases, 10,000 instances = 10,004 databases
- **Security**: Service-specific credentials per database + per-instance database users
- **Connection Management**:
  - **PgBouncer Required** at 500+ instances for connection pooling
  - Each Odoo container maintains 2-10 database connections
  - Platform services use connection pools (asyncpg, SQLAlchemy)
- **High Availability Needs**:
  - Master-replica replication (streaming replication)
  - Automated backups with per-database granularity
  - pg_dump per database for customer data isolation
- **Estimated Total Database Size**:
  - 100 instances: ~5-10 GB (platform) + ~50-100 GB (customer databases) = **~60-110 GB total**
  - 1,000 instances: ~10-20 GB (platform) + ~500 GB-1 TB (customer databases) = **~510 GB-1 TB total**
  - 10,000 instances: ~20-50 GB (platform) + ~5-10 TB (customer databases) = **~5-10 TB total**
- **Query Load Estimate**:
  - 100 instances: ~500-1,000 queries/sec
  - 1,000 instances: ~5,000-10,000 queries/sec
  - 10,000 instances: ~50,000-100,000 queries/sec (requires read replicas + sharding)

#### Redis (Port 6379)
- **Image**: `redis:7-alpine`
- **Purpose**:
  - Session storage for user authentication
  - Caching layer for frequently accessed data
  - Celery task result backend
- **Persistence**: RDB snapshots enabled
- **High Availability Needs**: Redis Sentinel or Redis Cluster
- **Estimated Load**:
  - 100 users: ~50 MB memory, ~100 ops/sec
  - 1,000 users: ~500 MB, ~1,000 ops/sec
  - 10,000 users: ~5 GB, ~10,000 ops/sec

#### RabbitMQ (Ports 5672, 15672)
- **Image**: `rabbitmq:3-management-alpine`
- **Purpose**: Message broker for Celery task queues
- **Queues**:
  - `instance_provisioning` - New instance creation (CPU-intensive)
  - `instance_operations` - Start/stop/restart operations
  - `instance_maintenance` - Backups, updates, scaling
  - `instance_monitoring` - Health checks, metrics collection
- **Management UI**: Port 15672
- **High Availability Needs**: RabbitMQ cluster with mirrored queues
- **Estimated Load**:
  - Peak provisioning: 10 concurrent tasks
  - Steady state: ~100 messages/hour

#### Traefik (Ports 80, 8080)
- **Image**: `traefik:v3.0`
- **Purpose**:
  - Reverse proxy and load balancer
  - Automatic SSL/TLS termination
  - Service discovery via Docker labels
  - Dynamic routing for customer subdomains
- **Routing Examples**:
  - `api.saasodoo.com/user/*` → user-service:8001
  - `api.saasodoo.com/billing/*` → billing-service:8004
  - `api.saasodoo.com/instance/*` → instance-service:8003
  - `app.saasodoo.com` → frontend-service:3000
  - `customer123.saasodoo.com` → Odoo instance container
- **Dashboard**: Port 8080
- **High Availability Needs**: Multiple Traefik replicas with shared config

### 4.2 Billing Infrastructure (KillBill)

#### KillBill MariaDB (Internal Port 3306)
- **Image**: `killbill/mariadb:0.24`
- **Purpose**: KillBill billing engine database
- **Databases**: `killbill`, `kaui` (admin UI)
- **Pre-built Schemas**: Included in image
- **Estimated Size**: ~1 GB per 10,000 subscriptions

#### KillBill Billing Engine (Port 8081)
- **Image**: `killbill/killbill:0.24.15`
- **Purpose**:
  - Subscription lifecycle management
  - Invoice generation and payment tracking
  - Trial period management
  - Webhook event publishing
  - Overdue handling with configurable grace periods
- **Multi-tenancy**: Enabled (tenant: fresh-tenant)
- **Test Mode**: Enabled (allows clock manipulation for testing)
- **Memory**: JVM 512 MB-1 GB
- **Critical Configuration**:
  - `KILLBILL_NOTIFICATION_URL` - Webhook endpoint for billing-service
  - `KILLBILL_SERVER_TEST_MODE=true` - Clock control for dev/staging

#### Kaui Admin UI (Port 9090)
- **Image**: `killbill/kaui:latest`
- **Purpose**: Web-based KillBill administration
- **Features**:
  - Account/subscription management
  - Invoice viewing and adjustment
  - Payment retry
  - Catalog management
- **Default Credentials**: admin/password

### 4.3 Monitoring & Observability Stack

#### Prometheus (Internal Port 9090)
- **Image**: `prom/prometheus:latest`
- **Purpose**: Metrics collection and time-series database
- **Targets**:
  - All microservices (/metrics endpoints)
  - Docker daemon metrics
  - Node exporter (system metrics)
  - Instance container metrics
- **Retention**: 200 hours (configurable)
- **Estimated Storage**: ~10 GB per 1,000 instances

#### Grafana (Internal Port 3000, routed via Traefik)
- **Image**: `grafana/grafana:latest`
- **Purpose**: Visualization and alerting dashboard
- **Pre-configured Datasources**: Prometheus, Elasticsearch
- **Dashboards** (planned):
  - Instance health and performance
  - Billing revenue and churn metrics
  - Resource utilization per plan tier
  - API request rates and latencies
- **Alerting**: Email/Slack notifications for critical events

#### Elasticsearch (Internal Port 9200)
- **Image**: `elasticsearch:8.8.0`
- **Purpose**: Centralized log aggregation
- **JVM Memory**: 512 MB-1 GB (configurable via ES_JAVA_OPTS)
- **Estimated Storage**: ~5 GB per 1,000 instances per week

#### Kibana (Internal Port 5601, routed via Traefik)
- **Image**: `kibana:8.8.0`
- **Purpose**: Log visualization and search
- **Index Patterns**: Service logs, instance logs, access logs

### 4.4 Development & Administration Tools

#### MailHog (Port 8025)
- **Image**: `mailhog/mailhog:latest`
- **Purpose**: Email testing (development only)
- **Features**: SMTP server + web UI for viewing sent emails
- **Production**: Replace with SendGrid/AWS SES/Mailgun

#### PgAdmin (Port 80, routed via Traefik)
- **Image**: `dpage/pgadmin4:latest`
- **Purpose**: PostgreSQL administration GUI
- **Pre-configured**: Server definitions via servers.json

#### MinIO (Ports 9000, 9001)
- **Image**: `minio/minio:latest`
- **Purpose**: S3-compatible object storage for backups and file uploads
- **Usage**: Instance backups, custom Odoo modules, document storage
- **Estimated Storage**: ~100 GB per 1,000 instances (backups + attachments)

---

## 5. Storage Architecture

### 5.1 CephFS Distributed Storage

**Purpose**:
- Primary storage for Odoo instance data
- Shared filesystem across Docker Swarm nodes
- Per-instance quotas and isolation

**Mount Point**: `/mnt/cephfs`

**Directory Structure**:
```
/mnt/cephfs/
├── odoo_instances/
│   ├── odoo_data_{db_name}_{instance_id}/  # Odoo filestore per instance
│   │   ├── addons/
│   │   ├── filestore/
│   │   └── sessions/
```

**Quota Management**:
- Set via `setfattr -n ceph.quota.max_bytes`
- Enforced per-instance (e.g., 10 GB starter, 50 GB professional, 200 GB enterprise)
- Live quota updates for plan upgrades (zero downtime)

**High Availability Requirements**:
- MicroCeph cluster: Minimum 3 nodes for replication
- Replication factor: 3 (configurable via Ceph pools)
- Monitor daemons: 3+ for quorum
- Manager daemons: 2+ for redundancy

**Estimated Capacity**:
- 100 instances: ~1 TB (avg 10 GB per instance)
- 1,000 instances: ~10 TB
- 10,000 instances: ~100 TB

### 5.2 Docker Volume Storage

**Volume Types**:
- `postgres-data` - PostgreSQL data directory (~50-500 GB depending on scale)
- `redis-data` - Redis RDB snapshots (~5-50 GB)
- `rabbitmq-data` - RabbitMQ persistence (~1-10 GB)
- `killbill-db-data` - KillBill MariaDB (~1-10 GB)
- `prometheus-data` - Metrics time-series (~10-100 GB)
- `grafana-data` - Dashboard configurations (~1 GB)
- `elasticsearch-data` - Log indices (~50-500 GB)
- `minio-data` - Backup storage (~100-1000 GB)
- `odoo-backups` - Instance backup archives (~100-1000 GB)

**Backup Strategy**:
- Database backups: Daily full + hourly incremental
- CephFS snapshots: Hourly (retained 24 hours), daily (retained 7 days)
- MinIO backups: Weekly full backup to external S3

---

## 6. Networking & Routing

### 6.1 Docker Network

**Network Mode**: Bridge (`saasodoo-network`)

**Service Discovery**:
- All containers communicate via service name (e.g., `http://user-service:8001`)
- Traefik uses Docker labels for automatic service registration

### 6.2 External Access Patterns

**API Gateway (Traefik)**:
- `api.saasodoo.com` - Microservice APIs
- `app.saasodoo.com` - Frontend web application
- `*.saasodoo.com` - Customer Odoo instances (wildcard DNS + routing)

**Admin Interfaces**:
- `traefik.saasodoo.com` - Traefik dashboard
- `grafana.saasodoo.com` - Grafana monitoring
- `kibana.saasodoo.com` - Kibana logs
- `billing.saasodoo.com` - KillBill API (direct access)
- `billing-admin.saasodoo.com` - Kaui admin UI
- `minio.saasodoo.com` - MinIO console
- `pgadmin.saasodoo.com` - PgAdmin database admin

### 6.3 Port Mapping

**Exposed Ports (for Docker Swarm external access)**:
- 80/443 - HTTP/HTTPS (Traefik ingress)
- 5432 - PostgreSQL (internal cluster only)
- 6379 - Redis (internal cluster only)
- 8001, 8003, 8004 - Microservices (direct debug access, optional)
- 8081 - KillBill API (direct access for admin)
- 9090 - Kaui admin UI (direct access)

---

## 7. Background Processing Architecture

### 7.1 Celery Workers

**Instance Worker** (`instance-worker` container):
- **Purpose**: Asynchronous instance operations
- **Concurrency**: 4-8 workers per node (configurable)
- **Tasks**:
  - `provision_instance_task` - Create new Odoo container (20-60 seconds)
  - `start_instance_task` - Start stopped instance (5-15 seconds)
  - `stop_instance_task` - Graceful container shutdown (10-30 seconds)
  - `restart_instance_task` - Container restart (15-45 seconds)
  - `backup_instance_task` - Database + filestore backup (60-300 seconds)
  - `restore_instance_task` - Restore from backup (120-600 seconds)
  - `update_instance_task` - Odoo version upgrade (300-1800 seconds)
  - `monitor_docker_events_task` - Container status monitoring (continuous)

**Queue Prioritization**:
1. `instance_provisioning` - New instance creation (high priority)
2. `instance_operations` - Start/stop/restart (medium priority)
3. `instance_maintenance` - Backups, updates (low priority)
4. `instance_monitoring` - Health checks (background)

**Resource Requirements per Worker**:
- CPU: 0.5-1.0 cores
- Memory: 512 MB - 1 GB
- Disk I/O: High during provisioning/backups

### 7.2 Task Failure Handling

**No Automatic Retries**: Configured with `task_max_retries=0`

**Failure States**:
- Instance transitions to `status=error`
- Error message stored in database
- Admin notification sent
- Manual retry via frontend admin panel

**Monitoring**:
- Celery Flower dashboard (optional deployment)
- Prometheus metrics for queue depth and task duration

---

## 8. Docker Swarm Deployment Considerations

### 8.1 Service Placement Constraints

**Stateful Services** (require persistent storage):
- PostgreSQL - Pin to specific node or use shared volume
- Redis - Persistent RDB, pin to node or replicate
- RabbitMQ - Cluster mode across multiple nodes
- KillBill MariaDB - Pin to specific node with persistent volume

**Stateless Services** (can scale horizontally):
- user-service - 2+ replicas
- instance-service - 2+ replicas
- billing-service - 2+ replicas
- notification-service - 2+ replicas
- frontend-service - 2+ replicas
- instance-worker - 4-8 replicas (scale with instance count)

**Singleton Services** (1 replica only):
- Traefik - 1-2 replicas with shared config
- Prometheus - 1 replica (or federated setup)
- Grafana - 1 replica (or use external Grafana Cloud)

### 8.2 Resource Allocation Strategy

**Manager Nodes** (minimum 3 for HA):
- Purpose: Swarm orchestration, service scheduling
- CPU: 4 cores
- Memory: 8 GB
- Disk: 100 GB SSD

**Database Nodes** (dedicated for stateful services):
- PostgreSQL, Redis, RabbitMQ, KillBill MariaDB
- CPU: 8-16 cores
- Memory: 32-64 GB
- Disk: 500 GB - 1 TB SSD (NVMe preferred)
- RAID 10 for database volumes

**Application Nodes** (microservices + workers):
- CPU: 16-32 cores
- Memory: 32-64 GB
- Disk: 200 GB SSD (OS + container images)
- Network: 10 Gbps preferred

**Instance Nodes** (Odoo containers):
- Purpose: Host customer Odoo instances
- CPU: 32-64 cores (oversubscription ~2:1 acceptable)
- Memory: 128-256 GB (2 GB per instance average)
- Disk: Minimal local storage (CephFS for instance data)
- Network: 10 Gbps required (high CephFS I/O)

**Storage Nodes** (MicroCeph cluster):
- Purpose: CephFS distributed storage
- CPU: 8-16 cores
- Memory: 16-32 GB (more for cache performance)
- Disk:
  - OS: 100 GB SSD
  - OSD disks: Multiple NVMe SSDs (1-4 TB each, total capacity = instances × avg_storage × replication_factor)
- Network: 25 Gbps preferred (dedicated storage network)

**Monitoring Nodes** (optional, can colocate):
- Prometheus, Grafana, Elasticsearch, Kibana
- CPU: 8 cores
- Memory: 16-32 GB
- Disk: 500 GB SSD (metrics + logs)

### 8.3 Scaling Strategy

**Initial Deployment (100-500 instances)**:
- 3 manager nodes
- 3 database nodes (combined PostgreSQL, Redis, RabbitMQ)
- 3 application nodes (microservices + workers)
- 3 instance nodes (Odoo containers)
- 3 storage nodes (MicroCeph, replication factor 3)
- **Total**: 15 nodes

**Medium Scale (500-2,000 instances)**:
- 3 manager nodes
- 6 database nodes (separate PostgreSQL, Redis/RabbitMQ)
- 6 application nodes
- 10 instance nodes
- 5 storage nodes (MicroCeph with more OSD disks)
- **Total**: 30 nodes

**Large Scale (2,000-10,000 instances)**:
- 5 manager nodes
- 10 database nodes (PostgreSQL read replicas, Redis cluster)
- 10 application nodes
- 40 instance nodes
- 10 storage nodes (MicroCeph horizontal scaling)
- **Total**: 75 nodes

### 8.4 Network Bandwidth Estimates

**Per Instance Average**:
- Ingress: 1-5 Mbps (user traffic)
- Egress: 1-5 Mbps
- CephFS I/O: 5-20 Mbps (database + file operations)

**Cluster-wide Estimates**:
- 100 instances: ~1 Gbps total bandwidth
- 1,000 instances: ~10 Gbps
- 10,000 instances: ~100 Gbps (requires multiple uplinks + bonding)

**CephFS Network**:
- Dedicated storage network strongly recommended (VLAN isolation)
- 10 Gbps minimum, 25 Gbps preferred for 1,000+ instances
- Low latency critical (<1 ms preferred)

---

## 9. Security & Isolation

### 9.1 Database Security

**Service-Specific Credentials**:
- Each microservice uses dedicated database user with minimal privileges
- Example: `auth_service` can only access `auth` database
- No shared admin credentials in application code

**Connection Encryption**:
- PostgreSQL SSL/TLS connections (production)
- Password authentication + connection limits per user

### 9.2 Container Isolation

**Odoo Instance Containers**:
- Each customer instance runs in isolated Docker container
- Resource limits enforced: CPU, memory (cgroups)
- Storage quotas enforced: CephFS per-directory quotas
- No privileged containers for customer workloads
- Network isolation via Docker networks

**Security Scanning**:
- Regular vulnerability scanning of base images
- Automated image updates for security patches

### 9.3 API Security

**Authentication**:
- JWT tokens for API authentication
- Token expiry: 24 hours (configurable)
- Refresh token rotation

**Authorization**:
- Role-based access control (RBAC)
- Customer data isolation (multi-tenancy)

**Rate Limiting**:
- API rate limits per customer
- DDoS protection via Traefik middleware

---

## 10. Backup & Disaster Recovery

### 10.1 Backup Schedule

**Databases**:
- PostgreSQL: Daily full backup + hourly WAL archiving
- Retention: 30 days full backups, 7 days WAL logs
- Storage: MinIO + offsite S3 replication

**Instance Data**:
- CephFS snapshots: Hourly (24 hour retention), daily (7 day retention)
- Customer-initiated backups: Stored in MinIO, retained 90 days
- Automatic backups before plan upgrades/updates

**Configuration**:
- Docker Compose files, Traefik configs: Version controlled (Git)
- KillBill catalog: Backed up with database

### 10.2 Recovery Time Objectives (RTO)

**Service Tier Failures**:
- Microservice crash: <1 minute (Docker Swarm auto-restart)
- Database node failure: 2-5 minutes (failover to replica)
- Storage node failure: <1 minute (Ceph rebalancing, no downtime)

**Catastrophic Failures**:
- Full cluster loss: 4-8 hours (restore from offsite backups)
- Data center failure: 1-4 hours (failover to DR site, if configured)

### 10.3 High Availability Targets

**Service Availability**:
- Target: 99.9% uptime (8.76 hours downtime/year)
- Achieved via: Service replication, health checks, auto-restart

**Data Durability**:
- Target: 99.999999999% (11 nines)
- Achieved via: Ceph replication (3x), offsite backups, WAL archiving

---

## 11. Monitoring & Alerting

### 11.1 Key Metrics

**Infrastructure Metrics**:
- Node CPU/memory/disk usage
- Network bandwidth and latency
- CephFS cluster health and capacity
- Docker Swarm service health

**Application Metrics**:
- API request rates and latencies (p50, p95, p99)
- Error rates per service
- Celery queue depths and task durations
- Database connection pool utilization

**Business Metrics**:
- Active instances by plan tier
- Monthly recurring revenue (MRR)
- Churn rate (cancelled subscriptions)
- Trial-to-paid conversion rate
- Average instance resource utilization

### 11.2 Critical Alerts

**Infrastructure**:
- Node disk usage >85%
- CephFS cluster health degraded
- Database connection failures
- Service replica count below desired state

**Application**:
- API error rate >5%
- Celery queue backlog >100 tasks
- Instance provisioning failures
- KillBill webhook failures

**Business**:
- Payment gateway downtime
- Spike in subscription cancellations
- Instance termination errors

---

## 13. Performance Benchmarks

### 13.1 Instance Provisioning

**Time to Provision**:
- Trial instance (automated): 30-60 seconds
- Paid instance (after payment): 45-90 seconds
- Total time (signup to access): 2-5 minutes

**Bottlenecks**:
- Odoo database initialization: 20-30 seconds
- Docker image pull (first time): 30-60 seconds
- CephFS directory creation: 2-5 seconds

### 13.2 API Response Times (p95)

- User authentication: <200 ms
- Instance list: <300 ms
- Instance creation (queued): <500 ms
- Plan upgrade (billing API): <1,000 ms
- Webhook processing: <2,000 ms

### 13.3 Database Query Performance

- User login query: <10 ms
- Instance lookup: <15 ms
- Billing history query: <50 ms
- Analytics aggregation: <500 ms

---

## 14. Deployment Pipeline

### 14.1 CI/CD Workflow

**Development**:
1. Code commit to feature branch
2. Automated tests run (pytest, unit tests)
3. Code review and approval
4. Merge to `main` branch

**Staging**:
1. Docker images built automatically
2. Deployed to staging Docker Swarm cluster
3. Integration tests + smoke tests
4. Manual QA testing

**Production**:
1. Tag release in Git
2. Build production Docker images
3. Rolling deployment to Docker Swarm (zero downtime)
4. Health checks verify service availability
5. Rollback if errors detected

### 14.2 Rollback Strategy

- **Docker Swarm Rollback**: `docker service update --rollback`
- **Database Migrations**: Forward-compatible migrations, manual rollback if needed
- **Configuration**: Version-controlled, Git revert for quick rollback

---

## 15. Future Scaling Considerations

### 15.1 Horizontal Scaling Paths

**Database Sharding**:
- Split instance database by customer ID ranges
- Read replicas for report queries
- Connection pooling with PgBouncer

**Geographic Distribution**:
- Deploy regional clusters (US-East, US-West, EU, Asia)
- Route customers to nearest region (latency optimization)
- Multi-region CephFS replication

**Service Decomposition**:
- Split instance-service into separate provisioning and lifecycle services
- Separate billing event processing from API service

### 15.2 Technology Upgrades

**Kubernetes Migration**:
- Current architecture compatible with Kubernetes
- Helm charts for service deployment
- Rook-Ceph operator for CephFS management

**Serverless Components**:
- AWS Lambda for webhook processing (reduce compute costs)
- Managed databases (RDS, ElastiCache) for reduced ops overhead

**Container Orchestration**:
- Docker Swarm (current, simpler operations)
- Kubernetes (future, advanced features)

---


## Conclusion

SaaSOdoo is a production-ready, scalable SaaS platform designed for multi-tenant Odoo provisioning with automated billing and comprehensive lifecycle management. The architecture supports horizontal scaling to 10,000+ instances with proper infrastructure planning. Docker Swarm provides a solid orchestration foundation with simpler operations than Kubernetes, suitable for teams with moderate DevOps resources.

**Key Design Principles**:
- Microservices for independent scaling and deployment
- Event-driven architecture for decoupled billing and provisioning
- CephFS for scalable, resilient distributed storage
- Comprehensive monitoring and observability
- Zero-downtime deployments and upgrades

This document provides the foundation for infrastructure procurement, network design, and capacity planning for Docker Swarm deployment at various scales.
