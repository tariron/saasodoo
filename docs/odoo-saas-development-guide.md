# Odoo SaaS Kit: Development Guide

## Overview

This guide focuses on key considerations when developing the Odoo SaaS Kit that will operate across two primary environments:
1. Development using a cloud server with MicroK8s and Docker
2. Production deployment on Contabo Ubuntu VPS

The platform programmatically creates isolated Odoo instances for customers in Kubernetes namespaces, with each tenant having a dedicated Odoo instance and either a shared or dedicated PostgreSQL database based on their subscription tier and requirements.

## Infrastructure Setup

The recommended infrastructure consists of two cloud servers:

1. **Development Server**:
   - MicroK8s for Kubernetes
   - Docker for building container images
   - Code editing via IDE (Cursor) connected remotely
   - Built-in MicroK8s registry for storing images

2. **Staging/Testing Server**:
   - MicroK8s for Kubernetes
   - Used for validating tenant provisioning
   - Mimics production environment for testing

## Namespace Strategy

The SaaS platform will utilize the following namespace structure:

1. **System namespace** (`saas-system` or `odoo-system`)
   - Contains core platform services (SaaS controller/API)
   - Shared services and infrastructure components
   - Traefik ingress controller
   - Central database for tenant management

2. **One namespace per tenant**
   - Each customer gets their own isolated namespace
   - Contains dedicated Odoo instance
   - Database connection (shared or dedicated based on tier)
   - Any tenant-specific services or customizations

3. **Shared database namespaces** (`postgres-shared-*`)
   - Contains shared PostgreSQL instances serving multiple tenants
   - Each shared instance supports up to 50 tenants
   - Separate databases within each PostgreSQL server
   - Centralized monitoring and backup management

4. **Development namespace** (`saas-dev`)
   - Used for platform development and testing
   - Isolated from production tenants
   - Simulates tenant provisioning and management

This multi-namespace approach ensures proper tenant isolation and mirrors the production environment during development.

## Key Considerations for Development

### 1. Environment-Aware Configuration

- **Use environment variables** for configuration that varies between environments:
  - `DOMAIN_NAME` - Different domains for dev and production
  - `FLASK_ENV` - To indicate development or production mode
  - Authentication credentials and secrets

- **Create a configuration hierarchy**:
  - Base config with shared settings
  - Environment-specific config overrides
  - Local development overrides in `.env` files (excluded from version control)

### 2. Kubernetes Client Implementation

- **Direct integration with MicroK8s** in development:
  - Use the same Kubernetes client code for both development and production
  - Configure kubectl to use the local MicroK8s cluster
  - Implement consistent namespacing approach across environments

- **Environment detection**:
  ```python
  # Simple environment detection
  DEV_MODE = os.environ.get('FLASK_ENV') == 'development'
  
  # Additional configuration based on environment
  if DEV_MODE:
      # Use development-specific settings
      DEFAULT_NAMESPACE = 'saas-dev'
  else:
      # Use production settings
      DEFAULT_NAMESPACE = 'saas-system'
  ```

### 3. Networking & Subdomain Strategy

- **Development Environment**: 
  - Configure Traefik as ingress controller on cloud server
  - Use a wildcard DNS record pointing to your cloud server IP
  - Alternatively, use `nip.io` or `sslip.io` for easy subdomain testing
  
- **Production**:
  - Configure Traefik with ClusterIP 
  - Set up wildcard DNS records
  - Use Let's Encrypt for SSL

### 4. Resource Management

- **Development**: 
  - Set reasonable resource limits to simulate production
  - Create resource quotas for tenant namespaces
  - Test resource allocation/deallocation during tenant provisioning

- **Production**: 
  - Implement production-grade resource limits based on service tier
  - Monitor resource usage across tenants
  - Implement auto-scaling where appropriate

### 5. Tenant Isolation Approach

Ensure consistent tenant isolation approach across environments:

- **Namespace isolation** - Each tenant gets its own Kubernetes namespace
- **Network policies** - Restrict cross-tenant communication
- **Resource quotas** - Prevent resource starvation between tenants
- **Database isolation** - Hybrid approach based on tenant requirements:
  
  **Shared Database Isolation:**
  - Separate database per tenant within shared PostgreSQL server
  - Database-level access controls and permissions
  - Tenant-specific connection pools and schemas
  - Row-level security policies for additional protection
  
  **Dedicated Database Isolation:**
  - Complete PostgreSQL server isolation per tenant
  - Full administrative control and resource allocation
  - Independent backup and maintenance schedules
  - Custom PostgreSQL configuration options

### 6. Testing Strategies

Create systematic testing procedures:

1. **API functionality tests** - Test SaaS controller functionality
2. **Tenant provisioning tests** - Test provisioning/deprovisioning workflows with both database strategies
3. **Database strategy tests** - Verify correct strategy assignment and isolation for both shared and dedicated approaches
4. **Isolation tests** - Verify tenant boundaries are correctly enforced for both database strategies
5. **Performance tests** - Verify resource usage and limits for both shared and dedicated database approaches
6. **Migration tests** - Test movement between database strategies if implemented

## Practical Implementation Recommendations

### Docker and MicroK8s Registry Workflow

- **Setup MicroK8s Registry**:
  ```bash
  # Enable the registry in MicroK8s
  microk8s enable registry
  
  # Verify the registry is running
  microk8s kubectl get pods -n container-registry
  ```

- **Building and Pushing Images**:
  ```bash
  # Build image with Docker
  docker build -t localhost:32000/saas-controller:dev .
  
  # Push to MicroK8s registry
  docker push localhost:32000/saas-controller:dev
  ```

- **Using Images in Kubernetes Manifests**:
  ```yaml
  # Example deployment.yaml
  apiVersion: apps/v1
  kind: Deployment
  metadata:
    name: saas-controller
  spec:
    # ... other specifications
    template:
      spec:
        containers:
        - name: saas-controller
          image: localhost:32000/saas-controller:dev
          # ... container specs
  ```

- **Internal Registry Address**:
  - From within MicroK8s pods, the registry is accessible at:
    `registry.container-registry.svc.cluster.local:5000/saas-controller:dev`
  - From the host machine (for Docker), use:
    `localhost:32000/saas-controller:dev`

### Development to Staging Workflow

- **Push Images to Dev Registry**:
  ```bash
  # On dev server
  docker build -t localhost:32000/saas-controller:v1 .
  docker push localhost:32000/saas-controller:v1
  ```

- **Transfer Manifests to Staging**:
  ```bash
  # Using git
  git add k8s-manifests/
  git commit -m "Update deployment files"
  git push origin main
  
  # On staging server
  git pull origin main
  ```

- **Apply Configurations on Staging**:
  ```bash
  # On staging server
  microk8s kubectl apply -f k8s-manifests/
  ```

### Traefik Configuration

- **Development**: Full Traefik configuration similar to production
- **Production**: Production configuration with SSL certificates

## Remote Development Workflow

For remote development using Cursor or other IDEs:

1. **SSH Setup**:
   - Configure SSH with key authentication
   - Set up SSH config with dedicated host entry
   - Consider using SSH agent forwarding for git operations

2. **Repository Management**:
   - Keep repository operations on the server
   - Use git for version control directly on the server
   - Consider setting up CI/CD for automated testing

3. **Port Forwarding**:
   - Use SSH port forwarding to access services locally
   - Example: `ssh -L 8080:localhost:80 user@server`

## Common Challenges & Solutions

### 1. Database Management

- **Challenge**: Database setup and migration across environments
- **Solutions**:
  - Use consistent PostgreSQL version across environments
  - Script database initialization
  - Implement backup/restore for migration

### 2. Security Model Consistency

- **Challenge**: Maintaining consistent security model
- **Solutions**:
  - Define security templates that work across environments
  - Apply network policies consistently
  - Use namespaces for isolation in all environments

### 3. Testing Tenant Isolation

- **Challenge**: Verifying proper tenant isolation
- **Solutions**:
  - Create automated tests for namespace boundaries
  - Test network policies between namespaces
  - Verify database isolation between tenants

### 4. Image Registry Access

- **Challenge**: Sharing images between development and staging
- **Solutions**:
  - If needed, expose registry with authentication:
    ```bash
    # On dev server, expose registry securely
    microk8s kubectl port-forward -n container-registry service/registry 5000:5000
    ```
  - Alternative: Save and load images for transfer:
    ```bash
    # On dev server
    docker save localhost:32000/image:tag > image.tar
    scp image.tar user@staging:/tmp/
    
    # On staging server
    docker load < /tmp/image.tar
    microk8s ctr image import /tmp/image.tar
    ```

## Development to Production Transition Checklist

- [ ] Update domain configuration
- [ ] Configure SSL certificates
- [ ] Set appropriate resource limits
- [ ] Test multi-node distribution
- [ ] Verify security policies and network isolation
- [ ] Implement monitoring and backup strategy
- [ ] Test tenant provisioning and lifecycle management
- [ ] Verify subdomain and routing configuration

## Conclusion

By using dedicated cloud servers with MicroK8s for development and staging, you create a more production-like environment from the start. This approach eliminates many of the challenges of cross-environment development by using the same underlying technologies (Kubernetes) throughout the development lifecycle.

The namespace-based tenant isolation strategy provides a clean, secure way to separate customer instances while maintaining ease of management for the platform operator.
