# Coding Standards
## Odoo SaaS Platform

**Version:** 1.0  
**Date:** December 2024

## 1. File Organization

### 1.1 Directory Structure
```
backend/
├── app.py              # Main Flask application
├── config.py           # Configuration settings
├── routes/             # API endpoints (one file per resource)
├── services/           # Business logic
├── models/             # Data models
└── utils/              # Helper functions

frontend/
├── index.html          # Main entry point
├── css/                # Stylesheets
├── js/                 # JavaScript modules
└── templates/          # HTML templates
```

### 1.2 File Naming
- **Python files**: `snake_case.py`
- **JavaScript files**: `camelCase.js`
- **CSS files**: `kebab-case.css`
- **HTML templates**: `kebab-case.html`

## 2. Python Standards

### 2.1 Import Organization
```python
# Standard library imports
import os
import sys
from datetime import datetime

# Third-party imports
from flask import Flask, request, jsonify
from kubernetes import client, config

# Local imports
from services.tenant import create_tenant
from utils.errors import APIError
```

### 2.2 Function Structure
```python
def create_tenant(subdomain, admin_email, admin_password):
    """Create a new tenant with Odoo instance
    
    Args:
        subdomain (str): Tenant subdomain
        admin_email (str): Admin email address
        admin_password (str): Admin password
        
    Returns:
        dict: Tenant creation result with status and details
        
    Raises:
        APIError: If tenant creation fails
    """
    try:
        # Implementation here
        return {"success": True, "tenant_id": tenant_id}
    except Exception as e:
        raise APIError(f"Failed to create tenant: {str(e)}", 500)
```

### 2.3 Error Handling
```python
# Always use structured error handling
try:
    result = risky_operation()
    return {"success": True, "data": result}
except SpecificException as e:
    return {"success": False, "error": str(e)}
except Exception as e:
    raise APIError(f"Unexpected error: {str(e)}", 500)
```

### 2.4 Configuration
```python
# Use environment variables for all configuration
DATABASE_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
KILLBILL_URL = os.environ.get("KILLBILL_URL")

# Provide defaults where appropriate
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
```

## 3. API Standards

### 3.1 Route Structure
```python
# routes/tenants.py
from flask import Blueprint

bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")

@bp.route("", methods=["POST"])
def create():
    """Create new tenant"""
    pass

@bp.route("/<tenant_id>", methods=["GET"])
def get(tenant_id):
    """Get tenant details"""
    pass

@bp.route("/<tenant_id>", methods=["DELETE"])
def delete(tenant_id):
    """Delete tenant"""
    pass
```

### 3.2 Response Format
```python
# Success response
{
    "success": true,
    "data": {...},
    "message": "Operation completed successfully"
}

# Error response
{
    "success": false,
    "error": "Error description",
    "code": "ERROR_CODE"
}
```

### 3.3 Input Validation
```python
@bp.route("", methods=["POST"])
def create():
    data = request.json
    
    # Validate required fields
    required_fields = ["subdomain", "admin_email", "admin_password"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                "success": False, 
                "error": f"{field} is required"
            }), 400
    
    # Process request
    result = create_tenant(**data)
    return jsonify(result), 201
```

## 4. Kubernetes Standards

### 4.1 Resource Naming
```yaml
# Use consistent naming: {resource-type}-{tenant-id}
metadata:
  name: odoo-${TENANT_ID}
  namespace: tenant-${TENANT_ID}
  labels:
    app: odoo
    tenant-id: ${TENANT_ID}
    managed-by: saas-platform
```

### 4.2 Template Variables
```yaml
# Always use ${VARIABLE_NAME} format
env:
- name: POSTGRESQL_HOST
  value: postgresql-${TENANT_ID}
- name: ODOO_EMAIL
  valueFrom:
    secretKeyRef:
      name: odoo-${TENANT_ID}
      key: admin-email
```

### 4.3 Resource Limits
```yaml
# Always specify resource requests and limits
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "1Gi"
    cpu: "1000m"
```

## 5. Database Standards

### 5.1 Supabase Table Naming
- Use `snake_case` for table names
- Use singular nouns: `tenant`, `user_profile`, `resource_usage`
- Include `created_at` and `updated_at` timestamps

### 5.2 Supabase Operations
```python
# Always handle Supabase responses consistently
def create_tenant_record(tenant_data):
    try:
        result = supabase.table("tenants").insert(tenant_data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        raise APIError(f"Database error: {str(e)}", 500)
```

## 6. Frontend Standards

### 6.1 JavaScript Structure
```javascript
// Use consistent function naming
function createTenant(tenantData) {
    return fetch('/api/tenants', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(tenantData)
    });
}

// Handle responses consistently
async function handleApiResponse(response) {
    const data = await response.json();
    if (!data.success) {
        throw new Error(data.error);
    }
    return data;
}
```

### 6.2 CSS Organization
```css
/* Use BEM methodology for CSS classes */
.tenant-card { }
.tenant-card__header { }
.tenant-card__body { }
.tenant-card--active { }

/* Use CSS custom properties for theming */
:root {
    --primary-color: #007bff;
    --secondary-color: #6c757d;
    --success-color: #28a745;
    --error-color: #dc3545;
}
```

## 7. Security Standards

### 7.1 Input Sanitization
```python
import re

def validate_subdomain(subdomain):
    """Validate subdomain format"""
    pattern = r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'
    if not re.match(pattern, subdomain):
        raise APIError("Invalid subdomain format", 400)
    return subdomain.lower()
```

### 7.2 Secrets Management
```python
# Never hardcode secrets
# Always use Kubernetes secrets or environment variables
secret_data = {
    "admin-password": base64.b64encode(password.encode()).decode(),
    "db-password": base64.b64encode(db_password.encode()).decode()
}
```

## 8. Testing Standards

### 8.1 Test File Organization
```
tests/
├── unit/               # Unit tests
├── integration/        # Integration tests
└── fixtures/           # Test data
```

### 8.2 Test Naming
```python
def test_create_tenant_success():
    """Test successful tenant creation"""
    pass

def test_create_tenant_invalid_subdomain():
    """Test tenant creation with invalid subdomain"""
    pass
```

## 9. Documentation Standards

### 9.1 Code Comments
```python
# Use docstrings for functions and classes
# Use inline comments sparingly for complex logic
# Explain WHY, not WHAT

def calculate_resource_usage(tenant_id):
    """Calculate resource usage for billing purposes
    
    This function aggregates CPU, memory, and storage usage
    over the billing period for accurate invoicing.
    """
    # Complex calculation logic here
    pass
```

### 9.2 README Structure
- Project overview
- Quick start guide
- Configuration requirements
- Deployment instructions
- Contributing guidelines

## 10. Git Standards

### 10.1 Commit Messages
```
feat: add tenant backup functionality
fix: resolve Kubernetes connection timeout
docs: update API documentation
refactor: simplify tenant provisioning logic
test: add unit tests for billing service
```

### 10.2 Branch Naming
- `feature/tenant-backup`
- `bugfix/k8s-timeout`
- `hotfix/security-patch`

---

**Remember**: Consistency is key. Follow these standards across all components of the platform to ensure maintainable, readable, and reliable code. 