# SaaSOdoo Infrastructure

This directory contains all infrastructure components for the SaaSOdoo platform, including container orchestration, reverse proxy configuration, monitoring setup, and automation scripts.

## 📁 Directory Structure

```
infrastructure/
├── compose/                    # Docker Compose configurations
│   └── docker-compose.dev.yml # Development environment setup
├── traefik/                   # Reverse proxy configuration
│   ├── traefik.yml           # Main Traefik configuration
│   └── dynamic/              # Dynamic configuration files
│       └── middlewares.yml   # Security, CORS, rate limiting
├── monitoring/               # Monitoring and observability
│   ├── prometheus.yml       # Metrics collection configuration
│   └── grafana/            # Grafana dashboards and datasources
│       ├── dashboards/     # Pre-built dashboards
│       └── datasources/    # Data source configurations
├── scripts/                 # Automation scripts
│   ├── dev-setup.sh        # Development environment setup
│   └── build-all.sh        # Build all Docker images
└── README.md               # This file
```

## 🚀 Quick Start

### 1. Initial Setup

Run the development setup script to initialize your environment:

```bash
# On Windows (PowerShell/Git Bash)
bash infrastructure/scripts/dev-setup.sh

# On Linux/macOS
./infrastructure/scripts/dev-setup.sh
```

This script will:
- ✅ Check Docker installation
- ✅ Create necessary directories
- ✅ Set up environment variables
- ✅ Configure PostgreSQL databases
- ✅ Set up Grafana datasources
- ✅ Pull required Docker images
- ✅ Configure local DNS entries

### 2. Start Development Environment

```bash
# Using Makefile (recommended)
make dev-up

# Or directly with Docker Compose
docker-compose -f infrastructure/compose/docker-compose.dev.yml up -d
```

### 3. Access Services

Once started, access these services in your browser:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Traefik Dashboard** | http://traefik.saasodoo.local:8080 | admin:admin |
| **Grafana** | http://grafana.saasodoo.local | admin:admin |
| **Prometheus** | http://prometheus.saasodoo.local | - |
| **RabbitMQ Management** | http://rabbitmq.saasodoo.local | saasodoo:saasodoo123 |
| **Kibana** | http://kibana.saasodoo.local | - |
| **MailHog** | http://mail.saasodoo.local | - |
| **MinIO Console** | http://minio.saasodoo.local | minioadmin:minioadmin |

## 🏗️ Infrastructure Components

### Reverse Proxy (Traefik)
- **Purpose**: Load balancing, SSL termination, routing
- **Features**: 
  - Automatic service discovery
  - SSL certificate management
  - Rate limiting and security headers
  - Health checks and circuit breakers
- **Configuration**: `traefik/traefik.yml`

### Database (PostgreSQL)
- **Purpose**: Primary data storage for all microservices
- **Features**:
  - Separate databases per service
  - Automatic initialization scripts
  - Extensions for UUID and full-text search
- **Databases**: auth, billing, tenant, communication, analytics

### Caching (Redis)
- **Purpose**: Session storage, caching, rate limiting
- **Features**:
  - Persistent storage
  - Configurable memory limits
  - Pub/Sub for real-time features

### Message Queue (RabbitMQ)
- **Purpose**: Asynchronous communication between services
- **Features**:
  - Management UI
  - Virtual hosts for isolation
  - Message persistence

### Monitoring Stack

#### Prometheus
- **Purpose**: Metrics collection and alerting
- **Features**:
  - Service discovery
  - Custom metrics for all services
  - Recording rules for common queries

#### Grafana
- **Purpose**: Metrics visualization and dashboards
- **Features**:
  - Pre-configured datasources
  - Custom dashboards for SaaSOdoo
  - Alerting and notifications

#### Elasticsearch + Kibana
- **Purpose**: Log aggregation and analysis
- **Features**:
  - Centralized logging
  - Full-text search
  - Log visualization

### Development Tools

#### MailHog
- **Purpose**: Email testing in development
- **Features**:
  - Catches all outgoing emails
  - Web UI for email inspection
  - API for automated testing

#### MinIO
- **Purpose**: S3-compatible object storage
- **Features**:
  - File uploads and storage
  - Backup storage
  - Compatible with AWS S3 APIs

## 🔧 Configuration

### Environment Variables

Key environment variables (defined in `.env`):

```bash
# Database
POSTGRES_DB=saasodoo
POSTGRES_USER=saasodoo
POSTGRES_PASSWORD=saasodoo123

# Redis
REDIS_PASSWORD=saasodoo123

# RabbitMQ
RABBITMQ_USER=saasodoo
RABBITMQ_PASSWORD=saasodoo123

# Monitoring
GF_ADMIN_USER=admin
GF_ADMIN_PASSWORD=admin

# Storage
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

### Traefik Configuration

#### Security Features
- **Rate Limiting**: API and web rate limits
- **Security Headers**: HSTS, XSS protection, frame denial
- **CORS**: Configurable cross-origin requests
- **IP Whitelisting**: Restrict admin interfaces

#### SSL/TLS
- **Development**: Self-signed certificates
- **Production**: Let's Encrypt integration
- **HTTP → HTTPS**: Automatic redirection

### Monitoring Configuration

#### Metrics Collection
- **Application Metrics**: Custom metrics from each service
- **Infrastructure Metrics**: Container, database, cache metrics
- **Network Metrics**: Request rates, response times, errors

#### Alerting Rules
- **Error Rate**: Alert on high error rates
- **Response Time**: Alert on slow responses
- **Resource Usage**: Alert on high CPU/memory usage
- **Service Health**: Alert when services are down

## 🛠️ Automation Scripts

### Development Setup (`dev-setup.sh`)

Comprehensive setup script that:
- Validates prerequisites
- Creates directory structure
- Configures services
- Sets up local DNS
- Pulls Docker images

**Usage:**
```bash
bash infrastructure/scripts/dev-setup.sh
```

### Build All Services (`build-all.sh`)

Builds all Docker images for the platform:
- Supports parallel and sequential builds
- Multi-architecture support (AMD64, ARM64)
- Build caching for faster iterations
- Optional image pushing to registry

**Usage:**
```bash
# Build all services
bash infrastructure/scripts/build-all.sh

# Build with custom tag
bash infrastructure/scripts/build-all.sh --tag v1.0.0

# Build and push to registry
bash infrastructure/scripts/build-all.sh --push --registry myregistry.com/saasodoo
```

## 📊 Monitoring and Observability

### Key Metrics Tracked

1. **Business Metrics**
   - User registrations
   - Subscription conversions
   - Payment processing
   - API usage

2. **Technical Metrics**
   - Request rates and latency
   - Error rates by service
   - Database performance
   - Cache hit rates

3. **Infrastructure Metrics**
   - Container resource usage
   - Network throughput
   - Storage utilization
   - Service availability

### Dashboard Categories

1. **Overview Dashboard**
   - Platform health summary
   - Key business metrics
   - Recent alerts

2. **Service Dashboards**
   - Per-service metrics
   - API performance
   - Database queries

3. **Infrastructure Dashboards**
   - Container metrics
   - Resource utilization
   - Network performance

## 🔒 Security Features

### Network Security
- **Isolated Networks**: Services communicate through dedicated networks
- **Firewall Rules**: Only necessary ports exposed
- **SSL/TLS**: Encrypted communication

### Application Security
- **Rate Limiting**: Prevent abuse and DoS attacks
- **Input Validation**: Request size limits and validation
- **Authentication**: Basic auth for admin interfaces
- **CORS**: Configured cross-origin policies

### Data Security
- **Encrypted Storage**: Database and file encryption
- **Secure Secrets**: Environment-based secret management
- **Audit Logging**: All access and changes logged

## 🚀 Production Considerations

### Scaling
- **Horizontal Scaling**: Services can be scaled independently
- **Load Balancing**: Traefik handles distribution
- **Database Scaling**: Read replicas and connection pooling

### High Availability
- **Service Redundancy**: Multiple instances per service
- **Health Checks**: Automatic service recovery
- **Backup Strategy**: Automated backups for data persistence

### Deployment
- **Blue-Green Deployment**: Zero-downtime deployments
- **Rolling Updates**: Gradual service updates
- **Rollback Strategy**: Quick rollback capabilities

## 📝 Next Steps

After completing the infrastructure setup:

1. **Verify Services**: Check all services are running
2. **Configure Monitoring**: Set up dashboards and alerts
3. **Test Connectivity**: Verify service communication
4. **Build Microservices**: Start implementing individual services
5. **Set Up CI/CD**: Implement automated deployments

## 🆘 Troubleshooting

### Common Issues

1. **Docker Not Running**
   ```bash
   # Start Docker Desktop
   # Or on Linux: sudo systemctl start docker
   ```

2. **Port Conflicts**
   ```bash
   # Check port usage
   netstat -an | grep :80
   # Stop conflicting services
   ```

3. **DNS Resolution**
   ```bash
   # Add to hosts file:
   # 127.0.0.1 *.saasodoo.local
   ```

4. **Memory Issues**
   ```bash
   # Increase Docker memory limit
   # Docker Desktop → Settings → Resources
   ```

### Logs and Debugging

```bash
# View service logs
make dev-logs

# View specific service logs
docker-compose -f infrastructure/compose/docker-compose.dev.yml logs traefik

# Check service health
docker-compose -f infrastructure/compose/docker-compose.dev.yml ps
```

## 📚 Additional Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Traefik Documentation](https://doc.traefik.io/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [SaaSOdoo Project README](../README.md) 