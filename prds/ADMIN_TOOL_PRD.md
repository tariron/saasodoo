# Product Requirements Document: SAASODOO Admin Tool

**Document Version:** 1.0
**Date:** 2026-01-16
**Project:** SAASODOO Platform Administration Dashboard
**Status:** Draft

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Problem Statement](#problem-statement)
3. [Goals & Objectives](#goals--objectives)
4. [User Personas](#user-personas)
5. [Functional Requirements](#functional-requirements)
6. [Non-Functional Requirements](#non-functional-requirements)
7. [UI/UX Guidelines](#uiux-guidelines)
8. [Technical Architecture](#technical-architecture)
9. [Data Model](#data-model)
10. [API Specifications](#api-specifications)
11. [Security Considerations](#security-considerations)
12. [Success Metrics](#success-metrics)
13. [Timeline & Milestones](#timeline--milestones)
14. [Risks & Mitigations](#risks--mitigations)

---

## 1. Executive Summary

The SAASODOO Admin Tool is a comprehensive web-based administration dashboard designed to provide platform operators with centralized visibility and control over the multi-tenant Odoo SaaS infrastructure. The tool consolidates existing scattered admin endpoints into a unified interface, enabling efficient management of customers, instances, billing, database pools, and system health.

**Key Value Propositions:**
- **Unified Control Center**: Single interface for all administrative operations
- **Proactive Monitoring**: Real-time visibility into system health and performance
- **Operational Efficiency**: Reduce manual intervention and troubleshooting time by 70%
- **Data-Driven Decisions**: Comprehensive analytics and reporting for capacity planning
- **Audit & Compliance**: Complete activity logging for security and compliance requirements

**Target Users:** Platform administrators, DevOps engineers, support staff, finance team

**Technology Stack:** React + TypeScript frontend, FastAPI backend, PostgreSQL + Redis storage

---

## 2. Problem Statement

### Current Pain Points

**1. Fragmented Admin Experience**
- Admin endpoints scattered across 4 microservices (user, instance, billing, database)
- No unified interface; requires direct API calls or database queries
- Inconsistent authentication and authorization patterns

**2. Limited Operational Visibility**
- No centralized dashboard for system health monitoring
- Instance failures require manual log diving
- Database pool capacity issues discovered reactively
- Billing anomalies detected after customer complaints

**3. Manual Intervention Overhead**
- Failed instance provisioning requires manual retry via API
- No bulk operations support (e.g., suspending multiple overdue accounts)
- Customer support issues require context switching across multiple services
- Trial eligibility checks require manual database queries

**4. Lack of Audit Trail**
- No systematic logging of admin actions
- Difficult to track who made configuration changes
- Compliance gaps for financial operations (PCI DSS, SOC 2)

**5. Scaling Challenges**
- Current approach won't scale beyond 1,000 instances
- No capacity planning tools or predictive analytics
- Resource allocation decisions made without data insights

### Impact on Business

- **Support Costs**: 40+ hours/month spent on manual admin tasks
- **Downtime**: Average 2-hour resolution time for instance failures
- **Customer Churn**: 15% of trial users lost due to provisioning delays
- **Revenue Leakage**: $5K/month from billing system gaps
- **Compliance Risk**: Audit trail deficiencies threaten enterprise contracts

---

## 3. Goals & Objectives

### Primary Goals

**G1: Operational Excellence**
- Reduce mean time to resolution (MTTR) for instance failures from 2 hours to 15 minutes
- Achieve 99.9% instance provisioning success rate
- Enable single-admin operation for up to 5,000 instances

**G2: Proactive Management**
- Detect and alert on capacity issues 7 days before critical threshold
- Identify billing anomalies within 1 hour of occurrence
- Predict resource needs based on growth trends

**G3: Unified Experience**
- Consolidate 100% of admin operations into single interface
- Reduce context switching between tools by 90%
- Enable new admin onboarding in < 1 day (vs current 5 days)

**G4: Audit & Compliance**
- Achieve 100% coverage of admin action logging
- Meet SOC 2 Type II audit requirements
- Enable compliance reporting within 30 minutes

### Success Criteria

| Metric | Current | Target | Timeline |
|--------|---------|--------|----------|
| Admin task completion time | 15 min avg | 3 min avg | Q2 2026 |
| Instance failure detection | 30 min | 2 min | Q1 2026 |
| Manual interventions/month | 80 | 10 | Q2 2026 |
| Dashboard load time | N/A | < 2 sec | Q1 2026 |
| Audit trail completeness | 20% | 100% | Q1 2026 |

---

## 4. User Personas

### Persona 1: Platform Administrator (Primary)

**Name:** Sarah Chen
**Role:** Senior Platform Administrator
**Experience:** 8 years in SaaS operations, 2 years with SAASODOO

**Responsibilities:**
- Monitor overall platform health
- Manage instance lifecycle (provision, pause, terminate)
- Handle customer escalations
- Capacity planning and resource allocation
- System configuration and maintenance

**Pain Points:**
- Spends 60% of time firefighting vs strategic work
- Context switching between 5+ tools daily
- No single source of truth for system state
- Manual data aggregation for weekly reports

**Needs:**
- Real-time dashboard with key metrics
- Quick access to instance details and logs
- One-click resolution for common issues
- Automated alerts for critical problems

**Success Metrics:**
- < 5 min to identify and triage any issue
- < 30 min to generate executive report
- Zero missed SLA breaches

---

### Persona 2: DevOps Engineer (Secondary)

**Name:** Marcus Johnson
**Role:** DevOps Lead
**Experience:** 10 years infrastructure, Kubernetes expert

**Responsibilities:**
- Infrastructure automation and scaling
- Database pool management
- Performance optimization
- Disaster recovery and backup verification
- Kubernetes cluster operations

**Pain Points:**
- Database pool health requires manual queries
- No visibility into Celery task queue depth
- Performance bottlenecks discovered after customer impact
- Backup success rates not monitored systematically

**Needs:**
- Infrastructure metrics and trends
- Database pool capacity planning tools
- Task queue monitoring and control
- Performance profiling capabilities

**Success Metrics:**
- Zero capacity-related outages
- 99.9% backup success rate
- < 10 min to identify performance bottleneck

---

### Persona 3: Finance Operations (Tertiary)

**Name:** Priya Patel
**Role:** Finance Operations Manager
**Experience:** 5 years SaaS billing, 1 year with SAASODOO

**Responsibilities:**
- Subscription and billing oversight
- Revenue recognition and reporting
- Dunning management (overdue payments)
- KillBill integration monitoring
- Trial-to-paid conversion tracking

**Pain Points:**
- Billing webhook failures not visible
- Manual reconciliation between KillBill and internal DB
- Trial abuse detection requires custom queries
- No visibility into payment gateway health

**Needs:**
- Billing dashboard with revenue metrics
- Trial eligibility audit trail
- Payment gateway status monitoring
- Automated dunning workflows

**Success Metrics:**
- < 1% billing discrepancies
- 100% webhook success rate
- 30% trial-to-paid conversion rate

---

### Persona 4: Customer Support (Tertiary)

**Name:** James Williams
**Role:** Senior Support Engineer
**Experience:** 4 years technical support

**Responsibilities:**
- L2/L3 customer issue resolution
- Instance troubleshooting
- Escalation to engineering
- Customer account management

**Pain Points:**
- No visibility into customer's instance status
- Cannot verify billing status during support calls
- Manual instance restart requires API knowledge
- No access to instance logs without SSH

**Needs:**
- Read-only customer/instance view
- Instance health check and restart tools
- Billing status verification
- Activity timeline for troubleshooting

**Success Metrics:**
- < 10 min average ticket resolution time
- 80% first-contact resolution rate
- Zero escalations due to lack of access

---

## 5. Functional Requirements

### 5.1 Authentication & Authorization

**REQ-AUTH-001: Single Sign-On (SSO)**
- **Priority:** P0 (Must-Have)
- **Description:** Admin tool must integrate with existing JWT authentication system
- **Acceptance Criteria:**
  - Reuse customer authentication flow with role-based access
  - Support existing HTTPBearer token scheme
  - Session management via Redis (consistent with user-service)
  - Auto-logout after 4 hours of inactivity

**REQ-AUTH-002: Role-Based Access Control (RBAC)**
- **Priority:** P0 (Must-Have)
- **Description:** Define and enforce granular permission model
- **Roles:**
  - **Super Admin**: Full access to all features
  - **Platform Admin**: Instance/pool management, read-only billing
  - **DevOps**: Infrastructure metrics, pool management, no billing access
  - **Finance**: Billing/subscription management, read-only instances
  - **Support**: Read-only access to customer/instance data, limited actions (restart)
- **Acceptance Criteria:**
  - Role assignment stored in database (new `admin_roles` table)
  - Frontend hides UI elements based on permissions
  - Backend validates permissions on every API call
  - Audit log records role at time of action

**REQ-AUTH-003: Admin User Management**
- **Priority:** P1 (Should-Have)
- **Description:** Self-service admin user provisioning and role management
- **Acceptance Criteria:**
  - Super Admin can invite new admin users via email
  - Admin users set password via invite link (24-hour expiration)
  - Super Admin can modify roles and revoke access
  - Support 2FA via TOTP (Google Authenticator) for Super Admins

---

### 5.2 Dashboard & Overview

**REQ-DASH-001: System Health Dashboard**
- **Priority:** P0 (Must-Have)
- **Description:** Real-time overview of platform health and key metrics
- **Components:**
  - **Instance Health Card**:
    - Total instances by status (running, stopped, error, creating)
    - Success rate (last 24 hours)
    - Failed instances alert (if any in ERROR status)
  - **Database Pool Card**:
    - Pool utilization percentage
    - Available capacity
    - Health status indicator (green/yellow/red)
  - **Billing Card**:
    - MRR (Monthly Recurring Revenue)
    - Trial-to-paid conversion rate
    - Overdue accounts count
  - **Task Queue Card**:
    - Active Celery tasks by queue
    - Failed task count (last 24 hours)
    - Average task duration
  - **System Resources**:
    - Kubernetes cluster CPU/memory usage
    - CephFS storage utilization
    - Redis/RabbitMQ health status
- **Acceptance Criteria:**
  - Auto-refresh every 30 seconds
  - Click-through to detailed views
  - Export snapshot as PDF/PNG for reporting

**REQ-DASH-002: Alerting & Notifications**
- **Priority:** P0 (Must-Have)
- **Description:** Proactive alerts for critical system events
- **Alert Types:**
  - **Critical**: Instance provisioning failure, database pool at 95% capacity, billing webhook failure
  - **Warning**: Pool at 80% capacity, task queue depth > 100, failed tasks > 10/hour
  - **Info**: Successful backups, scheduled maintenance completion
- **Channels:**
  - In-app notification center (bell icon)
  - Email (configurable per admin)
  - Webhook integration (Slack, PagerDuty, etc.)
- **Acceptance Criteria:**
  - Notifications persist until acknowledged
  - Configurable alert thresholds
  - Alert history log with timestamps

---

### 5.3 Customer Management

**REQ-CUST-001: Customer List View**
- **Priority:** P0 (Must-Have)
- **Description:** Searchable, filterable list of all customers
- **Features:**
  - Search by email, name, customer ID
  - Filter by: verification status, active/inactive, account age, total spend
  - Sort by: registration date, last login, instance count, MRR
  - Pagination (50 customers per page)
  - Bulk actions: export to CSV, send notification
- **Display Fields:**
  - Customer ID, email, name, status (active/inactive), verified (yes/no)
  - Registration date, last login
  - Instance count, billing status
  - Quick actions: view details, impersonate, suspend

**REQ-CUST-002: Customer Detail View**
- **Priority:** P0 (Must-Have)
- **Description:** Comprehensive single-customer view
- **Tabs:**
  - **Overview**:
    - Customer info (name, email, phone, verified status)
    - Account age, last login, IP address
    - Admin notes field (internal use only)
  - **Instances**:
    - List of all customer instances with status
    - Quick actions: restart, pause, terminate
    - Link to instance detail view
  - **Billing**:
    - Active subscriptions with plan details
    - Payment history (invoices, transactions)
    - Trial eligibility status
    - Overdue balance (if any)
  - **Activity Log**:
    - Login history
    - Instance actions (create, start, stop)
    - Billing events (subscription created, payment received)
    - Support tickets (if integrated)
- **Acceptance Criteria:**
  - Load time < 3 seconds
  - Real-time data (no caching)
  - Export customer data as JSON

**REQ-CUST-003: Customer Actions**
- **Priority:** P1 (Should-Have)
- **Description:** Administrative actions on customer accounts
- **Actions:**
  - **Suspend Account**: Block login, pause all instances, preserve data
  - **Activate Account**: Reverse suspension
  - **Verify Email**: Manually mark email as verified (for support escalations)
  - **Reset Password**: Send password reset email
  - **Impersonate**: View platform as customer (audit logged)
  - **Delete Account**: Permanent deletion (GDPR compliance), requires confirmation + reason
- **Acceptance Criteria:**
  - Require confirmation for destructive actions
  - Audit log records admin, timestamp, reason
  - Prevent self-suspension (Super Admin exception)

---

### 5.4 Instance Management

**REQ-INST-001: Instance List View**
- **Priority:** P0 (Must-Have)
- **Description:** Comprehensive instance inventory with filtering
- **Features:**
  - Search by: instance ID, name, customer email, database name
  - Filter by: status, billing status, Odoo version, instance type, date range
  - Sort by: creation date, CPU usage, memory usage, storage usage, last activity
  - Pagination (100 instances per page)
  - Bulk actions: pause, resume, restart, export
- **Display Fields:**
  - Instance ID, name, customer email
  - Status badge (color-coded)
  - Odoo version, instance type (dev/staging/prod)
  - Resource usage (CPU %, memory %, storage %)
  - Health status indicator
  - Quick actions: view details, restart, pause, terminate

**REQ-INST-002: Instance Detail View**
- **Priority:** P0 (Must-Have)
- **Description:** Deep dive into single instance
- **Sections:**
  - **Configuration**:
    - Instance ID, name, customer, creation date
    - Odoo version, instance type
    - Resource limits (CPU, memory, storage)
    - Custom addons list
    - Environment variables (masked secrets)
    - Database name, admin email
  - **Status & Health**:
    - Current status with state transition history
    - Provisioning status (if in progress)
    - Health check results (last run, next run)
    - Uptime percentage (last 30 days)
    - Error messages (if any)
  - **Resource Metrics** (charts):
    - CPU usage (last 24 hours)
    - Memory usage (last 24 hours)
    - Storage usage trend
    - Request rate and latency
  - **Billing**:
    - Subscription ID, plan name
    - Billing status, trial remaining (if applicable)
    - Next billing date, last payment
  - **Jobs & Tasks**:
    - Recent Celery tasks (provision, backup, maintenance)
    - Job status, start time, duration
    - Error logs (if failed)
  - **Logs** (last 1000 lines):
    - Instance application logs
    - Kubernetes pod events
    - Filter by log level (info, warning, error)
- **Acceptance Criteria:**
  - Real-time metrics (30-second refresh)
  - Exportable configuration as YAML
  - Direct link to Kubernetes pod (if K8s dashboard available)

**REQ-INST-003: Instance Lifecycle Actions**
- **Priority:** P0 (Must-Have)
- **Description:** Administrative control over instance lifecycle
- **Actions:**
  - **Start**: Start stopped instance
  - **Stop**: Gracefully stop running instance
  - **Restart**: Stop and start (useful for config changes)
  - **Pause**: Suspend instance without termination (preserve data)
  - **Resume**: Unpause instance
  - **Terminate**: Permanent deletion (requires confirmation)
  - **Retry Provisioning**: Retry failed instance creation
  - **Scale Resources**: Modify CPU/memory/storage limits (requires restart)
  - **Change Plan**: Upgrade/downgrade subscription plan
- **Acceptance Criteria:**
  - Confirmation dialog for destructive actions
  - Show estimated downtime (if any)
  - Progress indicator for async operations
  - Success/failure notification
  - Audit log entry with reason field (mandatory for terminate)

**REQ-INST-004: Bulk Instance Operations**
- **Priority:** P1 (Should-Have)
- **Description:** Perform actions on multiple instances simultaneously
- **Use Cases:**
  - Pause all instances for customers with overdue payments
  - Restart all instances running specific Odoo version (for upgrades)
  - Terminate all trial instances older than 30 days (cleanup)
- **Acceptance Criteria:**
  - Select instances via checkboxes or filters
  - Preview affected instances before execution
  - Progress bar showing completion percentage
  - Summary report (succeeded, failed, skipped)

---

### 5.5 Database Pool Management

**REQ-POOL-001: Pool List View**
- **Priority:** P0 (Must-Have)
- **Description:** Overview of all database pools
- **Features:**
  - Filter by: server type (CNPG, standalone), health status, utilization percentage
  - Sort by: capacity, utilization, health score
- **Display Fields:**
  - Pool ID, name, server type
  - Capacity (max databases), current utilization (%)
  - Health status badge (healthy, degraded, critical)
  - PostgreSQL version
  - Quick actions: view details, health check, provision

**REQ-POOL-002: Pool Detail View**
- **Priority:** P0 (Must-Have)
- **Description:** Detailed pool metrics and configuration
- **Sections:**
  - **Configuration**:
    - Pool ID, name, server type
    - Capacity, PostgreSQL version
    - Connection limits, resource allocation
  - **Utilization Metrics**:
    - Current database count
    - Storage used / available
    - Connection pool stats
    - Query performance metrics (avg query time)
  - **Health Status**:
    - Last health check timestamp and result
    - Replication lag (if CNPG)
    - Disk I/O performance
    - Warning/error messages
  - **Databases**:
    - List of databases in pool
    - Per-database size and connection count
- **Acceptance Criteria:**
  - Charts showing utilization trends (7 days)
  - Manual health check trigger button
  - Alerting threshold configuration

**REQ-POOL-003: Pool Operations**
- **Priority:** P1 (Should-Have)
- **Description:** Administrative pool management actions
- **Actions:**
  - **Provision Pool**: Create new database pool (testing/scaling)
  - **Health Check**: Manual health verification
  - **Rebalance**: Move databases between pools (future)
  - **Decommission**: Mark pool for retirement (no new databases)
- **Acceptance Criteria:**
  - Provision form validates input (capacity, PostgreSQL version)
  - Health check shows detailed pass/fail reasons
  - Cannot delete pool with active databases

**REQ-POOL-004: Capacity Planning**
- **Priority:** P1 (Should-Have)
- **Description:** Predictive analytics for pool capacity
- **Features:**
  - Growth trend chart (database creation rate)
  - Projected days until pools reach 80% / 100% capacity
  - Recommendation engine: "Add 2 new pools in next 30 days"
- **Acceptance Criteria:**
  - Predictions based on 30-day rolling average
  - Email alert when capacity projected < 14 days

---

### 5.6 Billing & Subscription Management

**REQ-BILL-001: Billing Overview Dashboard**
- **Priority:** P0 (Must-Have)
- **Description:** Financial health snapshot
- **Metrics:**
  - MRR (Monthly Recurring Revenue)
  - ARR (Annual Recurring Revenue)
  - Active subscriptions count
  - Trial subscriptions count
  - Overdue accounts (count + total amount)
  - Churn rate (last 30 days)
  - Trial-to-paid conversion rate
- **Charts:**
  - Revenue trend (last 12 months)
  - Subscription growth (last 6 months)
  - Payment method distribution (pie chart)
- **Acceptance Criteria:**
  - Real-time data from KillBill
  - Export as CSV for accounting

**REQ-BILL-002: Subscription List View**
- **Priority:** P0 (Must-Have)
- **Description:** All subscriptions with filtering
- **Features:**
  - Search by: customer email, subscription ID, plan name
  - Filter by: status (active, trial, overdue, canceled), plan, payment method
  - Sort by: start date, MRR, next billing date
- **Display Fields:**
  - Subscription ID, customer email, plan name
  - Status badge, MRR
  - Start date, next billing date
  - Trial remaining (if applicable)
  - Quick actions: view details, cancel, change plan

**REQ-BILL-003: Subscription Detail View**
- **Priority:** P0 (Must-Have)
- **Description:** Detailed subscription information
- **Sections:**
  - **Subscription Info**:
    - Subscription ID, customer, plan name
    - Status, start date, next billing date
    - Billing cycle (monthly/annual)
    - Trial info (if applicable)
  - **Pricing**:
    - Base price, addons, discounts
    - Total MRR
  - **Payment History**:
    - Invoices (date, amount, status, PDF download)
    - Transactions (date, amount, gateway, status)
    - Failed payments with retry history
  - **Instance Mapping**:
    - Associated instance(s)
- **Acceptance Criteria:**
  - Direct link to customer and instance pages
  - Invoice PDF generation on demand

**REQ-BILL-004: Payment & Invoice Management**
- **Priority:** P1 (Should-Have)
- **Description:** Handle payment-related admin tasks
- **Actions:**
  - **Manual Payment Recording**: Mark invoice as paid (offline payment)
  - **Refund**: Process refund through KillBill
  - **Retry Failed Payment**: Trigger payment retry
  - **Send Invoice**: Resend invoice email
  - **Apply Credit**: Add account credit (compensation)
- **Acceptance Criteria:**
  - Confirmation required for refunds > $100
  - Audit log for all financial transactions
  - KillBill webhook sync verification

**REQ-BILL-005: Trial Management**
- **Priority:** P1 (Should-Have)
- **Description:** Monitor and control trial usage
- **Features:**
  - Trial eligibility audit (customer list with used/unused trial)
  - Trial abuse detection (multiple accounts from same IP/email pattern)
  - Manual trial grant (customer success exception)
  - Trial extension (support escalation)
- **Acceptance Criteria:**
  - Cannot grant trial if already used (unless Super Admin override)
  - Extension logged with reason
  - Alert on suspicious trial patterns (5+ from same IP)

**REQ-BILL-006: Dunning Management**
- **Priority:** P1 (Should-Have)
- **Description:** Automated overdue payment handling
- **Workflow:**
  - Day 0: Payment fails → retry in 3 days
  - Day 3: Retry fails → send reminder email
  - Day 7: Still overdue → pause instances
  - Day 14: Still overdue → suspend account
  - Day 30: Still overdue → terminate instances
- **Admin Controls:**
  - View all overdue accounts
  - Manual dunning stage override
  - Exception list (VIP customers)
- **Acceptance Criteria:**
  - Configurable dunning timeline
  - Email templates editable
  - Override requires reason

---

### 5.7 System Monitoring & Logs

**REQ-MON-001: Real-Time Monitoring Dashboard**
- **Priority:** P0 (Must-Have)
- **Description:** Live system metrics
- **Metrics:**
  - **Kubernetes Cluster**:
    - Node count, CPU %, memory %
    - Pod count (running, pending, failed)
  - **Services**:
    - Health status (user, instance, billing, database services)
    - Response time (avg, p95, p99)
    - Error rate (last hour)
  - **Task Queues**:
    - Active tasks by queue
    - Queue depth (pending tasks)
    - Failed tasks (last 24 hours)
  - **Databases**:
    - Connection count, query rate
    - Replication lag (CNPG)
    - Storage usage
  - **Cache & Queue Infrastructure**:
    - Redis memory usage, hit rate
    - RabbitMQ queue depth, message rate
- **Acceptance Criteria:**
  - Auto-refresh every 10 seconds
  - Drill-down to per-service metrics
  - Historical data (last 7 days)

**REQ-MON-002: Celery Task Queue Management**
- **Priority:** P0 (Must-Have)
- **Description:** Visibility and control over background tasks
- **Features:**
  - **Task List**:
    - Active tasks (in-progress)
    - Pending tasks (queued)
    - Failed tasks (last 7 days)
    - Filter by queue, task type, date range
  - **Task Detail**:
    - Task ID, type, arguments
    - Status, start time, duration
    - Error message and stack trace (if failed)
    - Worker ID that executed task
  - **Task Actions**:
    - Retry failed task
    - Cancel pending task
    - Purge queue (emergency use)
- **Acceptance Criteria:**
  - Real-time task status updates
  - Search by instance ID or customer ID
  - Alert if queue depth > 100 for 5+ minutes

**REQ-MON-003: System Logs & Search**
- **Priority:** P1 (Should-Have)
- **Description:** Centralized log aggregation and search
- **Features:**
  - Search across all services (user, instance, billing, database)
  - Filter by: log level, service, date range, customer ID, instance ID
  - Full-text search
  - Log streaming (tail -f style)
- **Acceptance Criteria:**
  - Search results in < 3 seconds
  - Export logs as JSON or text
  - Syntax highlighting for error logs

**REQ-MON-004: Audit Log**
- **Priority:** P0 (Must-Have)
- **Description:** Complete audit trail of all admin actions
- **Logged Events:**
  - User logins/logouts
  - Instance lifecycle actions (start, stop, terminate)
  - Customer account modifications (suspend, delete)
  - Billing actions (manual payment, refund, trial grant)
  - Configuration changes (pool provision, alert threshold)
- **Log Fields:**
  - Timestamp, admin user, action type
  - Resource ID (customer, instance, subscription)
  - Before/after values (for modifications)
  - IP address, user agent
  - Reason (if provided)
- **Acceptance Criteria:**
  - Immutable log (append-only)
  - Retention: 7 years (compliance requirement)
  - Export for compliance audits
  - Search and filter by any field

---

### 5.8 Configuration & Settings

**REQ-CONF-001: System Configuration**
- **Priority:** P1 (Should-Have)
- **Description:** Global platform settings (Super Admin only)
- **Settings:**
  - **Instance Defaults**:
    - Default CPU/memory/storage limits
    - Default Odoo version
    - Allowed Odoo versions
  - **Billing Defaults**:
    - Trial duration (days)
    - Dunning timeline
    - Allowed payment gateways
  - **Notification Settings**:
    - SMTP configuration (email notifications)
    - Webhook URLs (Slack, PagerDuty)
    - Alert thresholds (pool capacity, task failures)
  - **Security**:
    - Session timeout duration
    - Password policy (min length, complexity)
    - 2FA enforcement
- **Acceptance Criteria:**
  - Changes logged in audit trail
  - Validation prevents invalid values
  - Confirmation required for critical changes

**REQ-CONF-002: Alert Configuration**
- **Priority:** P1 (Should-Have)
- **Description:** Customize alerting rules
- **Features:**
  - Enable/disable alert types
  - Set thresholds (e.g., pool capacity warning at 75% vs 80%)
  - Configure notification channels per alert type
  - Define escalation rules (if not acknowledged in 30 min, escalate)
- **Acceptance Criteria:**
  - Per-admin notification preferences
  - Test alert button (send sample alert)

---

### 5.9 Reporting & Analytics

**REQ-REPORT-001: Pre-built Reports**
- **Priority:** P1 (Should-Have)
- **Description:** Common operational reports
- **Reports:**
  - **Executive Summary** (weekly):
    - MRR growth, active instances, support tickets
    - System uptime, incident count
  - **Capacity Report** (monthly):
    - Database pool utilization trends
    - Instance growth projection
    - Recommended infrastructure scaling
  - **Billing Report** (monthly):
    - Revenue by plan, churn rate, refunds
    - Trial conversion funnel
  - **Operational Report** (daily):
    - Failed tasks, instance errors
    - Peak usage times
- **Acceptance Criteria:**
  - Exportable as PDF or Excel
  - Schedule automatic email delivery
  - Customizable date ranges

**REQ-REPORT-002: Custom Queries**
- **Priority:** P2 (Nice-to-Have)
- **Description:** Ad-hoc SQL query interface (Super Admin only)
- **Features:**
  - SQL editor with syntax highlighting
  - Query history (last 50 queries)
  - Export results as CSV/JSON
  - Save frequently-used queries
- **Acceptance Criteria:**
  - Read-only access (no INSERT/UPDATE/DELETE)
  - Query timeout: 30 seconds
  - Audit log records all queries

---

### 5.10 Integrations

**REQ-INT-001: KillBill Integration**
- **Priority:** P0 (Must-Have)
- **Description:** Bidirectional sync with billing system
- **Features:**
  - Real-time webhook listener (already exists)
  - Webhook status dashboard (success/failure rate)
  - Manual webhook replay (for failed events)
  - KillBill health check (API connectivity)
- **Acceptance Criteria:**
  - Alert on webhook failures
  - Display discrepancies between KillBill and internal DB

**REQ-INT-002: Kubernetes Integration**
- **Priority:** P0 (Must-Have)
- **Description:** Direct cluster visibility and control
- **Features:**
  - Pod list view (filtered by namespace)
  - Pod logs viewer (last 1000 lines)
  - Pod restart action
  - Node resource utilization
- **Acceptance Criteria:**
  - Uses existing Kubernetes Python Client
  - Read-only by default (write requires Super Admin)

**REQ-INT-003: Prometheus/Grafana Integration**
- **Priority:** P1 (Should-Have)
- **Description:** Embed existing monitoring dashboards
- **Features:**
  - iFrame embed of Grafana dashboards
  - Direct links to relevant Prometheus queries
- **Acceptance Criteria:**
  - SSO pass-through (if Grafana supports)
  - Fallback to separate tab if embedding blocked

**REQ-INT-004: Slack Integration**
- **Priority:** P1 (Should-Have)
- **Description:** Real-time alerts to Slack channels
- **Features:**
  - Webhook configuration for Slack channels
  - Alert routing (critical → #incidents, warnings → #ops)
  - Interactive buttons (acknowledge, escalate)
- **Acceptance Criteria:**
  - Configurable per alert type
  - Rich formatting (color-coded severity)

---

## 6. Non-Functional Requirements

### 6.1 Performance

**REQ-PERF-001: Response Time**
- Dashboard loads in < 2 seconds (P95)
- API endpoints respond in < 500ms (P95)
- Search queries return in < 3 seconds
- Chart rendering in < 1 second

**REQ-PERF-002: Scalability**
- Support 10,000+ instances without performance degradation
- Handle 100+ concurrent admin users
- Dashboard auto-refresh every 30 seconds without impacting API performance

**REQ-PERF-003: Data Refresh**
- Critical metrics (instance status, alerts) refresh every 10-30 seconds
- Historical data (charts, trends) cached for 5 minutes
- Manual refresh button available on all pages

---

### 6.2 Reliability

**REQ-REL-001: Availability**
- 99.9% uptime target (excluding planned maintenance)
- Graceful degradation if backend services unavailable
- Offline indicator with automatic reconnection

**REQ-REL-002: Data Consistency**
- All API calls must be idempotent (safe to retry)
- Optimistic concurrency control (detect concurrent modifications)
- Transaction boundaries for multi-step operations

**REQ-REL-003: Error Handling**
- User-friendly error messages (no stack traces in UI)
- Automatic retry for transient failures (network timeouts)
- Fallback to cached data if real-time fetch fails

---

### 6.3 Security

**REQ-SEC-001: Authentication**
- JWT token-based authentication (reuse existing system)
- Token expiration: 4 hours
- Automatic token refresh (transparent to user)
- Secure logout (delete session from Redis)

**REQ-SEC-002: Authorization**
- RBAC enforced on frontend and backend
- API endpoints validate permissions before execution
- Prevent privilege escalation (users cannot grant themselves higher roles)

**REQ-SEC-003: Data Protection**
- HTTPS-only (enforce TLS 1.3)
- Sensitive data (passwords, API keys) never logged or displayed
- Encrypted storage for audit logs
- GDPR-compliant data deletion (customer account termination)

**REQ-SEC-004: Audit Trail**
- 100% coverage of admin actions
- Immutable logs (append-only)
- Tamper detection (cryptographic signatures)

**REQ-SEC-005: API Security**
- Rate limiting (100 requests/minute per user)
- CORS policy (admin frontend domain only)
- CSRF protection
- Input validation (prevent SQL injection, XSS)

---

### 6.4 Usability

**REQ-USE-001: Responsive Design**
- Desktop-first (1920x1080 primary target)
- Tablet support (1024x768 minimum)
- Mobile read-only view (emergency access)

**REQ-USE-002: Accessibility**
- WCAG 2.1 Level AA compliance
- Keyboard navigation support
- Screen reader compatible
- High-contrast mode

**REQ-USE-003: Internationalization**
- English as primary language
- Framework support for future translations (i18n-ready)

**REQ-USE-004: User Experience**
- Consistent design language (same as customer portal)
- Loading indicators for all async operations
- Toast notifications for success/error
- Confirmation dialogs for destructive actions

---

### 6.5 Maintainability

**REQ-MAINT-001: Code Quality**
- TypeScript for frontend (100% type coverage)
- Python type hints for backend (mypy validation)
- Unit test coverage > 80%
- Integration tests for critical workflows

**REQ-MAINT-002: Documentation**
- API documentation (OpenAPI/Swagger)
- Admin user guide (with screenshots)
- Developer setup guide
- Deployment runbook

**REQ-MAINT-003: Monitoring**
- Application metrics (request rate, error rate, latency)
- Business metrics (daily active admins, actions per admin)
- Automated alerts for application errors

---

## 7. UI/UX Guidelines

### 7.1 Design Principles

**Principle 1: Clarity Over Cleverness**
- Prioritize information density and clarity
- Avoid unnecessary animations or visual flourishes
- Use consistent terminology (e.g., "Instance" not "Environment" or "Deployment")

**Principle 2: Progressive Disclosure**
- Show summary views by default, detail on demand
- Use tabs, accordions, and modals to organize complex data
- Provide "Show More" options rather than overwhelming with data

**Principle 3: Action-Oriented**
- Primary actions (start, stop, retry) always visible
- Destructive actions (terminate, delete) require confirmation
- Provide undo where possible (e.g., undelete within 24 hours)

**Principle 4: Context-Aware Help**
- Inline tooltips for technical terms
- Help icons link to documentation
- Error messages include remediation steps

---

### 7.2 Visual Design

**Color Palette:**
- **Primary**: Blue (#2563EB) - actions, links
- **Success**: Green (#10B981) - healthy status, positive metrics
- **Warning**: Yellow (#F59E0B) - degraded status, approaching limits
- **Danger**: Red (#EF4444) - errors, critical alerts
- **Neutral**: Gray (#6B7280) - text, borders

**Typography:**
- **Headings**: Inter, 600 weight
- **Body**: Inter, 400 weight
- **Monospace**: JetBrains Mono (logs, IDs, code)

**Iconography:**
- Use Heroicons (consistent with existing frontend)
- 20px icons for list views, 24px for detail views
- Always pair icons with text labels

---

### 7.3 Component Library

**Reusable Components:**
- **StatusBadge**: Color-coded pill (running=green, error=red, stopped=gray)
- **MetricCard**: Stat with title, value, trend indicator (↑ ↓)
- **DataTable**: Sortable, filterable table with pagination
- **SearchBar**: Full-text search with autocomplete suggestions
- **ActionMenu**: Dropdown for secondary actions (⋮)
- **ConfirmDialog**: Modal for destructive actions with "Type DELETE to confirm"
- **ChartWidget**: Recharts-based line/bar/pie charts with responsive layout

---

### 7.4 Page Layouts

**Master Layout:**
```
┌─────────────────────────────────────────────────┐
│ Header (Logo | Search | Notifications | User)  │
├──────┬──────────────────────────────────────────┤
│ Side │                                          │
│ Nav  │         Main Content Area                │
│      │                                          │
│      │                                          │
└──────┴──────────────────────────────────────────┘
```

**Sidebar Navigation:**
- Dashboard (home icon)
- Customers
- Instances
- Database Pools
- Billing & Subscriptions
- Monitoring
- Reports
- Settings (gear icon)

**Dashboard Layout:**
```
┌──────────────────────────────────────────────────┐
│ System Health Overview                           │
├───────────────┬───────────────┬──────────────────┤
│ Instances     │ DB Pools      │ Billing          │
│ Card          │ Card          │ Card             │
├───────────────┴───────────────┴──────────────────┤
│ Task Queue                    │ System Resources │
│ Card                          │ Card             │
├───────────────────────────────┴──────────────────┤
│ Recent Alerts                                    │
└──────────────────────────────────────────────────┘
```

**List View Layout:**
```
┌──────────────────────────────────────────────────┐
│ Page Title                    [+ New] [Export]   │
├──────────────────────────────────────────────────┤
│ [Search...] [Filter ▾] [Sort ▾]                 │
├──────────────────────────────────────────────────┤
│ ╔════════════════════════════════════════════╗  │
│ ║ Data Table with Sortable Columns          ║  │
│ ║ ...                                        ║  │
│ ╚════════════════════════════════════════════╝  │
│                    [← 1 2 3 ... 10 →]           │
└──────────────────────────────────────────────────┘
```

**Detail View Layout:**
```
┌──────────────────────────────────────────────────┐
│ ← Back | Resource Name              [Actions ▾]  │
├──────────────────────────────────────────────────┤
│ [Overview] [Details] [Metrics] [Logs] [History] │
├──────────────────────────────────────────────────┤
│                                                  │
│              Tab Content Area                    │
│                                                  │
└──────────────────────────────────────────────────┘
```

---

### 7.5 User Flows

**Flow 1: Troubleshooting Failed Instance**
1. Admin sees alert "Instance Provisioning Failed" on dashboard
2. Clicks alert → navigates to instance detail page
3. Views error message in "Status & Health" section
4. Checks logs tab for detailed error
5. Identifies missing addon dependency
6. Clicks "Retry Provisioning" button
7. Sees progress indicator
8. Receives success notification
9. Instance status changes to "Running"

**Flow 2: Managing Overdue Payment**
1. Admin navigates to Billing dashboard
2. Sees "5 Overdue Accounts" in warning card
3. Clicks card → filtered list of overdue subscriptions
4. Selects customer → customer detail page
5. Views billing tab showing failed payment attempt
6. Clicks "Send Payment Reminder" button
7. Confirmation modal: "Email will be sent to customer@email.com"
8. Clicks confirm
9. Success notification: "Payment reminder sent"
10. Audit log records action

**Flow 3: Capacity Planning**
1. Admin navigates to Database Pools page
2. Sees pool at 85% capacity with yellow warning badge
3. Clicks pool → pool detail page
4. Views "Capacity Planning" section showing projection: "Pool will reach 100% in 12 days"
5. Clicks "Provision New Pool" button
6. Form appears: capacity (default 100), PostgreSQL version (default 16)
7. Submits form
8. Background task starts (progress tracked)
9. Receives notification when complete
10. New pool appears in list

---

## 8. Technical Architecture

### 8.1 System Architecture

**High-Level Diagram:**
```
┌─────────────────────────────────────────────────────────┐
│                    Admin Frontend                       │
│              (React + TypeScript + Tailwind)            │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS (JWT)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Admin Backend API                     │
│                   (FastAPI + Python)                    │
└───┬─────────┬─────────┬─────────┬─────────┬────────────┘
    │         │         │         │         │
    ▼         ▼         ▼         ▼         ▼
┌────────┐┌─────────┐┌─────────┐┌────────┐┌──────────┐
│ User   ││Instance ││Billing  ││Database││Celery    │
│Service ││Service  ││Service  ││Service ││Worker    │
└────────┘└─────────┘└─────────┘└────────┘└──────────┘
    │         │         │         │         │
    └─────────┴─────────┴─────────┴─────────┘
                         │
                         ▼
        ┌─────────────────────────────────┐
        │  PostgreSQL + Redis + RabbitMQ  │
        │  Kubernetes API + KillBill      │
        └─────────────────────────────────┘
```

---

### 8.2 Technology Stack

**Frontend:**
- **Framework**: React 18 with TypeScript
- **UI Library**: Tailwind CSS + Headless UI
- **Charts**: Recharts or Chart.js
- **State Management**: React Query (server state) + Zustand (UI state)
- **Routing**: React Router v6
- **HTTP Client**: Axios with interceptors (auth, error handling)
- **Build Tool**: Vite

**Backend:**
- **Framework**: FastAPI 0.109+
- **ORM**: SQLAlchemy 2.0+ (async)
- **Validation**: Pydantic v2
- **Authentication**: Reuse existing JWT implementation
- **Testing**: pytest + pytest-asyncio
- **ASGI Server**: Uvicorn

**Databases & Infrastructure:**
- **PostgreSQL**: New `admin_tool` database (separate from services)
- **Redis**: Session storage, caching (reuse existing instance)
- **Celery**: Background tasks (alert processing, report generation)
- **Docker**: Containerized deployment
- **Kubernetes**: Same cluster as existing services

---

### 8.3 Data Architecture

**New Database: `admin_tool`**

```sql
-- Admin users (extends existing customers table with admin flag)
CREATE TABLE admin_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) NOT NULL,
    role VARCHAR(50) NOT NULL, -- super_admin, platform_admin, devops, finance, support
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID REFERENCES admin_users(id),
    UNIQUE(customer_id)
);

-- Audit log
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT NOW(),
    admin_user_id UUID REFERENCES admin_users(id) NOT NULL,
    action_type VARCHAR(100) NOT NULL, -- instance_restart, customer_suspend, etc.
    resource_type VARCHAR(50), -- customer, instance, subscription, etc.
    resource_id VARCHAR(255),
    before_state JSONB,
    after_state JSONB,
    reason TEXT,
    ip_address INET,
    user_agent TEXT,
    result VARCHAR(20), -- success, failure
    error_message TEXT
);

-- Alert definitions
CREATE TABLE alert_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- critical, warning, info
    condition JSONB NOT NULL, -- {"metric": "pool_capacity", "operator": ">", "threshold": 80}
    enabled BOOLEAN DEFAULT true,
    notification_channels JSONB, -- ["email", "slack"]
    created_at TIMESTAMP DEFAULT NOW()
);

-- Alert history
CREATE TABLE alert_history (
    id BIGSERIAL PRIMARY KEY,
    alert_definition_id UUID REFERENCES alert_definitions(id),
    triggered_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    acknowledged_at TIMESTAMP,
    acknowledged_by UUID REFERENCES admin_users(id),
    message TEXT,
    metadata JSONB
);

-- System configuration
CREATE TABLE system_config (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW(),
    updated_by UUID REFERENCES admin_users(id)
);

-- Saved reports/queries
CREATE TABLE saved_queries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admin_user_id UUID REFERENCES admin_users(id) NOT NULL,
    name VARCHAR(255) NOT NULL,
    sql_query TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_log_admin_user ON audit_log(admin_user_id);
CREATE INDEX idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_alert_history_triggered ON alert_history(triggered_at DESC);
CREATE INDEX idx_alert_history_resolved ON alert_history(resolved_at) WHERE resolved_at IS NULL;
```

---

### 8.4 API Structure

**Base URL:** `https://admin.saasodoo.com/api/v1`

**Authentication:** All endpoints require `Authorization: Bearer <JWT_TOKEN>` header

**Endpoint Groups:**

**1. Authentication**
- `POST /auth/login` - Admin login (returns JWT)
- `POST /auth/logout` - Invalidate session
- `GET /auth/me` - Current admin user info + role

**2. Dashboard**
- `GET /dashboard/overview` - System health summary
- `GET /dashboard/metrics` - Real-time metrics (instances, pools, billing)

**3. Customers**
- `GET /customers` - List customers (paginated, filterable)
- `GET /customers/{id}` - Customer details
- `PUT /customers/{id}/suspend` - Suspend account
- `PUT /customers/{id}/activate` - Activate account
- `DELETE /customers/{id}` - Delete account (GDPR)

**4. Instances**
- `GET /instances` - List instances (paginated, filterable)
- `GET /instances/{id}` - Instance details
- `POST /instances/{id}/start` - Start instance
- `POST /instances/{id}/stop` - Stop instance
- `POST /instances/{id}/restart` - Restart instance
- `POST /instances/{id}/terminate` - Terminate instance
- `POST /instances/{id}/retry` - Retry failed provisioning
- `GET /instances/{id}/logs` - Stream logs
- `GET /instances/{id}/metrics` - Resource usage metrics

**5. Database Pools**
- `GET /pools` - List pools
- `GET /pools/{id}` - Pool details
- `POST /pools/{id}/health-check` - Run health check
- `POST /pools` - Provision new pool

**6. Billing**
- `GET /billing/overview` - Financial metrics
- `GET /subscriptions` - List subscriptions
- `GET /subscriptions/{id}` - Subscription details
- `PUT /subscriptions/{id}/cancel` - Cancel subscription
- `GET /invoices` - List invoices
- `POST /invoices/{id}/retry-payment` - Retry payment

**7. Monitoring**
- `GET /monitoring/celery/tasks` - List Celery tasks
- `POST /monitoring/celery/tasks/{id}/retry` - Retry failed task
- `GET /monitoring/kubernetes/pods` - List pods
- `GET /monitoring/logs` - Search logs

**8. Alerts**
- `GET /alerts` - List active alerts
- `POST /alerts/{id}/acknowledge` - Acknowledge alert
- `GET /alerts/history` - Alert history

**9. Audit**
- `GET /audit/logs` - Search audit logs (filterable)

**10. Admin Management**
- `GET /admin-users` - List admin users
- `POST /admin-users` - Invite new admin
- `PUT /admin-users/{id}/role` - Change role
- `DELETE /admin-users/{id}` - Revoke access

---

### 8.5 Integration Points

**1. User Service**
- Endpoint: `http://user-service:8001/api/v1`
- Used for: Customer authentication, profile data

**2. Instance Service**
- Endpoint: `http://instance-service:8003/api/v1`
- Used for: Instance lifecycle, status, logs

**3. Billing Service**
- Endpoint: `http://billing-service:8004/api/v1`
- Used for: Subscription data, payment history

**4. Database Service**
- Endpoint: `http://database-service:8005/api/v1`
- Used for: Pool management, health checks

**5. KillBill**
- Endpoint: `http://killbill:8080`
- Used for: Billing operations, invoice generation

**6. Kubernetes API**
- Client: Python Kubernetes client (in-cluster config)
- Used for: Pod management, cluster metrics

**7. Redis**
- Used for: Session storage, caching, alert state

---

## 9. Data Model

### 9.1 Existing Entities (Read Access)

Admin tool queries but does not modify these:

**From User Service (`auth` DB):**
- `customers`: Customer accounts
- `customer_sessions`: Active sessions

**From Instance Service (`instance` DB):**
- `instances`: Odoo instances
- `instance_jobs`: Provisioning job history

**From Billing Service (`billing` DB):**
- `subscriptions`: Customer subscriptions
- `invoices`: Billing invoices
- `payments`: Transaction records

**From Database Service (`instance` DB):**
- `database_pools`: Pool metadata
- `pool_databases`: Database assignments

---

### 9.2 New Entities (Admin Tool DB)

See [8.3 Data Architecture](#83-data-architecture) for complete schema.

**Key Entities:**
- `admin_users`: Admin accounts with roles
- `audit_log`: Immutable action log
- `alert_definitions`: Configurable alerts
- `alert_history`: Alert events
- `system_config`: Global settings
- `saved_queries`: Custom SQL queries

---

## 10. API Specifications

### 10.1 Authentication Flow

**Login:**
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "admin@saasodoo.com",
  "password": "SecurePassword123!"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 14400,
  "admin_user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "admin@saasodoo.com",
    "role": "super_admin"
  }
}
```

---

### 10.2 Example Endpoints

**Get Dashboard Overview:**
```http
GET /api/v1/dashboard/overview
Authorization: Bearer <token>
```

**Response:**
```json
{
  "instances": {
    "total": 1247,
    "by_status": {
      "running": 1150,
      "stopped": 45,
      "error": 12,
      "creating": 40
    },
    "success_rate_24h": 98.5
  },
  "database_pools": {
    "total": 12,
    "utilization_avg": 67.3,
    "critical_pools": 1
  },
  "billing": {
    "mrr": 125000,
    "active_subscriptions": 980,
    "overdue_accounts": 23,
    "trial_to_paid_rate": 28.5
  },
  "celery_tasks": {
    "active": 15,
    "pending": 23,
    "failed_24h": 8
  },
  "system_resources": {
    "kubernetes_cpu_percent": 45.2,
    "kubernetes_memory_percent": 62.8,
    "cephfs_usage_percent": 38.5
  }
}
```

---

**List Instances (with filters):**
```http
GET /api/v1/instances?status=error&page=1&per_page=50&sort=created_at&order=desc
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": "inst_abc123",
      "name": "Production Instance",
      "customer": {
        "id": "cust_xyz789",
        "email": "customer@example.com"
      },
      "status": "error",
      "odoo_version": "17",
      "type": "production",
      "resource_usage": {
        "cpu_percent": 0,
        "memory_percent": 0,
        "storage_mb": 2048
      },
      "health_status": "unhealthy",
      "created_at": "2026-01-10T15:30:00Z",
      "error_message": "Database connection failed"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 12,
    "pages": 1
  }
}
```

---

**Retry Failed Instance:**
```http
POST /api/v1/instances/inst_abc123/retry
Authorization: Bearer <token>
Content-Type: application/json

{
  "reason": "Fixed database connectivity issue"
}
```

**Response:**
```json
{
  "message": "Provisioning retry queued",
  "task_id": "task_def456",
  "status": "pending"
}
```

---

**Get Audit Logs:**
```http
GET /api/v1/audit/logs?action_type=instance_terminate&start_date=2026-01-01&end_date=2026-01-16&page=1&per_page=100
Authorization: Bearer <token>
```

**Response:**
```json
{
  "items": [
    {
      "id": 12345,
      "timestamp": "2026-01-15T14:22:33Z",
      "admin_user": {
        "id": "admin_123",
        "email": "admin@saasodoo.com",
        "role": "super_admin"
      },
      "action_type": "instance_terminate",
      "resource_type": "instance",
      "resource_id": "inst_abc123",
      "reason": "Customer requested deletion",
      "result": "success",
      "ip_address": "192.168.1.100"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 100,
    "total": 45,
    "pages": 1
  }
}
```

---

## 11. Security Considerations

### 11.1 Threat Model

**Threat 1: Unauthorized Admin Access**
- **Risk**: External attacker gains admin credentials
- **Mitigation**:
  - Enforce strong password policy (min 12 chars, complexity)
  - Mandate 2FA for Super Admin role
  - IP allowlist for admin access (optional)
  - Session timeout after 4 hours
  - Auto-logout after 15 min inactivity

**Threat 2: Privilege Escalation**
- **Risk**: Lower-privileged admin gains Super Admin access
- **Mitigation**:
  - RBAC enforced on every API call
  - Role changes logged in audit trail
  - Cannot self-modify role
  - Database constraints prevent invalid role assignments

**Threat 3: Insider Threat (Malicious Admin)**
- **Risk**: Admin intentionally sabotages system or steals data
- **Mitigation**:
  - 100% audit logging (immutable)
  - Require reason for destructive actions
  - Alert on bulk deletions
  - Separate database credentials (admin tool cannot directly modify service DBs)

**Threat 4: Data Exfiltration**
- **Risk**: Admin exports sensitive customer data
- **Mitigation**:
  - Log all export actions
  - Rate limit exports (max 100 records/minute)
  - Mask sensitive fields (passwords, payment info) in exports
  - Alert on large exports (> 1000 records)

**Threat 5: Audit Log Tampering**
- **Risk**: Admin modifies audit log to cover tracks
- **Mitigation**:
  - Append-only table (no UPDATE/DELETE permissions)
  - Cryptographic signatures on log entries
  - Periodic backup to immutable storage (S3 Glacier)
  - Alert on direct database access (outside API)

---

### 11.2 Security Controls

**1. Authentication & Authorization:**
- JWT with 4-hour expiration
- RBAC with least-privilege principle
- 2FA for Super Admin (mandatory)
- Session binding to IP address (optional)

**2. Data Protection:**
- TLS 1.3 for all communication
- Secrets stored in environment variables (not code)
- Sensitive data encrypted at rest (database encryption)
- PII masking in logs

**3. Input Validation:**
- Pydantic validation for all API inputs
- Parameterized queries (prevent SQL injection)
- HTML sanitization (prevent XSS)
- File upload validation (if implemented)

**4. API Security:**
- Rate limiting (100 req/min per user, 1000 req/min global)
- CORS policy (admin domain only)
- CSRF tokens for state-changing operations
- Request size limits (max 10MB)

**5. Monitoring & Alerting:**
- Alert on failed login attempts (5+ in 10 min)
- Alert on privilege escalation attempts
- Alert on bulk data exports
- Anomaly detection (unusual access patterns)

---

### 11.3 Compliance Requirements

**SOC 2 Type II:**
- Complete audit trail (CC6.1)
- Access controls (CC6.2)
- Encryption in transit and at rest (CC6.7)
- Security monitoring (CC7.2)

**GDPR:**
- Customer data deletion workflow
- Audit log retention: 7 years
- Right to access (customer data export)
- Consent management (not applicable to admin tool)

**PCI DSS (for payment data):**
- No storage of full card numbers (use KillBill tokens)
- Access logging (requirement 10)
- Strong authentication (requirement 8)
- Network segmentation (admin tool separate network)

---

## 12. Success Metrics

### 12.1 Product Metrics

**Adoption:**
- 100% of admin users onboarded within 30 days
- 90% of admin tasks performed via dashboard (vs direct DB/API)
- < 1 day training time for new admins

**Efficiency:**
- 70% reduction in manual admin task time
- 80% reduction in mean time to resolution (MTTR) for issues
- 50% reduction in customer support escalations

**System Health:**
- 99.9% instance provisioning success rate
- Zero capacity-related outages
- 100% billing webhook success rate

---

### 12.2 Business Metrics

**Cost Reduction:**
- 40 hours/month admin time savings = $8K/month savings
- 50% reduction in support costs
- Prevent $5K/month revenue leakage (billing gaps)

**Revenue Impact:**
- Improve trial-to-paid conversion by 10% (from 28% to 30%)
- Reduce churn by 5% (proactive issue resolution)

**Customer Satisfaction:**
- 95% reduction in provisioning delays
- 90% first-contact resolution rate for support

---

### 12.3 Technical Metrics

**Performance:**
- Dashboard load time < 2 seconds (P95)
- API response time < 500ms (P95)
- 99.9% admin tool uptime

**Usage:**
- 100+ active admin sessions/day
- 1000+ admin actions/day
- 50+ alerts triggered/week

---

## 13. Timeline & Milestones

### Phase 1: Foundation (Weeks 1-4)

**Week 1: Setup & Authentication**
- Set up admin tool repository
- Create admin database schema
- Implement JWT authentication
- Build basic frontend scaffold (routing, layout)

**Week 2: Dashboard & Core UI**
- Build dashboard with metric cards
- Implement customer list view
- Implement instance list view
- Create reusable UI components (DataTable, StatusBadge, etc.)

**Week 3: Customer & Instance Management**
- Customer detail view with tabs
- Instance detail view with metrics
- Basic instance actions (start, stop, restart)
- Customer actions (suspend, activate)

**Week 4: Audit & Testing**
- Audit log implementation
- RBAC enforcement
- Unit + integration tests
- Security review

**Milestone 1 Deliverables:**
- Functional admin dashboard
- Customer/instance read-only views
- Basic lifecycle actions
- Audit logging
- **Success Criteria**: 2 admins can perform daily tasks via dashboard

---

### Phase 2: Advanced Features (Weeks 5-8)

**Week 5: Database Pool Management**
- Pool list and detail views
- Pool health checks
- Pool provisioning
- Capacity planning widget

**Week 6: Billing Integration**
- Billing overview dashboard
- Subscription list and detail views
- Trial management
- Manual payment actions

**Week 7: Monitoring & Alerts**
- Celery task queue monitoring
- Alert definition and history
- Real-time metrics dashboard
- Log search and viewer

**Week 8: Reporting & Polish**
- Pre-built reports (executive, capacity, billing)
- Export functionality (CSV, PDF)
- Advanced filters and search
- Mobile-responsive layouts

**Milestone 2 Deliverables:**
- Complete feature parity with scattered admin endpoints
- Proactive alerting system
- Comprehensive reporting
- **Success Criteria**: Zero manual API calls for admin tasks

---

### Phase 3: Optimization & Scale (Weeks 9-12)

**Week 9: Performance Optimization**
- Database query optimization
- Frontend code splitting
- Caching strategy
- Load testing (100 concurrent users)

**Week 10: Advanced Admin Features**
- Bulk operations (pause multiple instances)
- Custom SQL query interface
- Kubernetes pod management
- Advanced RBAC (custom permissions)

**Week 11: Integrations**
- Slack notifications
- PagerDuty integration
- Grafana dashboard embedding
- Webhook configuration UI

**Week 12: Documentation & Launch**
- Admin user guide (with screenshots)
- API documentation (Swagger)
- Deployment runbook
- Launch readiness review

**Milestone 3 Deliverables:**
- Production-ready admin tool
- Complete documentation
- Performance validated at scale
- **Success Criteria**: 99.9% uptime, < 2 sec load time, 90% user satisfaction

---

### Phase 4: Future Enhancements (Post-Launch)

**Q2 2026:**
- Machine learning-based anomaly detection
- Predictive capacity planning (ML models)
- Automated remediation (self-healing instances)
- Advanced analytics (cohort analysis, funnel reports)

**Q3 2026:**
- Multi-tenant admin tool (for white-label partners)
- Mobile app (iOS/Android)
- API marketplace (third-party integrations)

---

## 14. Risks & Mitigations

### 14.1 Technical Risks

**Risk 1: Performance Degradation at Scale**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Load testing before launch (simulate 10K instances)
  - Database indexing strategy
  - Implement caching (Redis) for expensive queries
  - Pagination and lazy loading
- **Contingency:** Vertical scaling (upgrade DB instance), read replicas

**Risk 2: Integration Failures**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  - Graceful degradation (show cached data if service unavailable)
  - Retry logic with exponential backoff
  - Circuit breaker pattern
  - Comprehensive integration tests
- **Contingency:** Fallback to direct DB queries (read-only)

**Risk 3: Data Inconsistency**
- **Likelihood:** Low
- **Impact:** High
- **Mitigation:**
  - Transaction boundaries for multi-step operations
  - Idempotent API design
  - Eventual consistency monitoring
  - Data validation checks
- **Contingency:** Manual reconciliation scripts, rollback procedures

---

### 14.2 Security Risks

**Risk 4: Unauthorized Access**
- **Likelihood:** Medium
- **Impact:** Critical
- **Mitigation:**
  - Strong authentication (2FA for Super Admin)
  - Rate limiting on login endpoint
  - IP allowlist (optional)
  - Intrusion detection alerts
- **Contingency:** Immediate credential rotation, incident response plan

**Risk 5: Audit Log Compromise**
- **Likelihood:** Low
- **Impact:** High
- **Mitigation:**
  - Append-only table (no UPDATE/DELETE)
  - Cryptographic signatures
  - Backup to immutable storage
  - Database-level access controls
- **Contingency:** Restore from backup, forensic analysis

---

### 14.3 Operational Risks

**Risk 6: Incomplete Migration from Manual Processes**
- **Likelihood:** Medium
- **Impact:** Medium
- **Mitigation:**
  - Phased rollout (pilot with 2 admins before full launch)
  - Comprehensive training (user guide + video tutorials)
  - Feedback loop (weekly check-ins during first month)
  - Deprecation timeline for old admin endpoints
- **Contingency:** Keep old endpoints active for 3 months, gradual deprecation

**Risk 7: Scope Creep**
- **Likelihood:** High
- **Impact:** Medium
- **Mitigation:**
  - Strict prioritization (P0/P1/P2)
  - Feature freeze after Week 8
  - Defer "nice-to-have" to Phase 4
  - Change control process
- **Contingency:** Push non-critical features to post-launch

**Risk 8: Resource Constraints (Dev Team)**
- **Likelihood:** Medium
- **Impact:** High
- **Mitigation:**
  - Dedicated 2-person team (1 backend, 1 frontend)
  - Reuse existing components from customer portal
  - Minimize custom development (leverage open-source)
  - Buffer time (2 weeks) in timeline
- **Contingency:** Reduce scope to P0 features only, extend timeline

---

### 14.4 Business Risks

**Risk 9: Low Adoption by Admin Team**
- **Likelihood:** Low
- **Impact:** High
- **Mitigation:**
  - Involve admins in design reviews (user-centered design)
  - Beta testing period (2 weeks before launch)
  - Incentivize usage (gamification, leaderboard)
  - Sunset manual processes
- **Contingency:** Extended training, one-on-one coaching

**Risk 10: Compliance Gaps**
- **Likelihood:** Low
- **Impact:** Critical
- **Mitigation:**
  - Security audit before launch
  - Compliance checklist (SOC 2, GDPR, PCI DSS)
  - Penetration testing
  - Legal review of audit log retention
- **Contingency:** Delay launch until compliance issues resolved

---

## 15. Appendices

### Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Instance** | A single Odoo deployment (database + application server) |
| **Database Pool** | A PostgreSQL server hosting multiple tenant databases |
| **Provisioning** | Automated process of creating a new instance |
| **MRR** | Monthly Recurring Revenue |
| **ARR** | Annual Recurring Revenue |
| **MTTR** | Mean Time To Resolution (for incidents) |
| **RBAC** | Role-Based Access Control |
| **CNPG** | CloudNativePG (Kubernetes PostgreSQL operator) |
| **KillBill** | Open-source billing and payment platform |
| **Celery** | Distributed task queue system |
| **Dunning** | Process of collecting overdue payments |

---

### Appendix B: User Roles & Permissions Matrix

| Feature / Action | Super Admin | Platform Admin | DevOps | Finance | Support |
|------------------|:-----------:|:--------------:|:------:|:-------:|:-------:|
| **Dashboard View** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Customer Management** |
| - View customers | ✓ | ✓ | ✓ | ✓ | ✓ |
| - Suspend account | ✓ | ✓ | - | - | - |
| - Delete account | ✓ | - | - | - | - |
| - Impersonate | ✓ | - | - | - | - |
| **Instance Management** |
| - View instances | ✓ | ✓ | ✓ | ✓ | ✓ |
| - Start/stop/restart | ✓ | ✓ | ✓ | - | Read-only* |
| - Terminate instance | ✓ | ✓ | - | - | - |
| - Retry provisioning | ✓ | ✓ | ✓ | - | - |
| **Database Pools** |
| - View pools | ✓ | ✓ | ✓ | - | - |
| - Health check | ✓ | ✓ | ✓ | - | - |
| - Provision pool | ✓ | - | ✓ | - | - |
| **Billing** |
| - View billing data | ✓ | Read-only | - | ✓ | Read-only |
| - Manual payment | ✓ | - | - | ✓ | - |
| - Refund | ✓ | - | - | ✓ | - |
| - Grant trial | ✓ | - | - | ✓ | - |
| **Monitoring** |
| - View metrics | ✓ | ✓ | ✓ | - | - |
| - View logs | ✓ | ✓ | ✓ | - | Read-only |
| - Retry failed tasks | ✓ | ✓ | ✓ | - | - |
| **Alerts** |
| - View alerts | ✓ | ✓ | ✓ | ✓ | ✓ |
| - Acknowledge alerts | ✓ | ✓ | ✓ | - | - |
| - Configure alerts | ✓ | - | ✓ | - | - |
| **Audit Logs** |
| - View audit logs | ✓ | ✓ | - | ✓ | - |
| **Admin Management** |
| - View admins | ✓ | - | - | - | - |
| - Invite admin | ✓ | - | - | - | - |
| - Change roles | ✓ | - | - | - | - |
| - Revoke access | ✓ | - | - | - | - |
| **System Config** |
| - View config | ✓ | ✓ | ✓ | - | - |
| - Modify config | ✓ | - | - | - | - |

*Support can restart instances but only after confirmation from Platform Admin

---

### Appendix C: Success Metrics Dashboard (Example)

**KPIs to Track (Weekly):**

```
┌─────────────────────────────────────────────────────────┐
│ Admin Tool Success Metrics - Week of 2026-01-16        │
├─────────────────────────────────────────────────────────┤
│ EFFICIENCY METRICS                                      │
│ ■ Avg time per admin task: 3.2 min (↓ 75% vs manual)  │
│ ■ MTTR for instance failures: 12 min (target: 15 min) │
│ ■ Admin actions via dashboard: 94% (target: 90%)      │
│                                                         │
│ SYSTEM HEALTH METRICS                                   │
│ ■ Instance provisioning success: 99.2% (target: 99.9%)│
│ ■ Billing webhook success: 100% (target: 100%)        │
│ ■ Capacity warnings triggered: 2 (resolved: 2)        │
│                                                         │
│ BUSINESS IMPACT METRICS                                 │
│ ■ Trial-to-paid conversion: 29.8% (↑ 1.3% vs baseline)│
│ ■ Support escalations: -45% vs previous month         │
│ ■ Revenue leakage prevented: $1,200                   │
│                                                         │
│ TECHNICAL METRICS                                       │
│ ■ Dashboard load time (P95): 1.8 sec (target: 2 sec)  │
│ ■ Admin tool uptime: 99.95% (target: 99.9%)           │
│ ■ Active admin users: 8 / 10 invited                  │
└─────────────────────────────────────────────────────────┘
```

---

### Appendix D: References

**Internal Documentation:**
- SAASODOO Architecture Overview
- KillBill Integration Guide
- Celery Task Queue Documentation
- Database Pool Management Procedures

**External Resources:**
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Query](https://tanstack.com/query/latest)
- [Tailwind CSS](https://tailwindcss.com/)
- [Recharts](https://recharts.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [SOC 2 Compliance Guide](https://www.aicpa.org/soc2)

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-16 | Claude AI | Initial PRD creation |

---

**End of Document**
