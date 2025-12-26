# Odoo SaaS Kit

A comprehensive SaaS platform for provisioning and managing Odoo instances with integrated billing, user management, and monitoring.

## Features

- **Multi-tenant Odoo Instances**: Support for Odoo versions 14-17
- **Automated Provisioning**: Docker-based instance creation and management
- **Integrated Billing**: PayNow, EcoCash, and OneMoney payment gateways
- **User Management**: Authentication and authorization with Supabase
- **Admin Dashboard**: System monitoring and management
- **Monitoring & Alerts**: Prometheus and Grafana integration
- **Backup & Restore**: Automated backup with Contabo integration

## Architecture

### Microservices
- **Web App** (Flask) - Frontend user interface
- **User Service** (FastAPI) - Authentication and user management
- **Instance Service** (FastAPI) - Odoo instance provisioning
- **Billing Service** (FastAPI) - Payment processing
- **Notification Service** (FastAPI) - Email and notifications
- **Admin Service** (FastAPI) - Admin dashboard

### Infrastructure
- **Traefik** - Reverse proxy and load balancer
- **PostgreSQL** - Primary database
- **pgAdmin** - Database management interface
- **Redis** - Caching and sessions
- **Prometheus/Grafana** - Monitoring stack

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.9+
- Git

### Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd odoo-saas-kit
   ```

2. **Copy environment configuration**
   ```bash
   cp .env.example .env
   ```

3. **Edit environment variables**
   ```bash
   # Edit .env with your configuration
   nano .env
   ```

4. **Start development environment**
   ```bash
   make dev-up
   ```

5. **Access the application**
   - Web App: http://localhost
   - Admin Dashboard: http://admin.localhost
   - API Documentation: http://api.localhost/docs

### Production Deployment

#### Kubernetes Production
```bash
./infrastructure/scripts/deploy.sh
```

## Development Commands

```bash
# Development
make dev-up          # Start development environment
make dev-down        # Stop development environment
make dev-logs        # View logs
make dev-shell       # Access service shell

# Testing
make test            # Run all tests
make test-service    # Run specific service tests

# Building
make build           # Build all images
make build-service   # Build specific service

# Production (Kubernetes)
kubectl get pods -n saasodoo                    # Check pod status
kubectl logs -n saasodoo -l app=instance-service  # View logs
kubectl rollout restart deployment/<name> -n saasodoo  # Restart service
./infrastructure/scripts/deploy.sh              # Deploy platform
./infrastructure/scripts/teardown.sh            # Teardown platform
```

## Configuration

### Environment Variables

Key environment variables in `.env`:

```bash
# Database
POSTGRES_HOST=postgres
POSTGRES_DB=saas_odoo
POSTGRES_USER=odoo_user
POSTGRES_PASSWORD=secure_password

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Payment Gateways
PAYNOW_INTEGRATION_ID=your_paynow_id
PAYNOW_INTEGRATION_KEY=your_paynow_key
ECOCASH_MERCHANT_CODE=your_ecocash_code
ONEMONEY_MERCHANT_ID=your_onemoney_id

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Security
JWT_SECRET_KEY=your_jwt_secret
ENCRYPTION_KEY=your_encryption_key
```

## API Documentation

### User Service
- **Base URL**: `http://api.localhost/user`
- **Endpoints**: Authentication, user management, profiles
- **Docs**: `http://api.localhost/user/docs`

### Instance Service
- **Base URL**: `http://api.localhost/instance`
- **Endpoints**: Instance provisioning, management, monitoring
- **Docs**: `http://api.localhost/instance/docs`

### Billing Service
- **Base URL**: `http://api.localhost/billing`
- **Endpoints**: Payments, subscriptions, billing
- **Docs**: `http://api.localhost/billing/docs`

## Monitoring

### Prometheus Metrics
- **URL**: `http://monitoring.localhost:9090`
- **Metrics**: Service health, instance usage, billing metrics

### Grafana Dashboards
- **URL**: `http://monitoring.localhost:3000`
- **Default Login**: admin/admin
- **Dashboards**: System overview, service metrics, billing analytics

## Backup & Restore

### Automated Backups
```bash
# Create backup
make backup

# Restore from backup
make restore BACKUP_FILE=backup_20231201.tar.gz
```

### Manual Database Backup
```bash
# Backup specific instance database
docker exec postgres pg_dump -U odoo_user instance_db_name > backup.sql

# Restore instance database
docker exec -i postgres psql -U odoo_user -d instance_db_name < backup.sql
```

## Troubleshooting

### Common Issues

1. **Services not starting**
   ```bash
   # Check logs
   make dev-logs
   
   # Restart services
   make dev-down && make dev-up
   ```

2. **Database connection issues**
   ```bash
   # Check PostgreSQL status
   docker exec postgres pg_isready
   
   # Reset database
   make db-reset
   ```

3. **Instance provisioning fails**
   ```bash
   # Check Docker daemon
   docker info
   
   # Check available resources
   docker system df
   ```

### Log Locations
- **Application Logs**: `logs/`
- **Container Logs**: `docker logs <container_name>`
- **System Logs**: `/var/log/`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: GitHub Issues
- **Email**: support@your-domain.com

## Roadmap

- [ ] Multi-region deployment
- [ ] Advanced analytics dashboard
- [ ] Mobile payment integration
- [ ] Kubernetes support
- [ ] Advanced backup strategies
- [ ] Multi-language support 