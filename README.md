# Odoo SaaS Kit

A lightweight, scalable platform for deploying isolated Odoo instances on Kubernetes.

## Overview

Odoo SaaS Kit enables you to create a multi-tenant Odoo hosting platform with complete tenant isolation, allowing each customer to have their own dedicated Odoo instance and PostgreSQL database in isolated Kubernetes namespaces. Built with Flask, MicroK8s, and Traefik, this platform enables quick deployment while maintaining proper security boundaries between tenants.

## Features

- **User Registration & Authentication**: Powered by Supabase
- **Self-Service Odoo Provisioning**: Create new instances in minutes
- **Complete Tenant Isolation**: Separate namespaces and dedicated PostgreSQL servers
- **Custom Subdomains**: Each tenant gets their own subdomain
- **Pre-Configured Admin Credentials**: Set during instance creation
- **Multi-Node Distribution**: Tenants spread across multiple Kubernetes nodes
- **Resource Monitoring**: Basic CPU and memory usage tracking
- **Admin Dashboard**: Manage all tenants from a central location

## Architecture

```
┌───────────────────────┐     ┌───────────────────────┐
│  Supabase              │     │  MicroK8s Cluster     │
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

## Quick Start

### Prerequisites

- Windows or Ubuntu machine
- Docker Desktop (for Windows)
- MicroK8s installed
- Supabase account
- Domain name with DNS access

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/odoo-saas-kit.git
   cd odoo-saas-kit
   ```

2. **Install MicroK8s**
   ```bash
   # On Windows: Download and install from https://microk8s.io/docs/install-windows
   
   # On Ubuntu
   sudo snap install microk8s --classic
   sudo usermod -a -G microk8s $USER
   sudo chown -f -R $USER ~/.kube
   newgrp microk8s
   ```

3. **Configure MicroK8s**
   ```bash
   microk8s status --wait-ready
   microk8s enable dns ingress metrics-server storage
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

### Multi-Node Setup on Windows

1. **On the first Windows machine**
   ```bash
   microk8s add-node
   ```

2. **On the second Windows machine**, run the command displayed from the previous step:
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

3. **Configure DNS**
   
   Set up a wildcard DNS record for your domain:
   ```
   *.yourdomain.com -> Your server IP
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
5. Click "Create"
6. Once provisioning completes, access your Odoo instance at `your-subdomain.yourdomain.com`

### Manage Existing Tenants (Admin)

1. Log in to admin dashboard
2. View all tenants and their status
3. Monitor resource usage
4. Manage tenant lifecycle

## Testing

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
