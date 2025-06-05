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

Last Updated: 2025-06-02 