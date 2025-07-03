# Issues Log - SaaS Odoo Platform

This document tracks known issues, their root causes, resolution status, and any temporary workarounds implemented.

## Format
- **Issue ID**: Unique identifier
- **Status**: Open, In Progress, Resolved, Workaround Applied
- **Priority**: Critical, High, Medium, Low
- **Component**: Which service/component is affected
- **Reporter**: Who identified the issue
- **Date**: When the issue was identified

---

## Issue #001 - Authentication Logout Session Invalidation

**Status**: ✅ Resolved  
**Priority**: Critical (Security Issue)  
**Component**: user-service  
**Date**: 2025-06-02  
**Reporter**: System Testing  

### Description
After user logout, session tokens remained valid and could be reused for authentication, creating a security vulnerability.

### Root Cause
The `logout_customer()` method in `AuthService` was not actually invalidating session tokens from the database. It only logged the logout event but left the session record intact in the `user_sessions` table.

### Resolution
- Added `invalidate_customer_session()` method to `CustomerDatabase`
- Modified logout route to extract session token from Authorization header
- Updated `logout_customer()` method to actually delete session from database
- Fixed parameter ordering syntax error in logout route

### Test Results
```bash
✅ Login: Get valid token
✅ Use token: Authentication works
✅ Logout: Session invalidated
✅ Reuse token: Returns 401 Unauthorized (Expected)
```

### Files Modified
- `services/user-service/app/utils/database.py` - Added invalidation method
- `services/user-service/app/routes/auth.py` - Updated logout route
- `services/user-service/app/services/auth_service.py` - Enhanced logout logic

---

## Issue #002 - Authentication /auth/me Endpoint Crashes

**Status**: ✅ Resolved  
**Priority**: High  
**Component**: user-service  
**Date**: 2025-06-02  
**Reporter**: User Testing  

### Description
The `/auth/me` endpoint was returning "Customer not found" errors and failing due to two main issues:
1. **UUID Conversion Issue**: Customer ID was being returned as UUID object but UserProfileSchema expected string
2. **Missing Dependencies**: Attempting to query tenant database that wasn't accessible from user-service

### Root Cause Analysis
```
ERROR:app.services.user_service:Get customer profile failed: 1 validation error for UserProfileSchema
id
  Input should be a valid string [type=string_type, input_value=UUID('5ad2f360-32b2-428b-b90b-6ddbcad8bf9d'), input_type=UUID]
```

### Resolution Implemented
1. **Fixed UUID Conversion**: Updated `get_customer_profile()` method to convert `customer['id']` to string using `str(customer['id'])`
2. **Applied Workaround**: Modified `_get_customer_instance_count()` and `_get_customer_subscription_info()` to return safe default values instead of querying unavailable tenant/billing databases

### Code Changes
- `services/user-service/app/services/user_service.py`:
  - Line 59: Changed `'id': customer['id']` to `'id': str(customer['id'])`
  - Line 99: Same fix in `update_customer_profile()` method
  - Lines 394-443: Updated methods to return default values

### Test Results
✅ **Before Fix**: Endpoint crashed with validation errors  
✅ **After Fix**: Returns proper user profile with default values  

```json
{
  "id": "5ad2f360-32b2-428b-b90b-6ddbcad8bf9d",
  "email": "testworkaround@example.com",
  "instance_count": 0,
  "subscription_plan": "Basic",
  "subscription_status": "active"
}
```

### Future Considerations
- When tenant-service is implemented, update `_get_customer_instance_count()` to make API calls
- When billing-service is implemented, update `_get_customer_subscription_info()` to fetch real data
- Remove workaround comments and implement proper microservice communication

---

## Issue #003 - Missing Tenant Service

**Status**: 🔄 In Progress  
**Priority**: High  
**Component**: tenant-service  
**Description**: Need to implement tenant-service to manage Odoo instance lifecycle and provide APIs for tenant operations.

**Status Update**: 
- ✅ **Completed**: Basic tenant CRUD operations implemented and tested
- 🔄 **In Progress**: Customer statistics API endpoint for user-service integration
- 📋 **Pending**: Remove workaround in user-service `_get_customer_instance_count()`

**Remaining Tasks**:
- [ ] Create `/api/v1/tenants/customer/{customer_id}/stats` endpoint in tenant-service
- [ ] Update user-service to call tenant-service API instead of returning default values
- [ ] Test end-to-end customer profile with real tenant data
- [ ] Remove TODO comments and workaround code

**Issue #004 - Missing Billing Service**  
**Status**: 📋 Planned  
**Priority**: Medium  
**Component**: billing-service  
**Description**: Need to implement billing-service to manage subscriptions and payment processing for Zimbabwe market (PayNow, EcoCash).

**Issue #005 - Service Communication Pattern**  
**Status**: 🔄 In Progress  
**Priority**: Medium  
**Component**: Architecture  
**Description**: Establish proper service-to-service communication patterns and replace direct database queries with API calls.

**Issue #006 - Port Standardization Across Services**  
**Status**: 📋 Open  
**Priority**: Medium  
**Component**: Architecture  
**Date**: 2025-01-15  
**Reporter**: Development Team  

### Description
Currently, services use different internal ports (user-service:8001, tenant-service:8002) which differs from microservices best practices. Industry standard is to use the same internal port (typically 5000) for all services while varying external ports for development access.

### Current State
```yaml
user-service:
  ports:
    - "8001:8001"  # External 8001 → Internal 8001

tenant-service:
  ports:
    - "8002:8002"  # External 8002 → Internal 8002
```

### Proposed Solution
```yaml
user-service:
  ports:
    - "8001:5000"  # External 8001 → Internal 5000

tenant-service:
  ports:
    - "8002:5000"  # External 8002 → Internal 5000
```

### Benefits
- Better container portability and consistency
- Simplified service-to-service communication URLs
- Easier scaling and replica management
- Cleaner production deployment (no external ports needed)
- Following microservices best practices

### Migration Tasks
- [ ] Update all service applications to listen on port 5000
- [ ] Update Dockerfiles to `EXPOSE 5000`
- [ ] Update Docker Compose port mappings to `external:5000`
- [ ] Update Traefik labels to use port 5000
- [ ] Update service-to-service communication URLs
- [ ] Update environment variables and configuration

### Files to Modify
- `infrastructure/compose/docker-compose.dev.yml`
- `services/user-service/Dockerfile`
- `services/tenant-service/Dockerfile` 
- `services/user-service/app/main.py`
- `services/tenant-service/app/main.py`
- Service communication code in user-service

### Impact Assessment
- **Low Risk**: Only affects development and deployment configuration
- **No Breaking Changes**: External API endpoints remain the same
- **Improved Maintainability**: Standardized architecture

---

## Issue #007 - Instance Creation Endpoint Failure

**Status**: ✅ Resolved  
**Priority**: High  
**Component**: instance-service  
**Date**: 2025-06-03  
**Reporter**: Endpoint Testing  

### Description
The instance creation endpoint `POST /api/v1/instances/` returns HTTP 500 Internal Server Error when attempting to create new Odoo instances. This prevents the core functionality of provisioning new Odoo instances for tenants.

### Test Case That Failed
```bash
curl -X POST http://localhost:8003/api/v1/instances/ \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "7e705917-0594-490e-a9dc-9447206539f2",
    "name": "Test Instance",
    "description": "Test Odoo Instance",
    "odoo_version": "17.0",
    "instance_type": "development",
    "cpu_limit": 1.0,
    "memory_limit": "2G",
    "storage_limit": "10G",
    "admin_email": "admin@example.com",
    "demo_data": true,
    "database_name": "test_db_123",
    "custom_addons": ["sale", "purchase"]
  }'

Response: {"detail":"Internal server error"}
```

### Root Cause Analysis
**Error**: `invalid input for query argument $12: ['sale'] (expected str, got list)`

The issue was a **data type mismatch** in the database layer:
- Database schema defines `custom_addons`, `disabled_modules`, and `environment_vars` as `JSONB` fields
- Python code was passing Python `list`/`dict` objects directly to asyncpg 
- AsyncPG expects JSON-serialized strings for JSONB fields, not Python objects

### Resolution Implemented
1. **Fixed Database Insertion**: Updated `create_instance()` method to JSON-serialize list/dict fields:
   ```python
   # Before (causing error)
   instance_data.custom_addons,        # Raw Python list: ['sale']
   instance_data.disabled_modules,     # Raw Python list: []
   instance_data.environment_vars,     # Raw Python dict: {}
   
   # After (working)
   json.dumps(instance_data.custom_addons),        # JSON string: '["sale"]'
   json.dumps(instance_data.disabled_modules),     # JSON string: '[]'
   json.dumps(instance_data.environment_vars),     # JSON string: '{}'
   ```

2. **Fixed Database Retrieval**: Updated `get_instance()` and `get_instances_by_tenant()` methods to JSON-deserialize the fields when reading from database

3. **Fixed Updates**: Updated `update_instance()` method to handle JSON serialization for update operations

### Code Changes
- `services/instance-service/app/utils/database.py`:
  - Lines 94-96: Added `json.dumps()` calls for JSONB fields in create operation
  - Lines 118-140: Added JSON deserialization logic in get_instance method
  - Lines 168-188: Added JSON deserialization logic in get_instances_by_tenant method  
  - Line 213: Added JSON serialization check in update_instance method

### Test Results
✅ **Before Fix**: HTTP 500 Internal Server Error  
✅ **After Fix**: Instance creation successful with proper JSON handling

```json
{
  "id": "373332f4-cec9-45f5-be33-43f6ea04c3b5",
  "tenant_id": "7e705917-0594-490e-a9dc-9447206539f2",
  "name": "Complete Test Instance",
  "status": "creating",
  "custom_addons": ["sale", "purchase"],
  "database_name": "complete_test_db"
}
```

### Verification Completed
✅ Instance creation - Working  
✅ Instance retrieval - Working  
✅ Instance listing - Working  
✅ Instance updates - Working  
✅ Instance actions - Working (with proper status validation)

### Working Endpoints
✅ `POST /api/v1/instances/` - Instance creation working  
✅ `GET /api/v1/instances/{id}` - Instance retrieval working  
✅ `PUT /api/v1/instances/{id}` - Instance updates working  
✅ `GET /api/v1/instances/?tenant_id=...` - List instances working  
✅ `POST /api/v1/instances/{id}/actions` - Instance actions working  

### Impact
- **Critical bug resolved**: Core SaaS functionality now operational
- **End-to-end workflow**: Customer → Tenant → Instance creation flow working
- **MVP milestone**: Instance provisioning capability achieved

---

## Issue #008 - Instance Provisioning Logic Gap

**Status**: ✅ Resolved  
**Priority**: Medium  
**Component**: Architecture - Service Integration  
**Date**: 2025-06-30  
**Reporter**: Service Integration Analysis  
**Resolved**: 2025-06-30

### Description
Current instance provisioning flow does not follow webhook-driven best practices. Instances are provisioned immediately upon request rather than waiting for billing confirmation, creating potential billing-provisioning mismatches.

### Original Problematic Flow
1. Instance request → Creates subscription → Provisions instance immediately
2. All subscriptions get 14-day trials regardless of customer eligibility
3. No differentiation between trial and immediate payment instances

### Implemented Solution (Webhook-Driven Architecture)

**New Flow for Trial Instances:**
1. User requests instance → Create pending instance + subscription in database
2. KillBill webhook: `SUBSCRIPTION_CREATION` → Trigger instance provisioning
3. Instance becomes active with trial billing status

**New Flow for Paid Instances:**
1. User requests instance → Create pending instance + subscription in database  
2. KillBill webhook: `PAYMENT_SUCCESS` → Trigger instance provisioning
3. Instance becomes active with paid billing status

### Implementation Details

**Database Schema Updates:**
- Added `subscription_id`, `billing_status`, `provisioning_status` to `instances` table
- Added `instance_id`, `trial_eligible`, `killbill_subscription_id` to `subscriptions` table
- Proper indexing for performance and association queries

**Instance Service Changes:**
- Removed immediate provisioning from instance creation route
- Added billing validation and trial eligibility checking
- Instances created with pending status until webhook confirmation
- Added `/api/v1/instances/{id}/provision` endpoint for webhook triggers

**Billing Webhook Enhancements:**
- `handle_subscription_created()`: Provisions trial instances (zero-dollar invoices)
- `handle_payment_success()`: Provisions paid instances after payment confirmation
- Proper customer-instance association via external keys

**Instance-Billing Integration:**
- Added `provision_instance()` method to billing service instance client
- Proper subscription-instance associations stored in both services
- Support for trial eligibility checking per customer

### Key Features Implemented
- **No instance provisioning without billing confirmation**
- **Trial instances only for eligible customers**
- **Paid instances only after payment success**
- **Proper database associations between billing and instances**
- **Webhook-driven event architecture**

### Files Modified
- `shared/configs/postgres/04-init-schemas.sql.template` - Database schema updates
- `services/instance-service/app/models/instance.py` - Added billing/provisioning status enums
- `services/instance-service/app/routes/instances.py` - Removed immediate provisioning, added webhook endpoint
- `services/instance-service/app/utils/database.py` - Database methods for new fields
- `services/billing-service/app/routes/webhooks.py` - Enhanced webhook handlers
- `services/billing-service/app/utils/instance_client.py` - Added provisioning methods
- `services/instance-service/app/utils/billing_client.py` - Added trial eligibility support

### Impact
- **Billing Security**: No instances provisioned without proper payment confirmation
- **Trial Management**: Proper trial eligibility tracking per customer
- **Revenue Protection**: Prevents revenue loss from improper billing flows
- **Scalability**: Event-driven architecture supports high volume
- **Compliance**: Audit trail of billing → provisioning flow

### Test Requirements
- Verify trial instances provision on subscription creation webhook
- Verify paid instances provision on payment success webhook  
- Verify no provisioning without webhook confirmation
- Verify proper instance-subscription associations
- Verify billing status tracking throughout lifecycle

---

## Resolution Categories

- 🚫 **Critical Security**: Issues that compromise system security
- ⚡ **Performance**: Issues affecting system performance  
- 🔧 **Functionality**: Features not working as expected
- 🏗️ **Architecture**: Design or structural issues
- 📋 **Enhancement**: Improvements or new features

---

## Maintenance

This log should be updated whenever:
- New issues are discovered
- Existing issues status changes
- Workarounds are applied
- Final resolutions are implemented

---

## Issue #008 - Instance Worker Database Privileges Security Issue

**Status**: ⚠️ Temporary Workaround Applied  
**Priority**: High (Security Issue)  
**Component**: instance-service worker  
**Date**: 2025-06-05  
**Reporter**: Instance Testing  

### Description
The instance-service worker needs to create new PostgreSQL databases for each Odoo instance but currently requires admin-level database credentials (superuser) to perform `CREATE DATABASE` operations. This violates the principle of least privilege.

### Current Security Issue
The worker container now has access to admin database credentials (`POSTGRES_USER` and `POSTGRES_PASSWORD`) which grants broad privileges including:
- Creating/dropping any database
- Creating/dropping any user
- Accessing any database in the system
- Potential system administration operations

### Root Cause
The provisioning workflow requires creating dedicated databases for each Odoo instance:
```sql
CREATE DATABASE "test_db_1";
CREATE USER "odoo_test_db_1" WITH PASSWORD 'generated_password';
GRANT ALL PRIVILEGES ON DATABASE "test_db_1" TO "odoo_test_db_1";
```

The `instance_service` user only has privileges on the `instance` database and cannot create new databases.

### Temporary Workaround Applied
Added admin credentials to instance-worker environment in docker-compose.dev.yml:
```yaml
# Database Configuration - Admin credentials for creating new databases (SECURITY ISSUE - TO FIX)
POSTGRES_USER: ${POSTGRES_USER:-odoo_user}
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-secure_password_change_me}
```

### Proper Solutions to Implement

**Option 1: Limited Privilege Escalation**
- Grant `CREATEDB` privilege to `instance_service` user
- Create a dedicated `instance_db_manager` user with only `CREATEDB` privileges
- Remove admin credentials from worker

**Option 2: Database Provisioning Service**
- Create separate microservice for database operations
- Worker calls API to request database creation
- Database service runs with appropriate privileges
- Better separation of concerns

**Option 3: Pre-provisioned Database Pool**
- Pre-create a pool of empty databases
- Worker assigns databases from pool instead of creating new ones
- Background service maintains database pool

### Recommended Solution
Implement **Option 1** first (quick fix), then migrate to **Option 2** for production (better architecture).

### Security Impact
- **Current Risk**: Worker has excessive database privileges
- **Exposure**: Admin credentials stored in container environment
- **Mitigation**: Development environment only, not production-ready

### Tasks to Complete
- [ ] Create `instance_db_manager` user with `CREATEDB` privilege only
- [ ] Update worker to use limited privilege user instead of admin
- [ ] Remove admin credentials from worker environment
- [ ] Test database creation with limited privileges
- [ ] Update provisioning.py to use new credentials

### Files to Modify
- `infrastructure/compose/docker-compose.dev.yml` - Remove admin credentials
- `shared/configs/postgres/03-create-users.sh` - Add db manager user
- `services/instance-service/app/tasks/provisioning.py` - Update connection logic

---

---

## Issue #009 - MinIO Long-term Backup Storage Implementation

**Status**: 📋 Open  
**Priority**: Medium  
**Component**: instance-service maintenance  
**Date**: 2025-06-06  
**Reporter**: Architecture Review  

### Description
Current backup implementation uses local volume storage (`/var/lib/odoo/backups`) for all backup operations. While this works for immediate backup/restore operations, we need to implement MinIO S3-compatible storage for long-term backup archival and improved scalability.

### Current Implementation
- **Storage**: Local Docker volume `odoo-backups:/var/lib/odoo/backups`
- **Access**: Direct filesystem operations within container
- **Limitations**: 
  - No off-site backup capability
  - Limited by local disk space
  - No cross-region replication
  - No backup deduplication

### MinIO Infrastructure Available
MinIO is already configured in `infrastructure/compose/docker-compose.dev.yml`:
- **Container**: `saasodoo-minio` 
- **API Endpoint**: `s3.localhost` (S3-compatible API)
- **Web Console**: `minio.localhost`
- **Storage**: `minio-data` volume for persistent storage
- **Credentials**: `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`

### Proposed Architecture

**Two-Tier Storage Strategy**:
```
Local Volume (Fast)          MinIO S3 (Archival)
├─ active/                   ├─ archived/
├─ staging/                  ├─ compressed/
└─ temp/                     └─ metadata/
```

**Backup Workflow**:
1. Create backup → Local volume (fast Docker operations)
2. Compress & process → Local staging area
3. Upload to MinIO S3 → Long-term storage with versioning
4. Cleanup local copy → Free local space
5. Catalog metadata → Both local and S3

**Restore Workflow**:
1. Check local cache → Recent backups (fast path)
2. Download from S3 → If not cached locally
3. Stage locally → Prepare for restoration
4. Restore operation → From local staging
5. Cleanup staging → Remove temporary files

### Implementation Tasks

**Phase 1: MinIO Integration**
- [ ] Add MinIO client library to requirements.txt (boto3 or minio-py)
- [ ] Create MinIO connection utility in shared/utils/
- [ ] Add MinIO configuration to instance-service environment
- [ ] Create backup bucket structure and policies

**Phase 2: Dual Storage Implementation**
- [ ] Modify backup tasks to support both local and S3 storage
- [ ] Implement backup upload workflow to MinIO after local creation
- [ ] Add restore download workflow from MinIO to local staging
- [ ] Create backup retention policies (local vs S3)

**Phase 3: Management Features**
- [ ] Backup catalog API endpoints (list S3 backups)
- [ ] Backup lifecycle management (auto-cleanup, retention)
- [ ] Cross-region backup replication configuration
- [ ] Backup integrity verification and checksums

### Benefits
- **Scalability**: Unlimited backup storage capacity
- **Durability**: S3-compatible storage with redundancy
- **Cost Efficiency**: Cheaper long-term storage vs local SSD
- **Disaster Recovery**: Off-site backup capability
- **Multi-tenancy**: Isolated backup buckets per tenant
- **Compliance**: Better audit trails and retention policies

### Technical Considerations
- **Async Uploads**: Background S3 uploads to avoid blocking operations
- **Compression**: Reduce bandwidth and storage costs
- **Encryption**: At-rest and in-transit encryption for sensitive data
- **Bandwidth**: Optimize upload/download for large Odoo instances
- **Caching**: Intelligent local caching for frequently accessed backups

### Files to Create/Modify
- `shared/utils/minio_client.py` - MinIO connection and operations
- `services/instance-service/app/tasks/maintenance.py` - Dual storage backup logic
- `services/instance-service/requirements.txt` - Add MinIO client dependency
- `infrastructure/compose/docker-compose.dev.yml` - MinIO environment variables

### Configuration Required
```yaml
# Instance Service Environment
MINIO_ENDPOINT: minio:9000
MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
MINIO_BUCKET_BACKUPS: odoo-backups
MINIO_SECURE: false  # true for HTTPS in production
```

### Priority Justification
**Medium Priority** because:
- Local storage works for immediate needs
- Critical for production scalability
- Important for disaster recovery
- Enables multi-region deployment
- Foundation for enterprise backup features

---

## Issue #010 - maintenance.py Refactoring Needed
**Status**: 📋 Open  
**Priority**: Medium  
**Component**: instance-service  
**Date**: 2025-06-06  
**Reporter**: Code Review  

### Description
The maintenance.py file has grown large (~1200+ lines) and contains multiple responsibilities that should be separated for better maintainability.

### Current Issues
- Single file handling backup, restore, and update operations
- Mixed concerns: database operations, Docker operations, file operations
- Repeated code patterns across backup/restore workflows
- Difficult to test individual components

### Recommended Refactoring
- Split into separate modules: backup_service.py, restore_service.py, update_service.py
- Extract common utilities: docker_utils.py, database_utils.py
- Create dedicated classes for each operation type
- Improve error handling and logging consistency

---

## Issue #011 - Upgrade Functionality Not Tested
**Status**: 📋 Open  
**Priority**: High  
**Component**: instance-service  
**Date**: 2025-06-06  
**Reporter**: Quality Assurance  

### Description
The Odoo version upgrade functionality exists in maintenance.py but has not been tested end-to-end.

### Current State
- Update workflow implementation exists
- Version validation logic present
- No testing of actual Odoo version upgrades
- Unknown compatibility with backup/restore after upgrades

### Testing Required
- Test upgrade from Odoo 16.0 to 17.0
- Verify data integrity after upgrades
- Test backup/restore compatibility across versions
- Validate rollback procedures

---

Last Updated: 2025-06-06 

# Instance Service Issue Log

## Issue #1: Docker SDK Version Compatibility
**Status**: ✅ RESOLVED  
**Severity**: Critical  
**Date Discovered**: 2025-06-05  
**Component**: Instance Service Worker  

### Description
Instance provisioning failed with Docker connection error: `"Error while fetching server API version: Not supported URL scheme http+docker"`

### Root Cause
- Docker SDK version mismatch: requirements.txt specified `docker==7.1.0` but containers had `docker==4.4.4` installed
- Docker SDK versions < 7.1.0 are incompatible with requests library 2.32.0+ due to URL scheme handler changes
- Docker build cache prevented proper dependency updates during rebuilds

### Impact
- All instance provisioning tasks failed immediately at Docker client initialization
- Users could create instance records but no actual Odoo containers were deployed
- Error propagated to instance status as "error" with meaningful error message

### Files Affected
- `services/instance-service/requirements.txt` (381B) - Correct version specified
- `services/instance-service/Dockerfile` (1.0KB) - Build process cached old dependencies
- `services/instance-service/app/tasks/provisioning.py` (11.7KB) - Docker client initialization at line 174

### Resolution
1. Stopped and removed existing containers
2. Deleted cached Docker images completely
3. Rebuilt containers with `--no-cache` to force fresh dependency installation
4. Verified Docker SDK 7.1.0 installation in worker container
5. Confirmed Docker connection now works: `Docker connection successful`

### Prevention
- Add dependency version verification to health checks
- Implement more aggressive cache invalidation in CI/CD
- Consider pinning transitive dependencies (requests, urllib3) to avoid future conflicts

---

## Issue #2: Missing DOCKER_HOST Environment Variable in Worker
**Status**: ⚠️ PARTIALLY RESOLVED  
**Severity**: Medium  
**Date Discovered**: 2025-06-05  
**Component**: Instance Service Worker Configuration  

### Description
The `instance-worker` service in docker-compose.dev.yml lacks the `DOCKER_HOST` environment variable, while the main `instance-service` has it properly configured.

### Root Cause
Configuration inconsistency between instance-service and instance-worker:
- `instance-service` has: `DOCKER_HOST: unix:///var/run/docker.sock`
- `instance-worker` missing this environment variable

### Impact
- Worker relies on Docker SDK's auto-detection which can be unreliable
- Potential for inconsistent behavior between main service and worker
- Docker client initialization may fail in some environments

### Files Affected
- `infrastructure/compose/docker-compose.dev.yml` (18.5KB) - Lines 335-420 (worker config section)

### Current Workaround
Docker SDK 7.1.0 auto-detection works with properly mounted socket

### Recommended Fix
Add `DOCKER_HOST: unix:///var/run/docker.sock` to instance-worker environment section

---

## Issue #3: Environment Variables Processing Bug
**Status**: 🔴 ACTIVE - BLOCKING  
**Severity**: Critical  
**Date Discovered**: 2025-06-05  
**Component**: Instance Provisioning Logic  

### Description
Instance provisioning fails during container deployment with error:
```
ValueError: dictionary update sequence element #0 has length 1; 2 is required
```

### Root Cause
Located in `/app/app/tasks/provisioning.py` at line 192:
```python
environment.update(instance['environment_vars'])
```

The code expects `instance['environment_vars']` to be a dictionary but receives incompatible data structure.

### Stack Trace
```
File "/app/app/tasks/provisioning.py", line 64, in _provision_instance_workflow
  container_info = await _deploy_odoo_container(instance, db_info)
File "/app/app/tasks/provisioning.py", line 192, in _deploy_odoo_container
  environment.update(instance['environment_vars'])
ValueError: dictionary update sequence element #0 has length 1; 2 is required
```

### Impact
- All instance provisioning fails after Docker connection is established
- Instance status shows "error" with cryptic error message
- No Odoo containers are created despite successful database provisioning

### Files Affected
- `services/instance-service/app/tasks/provisioning.py` (11.7KB) - Line 192 in `_deploy_odoo_container` function
- `services/instance-service/app/models/instance.py` (10.6KB) - InstanceCreate model definition
- Test data structure in API requests

### Debug Data
Test instance data causing the error:
```json
"environment_vars": {
    "ODOO_WORKERS": "2",
    "ODOO_MAX_CRON_THREADS": "1"
}
```

### Investigation Needed
1. Check how `environment_vars` is stored/retrieved from database
2. Verify data serialization/deserialization in database layer
3. Examine type conversion between Pydantic model and database record

---

## Issue #4: Architectural Anti-Pattern - Module Level Docker Client
**Status**: 🟡 DESIGN ISSUE  
**Severity**: Medium  
**Date Discovered**: 2025-06-05 (from audit report)  
**Component**: Async Celery Integration  

### Description
Current code uses `docker.from_env()` in function scope which is correct, but the overall pattern needs improvement for production reliability.

### Root Cause
Based on Docker SDK 6.1.3 Async Celery Compatibility analysis:
- Docker SDK is fundamentally synchronous, not designed for asyncio
- Celery multiprocessing creates isolation challenges
- Module-level Docker client initialization would fail in worker processes

### Current Implementation Status
✅ Good: Per-task client initialization  
❌ Missing: Proper async integration patterns  
❌ Missing: Thread-safe client management  
❌ Missing: Comprehensive error handling  

### Files Affected
- `services/instance-service/app/tasks/provisioning.py` (11.7KB) - All Docker operations
- `services/instance-service/app/celery_config.py` (1.2KB) - Worker configuration

### Recommended Improvements
1. Implement `asyncio.to_thread()` wrappers for Docker operations
2. Add thread-local storage for client reuse
3. Implement comprehensive retry logic
4. Consider aiodocker migration for true async support

---

## Issue #5: Database Name Validation Working Correctly
**Status**: ✅ FUNCTIONING  
**Severity**: Info  
**Date Discovered**: 2025-06-05  
**Component**: Instance Validation  

### Description
Duplicate database name validation is working properly - returned appropriate error when attempting to reuse `test_instance_001`.

### Evidence
API Response: `{"detail":"Database name 'test_instance_001' already exists for this tenant"}`

### Files Affected
- `services/instance-service/app/utils/validators.py` - Database name validation
- `services/instance-service/app/routes/instances.py` (24KB) - Validation integration

---

## Issue #6: Dependency Version Conflicts (Historical)
**Status**: ✅ RESOLVED  
**Severity**: High  
**Date Discovered**: From compatibility audit  
**Component**: Python Dependencies  

### Description
Multiple dependency layers created compatibility matrix issues:
- urllib3 conflicts with Docker SDK < 6.1.0
- requests 2.32.0+ breaks Docker SDK < 7.1.0
- Legacy versions had chunked parameter issues

### Resolution
Upgraded to stable compatibility matrix:
```
docker>=7.1.0
requests>=2.32.2  
urllib3>=2.0.2
```

### Files Affected
- `services/instance-service/requirements.txt` (381B) - All dependency versions

---

## Testing Results Summary

### ✅ Working Components
1. **API Layer**: Instance creation, validation, status retrieval
2. **Database Integration**: PostgreSQL connection, instance record creation
3. **Celery Integration**: Task queuing and worker communication  
4. **Docker SDK**: Version 7.1.0 connection and API access
5. **Health Checks**: Service availability monitoring
6. **Error Handling**: Proper error propagation and status updates

### 🔴 Blocking Issues
1. **Environment Variables Processing**: Critical bug preventing container deployment
2. **Container Provisioning**: Cannot complete instance creation workflow

### 🟡 Improvement Areas
1. **Async Integration**: Need proper asyncio patterns
2. **Error Recovery**: Missing comprehensive retry logic
3. **Resource Management**: No cleanup automation
4. **Performance**: Synchronous Docker operations in async context

---

## Next Actions Required

### Immediate (Critical Path)
1. **Fix environment_vars processing bug** - investigate data serialization issue
2. **Add DOCKER_HOST to worker config** - ensure consistent Docker access
3. **Test complete provisioning workflow** - verify end-to-end functionality

### Short Term (Reliability)
1. **Implement asyncio.to_thread() wrappers** - proper async integration
2. **Add comprehensive error handling** - retry logic and cleanup
3. **Thread-safe client management** - production reliability

### Long Term (Architecture)
1. **Evaluate aiodocker migration** - true async Docker operations  
2. **Performance optimization** - reduce blocking operations
3. **Monitoring integration** - comprehensive observability

---

## File Size Reference
- `docker-compose.dev.yml`: 18.5KB (473 lines)
- `provisioning.py`: 11.7KB (347 lines) 
- `instances.py`: 24KB (595 lines)
- `instance.py` models: 10.6KB (265 lines)
- `requirements.txt`: 381B (22 lines)
- `Dockerfile`: 1.0KB (41 lines)
- `celery_config.py`: 1.2KB (39 lines)

**Total codebase analysis**: ~67KB across 7 core files for instance service functionality.

---

## Issue #012 - KillBill/Kaui Database User Configuration

**Status**: ✅ Resolved  
**Priority**: High  
**Component**: billing-infrastructure  
**Date**: 2025-06-11  
**Reporter**: Database Permission Issues  

### Description
KillBill and Kaui services couldn't connect to databases due to custom user configuration conflicting with the killbill/mariadb image's automatic setup.

### Root Cause
- Used custom `killbill` user instead of `root` user that killbill/mariadb image expects
- killbill/mariadb:0.24 automatically creates both `killbill` and `kaui` databases with schemas
- Custom user creation variables (`MYSQL_USER`, `MYSQL_ADDITIONAL_DATABASES`) don't work with this image
- Manual permission grants were required for the custom user

### Solution Applied
Switched to reference configuration using `root` user:
- **Database**: Use only `MYSQL_ROOT_PASSWORD: killbill`
- **KillBill**: `KILLBILL_DAO_USER: root` with `KILLBILL_DAO_PASSWORD: killbill`
- **Kaui**: `KAUI_CONFIG_DAO_USER: root` with `KAUI_CONFIG_DAO_PASSWORD: killbill`

### Technical Details
killbill/mariadb image automatically:
- Creates `killbill` database with full schema (100+ tables)
- Creates `kaui` database with admin schema (4 tables)
- Only creates `root` user with default password
- Doesn't support custom user creation via environment variables

### Files Modified
- `infrastructure/compose/docker-compose.dev.yml` - Updated to use root credentials

### Verification
Both services now connect successfully with root user, eliminating permission issues.

---

## Issue #013 - Instance Status Sync Issue

**Status**: 📋 Open  
**Priority**: Medium  
**Component**: instance-service  
**Date**: 2025-06-18  
**Reporter**: Testing

### Description
Database instance status becomes out of sync with actual Docker container state.

### Problem
- Manual Docker operations (stop, start, kill) don't update database status
- Container crashes/system restarts leave database showing incorrect status  
- Database shows "running" while container is actually stopped

### Impact
- Misleading status information
- API health checks unreliable
- Potential backup/restore operations on incorrect state

### Root Cause
- No background health monitoring service
- Database only updated via API endpoints
- Missing periodic sync between database and Docker state

### Fix Needed
- Implement background health monitoring task
- Add periodic status synchronization service  
- Real-time container state change detection

---

## Issue #014 - Health Check Timeout Causes False Error Status

**Status**: 📋 Open  
**Priority**: High  
**Component**: instance-service  
**Date**: 2025-06-20  
**Reporter**: Dashboard Testing

### Description
Instance provisioning marks instances as "error" when Odoo takes longer than 120 seconds to start, even when instance eventually becomes healthy.

### Problem
- Health check timeout set to 120 seconds is too short for Odoo startup (especially with demo data)
- Once marked as "error", status never updates automatically
- Dashboard shows working instances as failed

### Example
Demo instance `33d590fb-a81f-46fe-b79a-56956c43573a`:
- Status: "error" 
- Error message: "Odoo did not start within 120 seconds"
- Container: Actually running and accessible
- Database record: Never updated from initial timeout

### Root Cause
1. **Short timeout**: 120 seconds insufficient for Odoo startup
2. **No retry mechanism**: No automatic status refresh after timeout
3. **No periodic health checks**: Status only set during initial provisioning

### Solutions Needed
1. **Increase timeout** to 300-600 seconds for initial health check
2. **Add periodic health monitoring** to update status of existing instances  
3. **Add status refresh API** for manual correction
4. **Implement retry logic** for failed health checks

--- 
 Complete TODO Comments List

  User Service (2 TODOs)

  File: services/user-service/app/services/user_service.py
  - Line 398: # TODO: Replace with billing-service API call when implemented - Replace hardcoded billing
  info with actual billing service integration
  - Line 422: # TODO: Replace with tenant-service API call when implemented - Replace hardcoded tenant
  count with actual tenant service API call

  Tenant Service (2 TODOs)

  File: services/tenant-service/app/services/tenant_service.py
  - Line 28: # TODO: Validate customer exists and is active via user-service API - Add customer
  validation by calling user-service
  - Line 33: # TODO: Check customer's subscription plan allows tenant creation - Add subscription plan
  validation for tenant limits

  Instance Service (23 TODOs)

  Route Layer - services/instance-service/app/routes/instances.py

  - Line 439: # TODO: Check actual container status and health - Replace placeholder with real container
  health checks
  - Line 471: # TODO: Implement log retrieval from container - Add Docker container log retrieval
  functionality
  - Line 577: # TODO: Implement actual container starting logic - Replace placeholder with real Docker
  start operations
  - Line 608: # TODO: Implement actual container stopping logic - Replace placeholder with real Docker
  stop operations
  - Line 633: # TODO: Implement actual container restarting logic - Replace placeholder with real Docker
  restart operations
  - Line 658: # TODO: Implement actual update logic - Implement Odoo version update functionality
  - Line 681: # TODO: Implement actual backup logic - Replace placeholder with real backup operations
  - Line 705: # TODO: Implement actual restore logic - Replace placeholder with real restore operations

  Service Layer - services/instance-service/app/services/instance_service.py

  - Line 47: # TODO: Trigger async provisioning - Add background task triggering for instance
  provisioning
  - Line 134: # TODO: Implement actual Docker container starting - Add real Docker container start
  implementation
  - Line 140: # TODO: Update instance URLs and connection info - Update database with container network
  information
  - Line 172: # TODO: Implement actual Docker container stopping - Add real Docker container stop
  implementation
  - Line 202: # TODO: Delete Docker container and volumes - Add Docker cleanup functionality
  - Line 205: # TODO: Delete Odoo database - Add PostgreSQL database deletion
  - Line 231: # TODO: Check actual container health - Replace mock health data with real container status
  - Line 241: "uptime_seconds": None, # TODO: Calculate from started_at - Calculate actual container
  uptime
  - Line 242: "container_status": "unknown", # TODO: Get from Docker - Get real Docker container status
  - Line 243: "odoo_status": "unknown", # TODO: Check Odoo health endpoint - Add Odoo application health
  check
  - Line 244: "database_status": "unknown", # TODO: Check database connectivity - Add PostgreSQL
  connectivity check
  - Line 273: # TODO: Apply resource changes to running container - Implement live container resource
  updates
  - Line 305: # TODO: Implement actual backup logic - Add real backup creation functionality
  - Line 316: "backup_id": "backup_placeholder_id" # TODO: Return actual backup ID - Return real backup
  identifiers
  - Line 324: # Private helper methods (TODO: Implement these with actual Docker operations) - General
  note about implementing Docker operations
  - Line 328: # TODO: Implement actual instance provisioning - Add real provisioning logic
  - Line 333: # TODO: Implement Docker container starting - Add Docker start implementation
  - Line 338: # TODO: Implement Docker container stopping - Add Docker stop implementation
  - Line 343: # TODO: Implement Docker resource cleanup - Add cleanup operations
  - Line 348: # TODO: Implement database deletion - Add database cleanup

  Summary by Priority

  High Priority (Core Functionality):
  - All Docker operations (start, stop, restart containers)
  - Real provisioning implementation
  - Backup/restore functionality
  - Health checks and monitoring

  Medium Priority (Service Integration):
  - User service validation in tenant service
  - Billing service integration in user service
  - Tenant service integration in user service

  Low Priority (Enhancement):
  - Container resource updates
  - Detailed health metrics
  - Log retrieval functionality

  Total: 27 TODO comments requiring implementation to complete the SaaS platform.

---

## Issue #015 - Hardcoded Plan Pricing Instead of KillBill Catalog Integration

**Status**: 📋 Open  
**Priority**: High  
**Component**: billing-service, instance-service  
**Date**: 2025-06-26  
**Reporter**: Architecture Review  

### Description
The system currently uses hardcoded plan mappings in the application code instead of fetching pricing and plan information from KillBill's native catalog system. This creates a disconnect between the billing system's source of truth and the application's pricing logic.

### Current Issues
- **Hardcoded pricing**: Plans defined in `instance-service/app/utils/billing_client.py` with fixed prices ($10/$25/$50)
- **Outdated pricing**: Current hardcoded prices don't match desired pricing ($5/$8/$10)  
- **Duplicate management**: Plan information exists in both application code and KillBill catalog
- **Inconsistent data**: Risk of pricing mismatches between KillBill and application
- **Manual updates**: Price changes require code deployment instead of catalog updates

### Root Cause
The billing integration was implemented with static plan mappings rather than dynamic catalog fetching from KillBill's catalog API endpoints.

### Current Implementation
```python
# services/instance-service/app/utils/billing_client.py
plan_mapping = {
    "development": "basic-plan-10",    # $10/month (should be $5)
    "staging": "standard-plan-25",     # $25/month (should be $8)  
    "production": "premium-plan-50"    # $50/month (should be $10)
}
```

### Desired Architecture
- **Single source of truth**: All pricing in KillBill catalog
- **Dynamic plan resolution**: Fetch plans via KillBill catalog API
- **Automatic pricing**: Price changes via KillBill admin without code changes
- **Proper trial integration**: KillBill-native trial phases (14 days $0 → recurring price)

### Required Implementation
1. **Add KillBill catalog API methods**: `get_catalog()`, `get_available_plans()`, `get_plan_details()`
2. **Create proper KillBill catalog**: Define products and plans with trial + recurring phases
3. **Replace hardcoded mapping**: Dynamic plan lookup based on instance type
4. **Update pricing enforcement**: Strict payment validation using catalog-based pricing
5. **Frontend integration**: Display real-time pricing from KillBill catalog

### Impact
- **Billing accuracy**: Ensures pricing consistency between catalog and application
- **Operational efficiency**: Price updates without code deployment
- **Scalability**: Easy addition of new plans and pricing tiers
- **Payment enforcement**: Proper validation before instance creation

### Files to Modify
- `services/billing-service/app/utils/killbill_client.py` - Add catalog methods
- `services/instance-service/app/utils/billing_client.py` - Remove hardcoded mapping  
- `services/instance-service/app/routes/instances.py` - Enhanced payment validation
- Frontend pricing components - Dynamic catalog display

### Business Requirements
- **Free Trial**: 14-day trial for all plans
- **Tier 1 (Basic)**: $5/month for development instances
- **Tier 2 (Standard)**: $8/month for staging instances  
- **Tier 3 (Premium)**: $10/month for production instances

This issue must be resolved to ensure proper billing integration and accurate pricing enforcement throughout the platform.

## Issue #011 - Password Validation Mismatch Between Frontend and Backend

**Status**: ✅ Resolved - No Issue Found  
**Priority**: Medium  
**Component**: frontend-service, user-service  
**Date**: 2025-01-15  
**Reporter**: User Testing  
**Investigated**: 2025-06-30  

### Description
Frontend password validation accepts passwords that backend rejects, creating user confusion during registration. Frontend allows passwords meeting 3/5 criteria while backend requires all 4 criteria.

### Investigation Results (2025-06-30)
**Issue description appears to be outdated.** Code analysis reveals:

- **Frontend**: Uses `isPasswordValid()` function requiring ALL 5 criteria (length + uppercase + lowercase + digit + special)
- **Backend**: Requires identical criteria with same validation rules
- **Submit button**: Properly disabled with `!isPasswordValid()` - requires all criteria, not 3/5
- **Validation logic**: Both frontend and backend use identical special character set and requirements

### Current Implementation
```javascript
// Frontend validation (Register.tsx:46-50)
const isPasswordValid = () => {
  const result = checkPasswordStrength(formData.password);
  const { checks } = result;
  return checks.length && checks.lowercase && checks.uppercase && checks.digit && checks.special;
};
```

```python
# Backend validation (shared/schemas/user.py:118-132)
if not all([has_upper, has_lower, has_digit, has_special]):
    raise ValueError('Password must contain uppercase, lowercase, digit, and special character')
```

### Root Cause
Original issue description was incorrect or the problem has been resolved in previous development cycles.

### Resolution
**No action required** - validation is properly aligned between frontend and backend. Both require all criteria for password acceptance.

### Files Investigated
- `services/frontend-service/frontend/src/pages/Register.tsx` - Password validation logic confirmed correct
- `shared/schemas/user.py` - Backend password validation requirements confirmed identical
