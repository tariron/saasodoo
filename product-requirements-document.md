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