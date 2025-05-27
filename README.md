# Odoo SaaS Kit

A lightweight, scalable platform for deploying isolated Odoo instances on Kubernetes.

## Overview

Odoo SaaS Kit enables you to create a multi-tenant Odoo hosting platform with complete tenant isolation, allowing each customer to have their own dedicated Odoo instance and PostgreSQL database in isolated Kubernetes namespaces. Built with Flask, MicroK8s, and Traefik, this platform enables quick deployment while maintaining proper security boundaries between tenants.

> **Note: Generic SaaS Platform Foundation**  
> While this kit is initially configured for Odoo deployment, the underlying architecture is designed as a generic SaaS foundation. The same isolation patterns, tenant management, and resource allocation mechanisms can be adapted for nearly any containerized SaaS application with minimal modifications to the core platform.

## Key Features

- **Instant Odoo Deployment**: Deploy a new Odoo instance in under 2 minutes
- **Complete Tenant Isolation**: Separate namespaces with hybrid database strategies (shared or dedicated)
- **Pre-Configured Admin Credentials**: Set during instance creation
- **Custom Subdomains**: Each tenant gets tenant.yourdomain.com
- **Admin Dashboard**: Manage all tenants from a central location with real-time status updates
- **Multi-Node Distribution**: Tenants distributed across cluster nodes for high availability
- **Comprehensive Network Policies**: Full network isolation between tenant namespaces
- **Automated & On-Demand Backups**: Daily backups with 7-day retention and restoration capability
- **Simple Server Migration**: Easily migrate all tenants between servers with minimal downtime

## Architecture

```
┌──────────────────────────────┐     ┌───────────────────────────┐
│  Supabase Cloud               │     │  MicroK8s Cluster         │
│  ┌────────────┐ ┌──────────┐ │     │                           │
│  │ Auth       │ │ Database │ │     │  ┌─────────────────────┐  │
│  └────────────┘ └──────────┘ │     │  │ Traefik Ingress     │  │
└───────────┬──────────────────┘     │  └─────────┬───────────┘  │
            │                         │            │              │
┌───────────┴───────────┐            │            │              │
│  Flask API             │───────────┼────────────┘              │
│  (Tenant Management)   │            │                           │
└───────────┬───────────┘            │  ┌─────────────────────┐  │
            │                         │  │ Tenant 1 (Shared)  │  │
            │                         │  │ ┌─────┐             │  │
            │                         │  │ │Odoo │    ┌──────┐ │  │
┌───────────┴───────────┐            │  │ └─────┘    │Shared│ │  │
│  Kill Bill             │            │  └────────────│ DB   │─┘  │
│  (Billing & Payment)   │            │               └──────┘    │
└───────────────────────┘            │                           │
                                      │  ┌─────────────────────┐  │
                                      │  │ Tenant 2 (Dedicated)│  │
                                      │  │ ┌─────┐ ┌─────┐     │  │
                                      │  │ │Odoo │ │ DB  │     │  │
                                      │  │ └─────┘ └─────┘     │  │
                                      │  └─────────────────────┘  │
                                      └───────────────────────────┘
```

### Supabase Integration

The platform leverages Supabase for multiple aspects of the SaaS platform:

- **Authentication**: User registration, login, and session management
- **User Management**: Profiles, preferences, and user metadata
- **Tenant Metadata**: Configuration, status, and relationship to users
- **Resource Tracking**: Usage metrics and quota management
- **Platform Configuration**: System-wide settings and feature flags
- **Real-time Updates**: Dashboard updates using Supabase's real-time capabilities

This integrated approach provides several benefits:
- Simplified infrastructure with fewer components to manage
- Consistent data access patterns across the application
- Real-time capabilities for improved user experience
- Reduced development time by leveraging Supabase's built-in features

### Kill Bill Integration

The platform integrates Kill Bill as its billing and payment solution:

- **Subscription Management**: Define and manage subscription plans aligned with resource tiers
- **Payment Processing**: Support for multiple payment providers (Stripe, PayPal, etc.)
- **Usage-Based Billing**: Track and bill based on actual resource consumption
- **Invoicing**: Automated invoice generation and delivery
- **Trial Periods**: Support for free trials with automatic conversion to paid plans
- **Customer Management**: Track customer payment information and billing history
- **Payment Gateway Integration**: Pre-built integrations with popular payment gateways

This integration provides several benefits:
- Mature, production-ready billing solution with minimal development effort
- Flexible subscription models to support various pricing strategies
- Reliable payment processing with support for global payment methods
- Complete billing lifecycle management from trial to paid subscriptions
- Open-source nature aligns with the platform's philosophy and avoids vendor lock-in

## Tenant Isolation

The platform ensures complete isolation between tenants through multiple layers:

### Kubernetes-Level Isolation

- **Namespace Separation**: Each tenant operates in its own Kubernetes namespace
- **Resource Quotas**: CPU and memory limits prevent resource contention between tenants
- **Network Policies**: Traffic isolation ensures tenants cannot communicate with each other
- **Storage Isolation**: Separate persistent volumes for each tenant

### Database Isolation Strategies

The platform implements a hybrid database approach based on tenant requirements:

#### Shared PostgreSQL Strategy
- **Target Tiers**: Basic and Standard subscription tiers
- **Isolation Method**: Separate databases within shared PostgreSQL servers
- **Security**: Database-level access controls and tenant-specific schemas
- **Benefits**: Cost-effective resource utilization and simplified management
- **Capacity**: Up to 50 tenants per shared PostgreSQL instance

#### Dedicated PostgreSQL Strategy  
- **Target Tiers**: Premium and Enterprise subscription tiers
- **Isolation Method**: Complete PostgreSQL server isolation per tenant
- **Security**: Full administrative control and independent resource allocation
- **Benefits**: Maximum security, compliance-ready, custom configurations
- **Use Cases**: High-performance requirements, regulatory compliance, large datasets

## Resource Management

The platform implements tiered resource plans for tenants through Kubernetes resource quotas and limits, which are directly mapped to Kill Bill subscription plans:

### Standard Tiers

| Tier | CPU Limit | Memory Limit | Storage | Database Strategy | Price | Billing Cycle |
|------|-----------|--------------|---------|-------------------|-------|---------------|
| Basic | 1 CPU | 1GB | 5GB | Shared PostgreSQL | Free tier | N/A |
| Standard | 2 CPU | 2GB | 10GB | Shared PostgreSQL | $19/month | Monthly |
| Premium | 4 CPU | 4GB | 20GB | Dedicated PostgreSQL | $39/month | Monthly/Annual |
| Enterprise | 8 CPU | 8GB | 50GB | Dedicated PostgreSQL | $99/month | Monthly/Annual |

### Implementation Details

- **Resource Quotas**: Each namespace has resource quotas defined during provisioning
- **Hard Limits**: CPU and memory limits prevent tenant resource abuse
- **Auto-scaling**: Configured at the namespace level for premium tiers
- **Resource Monitoring**: Tracks usage against quota to alert approaching limits

## Backup System

The platform includes a robust backup and restoration system for tenant data protection:

### Backup Features

- **Scheduled Daily Backups**: Automated backups run daily at 2 AM
- **On-Demand Backups**: Create backups instantly via the admin dashboard
- **Comprehensive Coverage**: Backups include both PostgreSQL database and Odoo filestore
- **7-Day Retention**: Rolling 7-day retention policy with automated cleanup
- **Fast Restoration**: One-click restore process from any available backup
- **Backup Verification**: Each backup includes metadata and verification

### Backup Storage

- Backups stored on a dedicated persistent volume
- Organized by tenant ID and timestamp
- Protected from tenant access
- Separate from tenant storage

## Migration Capabilities

The platform is designed for easy migration between servers, allowing you to:

### Migration Features

- **Seamless Server Migration**: Move all tenants to a new server with minimal downtime
- **Automated Process**: Detailed migration scripts handle the entire process
- **Comprehensive Data Transfer**: All tenant data, configurations, and backups are preserved
- **Verification Tools**: Validation steps ensure successful migration
- **DNS Management**: Simple DNS updates to point to the new server
- **Minimal Downtime**: Typically less than 30 minutes depending on data size

### Migration Documentation

A detailed [Migration Guide](migration-guide.md) is provided that includes:
- Step-by-step instructions for migration
- Ready-to-use migration scripts
- Troubleshooting information
- Verification procedures
- Post-migration checklist

## Quick Start

### Prerequisites

- Cloud server (Ubuntu recommended)
- Docker installed on the server
- MicroK8s installed on the server
- Supabase cloud account
- Kill Bill instance (self-hosted or cloud)
- Domain name with DNS access

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/odoo-saas-kit.git
   cd odoo-saas-kit
   ```

2. **Install MicroK8s**
   ```bash
   # On Ubuntu cloud server
   sudo snap install microk8s --classic
   sudo usermod -a -G microk8s $USER
   sudo chown -f -R $USER ~/.kube
   newgrp microk8s
   ```

3. **Configure MicroK8s**
   ```bash
   microk8s status --wait-ready
   microk8s enable dns ingress metrics-server storage registry
   mkdir -p ~/.kube
   microk8s config > ~/.kube/config
   ```

4. **Install Traefik**
   ```bash
   cd kubernetes/traefik
   bash install.sh
   cd ../..
   ```

5. **Set up environment variables**
   ```bash
   export SUPABASE_URL="your_supabase_url"
   export SUPABASE_KEY="your_supabase_key"
   export KILLBILL_URL="your_killbill_url"
   export KILLBILL_API_KEY="your_killbill_api_key"
   export KILLBILL_API_SECRET="your_killbill_api_secret"
   export DOMAIN_NAME="your_domain.com"
   ```

6. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

7. **Run the backend**
   ```bash
   cd backend
   python app.py
   ```

8. **Access the frontend**
   
   Open `frontend/index.html` in your browser or serve it using a simple HTTP server:
   ```bash
   cd frontend
   python -m http.server 8000
   ```

### Multi-Node Setup

1. **On the primary node**
   ```bash
   microk8s add-node
   ```

2. **On the secondary node**, run the command displayed from the previous step:
   ```bash
   microk8s join 192.168.1.101:25000/abcdefghijklmnopqrstuvwxyz
   ```

3. **Verify nodes**
   ```bash
   microk8s kubectl get nodes
   ```

## Production Deployment

1. **Prepare Ubuntu 24.10 server**
   
   Ensure you have SSH access to your server.

2. **Deploy to production**
   ```bash
   # Update server address in deploy.sh
   vim scripts/deploy.sh
   
   # Run deployment
   bash scripts/deploy.sh
   ```

3. **Configure DNS and SSL**
   
   Set up a wildcard DNS record for your domain:
   ```
   *.yourdomain.com -> Your server IP
   ```

   The platform uses a single wildcard SSL certificate for all tenant subdomains:
   ```bash
   # Install cert-manager for Let's Encrypt integration
   microk8s kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.12.0/cert-manager.yaml
   
   # Request wildcard certificate (configured in Traefik)
   microk8s kubectl apply -f kubernetes/traefik/certificate.yaml
   ```

## Usage

### Create a New Tenant

1. Register on the platform
2. Log in to your dashboard
3. Click "Create New Instance"
4. Enter:
   - Subdomain name
   - Admin email
   - Admin password
   - Select resource tier
5. Click "Create"
6. Once provisioning completes, access your Odoo instance at `your-subdomain.yourdomain.com`

### Manage Existing Tenants (Admin)

1. Log in to admin dashboard
2. View all tenants and their status
3. Monitor resource usage
4. Manage tenant lifecycle
5. Upgrade or downgrade tenant resource tiers

## Testing

### Test Network Isolation

```bash
python scripts/test-network-isolation.py tenant1 tenant2
```

### Test Tenant Distribution

```bash
python scripts/test-distribution.py
```

### Run Basic Tests

```bash
python -m pytest tests/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgements

- [Bitnami Odoo Images](https://github.com/bitnami/containers/tree/main/bitnami/odoo)
- [MicroK8s](https://microk8s.io/)
- [Traefik](https://traefik.io/)
- [Supabase](https://supabase.io/)
- [Flask](https://flask.palletsprojects.com/)
