# Odoo SaaS Kit: Cross-Environment Development Guide

## Overview

This guide focuses on key considerations when developing the Odoo SaaS Kit that will operate across three different environments:
1. Local development using Docker Compose
2. Testing using MicroK8s on Windows
3. Production deployment on Contabo Ubuntu VPS

The platform programmatically creates isolated Odoo instances for customers in Kubernetes namespaces, with each tenant having a dedicated Odoo instance and PostgreSQL database.

## Key Considerations for Cross-Environment Development

### 1. Environment-Aware Configuration

- **Use environment variables** for configuration that varies between environments:
  - `DOMAIN_NAME` - Different domains for dev, testing, and production
  - `FLASK_ENV` - To indicate development, testing, or production mode
  - Authentication credentials and secrets

- **Create a configuration hierarchy**:
  - Base config with shared settings
  - Environment-specific config overrides
  - Local development overrides in `.env` files (excluded from version control)

### 2. Kubernetes Client Abstraction

- **Create an abstraction layer** for Kubernetes operations:
  - Mock implementation for local Docker development (no actual K8s)
  - Real implementation for MicroK8s testing and production
  - Same API interface regardless of environment

- **Switch based on environment detection**:
  ```
  # Conceptual pseudocode (not actual implementation)
  if MOCK_K8S:
      # Use mock implementation
  else:
      # Use actual Kubernetes client
  ```

### 3. Networking & Subdomain Strategy

- **Local Development**: 
  - Use mock services in Docker Compose
  - For testing with actual Odoo, use `localtest.me` or add entries to hosts file
  
- **MicroK8s Testing**:
  - Configure Traefik as ingress controller with NodePort exposed
  - Use hosts file entries or `nip.io`/`sslip.io` for accessing subdomains
  
- **Production**:
  - Configure Traefik with ClusterIP 
  - Set up wildcard DNS records
  - Use Let's Encrypt for SSL

### 4. Resource Management

- **Development**: Minimal resources, mock services
- **Testing**: Lower resource limits in MicroK8s to test more tenants
- **Production**: Realistic resource limits based on actual requirements

### 5. Tenant Isolation Approach

Ensure consistent tenant isolation approach across environments:

- **Namespace isolation** - Each tenant gets its own Kubernetes namespace
- **Network policies** - Restrict cross-tenant communication
- **Resource quotas** - Prevent resource starvation between tenants
- **Dedicated databases** - Each tenant has its own PostgreSQL database

### 6. Testing Cross-Environment Compatibility

Create systematic testing procedures:

1. **Local development tests** - Test API functionality with mocks
2. **MicroK8s deployment tests** - Test actual Kubernetes provisioning
3. **Cross-environment validation tests** - Ensure consistent behavior

## Practical Implementation Recommendations

### Docker to MicroK8s Transition

- **API Structure**: Keep API interface identical
- **Environment Detection**:
  ```
  # Detect if running in Kubernetes
  IN_KUBERNETES = os.environ.get('KUBERNETES_SERVICE_HOST') is not None
  ```
- **Error Handling**: Consistent error responses across environments

### MicroK8s to Production Transition

- **Template-based Resources**: Use templates with variables for Kubernetes manifests
- **Separate Configuration**: Keep values files for different environments
- **Consistent Naming**: Use consistent naming conventions across environments

### Traefik Configuration Across Environments

- **Development**: Basic Traefik configuration for local testing
- **MicroK8s**: NodePort with minimal configuration for testing
- **Production**: Full configuration with SSL certificates

## Common Challenges & Solutions

### 1. MicroK8s on Windows Networking

- **Challenge**: Accessing services on MicroK8s from Windows
- **Solutions**:
  - Use NodePort for Traefik and access via localhost:NodePort
  - Configure hosts file for testing subdomains
  - Consider port-forwarding for direct testing

### 2. Resource Limitations in Testing

- **Challenge**: Windows MicroK8s may have resource constraints
- **Solutions**:
  - Lower resource limits for testing
  - Use lightweight pod anti-affinity
  - Test with fewer tenants or one at a time

### 3. Database Management Across Environments

- **Challenge**: Database setup and migration across environments
- **Solutions**:
  - Use consistent PostgreSQL version across environments
  - Script database initialization
  - Implement backup/restore for migration

### 4. Security Model Consistency

- **Challenge**: Maintaining consistent security model
- **Solutions**:
  - Define security templates that work across environments
  - Apply network policies consistently
  - Use namespaces for isolation in all environments

## Environmental Transition Checklist

### Local to MicroK8s Transition

- [ ] Verify API compatibility with actual Kubernetes
- [ ] Test tenant creation and isolation
- [ ] Verify Traefik ingress and subdomain routing
- [ ] Test resource allocation and limits
- [ ] Verify database connectivity and persistence

### MicroK8s to Production Transition

- [ ] Update domain configuration
- [ ] Configure SSL certificates
- [ ] Set appropriate resource limits
- [ ] Test multi-node distribution
- [ ] Verify security policies and network isolation
- [ ] Implement monitoring and backup strategy

## Conclusion

By following these guidelines, you can ensure your Odoo SaaS Kit functions consistently across all three environments: local Docker development, MicroK8s testing on Windows, and production deployment on Contabo Ubuntu VPS.

The key is to create proper abstractions for environment-specific functionality while maintaining a consistent API and feature set that works the same way regardless of the underlying infrastructure.
