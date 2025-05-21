# Implementation Plan
## Odoo SaaS Platform Weekend Project

**Version:** 1.0  
**Date:** May 20, 2025  

## 1. Pre-Weekend Preparation

### 1.1 Prerequisites

- Windows machine with Docker Desktop installed
- Windows machine for multi-node testing
- Ubuntu 24.10 server prepared for production
- Domain name with DNS access
- Supabase account created

### 1.2 Environment Setup on Windows

1. Install MicroK8s:
   - Download from https://microk8s.io/docs/install-windows
   - Follow installation instructions
   - Enable required addons:
     ```bash
     microk8s enable dns ingress metrics-server storage
     ```

2. Set up kubectl:
   ```bash
   mkdir -p ~/.kube
   microk8s config > ~/.kube/config
   ```

3. Install Python dependencies:
   ```bash
   pip install flask flask-cors pyyaml kubernetes supabase
   ```

## 2. Weekend Implementation Timeline

### 2.1 Saturday Morning (4 hours): Core Infrastructure

| Time | Task | Details |
|------|------|---------|
| 9:00 - 9:30 | Project structure setup | Create directory structure, initialize git repo |
| 9:30 - 10:30 | MicroK8s setup | Configure MicroK8s, enable addons, test connectivity |
| 10:30 - 12:00 | Traefik configuration | Set up Traefik ingress, configure for subdomains |
| 12:00 - 13:00 | Kubernetes templates | Create base templates for namespace, Odoo, PostgreSQL |

### 2.2 Saturday Afternoon (4 hours): Core Services

| Time | Task | Details |
|------|------|---------|
| 14:00 - 15:00 | Supabase integration | Set up Supabase client, auth endpoints |
| 15:00 - 16:30 | Tenant provisioning | Implement tenant creation service |
| 16:30 - 18:00 | Flask API setup | Create basic API endpoints for tenants |

### 2.3 Saturday Evening (4 hours): Frontend & Testing

| Time | Task | Details |
|------|------|---------|
| 19:00 - 20:30 | Simple frontend | Create basic UI for registration and tenant creation |
| 20:30 - 21:30 | Testing core functionality | Test tenant creation, Odoo access |
| 21:30 - 23:00 | Multi-node setup | Configure second Windows machine for testing |

### 2.4 Sunday Morning (4 hours): Advanced Features

| Time | Task | Details |
|------|------|---------|
| 9:00 - 10:00 | Resource monitoring | Implement resource usage monitoring |
| 10:00 - 11:00 | Node distribution | Implement pod anti-affinity, distribution testing |
| 11:00 - 13:00 | Admin dashboard | Create admin interface for tenant management |

### 2.5 Sunday Afternoon (4 hours): Polishing & Deployment

| Time | Task | Details |
|------|------|---------|
| 14:00 - 15:00 | Error handling | Improve error handling and user feedback |
| 15:00 - 16:00 | Security hardening | Review security, ensure proper isolation |
| 16:00 - 18:00 | Production deployment | Deploy to Ubuntu 24.10 server |

### 2.6 Sunday Evening (4 hours): Final Testing & Documentation

| Time | Task | Details |
|------|------|---------|
| 19:00 - 20:00 | Final testing | End-to-end testing of all features |
| 20:00 - 21:00 | Bug fixes | Address any remaining issues |
| 21:00 - 23:00 | Documentation | Document usage, API endpoints, deployment |

## 3. Detailed Implementation Tasks

### 3.1 Core Infrastructure Setup

```bash
# Clone your repo or create from scratch
mkdir -p odoo-saas-kit
cd odoo-saas-kit

# Create directory structure
mkdir -p backend/{models,routes,services,utils}
mkdir -p frontend/{css,js,templates}
mkdir -p kubernetes/{traefik,odoo,postgres,network-policies}
mkdir -p scripts

# Initialize git
git init
echo "# Odoo SaaS Kit" > README.md
git add README.md
git commit -m "Initial commit"

# Configure MicroK8s
microk8s status
microk8s enable dns ingress metrics-server storage
microk8s kubectl get nodes
```

#### 3.1.1 Traefik Configuration

Create `kubernetes/traefik/values.yaml`:
```yaml
providers:
  kubernetesCRD:
    enabled: true
  kubernetesIngress:
    enabled: true

ports:
  web:
    redirectTo: websecure
  websecure:
    tls:
      enabled: true

ingressRoute:
  dashboard:
    enabled: true
```

Create `kubernetes/traefik/install.sh`:
```bash
#!/bin/bash
# Add Traefik Helm repo
microk8s kubectl create namespace traefik
microk8s helm repo add traefik https://helm.traefik.io/traefik
microk8s helm repo update
microk8s helm install traefik traefik/traefik -n traefik -f values.yaml
```

### 3.2 Kubernetes Templates Creation

Create base templates in `kubernetes/` directory:

- `namespace.yaml.template`: Template for tenant namespace
- `postgres/deployment.yaml.template`: PostgreSQL deployment
- `postgres/service.yaml.template`: PostgreSQL service
- `postgres/storage.yaml.template`: PostgreSQL storage
- `odoo/deployment.yaml.template`: Odoo deployment
- `odoo/service.yaml.template`: Odoo service
- `odoo/ingress.yaml.template`: Odoo ingress

#### 3.2.1 Network Policy Templates

Create the following network policy templates in `kubernetes/network-policies/`:

- `default-deny.yaml.template`: Blocks all ingress/egress by default
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny
  namespace: tenant-${TENANT_ID}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

- `allow-same-namespace.yaml.template`: Allow pods in same namespace to communicate
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace
  namespace: tenant-${TENANT_ID}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector: {}
```

- `postgres-access.yaml.template`: Only allow Odoo pods to access PostgreSQL
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-access
  namespace: tenant-${TENANT_ID}
spec:
  podSelector:
    matchLabels:
      app: postgresql
  policyTypes:
  - Ingress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: odoo
    ports:
    - protocol: TCP
      port: 5432
```

- `allow-ingress.yaml.template`: Allow Traefik to access Odoo pods
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress
  namespace: tenant-${TENANT_ID}
spec:
  podSelector:
    matchLabels:
      app: odoo
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: traefik
    ports:
    - protocol: TCP
      port: 8069
```

- `allow-dns.yaml.template`: Allow DNS resolution
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: tenant-${TENANT_ID}
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
    ports:
    - protocol: UDP
      port: 53
    - protocol: TCP
      port: 53
```

### 3.3 Backend Implementation

Create `backend/app.py`:
```python
from flask import Flask, jsonify
from flask_cors import CORS
import os

# Import blueprints
from routes.auth import auth_bp
from routes.tenants import tenants_bp
from routes.admin import admin_bp

# Create Flask app
app = Flask(__name__)
CORS(app)

# Register blueprints
app.register_blueprint(auth_bp, url_prefix='/api/auth')
app.register_blueprint(tenants_bp, url_prefix='/api/tenants')
app.register_blueprint(admin_bp, url_prefix='/api/admin')

# Error handling
from utils.errors import APIError

@app.errorhandler(APIError)
def handle_api_error(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

# Root endpoint
@app.route('/')
def home():
    return jsonify({"status": "ok", "service": "Odoo SaaS Platform API"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
```

#### 3.3.1 Network Policy Service Implementation

Create `backend/services/network_policies.py`:
```python
import yaml
from kubernetes import client

def apply_network_policies(networking_v1, tenant_id):
    """Apply network policies to tenant namespace"""
    network_policy_templates = [
        "kubernetes/network-policies/default-deny.yaml.template",
        "kubernetes/network-policies/allow-same-namespace.yaml.template",
        "kubernetes/network-policies/postgres-access.yaml.template",
        "kubernetes/network-policies/allow-ingress.yaml.template",
        "kubernetes/network-policies/allow-dns.yaml.template",
    ]
    
    for template_path in network_policy_templates:
        with open(template_path, "r") as f:
            policy_yaml = f.read()
        
        # Replace template variables
        policy_yaml = policy_yaml.replace("${TENANT_ID}", tenant_id)
        policy = yaml.safe_load(policy_yaml)
        
        # Apply the network policy
        try:
            networking_v1.create_namespaced_network_policy(
                namespace=f"tenant-{tenant_id}",
                body=policy
            )
        except client.exceptions.ApiException as e:
            if e.status != 409:  # Ignore if policy already exists
                raise
```

Update `backend/services/tenant.py` to integrate network policies:
```python
# ... existing imports ...
from services.network_policies import apply_network_policies

def create_tenant(subdomain, admin_email, admin_password, resource_tier="basic"):
    """Create a new tenant with Odoo instance"""
    # Generate tenant ID from subdomain
    tenant_id = subdomain.lower().replace('.', '-')
    
    # Get Kubernetes clients
    core_v1, apps_v1, networking_v1 = get_k8s_client()
    
    # Create namespace
    create_namespace(core_v1, tenant_id)
    
    # Apply resource quotas based on tier
    apply_resource_quotas(core_v1, tenant_id, resource_tier)
    
    # Create PostgreSQL
    db_password = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
    create_postgres(core_v1, apps_v1, tenant_id, db_password)
    
    # Create Odoo
    create_odoo(core_v1, apps_v1, networking_v1, tenant_id, subdomain, 
                admin_email, admin_password, db_password)
    
    # Apply network policies for tenant isolation
    apply_network_policies(networking_v1, tenant_id)
    
    return {
        "tenant_id": tenant_id,
        "subdomain": subdomain,
        "status": "creating",
        "url": f"https://{subdomain}.example.com"
    }

# ... rest of the file ...
```

### 3.4 Frontend Implementation

Create `frontend/index.html` for the landing page, and other templates:
- `frontend/templates/login.html`: Login page
- `frontend/templates/register.html`: Registration page
- `frontend/templates/dashboard.html`: User dashboard
- `frontend/templates/admin.html`: Admin dashboard

### 3.5 Multi-Node Testing Setup

```bash
# On the first Windows machine
microk8s add-node

# This will output a command like:
# microk8s join 192.168.1.101:25000/abcdefghijklmnopqrstuvwxyz

# Run this command on the second Windows machine
microk8s join 192.168.1.101:25000/abcdefghijklmnopqrstuvwxyz

# Verify nodes on the first machine
microk8s kubectl get nodes
```

### 3.6 Production Deployment

Create `scripts/deploy.sh`:
```bash
#!/bin/bash
# Deploy to production Ubuntu 24.10 server

# Copy files to server
rsync -av --exclude=".git" --exclude="__pycache__" . ubuntu@your-server:/opt/odoo-saas-kit

# SSH to server and perform installation
ssh ubuntu@your-server << 'EOF'
  cd /opt/odoo-saas-kit

  # Install MicroK8s
  sudo snap install microk8s --classic
  sudo usermod -a -G microk8s ubuntu
  sudo chown -R ubuntu ~/.kube
  
  # Wait for MicroK8s to start
  microk8s status --wait-ready
  
  # Enable required addons
  microk8s enable dns ingress metrics-server storage
  
  # Set up kubectl
  mkdir -p ~/.kube
  microk8s config > ~/.kube/config
  
  # Install Traefik
  cd kubernetes/traefik
  bash install.sh
  cd ../..
  
  # Install Python dependencies
  pip install flask flask-cors pyyaml kubernetes supabase gunicorn
  
  # Start the backend service
  cd backend
  nohup gunicorn -b 0.0.0.0:5000 app:app &
EOF
```

### 3.7 Network Policy Testing

Create `scripts/test-network-isolation.py`:
```python
from kubernetes import client, config
import subprocess
import sys

def test_network_isolation(tenant1_id, tenant2_id):
    """Test that tenants are properly isolated"""
    config.load_kube_config()
    v1 = client.CoreV1Api()
    
    # Get a pod from tenant1
    tenant1_pods = v1.list_namespaced_pod(namespace=f"tenant-{tenant1_id}")
    tenant2_pods = v1.list_namespaced_pod(namespace=f"tenant-{tenant2_id}")
    
    if not tenant1_pods.items or not tenant2_pods.items:
        print("Error: Could not find pods in both tenant namespaces")
        return False
    
    tenant1_pod = tenant1_pods.items[0].metadata.name
    tenant2_pod = tenant2_pods.items[0].metadata.name
    
    # Try to access tenant2's PostgreSQL from tenant1
    cmd = [
        "kubectl", "exec", "-n", f"tenant-{tenant1_id}", tenant1_pod, "--",
        "nc", "-zv", f"postgresql.tenant-{tenant2_id}.svc.cluster.local", "5432"
    ]
    
    print(f"Testing isolation between tenant-{tenant1_id} and tenant-{tenant2_id}...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True)
    
    # If network policies are working correctly, this should fail
    if result.returncode != 0:
        print("✅ Network policies are correctly enforcing isolation")
        return True
    else:
        print("❌ Network policies are NOT correctly enforcing isolation")
        print(f"Output: {result.stdout.decode()}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test-network-isolation.py <tenant1_id> <tenant2_id>")
        sys.exit(1)
    
    tenant1_id = sys.argv[1]
    tenant2_id = sys.argv[2]
    sys.exit(0 if test_network_isolation(tenant1_id, tenant2_id) else 1)
```

## 4. Testing Procedures

### 4.1 Tenant Creation Testing

1. Register a new user
2. Log in to the dashboard
3. Create a new Odoo instance
4. Verify instance creation status
5. Access the Odoo instance using provided URL
6. Log in with admin credentials
7. Test basic Odoo functionality

### 4.2 Multi-Node Distribution Testing

1. Create multiple tenants (at least 5)
2. Run the node distribution test script:
   ```bash
   python scripts/test-distribution.py
   ```
3. Verify tenants are distributed across both nodes
4. Check resource usage for each tenant

### 4.3 Production Deployment Testing

1. Deploy to Ubuntu 24.10 server
2. Verify all services are running
3. Test tenant creation in production
4. Test Odoo instance access
5. Verify proper subdomain routing
6. Test admin dashboard functionality

## 5. Challenges and Contingency Plans

| Challenge | Impact | Contingency Plan |
|-----------|--------|------------------|
| Traefik subdomain routing issues | High | Fallback to path-based routing (`example.com/tenant-id/`) |
| MicroK8s networking on Windows | Medium | Use port forwarding instead of ingress, or test on Ubuntu VM |
| Supabase authentication issues | Medium | Implement simple JWT authentication as backup |
| Kubernetes resource constraints | Medium | Reduce resource requests/limits or add more nodes |
| DNS propagation delays | Low | Use local `/etc/hosts` file for testing |

## 6. Post-Weekend Enhancements

Once the MVP is working, consider these quick enhancements:

1. **14-day Trial Implementation**:
   - Add expiration timestamp to tenant namespace
   - Create daily job to check for expired trials
   - Implement payment form for conversion

2. **Simple Backup Solution**:
   - Create a script to backup PostgreSQL databases
   - Add backup button to admin dashboard
   - Store backups in a persistent volume

3. **Monitoring Dashboard**:
   - Enhance resource monitoring with graphs
   - Add email alerts for resource limits
   - Implement simple log viewing

4. **Custom Domain Support**:
   - Allow users to enter custom domain
   - Create verification process
   - Update ingress configuration

## 7. Resources and References

- MicroK8s Documentation: https://microk8s.io/docs
- Kubernetes Python Client: https://github.com/kubernetes-client/python
- Traefik Documentation: https://doc.traefik.io/traefik/
- Bitnami Odoo: https://github.com/bitnami/containers/tree/main/bitnami/odoo
- Supabase Documentation: https://supabase.io/docs
- Flask Documentation: https://flask.palletsprojects.com/