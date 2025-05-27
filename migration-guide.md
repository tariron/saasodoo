# Migration Guide
## Odoo SaaS Platform

**Version:** 1.0  
**Date:** May 20, 2025  

This guide provides detailed instructions for migrating your Odoo SaaS platform between servers. The process is designed to be straightforward with minimal downtime.

## Pre-Migration Checklist

- [ ] Source server is running correctly
- [ ] Destination server meets the minimum requirements
- [ ] SSH access to both servers
- [ ] DNS access to update records
- [ ] Enough storage on destination server for all tenant data
- [ ] Maintenance window communicated to users

## 1. Preparation

### 1.1 Set Up Environment Variables

1. Define environment variables for source and destination servers
2. Create migration directory for temporary storage

### 1.2 Install Required Tools on Destination Server

1. Install MicroK8s on the destination server
2. Enable required addons: DNS, ingress, metrics-server, storage, registry
3. Install supporting packages: Python, pip, jq, rsync
4. Install Python dependencies for the platform

## 2. Export Configurations

### 2.1 Export Kubernetes Resources

1. Create an export script to capture all tenant namespaces
2. Export all resources per namespace:
   - Deployments
   - Services
   - Persistent volume claims
   - ConfigMaps
   - Secret structures (without actual data)
   - Ingress configurations
   - Network policies

3. Export system namespace resources
4. Export Traefik configuration

### 2.2 Export Platform Code and Data

1. Create a backup of the application code
2. Generate a list of all tenant namespaces

## 3. Backup Tenant Data

### 3.1 Create Tenant Backups

1. Create a backup directory structure
2. For each tenant namespace:
   - **Database Strategy Detection**: Identify if tenant uses shared or dedicated PostgreSQL
   - **Shared Database Backup**: For tenants using shared PostgreSQL, backup specific database within shared instance
   - **Dedicated Database Backup**: For tenants using dedicated PostgreSQL, backup entire PostgreSQL instance
   - Export the Odoo filestore
   - Capture tenant-specific secrets and database strategy metadata
3. **Shared Instance Backup**: Create consolidated backups of shared PostgreSQL instances
4. Backup central system database if present
5. Archive existing platform backups

### 3.2 Create Archive of All Exported Data

1. Package all backups and configuration files into a single archive
2. Include timestamp in the archive name

## 4. Transfer Data to New Server

1. Transfer migration archive to destination server
2. Transfer platform code to destination server

## 5. Set Up New Server

### 5.1 Prepare Platform Environment

1. Create platform directory structure
2. Extract platform code
3. Extract migration data
4. Configure kubectl

### 5.2 Install Core Components

1. Set up Traefik ingress controller
2. Create backup storage volume

## 6. Restore Tenant Data

### 6.1 Restore System Components

1. Recreate system namespace
2. Restore system database
3. Deploy system services

### 6.2 Restore Individual Tenants

1. For each tenant in the backup:
   - Create tenant namespace
   - Apply network policies
   - **Database Strategy Restoration**:
     - **Shared Strategy**: Assign to appropriate shared PostgreSQL instance or create new shared instance
     - **Dedicated Strategy**: Deploy dedicated PostgreSQL instance
   - Restore database from backup (strategy-specific)
   - Deploy Odoo instance with appropriate database connection configuration
   - Restore filestore data
   - Apply ingress configuration
2. **Shared Instance Management**: Ensure shared PostgreSQL instances are properly configured for multi-tenant access
3. Verify tenant restoration and database strategy assignment

## 7. Configure DNS and Test

### 7.1 DNS Configuration

1. Update DNS records to point to new server
2. Configure proper TTL values to minimize downtime
3. Verify DNS propagation

### 7.2 Testing Procedure

1. Test system components:
   - Authentication
   - Admin dashboard
   - Monitoring systems
   - Database strategy management
2. Test sample tenants:
   - Verify access to instances
   - Confirm database integrity for both shared and dedicated strategies
   - Validate user accounts
   - Test database strategy assignment accuracy
3. **Database Strategy Testing**:
   - Verify shared PostgreSQL instances serve multiple tenants correctly
   - Confirm dedicated PostgreSQL instances are properly isolated
   - Test database connection routing for both strategies
4. Run comprehensive test suite

## 8. Final Verification

### 8.1 Resource Verification

1. Compare resource usage between old and new servers
2. Verify pod distribution and scheduling
3. Check network policy enforcement

### 8.2 Performance Verification

1. Compare response times between old and new servers
2. Validate resource utilization under load
3. Test multi-tenant isolation

## 9. Cleanup Operations

### 9.1 Post-Migration Tasks

1. Archive migration files on destination server
2. Document any configuration differences
3. Update monitoring system targets

### 9.2 Source Server Decommissioning

1. Create final backup of source server
2. Verify all data has been successfully migrated
3. Schedule source server decommissioning after 1-2 weeks of successful operation

## 10. Troubleshooting

### 10.1 Common Issues

1. **DNS Propagation Delays**
   - Symptoms: Some users cannot access new system
   - Resolution: Verify DNS records, flush DNS caches

2. **Database Restoration Failures**
   - Symptoms: Odoo instance cannot connect to database
   - Resolution: Check PostgreSQL logs, verify credentials, retry restoration

3. **Ingress Configuration Issues**
   - Symptoms: Unable to access tenants through subdomains
   - Resolution: Verify Traefik configuration, check ingress resources

4. **Resource Constraints**
   - Symptoms: Pods failing to schedule or in pending state
   - Resolution: Check node resources, adjust resource requests

### 10.2 Rollback Procedure

1. Revert DNS changes to point back to source server
2. Document the reason for rollback
3. Analyze migration logs to identify failure points
4. Develop remediation plan before next attempt 