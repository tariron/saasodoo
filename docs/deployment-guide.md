# Deployment Guide
## Odoo SaaS Platform Production Deployment

**Version:** 2.0  
**Date:** December 2024  
**Target Environments:** Production, Staging

## 🎯 Overview

This guide provides comprehensive instructions for deploying the Odoo SaaS platform to production environments. The deployment process covers infrastructure setup, service configuration, security hardening, and monitoring implementation.

## 📋 Prerequisites

### Infrastructure Requirements

#### Minimum Production Requirements
- **CPU**: 8 cores (16 recommended)
- **Memory**: 16GB RAM (32GB recommended)
- **Storage**: 100GB SSD (500GB recommended)
- **Network**: 1Gbps connection
- **OS**: Ubuntu 24.10 LTS or compatible Linux distribution

#### Recommended Production Setup
- **Master Nodes**: 3 nodes (HA control plane)
- **Worker Nodes**: 3+ nodes (tenant workloads)
- **Load Balancer**: External load balancer (cloud provider or hardware)
- **Storage**: Distributed storage system (Ceph, GlusterFS, or cloud storage)

### External Services
- **Domain Name**: Registered domain with DNS management
- **SSL Certificate**: Wildcard SSL certificate for subdomains
- **Supabase Account**: Production Supabase project
- **Kill Bill Instance**: Production Kill Bill deployment
- **Monitoring**: External monitoring service (optional)

### Required Software
- **Docker**: Version 24.0+
- **Kubernetes**: Version 1.28+ (MicroK8s recommended)
- **kubectl**: Kubernetes CLI tool
- **Helm**: Package manager for Kubernetes (optional)

## 🚀 Deployment Process

### Phase 1: Infrastructure Setup

#### 1.1 Server Preparation

Update system packages and install essential tools including curl, wget, git, and unzip. Configure firewall rules to allow SSH (port 22), HTTP (port 80), HTTPS (port 443), and Kubernetes API (port 6443) traffic. Enable the firewall to secure the server environment.

#### 1.2 Docker Installation

Install Docker using the official installation script and add the current user to the docker group for non-root access. Verify the installation by checking the Docker version and ensuring the service is running properly.

#### 1.3 MicroK8s Installation

Install MicroK8s using snap package manager and configure user permissions for cluster access. Enable essential addons including DNS, ingress controller, metrics server, storage provisioner, container registry, and Prometheus monitoring. Configure kubectl for cluster management and verify the installation by checking node status.

#### 1.4 Multi-Node Cluster Setup (Optional)

For high availability deployments, configure additional nodes by generating join tokens on the primary node and executing the join command on worker nodes. Verify cluster formation by checking node status and ensuring all nodes are in Ready state with proper networking.

### Phase 2: Platform Deployment

#### 2.1 Clone Repository

Clone the platform repository from the designated source control system and switch to the production branch. Ensure you have the latest stable release with all necessary configuration files and deployment manifests.

#### 2.2 Environment Configuration

Copy the production environment template and configure all required environment variables including platform settings, database connections, external service credentials, security keys, monitoring configuration, and backup storage settings. Ensure all sensitive values are properly secured and validated.

#### 2.3 SSL Certificate Setup

Install cert-manager for automatic SSL certificate management using Let's Encrypt. Create a ClusterIssuer for production certificate generation and configure automatic certificate renewal. Verify cert-manager is ready before proceeding with platform deployment.

#### 2.4 Deploy Platform Services

Create the saasodoo-system namespace and deploy platform secrets from environment configuration. Apply platform services using Kustomize with production overlays and wait for all deployments to become available. Monitor deployment progress and verify all services are running correctly.

#### 2.5 Verify Deployment

Check pod status across all platform services and verify service endpoints are accessible. Review ingress configuration and examine logs for any startup errors or configuration issues.

### Phase 3: DNS Configuration

#### 3.1 DNS Records Setup

Configure DNS records with your DNS provider including A records for the main domain, API subdomain, and admin interface. Set up wildcard CNAME records for tenant subdomains and optional service-specific records for monitoring components.

#### 3.2 DNS Verification

Test DNS resolution for all configured domains and verify wildcard subdomain resolution is working correctly. Ensure DNS propagation is complete before proceeding with SSL certificate generation.

### Phase 4: Security Hardening

#### 4.1 Network Security

```bash
# Apply network policies
kubectl apply -f k8s/base/security/network-policies.yaml

# Configure pod security standards
kubectl apply -f k8s/base/security/pod-security-standards.yaml

# Set up RBAC
kubectl apply -f k8s/base/security/rbac-policies.yaml
```

#### 4.2 Secret Management

```bash
# Rotate default secrets
kubectl delete secret platform-secrets -n saasodoo-system
kubectl create secret generic platform-secrets \
  --from-env-file=.env \
  -n saasodoo-system

# Enable secret encryption at rest
microk8s enable encryption
```

#### 4.3 Security Scanning

```bash
# Run security scan
python security/scanning/security-audit.py

# Check for vulnerabilities
python security/scanning/vulnerability-scanner.py

# Verify compliance
python security/scanning/compliance-checker.py
```

### Phase 5: Monitoring Setup

#### 5.1 Prometheus Configuration

```bash
# Verify Prometheus is running
kubectl get pods -l app=prometheus -n saasodoo-system

# Access Prometheus UI (port-forward for initial setup)
kubectl port-forward svc/prometheus 9090:9090 -n saasodoo-system
```

#### 5.2 Grafana Setup

```bash
# Get Grafana admin password
kubectl get secret grafana-admin -n saasodoo-system -o jsonpath="{.data.password}" | base64 -d

# Access Grafana UI
kubectl port-forward svc/grafana 3000:3000 -n saasodoo-system

# Import dashboards
curl -X POST \
  http://admin:${GRAFANA_PASSWORD}@localhost:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @config/monitoring/grafana/dashboards/platform-overview.json
```

#### 5.3 Alerting Configuration

```bash
# Configure alert rules
kubectl apply -f config/monitoring/alerting/alert-rules.yml

# Set up notification channels
kubectl apply -f config/monitoring/alerting/notification-channels.yml
```

## 🔧 Post-Deployment Configuration

### Initial Platform Setup

#### 1. Create Admin User

```bash
# Access the platform
curl -X POST https://api.yourdomain.com/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@yourdomain.com",
    "password": "secure-admin-password",
    "full_name": "Platform Administrator",
    "role": "admin"
  }'
```

#### 2. Configure Billing Plans

```bash
# Create subscription plans in Kill Bill
python scripts/setup/configure-billing-plans.py
```

#### 3. Test Tenant Creation

```bash
# Create a test tenant
python tools/cli/create-tenant.py \
  --name test-tenant \
  --subdomain test-tenant \
  --tier standard \
  --admin-email admin@test-tenant.com
```

### Performance Optimization

#### 1. Resource Tuning

```bash
# Apply performance patches
kubectl apply -k k8s/overlays/production/patches/performance-tuning.yaml

# Configure autoscaling
kubectl apply -f k8s/base/backend/hpa.yaml
kubectl apply -f k8s/base/frontend/hpa.yaml
```

#### 2. Database Optimization

```bash
# Optimize PostgreSQL configuration
kubectl apply -f config/database/postgresql-optimized.conf

# Configure connection pooling
kubectl apply -f k8s/base/database/pgbouncer.yaml
```

## 📊 Monitoring and Maintenance

### Health Checks

```bash
# Platform health check
curl https://api.yourdomain.com/health/detailed

# Service-specific health checks
kubectl get pods -n saasodoo-system
kubectl top nodes
kubectl top pods -n saasodoo-system
```

### Backup Verification

```bash
# Test backup system
python scripts/maintenance/test-backup-system.py

# Verify backup storage
python scripts/maintenance/verify-backup-integrity.py
```

### Log Management

```bash
# View platform logs
kubectl logs -f deployment/backend -n saasodoo-system --tail=100

# Aggregate logs
kubectl logs --selector=app=saasodoo -n saasodoo-system --since=1h
```

## 🚨 Troubleshooting

### Common Issues

#### 1. Pod Startup Issues

```bash
# Check pod events
kubectl describe pod <pod-name> -n saasodoo-system

# Check resource constraints
kubectl top pods -n saasodoo-system

# Verify secrets
kubectl get secrets -n saasodoo-system
```

#### 2. DNS Resolution Issues

```bash
# Test DNS from within cluster
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup yourdomain.com

# Check CoreDNS logs
kubectl logs -f deployment/coredns -n kube-system
```

#### 3. SSL Certificate Issues

```bash
# Check certificate status
kubectl get certificates -n saasodoo-system

# Check cert-manager logs
kubectl logs -f deployment/cert-manager -n cert-manager

# Force certificate renewal
kubectl delete certificate platform-tls -n saasodoo-system
```

#### 4. Database Connection Issues

```bash
# Test database connectivity
kubectl exec -it deployment/backend -n saasodoo-system -- python -c "
import psycopg2
conn = psycopg2.connect('${DATABASE_URL}')
print('Database connection successful')
"

# Check PostgreSQL logs
kubectl logs -f statefulset/postgres -n saasodoo-system
```

### Performance Issues

#### 1. High Resource Usage

```bash
# Identify resource-heavy pods
kubectl top pods -n saasodoo-system --sort-by=cpu
kubectl top pods -n saasodoo-system --sort-by=memory

# Scale services
kubectl scale deployment backend --replicas=3 -n saasodoo-system
kubectl scale deployment frontend --replicas=2 -n saasodoo-system
```

#### 2. Slow Response Times

```bash
# Check service metrics
curl https://api.yourdomain.com/metrics

# Analyze Grafana dashboards
# Access: https://grafana.yourdomain.com

# Review application logs
kubectl logs deployment/backend -n saasodoo-system | grep "slow\|timeout\|error"
```

## 🔄 Updates and Maintenance

### Rolling Updates

```bash
# Update platform images
kubectl set image deployment/backend backend=your-registry/backend:v2.1 -n saasodoo-system
kubectl set image deployment/frontend frontend=your-registry/frontend:v2.1 -n saasodoo-system

# Monitor rollout
kubectl rollout status deployment/backend -n saasodoo-system
kubectl rollout status deployment/frontend -n saasodoo-system
```

### Backup and Recovery

```bash
# Create platform backup
python scripts/maintenance/backup-platform.py

# Test recovery procedure
python scripts/maintenance/test-recovery.py

# Schedule regular backups
kubectl apply -f k8s/base/database/backup-cronjob.yaml
```

### Security Updates

```bash
# Update security policies
kubectl apply -f k8s/base/security/

# Rotate secrets
python scripts/maintenance/rotate-secrets.py

# Update SSL certificates
kubectl delete certificate platform-tls -n saasodoo-system
```

## 📈 Scaling Considerations

### Horizontal Scaling

```bash
# Scale backend services
kubectl scale deployment backend --replicas=5 -n saasodoo-system

# Add worker nodes
microk8s add-node

# Configure load balancing
kubectl apply -f k8s/base/ingress/load-balancer.yaml
```

### Vertical Scaling

```bash
# Increase resource limits
kubectl patch deployment backend -n saasodoo-system -p '
{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "backend",
          "resources": {
            "limits": {"cpu": "2", "memory": "4Gi"},
            "requests": {"cpu": "1", "memory": "2Gi"}
          }
        }]
      }
    }
  }
}'
```

### Database Scaling

```bash
# Scale shared PostgreSQL instances
kubectl scale statefulset shared-postgres --replicas=3 -n saasodoo-system

# Configure read replicas
kubectl apply -f k8s/base/database/postgres-replica.yaml
```

## 🎯 Production Checklist

### Pre-Deployment
- [ ] Infrastructure requirements met
- [ ] External services configured
- [ ] DNS records configured
- [ ] SSL certificates ready
- [ ] Environment variables set
- [ ] Security policies reviewed

### Deployment
- [ ] Platform deployed successfully
- [ ] All pods running
- [ ] Services accessible
- [ ] SSL certificates issued
- [ ] Monitoring active
- [ ] Backups configured

### Post-Deployment
- [ ] Admin user created
- [ ] Test tenant created
- [ ] Billing configured
- [ ] Performance optimized
- [ ] Security hardened
- [ ] Documentation updated

### Ongoing Maintenance
- [ ] Regular backups verified
- [ ] Security updates applied
- [ ] Performance monitored
- [ ] Logs reviewed
- [ ] Capacity planning
- [ ] Disaster recovery tested

This deployment guide provides a comprehensive foundation for production deployment of the Odoo SaaS platform. Regular review and updates of this guide ensure continued reliability and security of the platform. 