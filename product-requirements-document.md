# Product Requirements Document (PRD)
## Simple Odoo SaaS Platform

**Version:** 1.0  
**Date:** May 20, 2025  

## 1. Product Overview

### 1.1 Product Vision
Create a simple yet robust Odoo SaaS platform that allows customers to deploy their own isolated Odoo instances with minimal overhead. The platform should enable easy tenant management while maintaining strong isolation between customer environments.

### 1.2 Target Market
- Small business owners seeking Odoo instances without IT overhead
- Odoo consultants who want to host instances for multiple clients
- Startups needing affordable ERP solutions

### 1.3 MVP Feature Set
- User registration and authentication via Supabase
- Self-service Odoo instance creation
- Complete tenant isolation (separate namespaces, dedicated databases)
- Custom subdomain per tenant (tenant.example.com)
- Pre-configured admin credentials during instance creation
- Basic admin dashboard for instance management
- Free tier for immediate usage (future: 14-day trial, paid plans)

### 1.4 Adaptability to Other SaaS Applications
This SaaS platform architecture has been designed with adaptability in mind and can be modified to host various containerized applications beyond Odoo:

- **Application Agnostic Design**: The core tenant isolation, resource management, and provisioning mechanisms are independent of the specific application being deployed
- **Containerization Support**: Any application that can be containerized can be adapted to this platform with minimal changes
- **Database Flexibility**: The PostgreSQL deployment pattern can be modified to support other database types (MySQL, MongoDB, etc.)
- **Customizable Resource Tiers**: Resource allocation tiers can be tailored to specific application requirements
- **Extensible API**: The backend API can be extended with application-specific endpoints as needed

## 2. Feature Requirements

### 2.1 User Authentication

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| UA-1 | User Registration | HIGH | Allow users to register with email/password |
| UA-2 | User Login | HIGH | Authenticate users using Supabase |
| UA-3 | Password Reset | MEDIUM | Enable users to reset their passwords |
| UA-4 | Profile Management | LOW | Allow users to update profile information |

### 2.2 Tenant Management

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| TM-1 | Instance Creation | HIGH | Create new Odoo instance with appropriate database strategy |
| TM-2 | Subdomain Selection | HIGH | Allow users to select subdomain (tenant.example.com) |
| TM-3 | Admin Credentials | HIGH | Configure admin username/password during creation |
| TM-4 | Instance Status | MEDIUM | Show status of Odoo instance (creating, running, stopped) |
| TM-5 | Instance Deletion | MEDIUM | Allow users to delete their instances |
| TM-6 | Database Strategy Display | MEDIUM | Show current database strategy (shared/dedicated) in tenant details |
| TM-7 | Strategy Migration Request | LOW | Allow users to request migration between database strategies |
| TM-8 | Performance Monitoring | MEDIUM | Monitor tenant performance to recommend strategy optimization |

### 2.3 Platform Administration

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| PA-1 | Admin Dashboard | HIGH | View all tenants and their status |
| PA-2 | Resource Monitoring | MEDIUM | Basic monitoring of CPU/memory usage per tenant |
| PA-3 | Node Distribution | MEDIUM | Verify tenant distribution across nodes |
| PA-4 | Database Strategy Overview | HIGH | View database strategy distribution and utilization |
| PA-5 | Strategy Migration Management | MEDIUM | Initiate and monitor database strategy migrations |
| PA-6 | Shared Instance Management | MEDIUM | Monitor and manage shared PostgreSQL instances |
| PA-7 | Capacity Planning | MEDIUM | Monitor shared instance capacity and plan scaling |

### 2.4 Security & Isolation

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| SI-1 | Namespace Isolation | HIGH | Each tenant in separate Kubernetes namespace |
| SI-2 | Database Isolation | HIGH | Hybrid database strategy: shared PostgreSQL for basic/standard tiers, dedicated PostgreSQL for premium/enterprise tiers |
| SI-3 | Network Policies | MEDIUM | Restrict network access between tenants |
| SI-4 | Resource Limits | MEDIUM | Apply CPU/memory limits per tenant |
| SI-5 | Database Strategy Selection | HIGH | Automatic selection of database approach based on tenant tier, compliance, and performance requirements |
| SI-6 | Shared Database Security | HIGH | Multi-tenant security for shared PostgreSQL instances with database-level isolation |
| SI-7 | Cross-Strategy Migration | MEDIUM | Ability to migrate tenants between shared and dedicated database strategies |

## 3. Technical Requirements

### 3.1 Infrastructure

| ID | Requirement | Description |
|----|-------------|-------------|
| IR-1 | MicroK8s | Kubernetes distribution for both development and production |
| IR-2 | Traefik | Ingress controller for subdomain routing |
| IR-3 | PostgreSQL | Database for Odoo instances |
| IR-4 | Bitnami Odoo | Pre-configured Odoo container images |
| IR-5 | Multi-node Support | Ability to distribute tenants across multiple nodes |

### 3.2 Development Environment

| ID | Requirement | Description |
|----|-------------|-------------|
| DE-1 | Windows Development | Support for Windows using Docker Desktop and MicroK8s |
| DE-2 | Multiple Windows Nodes | Testing across multiple Windows machines |
| DE-3 | Code Limitations | Maximum 4000 lines of code total |

### 3.3 Production Environment

| ID | Requirement | Description |
|----|-------------|-------------|
| PE-1 | Ubuntu 24.10 | Production environment on Ubuntu 24.10 |
| PE-2 | Scalability | Support for multiple nodes in production |
| PE-3 | Deployment | Simple deployment process |

### 3.4 Technology Stack

| Layer | Technology | Description |
|-------|------------|-------------|
| Container Orchestration | MicroK8s | Lightweight Kubernetes distribution for both dev and production |
| Containerization | Docker | For building and managing container images |
| Application | Bitnami Odoo | Pre-configured Odoo container images (Community Edition) |
| Database | PostgreSQL | Hybrid approach: shared PostgreSQL instances for basic/standard tiers, dedicated instances for premium/enterprise tiers |
| API Backend | Python/Flask | Simple API for tenant provisioning and management |
| Platform Database & Auth | Supabase | User authentication, tenant metadata storage, user management, and platform configuration |
| Billing | Kill Bill | Open-source subscription billing and payment platform |
| Ingress | Traefik | Ingress controller for routing and subdomain management |
| DNS | Any provider with wildcard DNS | To support tenant subdomains |
| Registry | MicroK8s Registry | For storing and distributing container images |
| Monitoring | Basic Kubernetes metrics | For resource usage monitoring |
| CI/CD | Git-based workflow | Simple deployment from dev to staging to production |

### 3.4.1 Database Strategy Requirements

The platform implements a hybrid database approach with automatic strategy selection based on multiple criteria:

#### Database Strategy Decision Matrix

| Criteria | Shared PostgreSQL | Dedicated PostgreSQL |
|----------|-------------------|----------------------|
| **Tenant Tier** | Basic, Standard | Premium, Enterprise |
| **Data Volume** | < 5GB | > 5GB |
| **Compliance Requirements** | General use | HIPAA, SOX, PCI-DSS |
| **Performance Requirements** | Standard workload | High-performance required |
| **Customization Needs** | Standard configuration | Custom database settings |
| **Cost Sensitivity** | Cost-optimized | Performance-focused |

#### Shared PostgreSQL Configuration

- **Resource Allocation**: 2-4 CPU cores, 4-8GB RAM per shared instance
- **Tenant Limits**: Maximum 50 tenants per shared PostgreSQL instance
- **Database Isolation**: Separate database per tenant within shared PostgreSQL server
- **Connection Management**: Dedicated connection pools per tenant
- **Security**: Row-level security policies and tenant-specific schemas

#### Dedicated PostgreSQL Configuration

- **Resource Allocation**: 1-2 CPU cores, 2-4GB RAM per dedicated instance
- **Isolation**: Complete PostgreSQL server isolation per tenant
- **Customization**: Tenant-specific PostgreSQL configuration options
- **Performance**: Dedicated resources for high-performance requirements
- **Compliance**: Full data isolation for regulatory compliance

#### Strategy Selection Logic

1. **Tier-Based Selection**: Automatic assignment based on subscription tier
2. **Compliance Override**: Force dedicated if compliance flags are set
3. **Performance Override**: Switch to dedicated if performance thresholds exceeded
4. **Volume Override**: Move to dedicated when data volume exceeds limits
5. **Custom Requirements**: Manual override for special tenant needs

### 3.5 System Architecture

The system follows a microservices architecture pattern with Kubernetes orchestration, focusing on tenant isolation and scalability.

#### Architecture Overview

```
                                  +-------------------+
                                  |    DNS (*.example.com)    |
                                  +----------+--------+
                                             |
                                  +----------v--------+
                                  |     Traefik       |
                                  | (Ingress Controller) |
                                  +----------+--------+
                                             |
                        +---------+----------+---------+
                        |                    |         |
             +----------v------+   +---------v----+   +-------v-------+
             |  SaaS Controller |   |              |   | Tenant Namespaces |
             |  (Flask API)     |<->| Supabase     |   | (Multiple)    |
             +----------+------+   +------+-------+   +-------+-------+
                        |                 |                   |
                        |                 |          +--------+--------+
                        v                 |          |                 |
                +----------------+        |    +-----v------+  +------v-----+
                | Tenant Metadata |       |    | Odoo App   |  | DB Strategy |
                | (Supabase DB)   |       |    | Container  |  | Selection   |
                +----------------+        |    +------------+  +------+-----+
                        |                 |                           |
                        |                 |          +----------------+-----------------+
                        v                 v          |                                  |
                +----------------+  +------------+   |    +-----------+    +----------+ |
                |    Kill Bill   |  | Auth & User|   |    | Shared    |    |Dedicated | |
                |   (Billing)    |  | Management |   |    |PostgreSQL |    |PostgreSQL| |
                +----------------+  +------------+   |    |(Multi-DB) |    |(Per-Tenant)| |
                                                     |    +-----------+    +----------+ |
                                                     +----------------------------------+
```

#### Key Components

1. **DNS Layer**
   - Wildcard DNS (*.example.com) directs all subdomains to the platform
   - Each tenant assigned a unique subdomain (tenant.example.com)

2. **Ingress Layer**
   - Traefik handles all incoming traffic
   - Routes requests to appropriate services based on hostname
   - Terminates SSL/TLS

3. **Control Plane**
   - SaaS Controller API (Flask)
     - Manages tenant provisioning
     - Creates Kubernetes resources
     - Communicates with Supabase for user and tenant data
     - Integrates with Kill Bill for subscription management
     - Database strategy selection and management
     - Cross-strategy migration orchestration
   - Supabase Platform
     - Authentication services
     - User profile management
     - Tenant metadata storage (including database strategy)
     - Platform configuration data
     - Real-time events for dashboard updates
   - Kill Bill
     - Subscription billing management
     - Payment processing
     - Invoice generation
     - Pricing plan management
     - Usage-based billing calculations

4. **Data Plane**
   - Tenant Metadata (in Supabase)
     - User profiles and preferences
     - Tenant configuration details
     - Database strategy assignments
     - Subscription and billing information
     - Platform settings and feature flags
   - Per-Tenant Resources (in isolated namespaces)
     - Odoo application container
     - Database connection (shared or dedicated based on strategy)
   - Shared PostgreSQL Instances
     - Multi-tenant PostgreSQL servers
     - Separate databases per tenant
     - Shared resource pools
     - Centralized backup management
   - Dedicated PostgreSQL Instances
     - Single-tenant PostgreSQL servers
     - Complete isolation per tenant
     - Individual resource allocation
     - Tenant-specific backup processes

#### Isolation Model

Each tenant receives:
- Dedicated Kubernetes namespace
- Network isolation via K8s Network Policies
- Resource quotas and limits
- Database isolation (shared database or dedicated PostgreSQL instance based on tier)
- Separate persistent storage volumes

#### Database Isolation Approaches

**Shared PostgreSQL Strategy:**
- Separate database within shared PostgreSQL server
- Database-level access controls and permissions
- Tenant-specific connection pools
- Row-level security policies
- Schema-based data separation
- Shared backup and maintenance windows

**Dedicated PostgreSQL Strategy:**
- Complete PostgreSQL server isolation per tenant
- Full administrative control over database instance
- Independent resource allocation and scaling
- Tenant-specific backup schedules
- Custom PostgreSQL configuration options
- Isolated maintenance and upgrade cycles

#### Provisioning Flow

1. User registers on the platform via Supabase authentication
2. User selects a resource tier and billing plan in Kill Bill
3. User enters payment information processed by Kill Bill
4. Upon successful payment setup, user requests new Odoo instance via API
5. SaaS Controller validates request and subscription status with Kill Bill
6. **Database Strategy Selection**: Controller determines database strategy based on:
   - Subscription tier (basic/standard → shared, premium/enterprise → dedicated)
   - Compliance requirements (regulatory compliance → dedicated)
   - Performance requirements (high-performance needs → dedicated)
   - Data volume projections (large datasets → dedicated)
7. Controller creates new namespace with resource constraints based on subscription tier
8. **Database Provisioning** (strategy-dependent):
   - **Shared Strategy**: Assign to existing shared PostgreSQL or create new shared instance
   - **Dedicated Strategy**: Deploy new dedicated PostgreSQL instance
9. Odoo container deployed with appropriate database connection configuration
10. Traefik configuration updated for subdomain routing
11. Initial admin credentials configured
12. Instance details returned to user
13. Periodic usage data sent to Kill Bill for billing calculations
14. **Continuous Monitoring**: Track usage patterns for potential strategy migration

### 3.6 Development Standards

#### Coding Patterns

1. **Module Organization**
   - Keep modules small and focused on a single responsibility
   - Large modules (>300 lines) must be broken into smaller components
   - Follow a hierarchical structure for related functionality

2. **Code Organization**
   - SaaS Controller should be organized by functional domains:
     - `api/` - API endpoints and request handling
     - `k8s/` - Kubernetes integration
     - `db/` - Database operations
     - `auth/` - Authentication functionality
     - `utils/` - Shared utility functions

3. **Function Size**
   - Individual functions should not exceed 50 lines
   - Complex operations should be broken into smaller, composable functions
   - Use descriptive naming for functions and variables

4. **Error Handling**
   - Consistent error handling pattern throughout the codebase
   - Proper logging of errors with context
   - Graceful degradation when possible

5. **Testing**
   - Unit tests for critical functionality
   - Mock external dependencies (Kubernetes, databases)
   - Maintainable test code that focuses on behavior, not implementation

## 4. User Journeys

### 4.1 New User Registration & Instance Creation

1. User visits the platform landing page
2. User clicks "Sign Up" and enters email/password
3. User confirms email via Supabase authentication flow
4. User is directed to dashboard
5. User clicks "Create New Instance"
6. User enters:
   - Subdomain name
   - Admin email
   - Admin password
7. User clicks "Create"
8. System shows progress indication while provisioning
9. Once complete, user is shown instance details with URL
10. User can access their Odoo instance at subdomain.example.com

### 4.2 Admin Management Flow

1. Admin logs in to platform
2. Admin views dashboard showing all tenants
3. Admin can see:
   - Instance status
   - Resource usage
   - Node distribution
   - Database strategy (shared/dedicated)
   - Shared instance utilization
4. Admin can filter/search for specific tenants
5. Admin can view detailed information for any tenant
6. Admin can manage database strategies:
   - View strategy distribution across all tenants
   - Monitor shared PostgreSQL instance capacity
   - Initiate strategy migrations when needed
   - Plan capacity for shared instances

## 5. Future Enhancements (Post-MVP)

| ID | Feature | Description |
|----|---------|-------------|
| FE-1 | Trial Period | 14-day free trial, then requiring payment |
| FE-2 | Subscription Tiers | Different pricing tiers with varied resources |
| FE-3 | Module Selection | Allow users to choose Odoo modules during setup |
| FE-4 | Automated Backups | Regular backups of tenant data |
| FE-5 | Custom Domains | Support for customer's own domains |

## 6. Success Metrics

- Successfully provision 5+ instances across multiple nodes
- Achieve complete tenant isolation (no data leakage)
- Maintain <2 minute provisioning time per instance
- Support at least 10 concurrent users on separate instances
- Implement the MVP within a single weekend