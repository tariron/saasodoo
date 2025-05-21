# Coding Patterns Document
## Odoo SaaS Platform Implementation

**Version:** 1.0  
**Date:** May 20, 2025  

## 1. Project Structure

```
saasodoo
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
- Network policies to restrict cross-tenant communication
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

## 8. Network Policy Implementation

Network policies are critical for enforcing proper tenant isolation within the Kubernetes cluster. Without these policies, pods in different namespaces could potentially communicate with each other, breaking the tenant isolation model.

### 8.1 Default Deny Policy

Each tenant namespace should start with a default deny policy that blocks all ingress and egress traffic:

```yaml
# kubernetes/network-policies/default-deny.yaml.template
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

### 8.2 Internal Communications Policy

Allow pods within the same namespace to communicate with each other:

```yaml
# kubernetes/network-policies/allow-same-namespace.yaml.template
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

### 8.3 Database Access Policy

Allow only the Odoo pod to communicate with the PostgreSQL pod:

```yaml
# kubernetes/network-policies/postgres-access.yaml.template
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

### 8.4 External Access Policy

Allow inbound traffic from the Traefik ingress controller to the Odoo service:

```yaml
# kubernetes/network-policies/allow-ingress.yaml.template
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

### 8.5 DNS Access Policy

Allow pods to access DNS for name resolution:

```yaml
# kubernetes/network-policies/allow-dns.yaml.template
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

### 8.6 Implementation in Tenant Provisioning

When provisioning a new tenant, these network policies should be applied as part of the tenant creation workflow:

```python
def apply_network_policies(core_v1, networking_v1, tenant_id):
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
                print(f"Error creating network policy: {e}")
                raise
```

### 8.7 Verification of Network Policies

To verify that network policies are correctly applied, a test script should be created:

```python
# scripts/test-network-isolation.py
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

These network policies together ensure that:
1. Tenants are completely isolated from each other
2. Only the necessary communication paths within a tenant are allowed
3. External access is restricted to only what's required
4. The policies are automatically applied during tenant provisioning
5. The isolation can be verified through testing

## 9. Backup Implementation Patterns

Automated and on-demand backups are critical for SaaS platforms. This section outlines the implementation patterns for backing up tenant instances.

### 9.1 Backup Components

Each tenant backup consists of two primary components:
1. **PostgreSQL Database Backup** - Contains all tenant business data
2. **Odoo File Storage Backup** - Contains attachments, documents, and binary files

### 9.2 Scheduled Backup Implementation

```python
# services/backup.py
import os
import datetime
import kubernetes.client
import subprocess
from kubernetes import client, config

def create_scheduled_backups():
    """Create CronJobs for regular tenant backups"""
    try:
        # Load Kubernetes configuration
        config.load_kube_config()
        batch_v1 = client.BatchV1Api()
        
        # Get all tenant namespaces
        core_v1 = client.CoreV1Api()
        namespaces = core_v1.list_namespace(label_selector="managed-by=odoo-saas")
        
        for ns in namespaces.items:
            tenant_id = ns.metadata.name.replace('tenant-', '')
            
            # Create CronJob for this tenant
            create_backup_cronjob(batch_v1, tenant_id)
            
        return {"success": True, "message": "Scheduled backups created successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def create_backup_cronjob(batch_v1, tenant_id):
    """Create a CronJob for a specific tenant"""
    # Define CronJob
    cronjob = client.V1CronJob(
        api_version="batch/v1beta1",
        kind="CronJob",
        metadata=client.V1ObjectMeta(
            name=f"backup-{tenant_id}",
            namespace="saas-system"
        ),
        spec=client.V1CronJobSpec(
            schedule="0 2 * * *",  # Daily at 2 AM
            job_template=client.V1JobTemplateSpec(
                spec=client.V1JobSpec(
                    template=client.V1PodTemplateSpec(
                        spec=client.V1PodSpec(
                            containers=[
                                client.V1Container(
                                    name="backup-job",
                                    image="bitnami/kubectl:latest",
                                    command=["/bin/sh", "-c"],
                                    args=[
                                        f"""
                                        # Create backup directory
                                        TIMESTAMP=$(date +%Y%m%d-%H%M%S)
                                        BACKUP_DIR="/backups/{tenant_id}/$TIMESTAMP"
                                        mkdir -p $BACKUP_DIR
                                        
                                        # Backup PostgreSQL database
                                        kubectl exec -n tenant-{tenant_id} svc/postgresql -- \
                                          pg_dump -U postgres -d postgres | gzip > $BACKUP_DIR/db.sql.gz
                                        
                                        # Backup Odoo filestore
                                        kubectl cp tenant-{tenant_id}/$(kubectl get pods -n tenant-{tenant_id} -l app=odoo -o name | cut -d/ -f2):/opt/bitnami/odoo/data/filestore/ \
                                          $BACKUP_DIR/filestore/
                                          
                                        # Create metadata file
                                        echo "Tenant ID: {tenant_id}" > $BACKUP_DIR/metadata.txt
                                        echo "Timestamp: $TIMESTAMP" >> $BACKUP_DIR/metadata.txt
                                        echo "Backup Type: Scheduled" >> $BACKUP_DIR/metadata.txt
                                        """
                                    ],
                                    volume_mounts=[
                                        client.V1VolumeMount(
                                            name="backup-storage",
                                            mount_path="/backups"
                                        )
                                    ]
                                )
                            ],
                            restart_policy="OnFailure",
                            volumes=[
                                client.V1Volume(
                                    name="backup-storage",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name="tenant-backups-pvc"
                                    )
                                )
                            ]
                        )
                    )
                )
            )
        )
    )
    
    # Create the CronJob
    batch_v1.create_namespaced_cron_job(
        namespace="saas-system",
        body=cronjob
    )
```

### 9.3 On-Demand Backup Implementation

```python
# services/backup.py (continued)
def create_ondemand_backup(tenant_id):
    """Create an on-demand backup for a tenant"""
    try:
        # Load Kubernetes configuration
        config.load_kube_config()
        batch_v1 = client.BatchV1Api()
        
        # Create timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        
        # Create Job for backup
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=f"backup-{tenant_id}-{timestamp}",
                namespace="saas-system"
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="backup-job",
                                image="bitnami/kubectl:latest",
                                command=["/bin/sh", "-c"],
                                args=[
                                    f"""
                                    # Create backup directory
                                    BACKUP_DIR="/backups/{tenant_id}/{timestamp}"
                                    mkdir -p $BACKUP_DIR
                                    
                                    # Backup PostgreSQL database
                                    kubectl exec -n tenant-{tenant_id} svc/postgresql -- \
                                      pg_dump -U postgres -d postgres | gzip > $BACKUP_DIR/db.sql.gz
                                    
                                    # Backup Odoo filestore
                                    kubectl cp tenant-{tenant_id}/$(kubectl get pods -n tenant-{tenant_id} -l app=odoo -o name | cut -d/ -f2):/opt/bitnami/odoo/data/filestore/ \
                                      $BACKUP_DIR/filestore/
                                      
                                    # Create metadata file
                                    echo "Tenant ID: {tenant_id}" > $BACKUP_DIR/metadata.txt
                                    echo "Timestamp: {timestamp}" >> $BACKUP_DIR/metadata.txt
                                    echo "Backup Type: On-Demand" >> $BACKUP_DIR/metadata.txt
                                    """
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="backup-storage",
                                        mount_path="/backups"
                                    )
                                ]
                            )
                        ],
                        restart_policy="Never",
                        volumes=[
                            client.V1Volume(
                                name="backup-storage",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="tenant-backups-pvc"
                                )
                            )
                        ]
                    )
                ),
                backoff_limit=3
            )
        )
        
        # Create the Job
        batch_v1.create_namespaced_job(
            namespace="saas-system",
            body=job
        )
        
        return {
            "success": True, 
            "message": f"Backup started for tenant {tenant_id}",
            "backup_id": f"{tenant_id}-{timestamp}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 9.4 Backup Storage Configuration

A dedicated persistent volume should be provisioned for backups:

```yaml
# kubernetes/backup/storage.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: tenant-backups-pvc
  namespace: saas-system
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 100Gi
  storageClassName: standard
```

### 9.5 Backup Listing and Restoration

```python
# services/backup.py (continued)
def list_tenant_backups(tenant_id):
    """List all backups for a tenant"""
    try:
        # Execute command to list backups from storage
        cmd = ["ls", "-la", f"/backups/{tenant_id}"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            return {"success": False, "error": result.stderr}
        
        # Parse output to get backup timestamps
        backups = []
        for line in result.stdout.splitlines():
            if line.startswith('d') and not (line.endswith('.') or line.endswith('..')):
                # This is a directory entry, extract timestamp
                parts = line.split()
                if len(parts) >= 9:
                    timestamp = parts[8]
                    backups.append({
                        "backup_id": f"{tenant_id}-{timestamp}",
                        "timestamp": timestamp,
                        "tenant_id": tenant_id
                    })
        
        return {"success": True, "backups": backups}
    except Exception as e:
        return {"success": False, "error": str(e)}

def restore_tenant_backup(tenant_id, backup_timestamp):
    """Restore a tenant from backup"""
    try:
        # Create restore job
        config.load_kube_config()
        batch_v1 = client.BatchV1Api()
        
        restore_timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=f"restore-{tenant_id}-{restore_timestamp}",
                namespace="saas-system"
            ),
            spec=client.V1JobSpec(
                template=client.V1PodTemplateSpec(
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="restore-job",
                                image="bitnami/kubectl:latest",
                                command=["/bin/sh", "-c"],
                                args=[
                                    f"""
                                    # Check if backup exists
                                    BACKUP_DIR="/backups/{tenant_id}/{backup_timestamp}"
                                    if [ ! -d "$BACKUP_DIR" ]; then
                                        echo "Backup not found: $BACKUP_DIR"
                                        exit 1
                                    fi
                                    
                                    # Temporarily scale down Odoo deployment
                                    kubectl scale deployment odoo -n tenant-{tenant_id} --replicas=0
                                    
                                    # Restore PostgreSQL database
                                    cat $BACKUP_DIR/db.sql.gz | gunzip | kubectl exec -i -n tenant-{tenant_id} svc/postgresql -- \
                                      psql -U postgres -d postgres
                                    
                                    # Restore Odoo filestore
                                    # Wait for Odoo pod to terminate
                                    sleep 10
                                    
                                    # Scale up Odoo deployment
                                    kubectl scale deployment odoo -n tenant-{tenant_id} --replicas=1
                                    
                                    # Wait for pod to be ready
                                    kubectl wait --for=condition=Ready pod -l app=odoo -n tenant-{tenant_id} --timeout=300s
                                    
                                    # Copy filestore back
                                    kubectl cp $BACKUP_DIR/filestore/ \
                                      tenant-{tenant_id}/$(kubectl get pods -n tenant-{tenant_id} -l app=odoo -o name | cut -d/ -f2):/opt/bitnami/odoo/data/filestore/
                                      
                                    # Restart Odoo pod for changes to take effect
                                    kubectl delete pod -n tenant-{tenant_id} -l app=odoo
                                    """
                                ],
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        name="backup-storage",
                                        mount_path="/backups"
                                    )
                                ]
                            )
                        ],
                        restart_policy="Never",
                        volumes=[
                            client.V1Volume(
                                name="backup-storage",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="tenant-backups-pvc"
                                )
                            )
                        ]
                    )
                ),
                backoff_limit=2
            )
        )
        
        # Create the Job
        batch_v1.create_namespaced_job(
            namespace="saas-system",
            body=job
        )
        
        return {
            "success": True,
            "message": f"Restore started for tenant {tenant_id} from backup {backup_timestamp}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
```

### 9.6 API Endpoints for Backup Management

```python
# routes/backups.py
from flask import Blueprint, request, jsonify
from services.backup import (
    create_ondemand_backup, 
    list_tenant_backups,
    restore_tenant_backup
)

bp = Blueprint("backups", __name__, url_prefix="/api/backups")

@bp.route("/create/<tenant_id>", methods=["POST"])
def create_backup(tenant_id):
    """Create an on-demand backup for a tenant"""
    result = create_ondemand_backup(tenant_id)
    return jsonify(result)

@bp.route("/list/<tenant_id>", methods=["GET"])
def list_backups(tenant_id):
    """List all backups for a tenant"""
    result = list_tenant_backups(tenant_id)
    return jsonify(result)

@bp.route("/restore/<tenant_id>", methods=["POST"])
def restore_backup(tenant_id):
    """Restore a tenant from backup"""
    data = request.json
    backup_timestamp = data.get("backup_timestamp")
    
    if not backup_timestamp:
        return jsonify({"success": False, "error": "backup_timestamp is required"}), 400
    
    result = restore_tenant_backup(tenant_id, backup_timestamp)
    return jsonify(result)
```

### 9.7 Backup Retention Policy Implementation

A separate CronJob should be created to enforce backup retention policies:

```python
def create_backup_cleanup_job():
    """Create CronJob for cleaning up old backups"""
    try:
        # Load Kubernetes configuration
        config.load_kube_config()
        batch_v1 = client.BatchV1Api()
        
        # Define CronJob
        cronjob = client.V1CronJob(
            api_version="batch/v1beta1",
            kind="CronJob",
            metadata=client.V1ObjectMeta(
                name="backup-cleanup",
                namespace="saas-system"
            ),
            spec=client.V1CronJobSpec(
                schedule="0 3 * * *",  # Daily at 3 AM
                job_template=client.V1JobTemplateSpec(
                    spec=client.V1JobSpec(
                        template=client.V1PodTemplateSpec(
                            spec=client.V1PodSpec(
                                containers=[
                                    client.V1Container(
                                        name="cleanup-job",
                                        image="bitnami/kubectl:latest",
                                        command=["/bin/sh", "-c"],
                                        args=[
                                            """
                                            # Retain last 7 daily backups
                                            find /backups -mindepth 2 -maxdepth 2 -type d | sort -r | awk 'NR>7' | xargs -r rm -rf
                                            """
                                        ],
                                        volume_mounts=[
                                            client.V1VolumeMount(
                                                name="backup-storage",
                                                mount_path="/backups"
                                            )
                                        ]
                                    )
                                ],
                                restart_policy="OnFailure",
                                volumes=[
                                    client.V1Volume(
                                        name="backup-storage",
                                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                            claim_name="tenant-backups-pvc"
                                        )
                                    )
                                ]
                            )
                        )
                    )
                )
            )
        )
        
        # Create the CronJob
        batch_v1.create_namespaced_cron_job(
            namespace="saas-system",
            body=cronjob
        )
        
        return {"success": True, "message": "Backup cleanup job created successfully"}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

The backup system provides:
1. Automatic daily backups of all tenant instances
2. On-demand backups through API
3. Backup listing and restoration capabilities
4. Simple retention policy (last 7 backups)
5. Comprehensive backup of both database and file storage