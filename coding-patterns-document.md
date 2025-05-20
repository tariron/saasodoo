# Coding Patterns Document
## Odoo SaaS Platform Implementation

**Version:** 1.0  
**Date:** May 20, 2025  

## 1. Project Structure

```
odoo-saas-kit/
├── backend/                # Flask application
│   ├── app.py              # Main Flask application
│   ├── config.py           # Configuration
│   ├── models/             # Data models
│   ├── routes/             # API endpoints
│   │   ├── auth.py         # Authentication routes
│   │   ├── tenants.py      # Tenant management routes
│   │   └── admin.py        # Admin routes
│   ├── services/           # Business logic
│   │   ├── kubernetes.py   # Kubernetes operations
│   │   ├── tenant.py       # Tenant provisioning
│   │   └── monitoring.py   # Resource monitoring
│   └── utils/              # Utilities and helpers
├── frontend/               # Simple UI
│   ├── index.html          # Landing page
│   ├── css/                # Stylesheets
│   ├── js/                 # JavaScript files
│   └── templates/          # HTML templates
├── kubernetes/             # K8s templates
│   ├── traefik/            # Traefik configuration
│   ├── odoo/               # Odoo templates
│   │   ├── deployment.yaml.template
│   │   ├── service.yaml.template
│   │   └── ingress.yaml.template
│   ├── postgres/           # PostgreSQL templates
│   │   ├── deployment.yaml.template
│   │   ├── service.yaml.template
│   │   └── storage.yaml.template
│   └── namespace.yaml.template
└── scripts/                # Helper scripts
    ├── setup.sh            # Environment setup
    ├── deploy.sh           # Deployment script
    └── test-distribution.py # Node distribution test
```

## 2. Flask Application Patterns

### 2.1 Simplified Flask App Structure

```python
# app.py
from flask import Flask
from flask_cors import CORS
from routes import auth, tenants, admin

app = Flask(__name__)
CORS(app)

# Register routes
app.register_blueprint(auth.bp)
app.register_blueprint(tenants.bp)
app.register_blueprint(admin.bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

```python
# routes/tenants.py
from flask import Blueprint, request, jsonify
from services.tenant import create_tenant, get_tenant, delete_tenant

bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")

@bp.route("", methods=["POST"])
def create():
    data = request.json
    result = create_tenant(
        subdomain=data["subdomain"],
        admin_email=data["admin_email"],
        admin_password=data["admin_password"]
    )
    return jsonify(result), 201

@bp.route("/<tenant_id>", methods=["GET"])
def get(tenant_id):
    tenant = get_tenant(tenant_id)
    return jsonify(tenant)

@bp.route("/<tenant_id>", methods=["DELETE"])
def delete(tenant_id):
    result = delete_tenant(tenant_id)
    return jsonify(result)
```

### 2.2 Supabase Authentication Integration

```python
# services/auth.py
import os
from supabase import create_client, Client

# Initialize Supabase client
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_KEY")
)

def register_user(email, password):
    """Register a new user with Supabase"""
    try:
        response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        return {"success": True, "user_id": response.user.id}
    except Exception as e:
        return {"success": False, "error": str(e)}

def login_user(email, password):
    """Login a user with Supabase"""
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        return {
            "success": True, 
            "access_token": response.session.access_token,
            "user_id": response.user.id
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## 3. Kubernetes Integration Patterns

### 3.1 Kubernetes Client Setup

```python
# services/kubernetes.py
from kubernetes import client, config
import os

def get_k8s_client():
    """Get Kubernetes API client"""
    try:
        # Try loading from kube config first
        config.load_kube_config()
    except:
        # If running in cluster, use in-cluster config
        config.load_incluster_config()
    
    return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()
```

### 3.2 Tenant Provisioning Pattern

```python
# services/tenant.py
import os
import yaml
import string
import random
from services.kubernetes import get_k8s_client

def create_tenant(subdomain, admin_email, admin_password):
    """Create a new tenant with Odoo instance"""
    # Generate tenant ID from subdomain
    tenant_id = subdomain.lower().replace('.', '-')
    
    # Get Kubernetes clients
    core_v1, apps_v1, networking_v1 = get_k8s_client()
    
    # Create namespace
    create_namespace(core_v1, tenant_id)
    
    # Create PostgreSQL
    db_password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    create_postgres(core_v1, apps_v1, tenant_id, db_password)
    
    # Create Odoo
    create_odoo(core_v1, apps_v1, networking_v1, tenant_id, subdomain, 
                admin_email, admin_password, db_password)
    
    return {
        "tenant_id": tenant_id,
        "subdomain": subdomain,
        "status": "creating",
        "url": f"https://{subdomain}.example.com"
    }

def create_namespace(core_v1, tenant_id):
    """Create a namespace for the tenant"""
    with open("kubernetes/namespace.yaml.template", "r") as f:
        namespace_yaml = f.read()
    
    namespace_yaml = namespace_yaml.replace("${TENANT_ID}", tenant_id)
    namespace = yaml.safe_load(namespace_yaml)
    
    try:
        core_v1.create_namespace(body=namespace)
    except client.exceptions.ApiException as e:
        if e.status != 409:  # Ignore if namespace already exists
            raise

def create_postgres(core_v1, apps_v1, tenant_id, db_password):
    """Create PostgreSQL for tenant"""
    # Create Secret for PostgreSQL password
    secret_data = {
        "postgresql-password": db_password.encode("utf-8").hex(),
        "postgresql-postgres-password": db_password.encode("utf-8").hex(),
    }
    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(
            name="postgresql",
            namespace=f"tenant-{tenant_id}"
        ),
        type="Opaque",
        data=secret_data
    )
    core_v1.create_namespaced_secret(
        namespace=f"tenant-{tenant_id}",
        body=secret
    )
    
    # Create PVC, Deployment, and Service from templates
    # (Using the same pattern of reading templates, replacing variables, and applying)

def create_odoo(core_v1, apps_v1, networking_v1, tenant_id, subdomain, 
               admin_email, admin_password, db_password):
    """Create Odoo instance for tenant"""
    # Create Secret for Odoo
    secret_data = {
        "odoo-password": admin_password.encode("utf-8").hex(),
        "odoo-email": admin_email.encode("utf-8").hex(),
        "postgresql-password": db_password.encode("utf-8").hex(),
    }
    secret = client.V1Secret(
        metadata=client.V1ObjectMeta(
            name="odoo",
            namespace=f"tenant-{tenant_id}"
        ),
        type="Opaque",
        data=secret_data
    )
    core_v1.create_namespaced_secret(
        namespace=f"tenant-{tenant_id}",
        body=secret
    )
    
    # Create Deployment, Service, and Ingress from templates
    # (Using the same pattern of reading templates, replacing variables, and applying)
```

## 4. Kubernetes Resource Templates

### 4.1 Namespace Template

```yaml
# kubernetes/namespace.yaml.template
apiVersion: v1
kind: Namespace
metadata:
  name: tenant-${TENANT_ID}
  labels:
    tenant-id: ${TENANT_ID}
    managed-by: odoo-saas
```

### 4.2 Odoo Deployment Template

```yaml
# kubernetes/odoo/deployment.yaml.template
apiVersion: apps/v1
kind: Deployment
metadata:
  name: odoo
  namespace: tenant-${TENANT_ID}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: odoo
  template:
    metadata:
      labels:
        app: odoo
        tenant-id: ${TENANT_ID}
    spec:
      # Pod anti-affinity for node distribution
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: tenant-id
                  operator: In
                  values:
                  - ${TENANT_ID}
              topologyKey: "kubernetes.io/hostname"
      containers:
      - name: odoo
        image: bitnami/odoo:16
        ports:
        - containerPort: 8069
        env:
        - name: ODOO_EMAIL
          valueFrom:
            secretKeyRef:
              name: odoo
              key: odoo-email
        - name: ODOO_PASSWORD
          valueFrom:
            secretKeyRef:
              name: odoo
              key: odoo-password
        - name: POSTGRESQL_HOST
          value: postgresql
        - name: POSTGRESQL_PORT
          value: "5432"
        - name: POSTGRESQL_PASSWORD
          valueFrom:
            secretKeyRef:
              name: odoo
              key: postgresql-password
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        readinessProbe:
          httpGet:
            path: /web/login
            port: 8069
          initialDelaySeconds: 30
          periodSeconds: 10
```

### 4.3 Ingress Template

```yaml
# kubernetes/odoo/ingress.yaml.template
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: odoo
  namespace: tenant-${TENANT_ID}
  annotations:
    kubernetes.io/ingress.class: traefik
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
spec:
  rules:
  - host: ${SUBDOMAIN}.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: odoo
            port:
              number: 8069
```

## 5. Error Handling Patterns

### 5.1 Structured API Errors

```python
# utils/errors.py
class APIError(Exception):
    """Base API error class"""
    def __init__(self, message, status_code=400, payload=None):
        self.message = message
        self.status_code = status_code
        self.payload = payload
        super().__init__(self.message)

    def to_dict(self):
        rv = dict(self.payload or {})
        rv['message'] = self.message
        rv['status'] = 'error'
        return rv

# Error handler for Flask
@app.errorhandler(APIError)
def handle_api_error(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response
```

### 5.2 Service Error Handling

```python
# services/tenant.py
def get_tenant(tenant_id):
    """Get tenant details"""
    try:
        core_v1, _, _ = get_k8s_client()
        
        # Check if namespace exists
        try:
            namespace = core_v1.read_namespace(f"tenant-{tenant_id}")
        except client.exceptions.ApiException as e:
            if e.status == 404:
                raise APIError(f"Tenant {tenant_id} not found", 404)
            raise APIError(f"Kubernetes API error: {str(e)}", 500)
        
        # Get pod status
        try:
            pods = core_v1.list_namespaced_pod(f"tenant-{tenant_id}")
            pod_statuses = [pod.status.phase for pod in pods.items]
            
            if all(status == "Running" for status in pod_statuses):
                status = "running"
            elif any(status == "Failed" for status in pod_statuses):
                status = "error"
            else:
                status = "creating"
        except client.exceptions.ApiException:
            status = "unknown"
        
        return {
            "tenant_id": tenant_id,
            "status": status,
            "url": f"https://{tenant_id}.example.com",
            "created_at": namespace.metadata.creation_timestamp
        }
    except APIError:
        raise
    except Exception as e:
        raise APIError(f"Failed to get tenant: {str(e)}", 500)
```

## 6. Testing Patterns

### 6.1 Node Distribution Testing

```python
# scripts/test-distribution.py
from kubernetes import client, config
import os
import sys

def test_node_distribution():
    """Test tenant distribution across nodes"""
    try:
        # Load Kubernetes configuration
        config.load_kube_config()
        
        # Create API client
        v1 = client.CoreV1Api()
        
        # Get all pods with label selector
        pods = v1.list_pod_for_all_namespaces(label_selector="app=odoo")
        
        # Track node distribution
        node_distribution = {}
        
        for pod in pods.items:
            node = pod.spec.node_name
            tenant = pod.metadata.namespace
            
            if node not in node_distribution:
                node_distribution[node] = []
            
            node_distribution[node].append(tenant)
        
        # Print distribution
        print("Tenant Distribution Across Nodes:")
        print("================================")
        
        for node, tenants in node_distribution.items():
            print(f"Node: {node} - {len(tenants)} tenants")
            for tenant in tenants:
                print(f"  - {tenant}")
        
        return True
    except Exception as e:
        print(f"Error testing node distribution: {str(e)}")
        return False

if __name__ == "__main__":
    sys.exit(0 if test_node_distribution() else 1)
```

### 6.2 Resource Usage Monitoring

```python
# services/monitoring.py
import os
from kubernetes import client, config

def get_tenant_resource_usage(tenant_id):
    """Get resource usage for a tenant"""
    try:
        # Load Kubernetes configuration
        config.load_kube_config()
        
        # Create API client
        v1 = client.CoreV1Api()
        
        # Get metrics API client
        metrics_api = client.CustomObjectsApi()
        
        # Get pod metrics for namespace
        pod_metrics = metrics_api.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=f"tenant-{tenant_id}",
            plural="pods"
        )
        
        # Calculate total CPU and memory usage
        total_cpu = 0
        total_memory = 0
        
        for pod in pod_metrics.get('items', []):
            for container in pod.get('containers', []):
                cpu = container.get('usage', {}).get('cpu', '0')
                memory = container.get('usage', {}).get('memory', '0')
                
                # Convert CPU cores
                if cpu.endswith('n'):
                    cpu_cores = float(cpu[:-1]) / 1000000000
                elif cpu.endswith('u'):
                    cpu_cores = float(cpu[:-1]) / 1000000
                elif cpu.endswith('m'):
                    cpu_cores = float(cpu[:-1]) / 1000
                else:
                    cpu_cores = float(cpu)
                
                # Convert memory
                if memory.endswith('Ki'):
                    memory_mb = float(memory[:-2]) / 1024
                elif memory.endswith('Mi'):
                    memory_mb = float(memory[:-2])
                elif memory.endswith('Gi'):
                    memory_mb = float(memory[:-2]) * 1024
                else:
                    memory_mb = float(memory) / (1024 * 1024)
                
                total_cpu += cpu_cores
                total_memory += memory_mb
        
        return {
            "tenant_id": tenant_id,
            "cpu_usage": round(total_cpu, 3),
            "memory_usage_mb": round(total_memory, 1)
        }
    except Exception as e:
        return {
            "tenant_id": tenant_id,
            "error": str(e)
        }
```

## 7. Best Practices

### 7.1 Tenant Isolation

- Each tenant gets its own namespace
- Dedicated PostgreSQL instance per tenant
- Network policies to restrict cross-tenant access
- Resource quotas to prevent resource starvation
- Randomized secure credentials for each tenant

### 7.2 Configuration Management

- Use environment variables for credentials
- Store templates in version control
- Keep configuration separated from code
- Use Kubernetes secrets for sensitive data

### 7.3 Code Maintainability

- Follow clear separation of concerns:
  - Routes for API endpoints
  - Services for business logic
  - Utils for helper functions
- Keep functions small and focused
- Use consistent error handling
- Add comments for complex operations

### 7.4 Security Considerations

- Never expose the Kubernetes API directly
- Always validate user input
- Use HTTPS for all external connections
- Store credentials in Kubernetes secrets
- Implement proper authentication with Supabase
- Apply principle of least privilege for service accounts