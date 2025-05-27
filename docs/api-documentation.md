# API Documentation
## Odoo SaaS Platform REST API

**Version:** 2.0  
**Date:** December 2024  
**Base URL:** `https://api.yourdomain.com/api/v1`

## 🔐 Authentication

All API endpoints require authentication using Bearer tokens obtained from Supabase. The platform uses JWT-based authentication with refresh token support for secure access to all resources.

### Authentication Flow
The authentication system follows OAuth 2.0 patterns with Supabase handling the underlying authentication infrastructure. Users authenticate using email/password credentials and receive access tokens for API requests.

## 📊 API Endpoints

### 🔐 Authentication Endpoints

#### POST /auth/login
Authenticates users with email and password credentials. Returns access and refresh tokens along with user profile information. The access token is used for subsequent API requests, while the refresh token enables token renewal without re-authentication.

#### POST /auth/register
Creates new user accounts with email verification. Requires email, password, and full name. The system validates email uniqueness and password strength before account creation. New users receive verification emails for account activation.

#### POST /auth/refresh
Renews expired access tokens using valid refresh tokens. This endpoint maintains user sessions without requiring re-authentication. Refresh tokens have longer expiration periods and can be revoked for security purposes.

### 🏢 Tenant Management Endpoints

#### GET /tenants
Retrieves all tenant instances owned by the authenticated user. Returns comprehensive tenant information including status, resource allocation, database strategy, and access URLs. Supports pagination and filtering by status or tier.

#### POST /tenants
Initiates creation of new tenant instances with specified configuration. Requires tenant name, subdomain, subscription tier, and admin credentials. The system validates subdomain availability and provisions Kubernetes resources asynchronously. Returns provisioning status and estimated completion time.

#### GET /tenants/{tenant_id}
Provides detailed information about a specific tenant including real-time resource usage, backup status, admin credentials, and operational metrics. Returns comprehensive tenant configuration, current status, and performance data.

#### PUT /tenants/{tenant_id}
Updates tenant configuration including subscription tier and database strategy. Changes are applied asynchronously with status tracking. Tier upgrades may trigger resource scaling and database migration processes.

#### DELETE /tenants/{tenant_id}
Initiates tenant deletion process including data cleanup and resource deallocation. The operation is performed asynchronously with confirmation and estimated completion time. Backup creation is automatically triggered before deletion.

### 📊 Monitoring Endpoints

#### GET /tenants/{tenant_id}/metrics
Retrieves real-time performance metrics for a specific tenant including CPU usage, memory consumption, storage utilization, and network traffic. Metrics are collected from Kubernetes and application-level monitoring systems with configurable time ranges and granularity.

#### GET /tenants/{tenant_id}/logs
Provides access to tenant application logs with filtering capabilities. Supports log level filtering, time range queries, and pagination. Logs include application events, system messages, and user activity with structured metadata for analysis.

### 💾 Backup Management Endpoints

#### GET /tenants/{tenant_id}/backups
Lists all available backups for a tenant with metadata including creation time, size, type (scheduled or manual), status, and retention period. Supports filtering by backup type and date range with pagination for large backup histories.

#### POST /tenants/{tenant_id}/backups
Initiates on-demand backup creation for a tenant. The backup process includes database dump, file storage, and configuration data. Returns backup job status and estimated completion time with progress tracking capabilities.

#### POST /tenants/{tenant_id}/backups/{backup_id}/restore
Restores a tenant from a selected backup point. The restoration process includes data validation, service shutdown, data restoration, and service restart. Provides restoration progress tracking and rollback capabilities if issues occur.

### 💰 Billing Endpoints

#### GET /billing/subscriptions
Retrieves subscription information for the authenticated user including active plans, billing periods, amounts, and payment status. Integrates with Kill Bill for comprehensive subscription management and supports multiple subscription tiers per user.

#### POST /billing/subscriptions
Creates new subscriptions for tenant instances with specified payment methods. Validates payment information, processes initial charges, and activates subscription services. Supports proration for mid-cycle upgrades and plan changes.

#### GET /billing/invoices
Provides access to billing invoices with filtering and pagination capabilities. Includes invoice details, payment status, due dates, and download links for PDF invoices. Supports status filtering and date range queries for financial reporting.

### ⚙️ Admin Endpoints

#### GET /admin/tenants
Provides comprehensive tenant overview for platform administrators with filtering and pagination capabilities. Returns tenant status, resource utilization, user information, and operational metrics. Supports filtering by status, tier, and date ranges for administrative reporting.

#### GET /admin/metrics/platform
Delivers platform-wide operational metrics including tenant distribution, resource utilization, user statistics, and system health indicators. Provides insights for capacity planning, performance optimization, and business intelligence reporting.

#### POST /admin/tenants/{tenant_id}/actions
Enables administrative actions on tenant instances including service management, database migrations, and maintenance operations. Supports restart, stop, start, migrate, and backup actions with reason tracking and audit logging for compliance.

## 🔍 Health Check Endpoints

#### GET /health
Provides basic platform health status with version information and timestamp. Used for load balancer health checks and basic monitoring systems to verify platform availability.

#### GET /health/detailed
Delivers comprehensive health information including individual service status, performance metrics, and system diagnostics. Includes database connectivity, external service status, and resource utilization for detailed monitoring.

## 📝 Error Responses

### Standard Error Format
All API errors follow a consistent format including error codes, descriptive messages, relevant details, and timestamps. Error responses include correlation IDs for debugging and support ticket tracking.

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Invalid or missing authentication token |
| `FORBIDDEN` | 403 | Insufficient permissions for the operation |
| `TENANT_NOT_FOUND` | 404 | Specified tenant does not exist |
| `TENANT_LIMIT_EXCEEDED` | 400 | User has reached maximum tenant limit |
| `INVALID_SUBDOMAIN` | 400 | Subdomain is invalid or already taken |
| `PROVISIONING_FAILED` | 500 | Tenant provisioning failed |
| `BACKUP_FAILED` | 500 | Backup operation failed |
| `BILLING_ERROR` | 402 | Payment or billing issue |
| `RATE_LIMIT_EXCEEDED` | 429 | API rate limit exceeded |
| `MAINTENANCE_MODE` | 503 | Platform is in maintenance mode |

## 🔄 Webhooks

The platform supports webhooks for real-time notifications of important events including tenant lifecycle changes, backup operations, billing events, and system alerts.

### Webhook Configuration
Webhooks can be configured through the user dashboard or API with customizable event subscriptions, retry policies, and security settings. Supports HMAC signature verification for secure event delivery.

### Webhook Events

#### tenant.created
Triggered when a new tenant provisioning process begins. Includes tenant configuration details, user information, and estimated completion time for integration with external systems.

#### tenant.ready
Fired when tenant provisioning completes successfully and the instance is accessible. Provides access URLs, admin credentials, and provisioning metrics for automated workflows.

#### backup.completed
Sent when backup operations finish, including both scheduled and manual backups. Contains backup metadata, size information, and retention details for backup management systems.

## 📊 Rate Limiting

API endpoints implement tiered rate limiting based on subscription levels to ensure fair resource usage and platform stability. Rate limits are enforced per user account with automatic reset periods and burst allowances for peak usage scenarios.

**Rate Limit Tiers:**
- **Standard Users**: 1000 requests per hour with burst capacity
- **Premium Users**: 5000 requests per hour with extended burst
- **Enterprise Users**: 10000 requests per hour with priority queuing
- **Admin Users**: 50000 requests per hour for platform management

Rate limit information is provided in response headers for client-side throttling and usage monitoring.

## 🔧 SDK and Client Libraries

### Python SDK
Official Python SDK provides comprehensive API access with automatic authentication, retry logic, and response parsing. Includes async support, pagination helpers, and built-in error handling for production applications.

### JavaScript SDK
TypeScript-compatible JavaScript SDK for browser and Node.js environments. Features automatic token refresh, request queuing, and WebSocket support for real-time updates. Includes React hooks and Vue.js composables for frontend integration.

## 📚 Additional Resources

- **Postman Collection**: Complete API collection for testing and development workflows
- **OpenAPI Specification**: Machine-readable API specification for code generation and documentation
- **SDK Documentation**: Detailed SDK documentation with examples and best practices
- **Webhook Testing Guide**: Comprehensive webhook testing and debugging procedures 