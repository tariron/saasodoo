# Product Requirements Document: SaaSOdoo Admin Tool

**Document Version:** 1.0
**Date:** 2026-01-16
**Status:** Draft - Pending Approval

---

## 1. Executive Summary

### 1.1 Overview

The SaaSOdoo Admin Tool is a unified administrative interface for the SaaSOdoo multi-tenant Odoo SaaS platform. It provides the internal team with comprehensive visibility and control over customers, instances, billing, and infrastructure—replacing the current fragmented approach of scattered API endpoints and direct database queries.

### 1.2 Problem Statement

Currently, the SaaSOdoo platform lacks a unified admin interface:
- Admin functionality is scattered across services (`/admin` endpoints in instance-service and database-service)
- No single view of customer data across services
- Troubleshooting requires querying multiple databases and services
- No audit trail for administrative actions
- Manual operations require direct API calls or database access

### 1.3 Solution

Build a dedicated Admin Tool consisting of:
- **Admin Service (BFF)**: A Backend-for-Frontend service that aggregates data from all microservices
- **Admin Frontend**: A React-based dashboard with comprehensive views and action capabilities

### 1.4 Target Users

Internal operations team handling:
- Platform operations and monitoring
- Customer support and success
- Billing and subscription management
- Infrastructure management

---

## 2. Architecture

### 2.1 System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Admin Frontend                            │
│              (React + Shadcn/ui + Tailwind)                 │
│                     Port: 3001                               │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Admin Service (BFF)                       │
│                   FastAPI - Port: 8010                       │
│  ┌─────────────┬─────────────┬─────────────┬──────────────┐ │
│  │ Auth Module │ Aggregation │  Actions    │  Audit Log   │ │
│  │ (JWT/Admin) │   Layer     │  Executor   │   Writer     │ │
│  └─────────────┴─────────────┴─────────────┴──────────────┘ │
│                           │                                  │
│              ┌────────────┴────────────┐                    │
│              ▼                         ▼                    │
│     ┌─────────────┐           ┌─────────────┐              │
│     │  Admin DB   │           │    Redis    │              │
│     │ (PostgreSQL)│           │  (Sessions) │              │
│     └─────────────┘           └─────────────┘              │
└─────────────────────┬───────────────────────────────────────┘
                      │ Internal HTTP calls
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
   ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐
   │  User   │  │ Instance │  │ Billing │  │ Database │
   │ Service │  │ Service  │  │ Service │  │ Service  │
   │  :8001  │  │  :8003   │  │  :8004  │  │          │
   └─────────┘  └──────────┘  └─────────┘  └──────────┘
```

### 2.2 Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Architecture | BFF Pattern | Services are isolated; aggregation layer needed for cross-service views |
| Auth | Separate admin users | Clean separation from customers; easier to audit and secure |
| Frontend Framework | React + Shadcn/ui | Matches team skills; pre-built components speed admin UI development |
| Backend Framework | FastAPI | Consistent with existing services; async support for aggregation |

---

## 3. Database Schema

### 3.1 Admin Database

```sql
-- Admin users (separate from customers)
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'operator',
    is_active BOOLEAN DEFAULT true,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Admin sessions
CREATE TABLE admin_sessions (
    id UUID PRIMARY KEY,
    admin_user_id UUID REFERENCES admin_users(id),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Audit log for all admin actions
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID REFERENCES admin_users(id),
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(255) NOT NULL,
    target_customer_id UUID,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_audit_logs_admin_user ON audit_logs(admin_user_id);
CREATE INDEX idx_audit_logs_target ON audit_logs(target_type, target_id);
CREATE INDEX idx_audit_logs_customer ON audit_logs(target_customer_id);
CREATE INDEX idx_audit_logs_created ON audit_logs(created_at DESC);
```

### 3.2 Role Permissions

| Role | Permissions |
|------|-------------|
| `operator` | View all, execute day-to-day actions (restart, extend trial, view logs) |
| `admin` | All operator permissions + billing adjustments, cancel subscriptions |
| `super_admin` | All permissions + manage admin users, full audit log access |

---

## 4. API Specification

### 4.1 Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/admin/auth/login` | Admin login → JWT token |
| POST | `/admin/auth/logout` | Invalidate session |
| POST | `/admin/auth/refresh` | Refresh token |
| GET | `/admin/auth/me` | Current admin user info |

### 4.2 Dashboard Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/dashboard/overview` | Platform stats (customers, instances, revenue, health) |
| GET | `/admin/dashboard/alerts` | Items needing attention |

### 4.3 Customer Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/customers` | List + search (paginated, filterable) |
| GET | `/admin/customers/{id}` | Customer 360 view |
| GET | `/admin/customers/{id}/instances` | Customer's instances |
| GET | `/admin/customers/{id}/billing` | Billing history, subscriptions |
| GET | `/admin/customers/{id}/activity` | Recent activity timeline |

### 4.4 Instance Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/instances` | List all instances (filterable) |
| GET | `/admin/instances/failed` | Failed instances queue |
| GET | `/admin/instances/{id}` | Instance details |
| GET | `/admin/instances/{id}/logs` | Instance logs |
| POST | `/admin/instances/{id}/retry` | Retry failed provisioning |
| POST | `/admin/instances/{id}/start` | Start instance |
| POST | `/admin/instances/{id}/stop` | Stop instance |
| POST | `/admin/instances/{id}/restart` | Restart instance |
| POST | `/admin/instances/{id}/backup` | Trigger manual backup |

### 4.5 Billing Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/billing/overview` | Revenue, MRR, failed payments, expiring trials |
| GET | `/admin/billing/subscriptions` | All subscriptions (filterable) |
| GET | `/admin/billing/subscriptions/{id}` | Subscription details |
| POST | `/admin/billing/subscriptions/{id}/extend-trial` | Extend trial period |
| POST | `/admin/billing/subscriptions/{id}/apply-credit` | Apply credit/adjustment |
| POST | `/admin/billing/subscriptions/{id}/cancel` | Cancel subscription |
| POST | `/admin/billing/subscriptions/{id}/refund` | Process refund |

### 4.6 Database Pool Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/pools` | All pools with health/capacity |
| GET | `/admin/pools/{id}` | Pool details |
| POST | `/admin/pools/provision` | Provision new pool |
| PATCH | `/admin/pools/{id}` | Update pool settings (max_instances, etc.) |
| POST | `/admin/pools/{id}/health-check` | Trigger health check |

### 4.7 Audit Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/audit` | Audit log (filterable by admin, action, target, date) |
| GET | `/admin/audit/export` | Export audit log as CSV |

---

## 5. Frontend Views

### 5.1 View Summary

| View | Route | Description |
|------|-------|-------------|
| Platform Overview | `/` | High-level stats, alerts, health |
| Customer List | `/customers` | Searchable customer table |
| Customer 360 | `/customers/:id` | Complete customer view |
| Instance List | `/instances` | All instances with filters |
| Failed Queue | `/instances/failed` | Instances needing attention |
| Billing Overview | `/billing` | Revenue, trials, payments |
| Database Pools | `/pools` | Pool status and management |
| Audit Log | `/audit` | Administrative action history |

### 5.2 Platform Overview (`/`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Platform Overview                                              │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │
│  │ Customers │ │ Instances │ │ Active    │ │ Monthly   │       │
│  │    247    │ │    312    │ │ Trials: 18│ │ Rev: $12K │       │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘       │
│                                                                 │
│  ⚠ Alerts (3)                                                   │
│  ├─ 2 failed instances awaiting retry                          │
│  ├─ 5 trials expiring in 3 days                                │
│  └─ 1 database pool at 90% capacity                            │
│                                                                 │
│  Recent Activity                    Instance Health             │
│  ┌─────────────────────────┐       ┌─────────────────────┐     │
│  │ 10:23 - Trial extended  │       │ ● Running: 280      │     │
│  │ 10:15 - Instance retry  │       │ ● Stopped: 25       │     │
│  │ 09:58 - Credit applied  │       │ ● Error: 2          │     │
│  └─────────────────────────┘       │ ● Creating: 5       │     │
│                                    └─────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 Customer List (`/customers`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Customers                                    [+ Add Customer]  │
├─────────────────────────────────────────────────────────────────┤
│  🔍 Search    [Filter: Status ▼] [Plan ▼] [Created ▼]          │
├─────────────────────────────────────────────────────────────────┤
│  Email              │ Name       │ Instances │ Plan    │ Status │
│  ─────────────────────────────────────────────────────────────  │
│  john@acme.com      │ John Smith │ 3         │ Premium │ Active │
│  sara@beta.io       │ Sara Lee   │ 1         │ Starter │ Trial  │
│  dev@gamma.co       │ Dev Team   │ 2         │ Premium │ Active │
├─────────────────────────────────────────────────────────────────┤
│  Showing 1-25 of 247                          < 1 2 3 ... 10 >  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 Customer 360 (`/customers/:id`)

```
┌─────────────────────────────────────────────────────────────────┐
│  ← Back    John Smith (john@acme.com)           [Actions ▼]     │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────┐ ┌─────────────────────────────┐│
│  │ Customer Info               │ │ Billing Summary             ││
│  │ ID: c7f3a2b1...             │ │ Plan: Premium Monthly       ││
│  │ Joined: 2024-08-15          │ │ Status: Active              ││
│  │ Email verified: ✓           │ │ MRR: $99/mo                 ││
│  │ Last login: 2 hours ago     │ │ Next invoice: Jan 25        ││
│  └─────────────────────────────┘ └─────────────────────────────┘│
│                                                                 │
│  [Instances]  [Billing History]  [Activity]                     │
│  ───────────────────────────────────────────────────────────── │
│  │ Name         │ Status  │ Version │ Plan    │ Actions       ││
│  │ production   │ ●Running│ 17.0    │ Premium │ [Stop][Logs]  ││
│  │ staging      │ ●Running│ 17.0    │ Premium │ [Stop][Logs]  ││
│  │ dev-test     │ ○Stopped│ 18.0    │ Premium │ [Start][Logs] ││
└─────────────────────────────────────────────────────────────────┘
```

### 5.5 Instance List (`/instances`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Instances                                                      │
├─────────────────────────────────────────────────────────────────┤
│  🔍 Search   [Status ▼] [Version ▼] [Plan ▼] [Type ▼]          │
├─────────────────────────────────────────────────────────────────┤
│  Name        │ Customer      │ Status   │ Version │ Plan       │
│  ──────────────────────────────────────────────────────────────│
│  production  │ john@acme.com │ ●Running │ 17.0    │ Premium    │
│  my-odoo     │ sara@beta.io  │ ●Running │ 16.0    │ Starter    │
│  test-inst   │ dev@gamma.co  │ ⚠ Error  │ 18.0    │ Premium    │
├─────────────────────────────────────────────────────────────────┤
│  Showing 1-25 of 312                          < 1 2 3 ... 13 >  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.6 Failed Instances Queue (`/instances/failed`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Failed Instances (2)                          [Retry All]      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ⚠ test-inst (dev@gamma.co)                                  ││
│  │ Failed: 2 hours ago │ Attempts: 3                           ││
│  │ Error: Database allocation timeout                          ││
│  │ [View Logs]  [Retry]  [View Customer]                       ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ⚠ new-instance (mike@delta.org)                             ││
│  │ Failed: 30 mins ago │ Attempts: 1                           ││
│  │ Error: Docker service creation failed                       ││
│  │ [View Logs]  [Retry]  [View Customer]                       ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### 5.7 Billing Overview (`/billing`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Billing Overview                                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐       │
│  │ MRR       │ │ Active    │ │ Trials    │ │ Failed    │       │
│  │ $12,450   │ │ Subs: 198 │ │ Active: 18│ │ Payments:3│       │
│  │ ↑ 8% mom  │ │           │ │ Exp <7d: 5│ │           │       │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘       │
│                                                                 │
│  [Active Subs]  [Trials]  [Failed Payments]  [Recent Actions]   │
│  ───────────────────────────────────────────────────────────── │
│  │ Customer       │ Plan     │ Status  │ Expires │ Actions    ││
│  │ sara@beta.io   │ Starter  │ Trial   │ 3 days  │ [Extend]   ││
│  │ new@user.com   │ Premium  │ Trial   │ 5 days  │ [Extend]   ││
│  │ test@demo.co   │ Starter  │ Trial   │ 7 days  │ [Extend]   ││
└─────────────────────────────────────────────────────────────────┘
```

### 5.8 Database Pools (`/pools`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Database Pools                               [+ Provision New] │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐ ┌──────────────────────┐             │
│  │ shared-pool-01       │ │ shared-pool-02       │             │
│  │ ████████░░ 45/50     │ │ █████░░░░░ 23/50     │             │
│  │ Health: ● Healthy    │ │ Health: ● Healthy    │             │
│  │ [Details] [Settings] │ │ [Details] [Settings] │             │
│  └──────────────────────┘ └──────────────────────┘             │
│  ┌──────────────────────┐ ┌──────────────────────┐             │
│  │ dedicated-pool-01    │ │ shared-pool-03       │             │
│  │ ██░░░░░░░░ 8/40      │ │ █████████░ 47/50     │ ⚠ 90%      │
│  │ Health: ● Healthy    │ │ Health: ● Healthy    │             │
│  │ [Details] [Settings] │ │ [Details] [Settings] │             │
│  └──────────────────────┘ └──────────────────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### 5.9 Audit Log (`/audit`)

```
┌─────────────────────────────────────────────────────────────────┐
│  Audit Log                                     [Export CSV]     │
├─────────────────────────────────────────────────────────────────┤
│  🔍 Search   [Admin ▼] [Action ▼] [Target ▼] [Date Range 📅]   │
├─────────────────────────────────────────────────────────────────┤
│  Timestamp        │ Admin      │ Action          │ Target       │
│  ──────────────────────────────────────────────────────────────│
│  Jan 16, 10:23    │ alice@team │ trial.extended  │ sara@beta.io │
│  Jan 16, 10:15    │ alice@team │ instance.retry  │ test-inst    │
│  Jan 16, 09:58    │ bob@team   │ credit.applied  │ john@acme.co │
│  Jan 16, 09:30    │ bob@team   │ instance.restart│ production   │
│  Jan 15, 17:45    │ alice@team │ sub.cancelled   │ old@user.com │
├─────────────────────────────────────────────────────────────────┤
│  [View Details] on row click → shows full JSONB payload         │
└─────────────────────────────────────────────────────────────────┘
```

### 5.10 Action Modals

**Extend Trial Modal**
```
┌─────────────────────────────────────────┐
│  Extend Trial                      [X]  │
├─────────────────────────────────────────┤
│  Customer: sara@beta.io                 │
│  Current expiry: Jan 19, 2025           │
│                                         │
│  Extend by: [7 days ▼]                  │
│  New expiry: Jan 26, 2025               │
│                                         │
│  Reason (required):                     │
│  ┌─────────────────────────────────┐   │
│  │ Customer evaluating enterprise  │   │
│  │ features, needs more time       │   │
│  └─────────────────────────────────┘   │
│                                         │
│            [Cancel]  [Extend Trial]     │
└─────────────────────────────────────────┘
```

**Apply Credit Modal**
```
┌─────────────────────────────────────────┐
│  Apply Credit                      [X]  │
├─────────────────────────────────────────┤
│  Customer: john@acme.com                │
│  Current balance: $0.00                 │
│                                         │
│  Amount: [$] [25.00        ]            │
│  Type:   (●) Credit  ( ) Debit          │
│                                         │
│  Reason (required):                     │
│  ┌─────────────────────────────────┐   │
│  │ Compensation for downtime on    │   │
│  │ Jan 14                          │   │
│  └─────────────────────────────────┘   │
│                                         │
│            [Cancel]  [Apply Credit]     │
└─────────────────────────────────────────┘
```

**Pool Settings Modal**
```
┌─────────────────────────────────────────┐
│  Pool Settings: shared-pool-03     [X]  │
├─────────────────────────────────────────┤
│  Current instances: 47                  │
│                                         │
│  Max instances:  [50      ] → [60     ] │
│  CPU limit:      [4 cores ]             │
│  Memory limit:   [8 GB    ]             │
│                                         │
│  Reason (required):                     │
│  ┌─────────────────────────────────┐   │
│  │ Increasing capacity for growth  │   │
│  └─────────────────────────────────┘   │
│                                         │
│            [Cancel]  [Save Changes]     │
└─────────────────────────────────────────┘
```

---

## 6. Project Structure

### 6.1 Admin Service (Backend)

```
services/admin-service/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app entry
│   ├── config.py                  # Settings & environment
│   ├── dependencies.py            # Dependency injection
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py                # /admin/auth endpoints
│   │   ├── dashboard.py           # /admin/dashboard endpoints
│   │   ├── customers.py           # /admin/customers endpoints
│   │   ├── instances.py           # /admin/instances endpoints
│   │   ├── billing.py             # /admin/billing endpoints
│   │   ├── pools.py               # /admin/pools endpoints
│   │   └── audit.py               # /admin/audit endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py        # Admin authentication logic
│   │   ├── aggregator.py          # Cross-service data aggregation
│   │   ├── user_client.py         # HTTP client → user-service
│   │   ├── instance_client.py     # HTTP client → instance-service
│   │   ├── billing_client.py      # HTTP client → billing-service
│   │   ├── database_client.py     # HTTP client → database-service
│   │   └── audit_service.py       # Audit logging
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── admin_user.py          # AdminUser SQLAlchemy model
│   │   ├── audit_log.py           # AuditLog SQLAlchemy model
│   │   └── schemas.py             # Pydantic request/response schemas
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py            # Database connection
│   │   └── migrations/            # Alembic migrations
│   │
│   └── utils/
│       ├── __init__.py
│       ├── security.py            # JWT, password hashing
│       └── permissions.py         # Role-based access control
│
├── tests/
│   ├── test_auth.py
│   ├── test_customers.py
│   └── ...
│
├── Dockerfile
├── requirements.txt
└── docker-compose.yml
```

### 6.2 Admin Frontend

```
admin-frontend/
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── index.css                  # Tailwind imports
│   │
│   ├── api/
│   │   ├── client.ts              # Axios instance with auth
│   │   ├── auth.ts                # Auth API calls
│   │   ├── dashboard.ts           # Dashboard API calls
│   │   ├── customers.ts           # Customer API calls
│   │   ├── instances.ts           # Instance API calls
│   │   ├── billing.ts             # Billing API calls
│   │   ├── pools.ts               # Pool API calls
│   │   └── audit.ts               # Audit API calls
│   │
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Header.tsx
│   │   │   └── Layout.tsx
│   │   ├── ui/                    # Shadcn components
│   │   │   ├── button.tsx
│   │   │   ├── table.tsx
│   │   │   ├── dialog.tsx
│   │   │   └── ...
│   │   ├── dashboard/
│   │   │   ├── StatCard.tsx
│   │   │   ├── AlertsList.tsx
│   │   │   └── HealthChart.tsx
│   │   ├── customers/
│   │   │   ├── CustomerTable.tsx
│   │   │   ├── Customer360.tsx
│   │   │   └── CustomerSearch.tsx
│   │   ├── instances/
│   │   │   ├── InstanceTable.tsx
│   │   │   ├── FailedQueue.tsx
│   │   │   ├── InstanceLogs.tsx
│   │   │   └── InstanceActions.tsx
│   │   ├── billing/
│   │   │   ├── BillingOverview.tsx
│   │   │   ├── TrialsList.tsx
│   │   │   └── CreditModal.tsx
│   │   └── pools/
│   │       ├── PoolGrid.tsx
│   │       ├── PoolSettings.tsx
│   │       └── ProvisionModal.tsx
│   │
│   ├── pages/
│   │   ├── Login.tsx
│   │   ├── Dashboard.tsx
│   │   ├── Customers.tsx
│   │   ├── CustomerDetail.tsx
│   │   ├── Instances.tsx
│   │   ├── FailedInstances.tsx
│   │   ├── Billing.tsx
│   │   ├── Pools.tsx
│   │   └── AuditLog.tsx
│   │
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── useCustomers.ts
│   │   └── ...
│   │
│   ├── stores/
│   │   └── authStore.ts           # Zustand for auth state
│   │
│   └── lib/
│       └── utils.ts               # Shadcn utils
│
├── package.json
├── tailwind.config.js
├── tsconfig.json
├── vite.config.ts
└── Dockerfile
```

---

## 7. Implementation Phases

### Phase 1: Foundation (MVP Core)

**Backend:**
- Admin service scaffolding (FastAPI + DB setup)
- Admin authentication (login, JWT, sessions)
- Service clients (HTTP calls to existing services)
- Audit logging infrastructure
- Basic RBAC (operator, admin, super_admin)

**Frontend:**
- Project setup (Vite + React + Shadcn + Tailwind)
- Auth flow (login page, protected routes)
- Layout (sidebar, header, navigation)
- Basic dashboard with stats

**Deliverables:**
- Admin can log in
- Basic dashboard shows platform stats
- Audit log captures login events

---

### Phase 2: Customer & Instance Management

**Backend:**
- Customer aggregation endpoints
- Customer 360 view assembly
- Instance list/detail endpoints
- Instance actions (retry, start, stop, restart, backup)
- Instance logs retrieval

**Frontend:**
- Customer list + search
- Customer 360 detail page
- Instance list + filters
- Failed instances queue
- Action modals (retry, start/stop)
- Instance logs viewer

**Deliverables:**
- Full customer visibility
- Instance troubleshooting workflow complete
- Retry failed instances from UI

---

### Phase 3: Billing & Pools

**Backend:**
- Billing aggregation endpoints
- Trial extension endpoint
- Credit/adjustment endpoint
- Subscription cancel/refund
- Pool management endpoints
- Pool settings update

**Frontend:**
- Billing overview dashboard
- Trial management (list, extend)
- Credit/adjustment modals
- Subscription actions
- Pool status grid
- Pool settings modal
- Provision new pool modal

**Deliverables:**
- Full billing management
- Trial extensions from UI
- Pool capacity management

---

### Phase 4: Polish & Audit

**Backend:**
- Full audit log querying
- Export functionality (CSV)
- Performance optimization (caching)

**Frontend:**
- Audit log page with filters
- Audit detail modal
- Global search improvements
- Error handling polish
- Loading states & optimistic updates

**Deliverables:**
- Complete audit trail
- Production-ready polish

---

## 8. Technical Requirements

### 8.1 Backend Dependencies

```
fastapi>=0.128.0
hypercorn>=0.14.0
asyncpg>=0.27.0
sqlalchemy>=2.0.0
alembic>=1.9.0
pydantic>=2.0.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4
httpx>=0.24.0
redis>=4.5.0
```

### 8.2 Frontend Dependencies

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.8.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.6.0",
    "zustand": "^4.4.0",
    "date-fns": "^2.30.0",
    "tailwindcss": "^3.4.0",
    "@radix-ui/react-*": "latest",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.0.0",
    "lucide-react": "^0.300.0"
  }
}
```

### 8.3 Infrastructure

- **Port allocations:**
  - Admin Service: 8010
  - Admin Frontend: 3001
- **Database:** New `admin` database in existing PostgreSQL cluster
- **Redis:** Shared with existing services for session storage
- **Traefik:** New route rule for `admin.yourdomain.com`

---

## 9. Security Considerations

### 9.1 Authentication
- Separate admin user store (not mixed with customers)
- JWT tokens with short expiry (15 min access, 7 day refresh)
- Session stored in Redis with IP/user-agent tracking
- Logout invalidates all sessions

### 9.2 Authorization
- Role-based access control (operator, admin, super_admin)
- Action-level permission checks
- All actions require authentication

### 9.3 Audit Trail
- Every admin action logged with full context
- Immutable audit log (append-only)
- Reason field required for sensitive actions

### 9.4 Network
- Admin service only accessible via internal network + VPN/Traefik
- No direct database access from frontend
- Rate limiting on auth endpoints

---

## 10. Success Metrics

| Metric | Target |
|--------|--------|
| Time to resolve failed instance | < 2 minutes (from alert to retry) |
| Time to find customer info | < 30 seconds (search to 360 view) |
| Admin actions per day | Track adoption |
| Audit log coverage | 100% of admin actions |

---

## 11. Out of Scope (Future)

- Customer impersonation (view as customer)
- Force password reset for customers
- Automated alerting (Slack/email integration)
- Advanced analytics and reporting
- Multi-admin approval workflows
- API key management for customers

---

## 12. Appendix

### A. Audit Action Types

```
auth.login
auth.logout
instance.retry
instance.start
instance.stop
instance.restart
instance.backup
billing.trial_extended
billing.credit_applied
billing.subscription_cancelled
billing.refund_processed
pool.provisioned
pool.settings_updated
pool.health_check_triggered
admin.user_created
admin.user_updated
admin.user_deactivated
```

### B. Environment Variables

```bash
# Admin Service
ADMIN_DATABASE_URL=postgresql+asyncpg://admin:pass@localhost/admin
ADMIN_REDIS_URL=redis://localhost:6379/2
ADMIN_JWT_SECRET=your-secret-key
ADMIN_JWT_ALGORITHM=HS256
ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES=15
ADMIN_REFRESH_TOKEN_EXPIRE_DAYS=7

# Service URLs (internal)
USER_SERVICE_URL=http://user-service:8001
INSTANCE_SERVICE_URL=http://instance-service:8003
BILLING_SERVICE_URL=http://billing-service:8004
DATABASE_SERVICE_URL=http://database-service:8005
```

---

**Document Prepared By:** Claude (AI Assistant)
**Reviewed By:** _Pending_
**Approved By:** _Pending_
