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

## Issue Backlog

### Planned Issues to Address

**Issue #003 - Missing Tenant Service**  
**Status**: 📋 Planned  
**Priority**: High  
**Component**: tenant-service  
**Description**: Need to implement tenant-service to manage Odoo instance lifecycle and provide APIs for tenant operations.

**Issue #004 - Missing Billing Service**  
**Status**: 📋 Planned  
**Priority**: Medium  
**Component**: billing-service  
**Description**: Need to implement billing-service to manage subscriptions and payment processing for Zimbabwe market (PayNow, EcoCash).

**Issue #005 - Service Communication Pattern**  
**Status**: 📋 Planned  
**Priority**: Medium  
**Component**: Architecture  
**Description**: Establish proper service-to-service communication patterns and replace direct database queries with API calls.

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