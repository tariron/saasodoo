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
| TM-1 | Instance Creation | HIGH | Create new Odoo instance with dedicated namespace and database |
| TM-2 | Subdomain Selection | HIGH | Allow users to select subdomain (tenant.example.com) |
| TM-3 | Admin Credentials | HIGH | Configure admin username/password during creation |
| TM-4 | Instance Status | MEDIUM | Show status of Odoo instance (creating, running, stopped) |
| TM-5 | Instance Deletion | MEDIUM | Allow users to delete their instances |

### 2.3 Platform Administration

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| PA-1 | Admin Dashboard | HIGH | View all tenants and their status |
| PA-2 | Resource Monitoring | MEDIUM | Basic monitoring of CPU/memory usage per tenant |
| PA-3 | Node Distribution | MEDIUM | Verify tenant distribution across nodes |

### 2.4 Security & Isolation

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| SI-1 | Namespace Isolation | HIGH | Each tenant in separate Kubernetes namespace |
| SI-2 | Database Isolation | HIGH | Each tenant has dedicated PostgreSQL server |
| SI-3 | Network Policies | MEDIUM | Restrict network access between tenants |
| SI-4 | Resource Limits | MEDIUM | Apply CPU/memory limits per tenant |

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
| Database | PostgreSQL | Dedicated database instance per tenant |
| API Backend | Python/Flask | Simple API for tenant provisioning and management |
| Authentication | Supabase (online) | User authentication and management with self-hosted Supabase instance |
| Ingress | Traefik | Ingress controller for routing and subdomain management |
| DNS | Any provider with wildcard DNS | To support tenant subdomains |
| Registry | MicroK8s Registry | For storing and distributing container images |
| Monitoring | Basic Kubernetes metrics | For resource usage monitoring |
| CI/CD | Git-based workflow | Simple deployment from dev to staging to production |

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
             |  (Flask API)     |   | Supabase     |   | (Multiple)    |
             +----------+------+   +------+-------+   +-------+-------+
                        |                 |                   |
                        |                 |          +--------+--------+
                        |                 |          |                 |
                +-------v---------+       |    +-----v------+  +------v-----+
                | System Database |       |    | Odoo App   |  | PostgreSQL |
                | (PostgreSQL)    |       |    | Container  |  | Database   |
                +-----------------+       |    +------------+  +------------+
                                          |
                                    +-----v------+
                                    | Auth DB    |
                                    | (PostgreSQL)|
                                    +------------+
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
     - Handles user management
     - Creates Kubernetes resources
      - Online Supabase
     - Provides authentication services
     - Manages user sessions

4. **Data Plane**
   - System Database
     - Stores platform configuration
     - Tenant metadata
   - Per-Tenant Resources (in isolated namespaces)
     - Odoo application container
     - Dedicated PostgreSQL database

#### Isolation Model

Each tenant receives:
- Dedicated Kubernetes namespace
- Network isolation via K8s Network Policies
- Resource quotas and limits
- Dedicated PostgreSQL database instance
- Separate persistent storage volumes

#### Provisioning Flow

1. User requests new Odoo instance via API
2. SaaS Controller validates request
3. Controller creates new namespace with resource constraints
4. PostgreSQL instance deployed within namespace
5. Odoo container deployed with connection to database
6. Traefik configuration updated for subdomain routing
7. Initial admin credentials configured
8. Instance details returned to user

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
4. Admin can filter/search for specific tenants
5. Admin can view detailed information for any tenant

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