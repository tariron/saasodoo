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