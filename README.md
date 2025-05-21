# Odoo SaaS Kit

A lightweight, scalable platform for deploying isolated Odoo instances on Kubernetes.

## Overview

Odoo SaaS Kit enables you to create a multi-tenant Odoo hosting platform with complete tenant isolation, allowing each customer to have their own dedicated Odoo instance and PostgreSQL database in isolated Kubernetes namespaces. Built with Flask, MicroK8s, and Traefik, this platform enables quick deployment while maintaining proper security boundaries between tenants.

## Features

- **User Registration & Authentication**: Powered by Supabase (cloud-hosted)
- **Self-Service Odoo Provisioning**: Create new instances in minutes
- **Complete Tenant Isolation**: Separate namespaces and dedicated PostgreSQL servers
- **Custom Subdomains**: Each tenant gets their own subdomain under your main domain
- **Pre-Configured Admin Credentials**: Set during instance creation
- **Multi-Node Distribution**: Tenants spread across multiple Kubernetes nodes
- **Resource Monitoring**: Basic CPU and memory usage tracking
- **Admin Dashboard**: Manage all tenants from a central location
- **Tiered Resource Plans**: Different resource allocation based on subscription tier
- **Comprehensive Network Policies**: Full network isolation between tenant namespaces

## Architecture

```
┌───────────────────────┐     ┌───────────────────────┐
│  Supabase Cloud        │     │  MicroK8s Cluster     │
│  (Authentication)      │     │                       │
└───────────┬───────────┘     │  ┌─────────────────┐  │
            │                  │  │ Traefik Ingress │  │
┌───────────┴───────────┐     │  └────────┬────────┘  │
│  Flask API             │────┼───────────┘           │
│  (Tenant Management)   │     │                       │
└───────────────────────┘     │  ┌─────────────────┐  │
                               │  │ Tenant 1        │  │
                               │  │ ┌─────┐ ┌─────┐ │  │
                               │  │ │Odoo │ │ DB  │ │  │
                               │  │ └─────┘ └─────┘ │  │
                               │  └─────────────────┘  │
                               │                       │
                               │  ┌─────────────────┐  │
                               │  │ Tenant 2        │  │
                               │  │ ┌─────┐ ┌─────┐ │  │
                               │  │ │Odoo │ │ DB  │ │  │
                               │  │ └─────┘ └─────┘ │  │
                               │  └─────────────────┘  │
                               └───────────────────────┘
```

## Tenant Isolation & Security

The platform implements a comprehensive tenant isolation strategy using multiple Kubernetes security mechanisms:

### Network Isolation

- **Default Deny Policies**: Each tenant namespace starts with all ingress and egress traffic blocked
- **Explicit Allowlists**: Only necessary communication paths are permitted:
  - Internal namespace communication between Odoo and PostgreSQL
  - Controlled ingress from Traefik for user access
  - DNS resolution for service discovery
- **Cross-Tenant Blocking**: Direct communication between tenant namespaces is explicitly prevented
- **Verified Isolation**: Automated testing ensures isolation boundaries are enforced

### Resource Separation

- **Namespace Boundaries**: Each tenant runs in a dedicated Kubernetes namespace
- **Dedicated Databases**: Every tenant gets their own PostgreSQL instance
- **Resource Quotas**: CPU/memory limits prevent resource contention between tenants

## Resource Management

The platform implements tiered resource plans for tenants through Kubernetes resource quotas and limits:

### Standard Tiers

| Tier | CPU Limit | Memory Limit | Storage | Price |
|------|-----------|--------------|---------|-------|
| Basic | 1 CPU | 1GB | 5GB | Free tier |
| Standard | 2 CPU | 2GB | 10GB | $19/month |
| Premium | 4 CPU | 4GB | 20GB | $39/month |
| Enterprise | 8 CPU | 8GB | 50GB | $99/month |

### Implementation Details

- **Resource Quotas**: Each namespace has resource quotas defined during provisioning
- **Hard Limits**: CPU and memory limits prevent tenant resource abuse
- **Auto-scaling**: Configured at the namespace level for premium tiers
- **Resource Monitoring**: Tracks usage against quota to alert approaching limits

## Quick Start

### Prerequisites

- Cloud server (Ubuntu recommended)
- Docker installed on the server
- MicroK8s installed on the server
- Supabase cloud account
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
