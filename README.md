# Odoo SaaS Kit

A comprehensive, production-ready platform for deploying isolated Odoo instances on Kubernetes with complete multi-tenant architecture.

## 🚀 Overview

Odoo SaaS Kit is an enterprise-grade multi-tenant platform that enables rapid deployment of isolated Odoo instances. Built with modern cloud-native technologies, it provides complete tenant isolation, flexible resource management, and comprehensive monitoring capabilities.

> **🔧 Adaptable SaaS Foundation**  
> While optimized for Odoo deployment, this platform serves as a generic SaaS foundation. The modular architecture, tenant isolation patterns, and resource management systems can be adapted for virtually any containerized SaaS application.

## ✨ Key Features

### Core Capabilities
- **⚡ Rapid Deployment**: Deploy new Odoo instances in under 2 minutes
- **🔒 Complete Isolation**: Multi-layer isolation with Kubernetes namespaces and hybrid database strategies
- **🌐 Custom Subdomains**: Automatic subdomain provisioning (tenant.yourdomain.com)
- **👤 Pre-configured Access**: Admin credentials set during instance creation
- **📊 Centralized Management**: Comprehensive admin dashboard with real-time monitoring
- **🏗️ High Availability**: Multi-node distribution with automatic failover

### Advanced Features
- **💾 Automated Backups**: Daily backups with 7-day retention and one-click restoration
- **🔄 Seamless Migration**: Server-to-server migration with minimal downtime
- **📈 Resource Monitoring**: Real-time CPU, memory, and storage tracking
- **🛡️ Network Security**: Comprehensive network policies and traffic isolation
- **💳 Integrated Billing**: Kill Bill integration for subscription management
- **🔐 Enterprise Auth**: Supabase-powered authentication and user management

## 🏗️ Architecture

### System Overview

```
┌──────────────────────────────┐     ┌───────────────────────────┐
│  External Services            │     │  Kubernetes Cluster       │
│  ┌────────────┐ ┌──────────┐ │     │                           │
│  │ Supabase   │ │Kill Bill │ │     │  ┌─────────────────────┐  │
│  │ (Auth/DB)  │ │(Billing) │ │     │  │ Traefik Ingress     │  │
│  └────────────┘ └──────────┘ │     │  └─────────┬───────────┘  │
└───────────┬──────────────────┘     │            │              │
            │                         │            │              │
┌───────────┴───────────┐            │  ┌─────────┴─────────┐    │
│  SaaS Platform API    │───────────┼──│ Backend Services  │    │
│  (Flask Microservices)│            │  │ - Auth Service    │    │
└───────────┬───────────┘            │  │ - Tenant Service  │    │
            │                         │  │ - Billing Service │    │
┌───────────┴───────────┐            │  │ - Admin Service   │    │
│  Frontend Dashboard   │            │  └───────────────────┘    │
│  (Flask Web UI)       │            │                           │
└───────────────────────┘            │  ┌─────────────────────┐  │
                                      │  │ Tenant Namespaces   │  │
                                      │  │ ┌─────┐ ┌─────────┐ │  │
                                      │  │ │Odoo │ │Database │ │  │
                                      │  │ │Apps │ │Strategy │ │  │
                                      │  │ └─────┘ └─────────┘ │  │
                                      │  └─────────────────────┘  │
                                      └───────────────────────────┘
```

### Microservices Architecture

The platform is built using a microservices architecture with the following services:

- **🔐 Auth Service**: Supabase integration for authentication and user management
- **🏢 Tenant Service**: Tenant lifecycle management and provisioning
- **💰 Billing Service**: Kill Bill integration for subscription and payment processing
- **⚙️ Admin Service**: Administrative operations and monitoring
- **🗄️ Database Management Service**: Hybrid database strategy management
- **🚀 Provisioning Service**: Kubernetes resource provisioning and management

## 🔒 Multi-Layer Tenant Isolation

### Kubernetes-Level Isolation
- **Namespace Separation**: Each tenant operates in an isolated Kubernetes namespace
- **Resource Quotas**: CPU, memory, and storage limits prevent resource contention
- **Network Policies**: Complete traffic isolation between tenants
- **Storage Isolation**: Dedicated persistent volumes per tenant

### Hybrid Database Strategy

The platform implements intelligent database isolation based on tenant requirements:

#### 📊 Shared PostgreSQL Strategy
- **Target Tiers**: Basic and Standard subscriptions
- **Capacity**: Up to 50 tenants per shared instance
- **Isolation**: Database-level separation with tenant-specific schemas
- **Benefits**: Cost-effective resource utilization
- **Security**: Row-level security and connection pooling

#### 🏛️ Dedicated PostgreSQL Strategy
- **Target Tiers**: Premium and Enterprise subscriptions
- **Isolation**: Complete PostgreSQL server per tenant
- **Benefits**: Maximum performance and compliance readiness
- **Use Cases**: High-performance workloads, regulatory compliance

## 💰 Resource Management & Pricing

| Tier | CPU | Memory | Storage | Database | Price | Features |
|------|-----|--------|---------|----------|-------|----------|
| **Basic** | 1 CPU | 1GB | 5GB | Shared | Free | Basic support |
| **Standard** | 2 CPU | 2GB | 10GB | Shared | $19/mo | Email support |
| **Premium** | 4 CPU | 4GB | 20GB | Dedicated | $39/mo | Priority support |
| **Enterprise** | 8 CPU | 8GB | 50GB | Dedicated | $99/mo | 24/7 support |

### Resource Features
- **Auto-scaling**: Automatic resource adjustment for premium tiers
- **Usage Monitoring**: Real-time resource consumption tracking
- **Quota Management**: Soft and hard limits with alerting
- **Performance Analytics**: Detailed performance metrics and recommendations

## 💾 Backup & Recovery System

### Backup Features
- **📅 Scheduled Backups**: Automated daily backups at 2 AM
- **⚡ On-Demand Backups**: Instant backup creation via dashboard
- **🔄 Complete Coverage**: Database and filestore backup
- **🗓️ Retention Policy**: 7-day rolling retention with automated cleanup
- **✅ Verification**: Backup integrity verification and metadata

### Recovery Options
- **🔄 One-Click Restore**: Simple restoration from any backup point
- **📊 Backup Browser**: Browse and select specific backup versions
- **🔍 Verification Tools**: Pre-restore validation and compatibility checks

## 🚀 Quick Start

### Prerequisites
- **Server**: Ubuntu 24.10+ or compatible Linux distribution
- **Container Runtime**: Docker 24.0+
- **Orchestration**: MicroK8s or Kubernetes 1.28+
- **External Services**: Supabase account, Kill Bill instance
- **Domain**: Registered domain with DNS management access

### Development Setup

1. **Clone and Setup**
   ```bash
   git clone https://github.com/yourusername/odoo-saas-kit.git
   cd odoo-saas-kit
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start Development Environment**
   ```bash
   docker-compose up -d
   ```

4. **Initialize Platform**
   ```bash
   python scripts/setup/init-platform.py
   ```

5. **Access Services**
   - **Frontend**: http://localhost:5001
   - **API**: http://localhost:5000/api
   - **Traefik Dashboard**: http://localhost:8082
   - **Grafana**: http://localhost:3000

### Production Deployment

1. **Prepare Server**
   ```bash
   # Install MicroK8s
   sudo snap install microk8s --classic
   microk8s enable dns ingress metrics-server storage registry
   ```

2. **Deploy Platform**
   ```bash
   # Configure environment
   cp config/environments/production.env .env
   
   # Deploy to Kubernetes
   kubectl apply -k k8s/overlays/production
   ```

3. **Configure DNS**
   ```bash
   # Set wildcard DNS record
   *.yourdomain.com -> YOUR_SERVER_IP
   ```

## 📖 Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[📋 Product Requirements](docs/product-requirements-document.md)**: Detailed feature specifications
- **[🏗️ Project Structure](docs/project-structure.md)**: Complete codebase organization
- **[⚡ Implementation Plan](docs/implementation-plan.md)**: Development roadmap and timeline
- **[👨‍💻 Development Guide](docs/odoo-saas-development-guide.md)**: Developer setup and guidelines
- **[🔄 Migration Guide](docs/migration-guide.md)**: Server migration procedures
- **[📝 Coding Patterns](docs/coding-patterns-document.md)**: Code standards and examples

## 🧪 Testing

### Run Test Suite
```bash
# Backend tests
cd backend && python -m pytest tests/

# Integration tests
python scripts/testing/run-integration-tests.py

# Network isolation tests
python scripts/testing/test-network-isolation.py
```

### Manual Testing
```bash
# Test tenant creation
python tools/cli/create-tenant.py --name test-tenant --tier standard

# Test resource monitoring
python tools/cli/monitor-resources.py --tenant test-tenant

# Test backup system
python tools/cli/backup-tenant.py --tenant test-tenant
```

## 🔧 Configuration

### Environment Variables
```bash
# Core Configuration
FLASK_ENV=production
DATABASE_URL=postgresql://user:pass@localhost:5432/saasodoo
REDIS_URL=redis://localhost:6379/0

# External Services
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
KILLBILL_URL=https://your-killbill-instance.com
KILLBILL_API_KEY=your-api-key

# Platform Settings
DOMAIN_NAME=yourdomain.com
DEFAULT_ADMIN_EMAIL=admin@yourdomain.com
BACKUP_RETENTION_DAYS=7
```

### Kubernetes Configuration
The platform uses Kustomize for environment-specific configurations:
- **Development**: `k8s/overlays/development/`
- **Staging**: `k8s/overlays/staging/`
- **Production**: `k8s/overlays/production/`

## 🛡️ Security

### Security Features
- **🔐 Multi-Factor Authentication**: Supabase-powered MFA
- **🌐 Network Policies**: Zero-trust network architecture
- **🔒 Secret Management**: Kubernetes secrets with encryption at rest
- **📜 Certificate Management**: Automated SSL/TLS with Let's Encrypt
- **🛡️ Security Scanning**: Automated vulnerability scanning

### Compliance
- **GDPR**: Data protection and privacy controls
- **SOC 2**: Security and availability controls
- **HIPAA**: Healthcare data protection (Enterprise tier)

## 📊 Monitoring & Observability

### Monitoring Stack
- **📈 Prometheus**: Metrics collection and alerting
- **📊 Grafana**: Visualization and dashboards
- **📋 Structured Logging**: Centralized log aggregation
- **🚨 Alerting**: Real-time alerts for critical events

### Key Metrics
- **Tenant Performance**: CPU, memory, storage utilization
- **Platform Health**: Service availability and response times
- **Business Metrics**: Tenant growth, resource consumption
- **Security Events**: Authentication failures, policy violations

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines
- Follow the coding patterns in `docs/coding-patterns-document.md`
- Add tests for new features
- Update documentation for API changes
- Ensure security best practices

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgements

- **[Bitnami Odoo](https://github.com/bitnami/containers/tree/main/bitnami/odoo)**: Pre-configured Odoo containers
- **[MicroK8s](https://microk8s.io/)**: Lightweight Kubernetes distribution
- **[Traefik](https://traefik.io/)**: Modern reverse proxy and load balancer
- **[Supabase](https://supabase.io/)**: Open source Firebase alternative
- **[Kill Bill](https://killbill.io/)**: Open source billing platform
- **[Flask](https://flask.palletsprojects.com/)**: Lightweight web framework

---

**🚀 Ready to deploy your SaaS platform?** Get started with our [Quick Start Guide](#-quick-start) or explore the [Documentation](#-documentation) for detailed implementation guidance.