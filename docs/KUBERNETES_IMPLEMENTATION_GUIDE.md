# Kubernetes Implementation Guide
## Comprehensive Step-by-Step Implementation with Code Examples

This guide provides detailed implementation instructions for migrating from Docker Swarm to K3s Kubernetes, with special focus on the instance-service code changes.

---

## Table of Contents
1. [Phase 1: Infrastructure Setup](#phase-1-infrastructure-setup)
2. [Phase 2: Supporting Services](#phase-2-supporting-services)
3. [Phase 3: Microservices Migration](#phase-3-microservices-migration)
4. [Phase 4: Instance Service Kubernetes Integration](#phase-4-instance-service-kubernetes-integration)
5. [Phase 5: Helm Charts](#phase-5-helm-charts)
6. [Phase 6: Testing & Validation](#phase-6-testing--validation)

---

## Phase 1: Infrastructure Setup

### Step 1.1: Install K3s Cluster

**Install K3s on control plane nodes (3 nodes for HA):**

```bash
# On first control plane node (node1)
curl -sfL https://get.k3s.io | sh -s - server \
  --cluster-init \
  --token="my-super-secret-token" \
  --tls-san=k3s-api.yourdomain.com \
  --write-kubeconfig-mode=644

# Save the K3s token for other nodes
sudo cat /var/lib/rancher/k3s/server/token

# On second control plane node (node2)
curl -sfL https://get.k3s.io | sh -s - server \
  --server https://node1:6443 \
  --token="my-super-secret-token" \
  --tls-san=k3s-api.yourdomain.com

# On third control plane node (node3)
curl -sfL https://get.k3s.io | sh -s - server \
  --server https://node1:6443 \
  --token="my-super-secret-token" \
  --tls-san=k3s-api.yourdomain.com
```

**Install K3s on worker nodes:**

```bash
# Get node-token from control plane
# On control plane: sudo cat /var/lib/rancher/k3s/server/node-token

# On each worker node
curl -sfL https://get.k3s.io | K3S_URL=https://node1:6443 \
  K3S_TOKEN="your-node-token" sh -
```

**Test:**
```bash
kubectl get nodes
# Should show all nodes as Ready

kubectl get pods -n kube-system
# Should show traefik pod running
```

---

### Step 1.2: Configure Rook-Ceph for CephFS

**Install Rook Operator:**

```bash
# Clone Rook repository
git clone --single-branch --branch v1.12.0 https://github.com/rook/rook.git
cd rook/deploy/examples

# Install Rook operator
kubectl create -f crds.yaml
kubectl create -f common.yaml
kubectl create -f operator.yaml

# Verify operator is running
kubectl -n rook-ceph get pods
```

**Create Ceph Cluster:**

```yaml
# infrastructure/k8s/rook-ceph/cluster.yaml
apiVersion: ceph.rook.io/v1
kind:CephCluster
metadata:
  name: rook-ceph
  namespace: rook-ceph
spec:
  cephVersion:
    image: quay.io/ceph/ceph:v17.2.6
    allowUnsupported: false
  dataDirHostPath: /var/lib/rook
  mon:
    count: 3
    allowMultiplePerNode: false
  mgr:
    count: 2
    modules:
      - name: pg_autoscaler
        enabled: true
  dashboard:
    enabled: true
    ssl: false
  storage:
    useAllNodes: true
    useAllDevices: false
    deviceFilter: "^sd[b-z]"  # Adjust based on your disks
  network:
    provider: host
```

```bash
kubectl apply -f infrastructure/k8s/rook-ceph/cluster.yaml
```

**Create CephFS Filesystem:**

```yaml
# infrastructure/k8s/rook-ceph/filesystem.yaml
apiVersion: ceph.rook.io/v1
kind: CephFilesystem
metadata:
  name: saasodoo-cephfs
  namespace: rook-ceph
spec:
  metadataPool:
    replicated:
      size: 3
  dataPools:
    - name: data0
      replicated:
        size: 3
  metadataServer:
    activeCount: 1
    activeStandby: true
```

```bash
kubectl apply -f infrastructure/k8s/rook-ceph/filesystem.yaml
```

**Create StorageClass with Quota Support:**

```yaml
# infrastructure/k8s/rook-ceph/storageclass.yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cephfs-quota
provisioner: rook-ceph.cephfs.csi.ceph.com
parameters:
  clusterID: rook-ceph
  fsName: saasodoo-cephfs
  pool: saasodoo-cephfs-data0

  # CSI driver parameters
  csi.storage.k8s.io/provisioner-secret-name: rook-csi-cephfs-provisioner
  csi.storage.k8s.io/provisioner-secret-namespace: rook-ceph
  csi.storage.k8s.io/controller-expand-secret-name: rook-csi-cephfs-provisioner
  csi.storage.k8s.io/controller-expand-secret-namespace: rook-ceph
  csi.storage.k8s.io/node-stage-secret-name: rook-csi-cephfs-node
  csi.storage.k8s.io/node-stage-secret-namespace: rook-ceph

reclaimPolicy: Retain
allowVolumeExpansion: true
mountOptions:
  - discard
```

```bash
kubectl apply -f infrastructure/k8s/rook-ceph/storageclass.yaml
```

**Test CephFS:**

```yaml
# infrastructure/k8s/rook-ceph/test-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-cephfs-pvc
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: cephfs-quota
  resources:
    requests:
      storage: 1Gi
---
apiVersion: v1
kind: Pod
metadata:
  name: test-cephfs-pod
spec:
  containers:
  - name: test
    image: busybox
    command: ["sh", "-c", "echo 'Hello CephFS' > /mnt/test.txt && cat /mnt/test.txt && sleep 3600"]
    volumeMounts:
    - name: cephfs
      mountPath: /mnt
  volumes:
  - name: cephfs
    persistentVolumeClaim:
      claimName: test-cephfs-pvc
```

```bash
kubectl apply -f infrastructure/k8s/rook-ceph/test-pvc.yaml
kubectl logs test-cephfs-pod  # Should show "Hello CephFS"
kubectl exec test-cephfs-pod -- ls -lh /mnt
kubectl delete pod test-cephfs-pod
kubectl delete pvc test-cephfs-pvc
```

---

### Step 1.3: Configure Traefik

**Create Traefik Configuration:**

```yaml
# /var/lib/rancher/k3s/server/manifests/traefik-config.yaml
apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    deployment:
      replicas: 3

    ports:
      web:
        port: 80
        exposedPort: 80
      websecure:
        port: 443
        exposedPort: 443

    service:
      type: LoadBalancer

    logs:
      general:
        level: INFO
        format: json
      access:
        enabled: true
        format: json
        fields:
          headers:
            defaultMode: keep
            names:
              Authorization: drop
              User-Agent: redact

    metrics:
      prometheus:
        enabled: true
        addEntryPointsLabels: true
        addServicesLabels: true
        buckets:
          - 0.1
          - 0.3
          - 1.2
          - 5.0

    dashboard:
      enabled: true
      domain: traefik.localhost

    providers:
      kubernetesCRD:
        enabled: true
        allowCrossNamespace: true
      kubernetesIngress:
        enabled: true
```

**Create Traefik Middlewares:**

```yaml
# infrastructure/k8s/traefik/middlewares.yaml
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: security-headers
  namespace: default
spec:
  headers:
    frameDeny: true
    browserXssFilter: true
    contentTypeNosniff: true
    stsSeconds: 31536000
    stsIncludeSubdomains: true
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: rate-limit
  namespace: default
spec:
  rateLimit:
    average: 50
    burst: 100
    period: 1m
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: api-cors
  namespace: default
spec:
  headers:
    accessControlAllowMethods:
      - GET
      - OPTIONS
      - PUT
      - POST
      - DELETE
      - PATCH
    accessControlAllowOriginList:
      - "*"
    accessControlAllowHeaders:
      - "*"
    accessControlMaxAge: 86400
    addVaryHeader: true
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-user-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /user
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-billing-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /billing
---
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: strip-instance-prefix
  namespace: default
spec:
  stripPrefix:
    prefixes:
      - /instance
```

```bash
kubectl apply -f infrastructure/k8s/traefik/middlewares.yaml
```

**Test Traefik:**

```bash
# Access Traefik dashboard
kubectl port-forward -n kube-system $(kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik -o name) 9000:9000

# Open http://localhost:9000/dashboard/ in browser
```

---

### Step 1.4: Secrets Management

**Create secrets from .env file:**

```bash
# Create namespace for secrets
kubectl create namespace saasodoo

# Create secrets from environment variables
kubectl create secret generic postgres-credentials \
  --from-literal=POSTGRES_USER=odoo_user \
  --from-literal=POSTGRES_PASSWORD=secure_password_change_me \
  --from-literal=POSTGRES_AUTH_SERVICE_PASSWORD=auth_service_secure_pass_change_me \
  --from-literal=POSTGRES_BILLING_SERVICE_PASSWORD=billing_service123 \
  --from-literal=POSTGRES_INSTANCE_SERVICE_PASSWORD=instance_service_secure_pass_change_me \
  --namespace=saasodoo

kubectl create secret generic jwt-secret \
  --from-literal=JWT_SECRET_KEY=your-secret-key-change-in-production \
  --namespace=saasodoo

kubectl create secret generic killbill-credentials \
  --from-literal=KILLBILL_USERNAME=admin \
  --from-literal=KILLBILL_PASSWORD=password \
  --from-literal=KILLBILL_API_KEY=fresh-tenant \
  --from-literal=KILLBILL_API_SECRET=fresh-secret \
  --namespace=saasodoo

kubectl create secret generic rabbitmq-credentials \
  --from-literal=RABBITMQ_USER=saasodoo \
  --from-literal=RABBITMQ_PASSWORD=saasodoo123 \
  --namespace=saasodoo
```

**Test secret access:**

```yaml
# test-secret-pod.yaml
apiVersion: v1
kind: Pod
metadata:
  name: test-secret
  namespace: saasodoo
spec:
  containers:
  - name: test
    image: busybox
    command: ["sh", "-c", "echo $POSTGRES_USER && sleep 3600"]
    env:
    - name: POSTGRES_USER
      valueFrom:
        secretKeyRef:
          name: postgres-credentials
          key: POSTGRES_USER
```

```bash
kubectl apply -f test-secret-pod.yaml
kubectl logs -n saasodoo test-secret  # Should show "odoo_user"
kubectl delete pod -n saasodoo test-secret
```

---

## Phase 2: Supporting Services

### Step 2.1: PostgreSQL StatefulSet

**Create PostgreSQL ConfigMap for init scripts:**

```yaml
# infrastructure/k8s/postgres/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-init-scripts
  namespace: saasodoo
data:
  01-create-databases.sh: |
    #!/bin/bash
    set -e

    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE DATABASE auth;
        CREATE DATABASE billing;
        CREATE DATABASE instance;
        CREATE DATABASE communication;
    EOSQL

  02-create-users.sh: |
    #!/bin/bash
    set -e

    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        CREATE USER auth_service WITH PASSWORD '${POSTGRES_AUTH_SERVICE_PASSWORD}';
        GRANT ALL PRIVILEGES ON DATABASE auth TO auth_service;

        CREATE USER billing_service WITH PASSWORD '${POSTGRES_BILLING_SERVICE_PASSWORD}';
        GRANT ALL PRIVILEGES ON DATABASE billing TO billing_service;

        CREATE USER instance_service WITH PASSWORD '${POSTGRES_INSTANCE_SERVICE_PASSWORD}';
        GRANT ALL PRIVILEGES ON DATABASE instance TO instance_service;
    EOSQL
```

**Create PostgreSQL StatefulSet:**

```yaml
# infrastructure/k8s/postgres/statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: saasodoo
spec:
  ports:
  - port: 5432
    name: postgres
  clusterIP: None
  selector:
    app: postgres
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: saasodoo
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
          name: postgres
        env:
        - name: POSTGRES_DB
          value: "odoo"
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_USER
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_PASSWORD
        - name: POSTGRES_AUTH_SERVICE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_AUTH_SERVICE_PASSWORD
        - name: POSTGRES_BILLING_SERVICE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_BILLING_SERVICE_PASSWORD
        - name: POSTGRES_INSTANCE_SERVICE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_INSTANCE_SERVICE_PASSWORD
        volumeMounts:
        - name: postgres-data
          mountPath: /var/lib/postgresql/data
          subPath: postgres
        - name: init-scripts
          mountPath: /docker-entrypoint-initdb.d
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - odoo_user
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - odoo_user
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
      volumes:
      - name: init-scripts
        configMap:
          name: postgres-init-scripts
          defaultMode: 0755
  volumeClaimTemplates:
  - metadata:
      name: postgres-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: cephfs-quota
      resources:
        requests:
          storage: 50Gi
```

```bash
kubectl apply -f infrastructure/k8s/postgres/configmap.yaml
kubectl apply -f infrastructure/k8s/postgres/statefulset.yaml

# Test
kubectl exec -it -n saasodoo postgres-0 -- psql -U odoo_user -c "\l"
# Should list all databases: auth, billing, instance, communication
```

---

### Step 2.2: Redis & RabbitMQ

**Redis StatefulSet:**

```yaml
# infrastructure/k8s/redis/statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: saasodoo
spec:
  ports:
  - port: 6379
    name: redis
  clusterIP: None
  selector:
    app: redis
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: saasodoo
spec:
  serviceName: redis
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        command: ["redis-server"]
        args: ["--appendonly", "yes"]
        ports:
        - containerPort: 6379
          name: redis
        volumeMounts:
        - name: redis-data
          mountPath: /data
        livenessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - redis-cli
            - ping
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            cpu: 100m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 1Gi
  volumeClaimTemplates:
  - metadata:
      name: redis-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: cephfs-quota
      resources:
        requests:
          storage: 10Gi
```

**RabbitMQ StatefulSet:**

```yaml
# infrastructure/k8s/rabbitmq/statefulset.yaml
apiVersion: v1
kind: Service
metadata:
  name: rabbitmq
  namespace: saasodoo
spec:
  ports:
  - port: 5672
    name: amqp
  - port: 15672
    name: management
  clusterIP: None
  selector:
    app: rabbitmq
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: rabbitmq
  namespace: saasodoo
spec:
  serviceName: rabbitmq
  replicas: 1
  selector:
    matchLabels:
      app: rabbitmq
  template:
    metadata:
      labels:
        app: rabbitmq
    spec:
      containers:
      - name: rabbitmq
        image: rabbitmq:3-management-alpine
        ports:
        - containerPort: 5672
          name: amqp
        - containerPort: 15672
          name: management
        env:
        - name: RABBITMQ_DEFAULT_USER
          valueFrom:
            secretKeyRef:
              name: rabbitmq-credentials
              key: RABBITMQ_USER
        - name: RABBITMQ_DEFAULT_PASS
          valueFrom:
            secretKeyRef:
              name: rabbitmq-credentials
              key: RABBITMQ_PASSWORD
        - name: RABBITMQ_DEFAULT_VHOST
          value: "saasodoo"
        volumeMounts:
        - name: rabbitmq-data
          mountPath: /var/lib/rabbitmq
        livenessProbe:
          exec:
            command:
            - rabbitmq-diagnostics
            - check_port_connectivity
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          exec:
            command:
            - rabbitmq-diagnostics
            - check_port_connectivity
          initialDelaySeconds: 20
          periodSeconds: 10
        resources:
          requests:
            cpu: 200m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 2Gi
  volumeClaimTemplates:
  - metadata:
      name: rabbitmq-data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: cephfs-quota
      resources:
        requests:
          storage: 20Gi
```

```bash
kubectl apply -f infrastructure/k8s/redis/statefulset.yaml
kubectl apply -f infrastructure/k8s/rabbitmq/statefulset.yaml

# Test Redis
kubectl exec -it -n saasodoo redis-0 -- redis-cli ping
# Should return "PONG"

# Test RabbitMQ
kubectl port-forward -n saasodoo rabbitmq-0 15672:15672
# Open http://localhost:15672 (login: saasodoo/saasodoo123)
```

---

## Phase 3: Microservices Migration

### Step 3.1: User Service Deployment

**Create Deployment:**

```yaml
# infrastructure/k8s/services/user-service.yaml
apiVersion: v1
kind: Service
metadata:
  name: user-service
  namespace: saasodoo
spec:
  selector:
    app: user-service
  ports:
  - port: 8001
    targetPort: 8001
    name: http
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
  namespace: saasodoo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: user-service
  template:
    metadata:
      labels:
        app: user-service
    spec:
      containers:
      - name: user-service
        image: your-registry/user-service:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 8001
        env:
        - name: POSTGRES_HOST
          value: "postgres"
        - name: POSTGRES_PORT
          value: "5432"
        - name: POSTGRES_DB
          value: "auth"
        - name: DB_SERVICE_USER
          value: "auth_service"
        - name: DB_SERVICE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-credentials
              key: POSTGRES_AUTH_SERVICE_PASSWORD
        - name: REDIS_HOST
          value: "redis"
        - name: REDIS_PORT
          value: "6379"
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: jwt-secret
              key: JWT_SECRET_KEY
        - name: JWT_ALGORITHM
          value: "HS256"
        - name: JWT_EXPIRE_MINUTES
          value: "1440"
        - name: DEBUG
          value: "true"
        - name: LOG_LEVEL
          value: "info"
        livenessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8001
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
---
apiVersion: traefik.containo.us/v1alpha1
kind: IngressRoute
metadata:
  name: user-service
  namespace: saasodoo
spec:
  entryPoints:
    - web
  routes:
  - match: Host(`api.localhost`) && PathPrefix(`/user`)
    kind: Rule
    services:
    - name: user-service
      port: 8001
    middlewares:
    - name: strip-user-prefix
    - name: api-cors
    - name: security-headers
```

```bash
kubectl apply -f infrastructure/k8s/services/user-service.yaml

# Test
curl http://api.localhost/user/health
```

---

## Phase 4: Instance Service Kubernetes Integration

This is the **most critical section** with detailed code changes.

### Step 4.1: Install Kubernetes Python Client

**Update requirements.txt:**

```txt
# services/instance-service/requirements.txt

# ... existing requirements ...

# Kubernetes Python Client (replaces Docker SDK)
kubernetes==28.1.0

# REMOVE Docker SDK - no longer needed
# The docker package and all Docker SDK code will be completely removed
```

```bash
# Install Kubernetes client
pip install kubernetes==28.1.0

# Uninstall Docker SDK
pip uninstall docker -y
```

---

### Step 4.2: Create Kubernetes Client Wrapper

**Create new file for Kubernetes operations:**

```python
# services/instance-service/app/utils/k8s_client.py
"""
Kubernetes client wrapper for instance service
Replaces Docker SDK operations with Kubernetes API calls
"""

import os
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID

from kubernetes import client, config
from kubernetes.client.rest import ApiException
import structlog

logger = structlog.get_logger(__name__)


class KubernetesClientWrapper:
    """Centralized Kubernetes client for managing Odoo instances as pods"""

    def __init__(self, namespace: str = "odoo-instances"):
        """
        Initialize Kubernetes client

        Args:
            namespace: Default namespace for Odoo instances
        """
        self.namespace = namespace
        self.apps_v1 = None
        self.core_v1 = None
        self.networking_v1 = None
        self._last_connection_check = 0
        self._connection_check_interval = 30  # seconds

        # Initialize connection
        self._ensure_connection()

    def _ensure_connection(self):
        """Ensure Kubernetes client is connected"""
        current_time = time.time()

        if (self.apps_v1 is None or
            current_time - self._last_connection_check > self._connection_check_interval):

            try:
                # Load kubeconfig from cluster (when running in pod)
                # or from ~/.kube/config (when running locally)
                try:
                    config.load_incluster_config()
                    logger.info("Loaded in-cluster Kubernetes config")
                except config.ConfigException:
                    config.load_kube_config()
                    logger.info("Loaded kubeconfig from file")

                # Initialize API clients
                self.apps_v1 = client.AppsV1Api()
                self.core_v1 = client.CoreV1Api()
                self.networking_v1 = client.NetworkingV1Api()

                self._last_connection_check = current_time
                logger.info("Kubernetes client initialized successfully")

            except Exception as e:
                logger.error("Failed to initialize Kubernetes client", error=str(e))
                raise

    def create_namespace_if_not_exists(self, namespace: str) -> bool:
        """
        Create namespace if it doesn't exist

        Args:
            namespace: Namespace name

        Returns:
            True if created or already exists
        """
        try:
            self._ensure_connection()

            # Check if namespace exists
            try:
                self.core_v1.read_namespace(name=namespace)
                logger.debug("Namespace already exists", namespace=namespace)
                return True
            except ApiException as e:
                if e.status != 404:
                    raise

            # Create namespace
            namespace_manifest = client.V1Namespace(
                metadata=client.V1ObjectMeta(
                    name=namespace,
                    labels={
                        "saasodoo.io/managed": "true",
                        "saasodoo.io/type": "instance-namespace"
                    }
                )
            )

            self.core_v1.create_namespace(body=namespace_manifest)
            logger.info("Created namespace", namespace=namespace)
            return True

        except Exception as e:
            logger.error("Failed to create namespace", namespace=namespace, error=str(e))
            return False

    def create_persistent_volume_claim(
        self,
        instance_id: str,
        storage_size: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create PersistentVolumeClaim for Odoo instance data

        Args:
            instance_id: Unique instance identifier
            storage_size: Storage size (e.g., "10Gi")
            namespace: Namespace (defaults to self.namespace)

        Returns:
            PVC information
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace
            pvc_name = f"odoo-data-{instance_id[:8]}"

            # Create PVC manifest
            pvc = client.V1PersistentVolumeClaim(
                metadata=client.V1ObjectMeta(
                    name=pvc_name,
                    namespace=ns,
                    labels={
                        "app": "odoo",
                        "saasodoo.io/instance-id": instance_id,
                        "saasodoo.io/managed": "true"
                    }
                ),
                spec=client.V1PersistentVolumeClaimSpec(
                    access_modes=["ReadWriteOnce"],
                    storage_class_name="cephfs-quota",
                    resources=client.V1ResourceRequirements(
                        requests={"storage": storage_size}
                    )
                )
            )

            # Create PVC
            created_pvc = self.core_v1.create_namespaced_persistent_volume_claim(
                namespace=ns,
                body=pvc
            )

            logger.info("Created PVC", pvc_name=pvc_name, storage_size=storage_size)

            return {
                "pvc_name": pvc_name,
                "storage_size": storage_size,
                "status": "created"
            }

        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.debug("PVC already exists", pvc_name=pvc_name)
                return {"pvc_name": pvc_name, "status": "exists"}
            logger.error("Failed to create PVC", error=str(e))
            raise

    def create_odoo_deployment(
        self,
        instance: Dict[str, Any],
        db_info: Dict[str, str],
        admin_password: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create Kubernetes Deployment for Odoo instance

        Args:
            instance: Instance metadata from database
            db_info: Database connection information
            admin_password: Generated admin password
            namespace: Namespace (defaults to self.namespace)

        Returns:
            Deployment information
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace
            instance_id = str(instance['id'])
            instance_name = f"odoo-{instance['database_name']}-{instance_id[:8]}"

            # Ensure namespace exists
            self.create_namespace_if_not_exists(ns)

            # Create PVC first
            storage_limit = instance.get('storage_limit', '10Gi')
            pvc_info = self.create_persistent_volume_claim(instance_id, storage_limit, ns)

            # Prepare environment variables
            env_vars = [
                client.V1EnvVar(name="ODOO_DATABASE_HOST", value=db_info['db_host']),
                client.V1EnvVar(name="ODOO_DATABASE_PORT_NUMBER", value=str(db_info['db_port'])),
                client.V1EnvVar(name="ODOO_DATABASE_NAME", value=db_info['db_name']),
                client.V1EnvVar(name="ODOO_DATABASE_USER", value=db_info['db_user']),
                client.V1EnvVar(name="ODOO_DATABASE_PASSWORD", value=db_info['db_password']),
                client.V1EnvVar(name="ODOO_EMAIL", value=instance['admin_email']),
                client.V1EnvVar(name="ODOO_PASSWORD", value=admin_password),
                client.V1EnvVar(name="ODOO_LOAD_DEMO_DATA",
                              value="yes" if instance.get('demo_data') else "no"),
            ]

            # Add custom environment variables
            for key, value in instance.get('environment_vars', {}).items():
                env_vars.append(client.V1EnvVar(name=key, value=value))

            # Resource limits
            memory_limit = instance.get('memory_limit', '2Gi')
            cpu_limit = instance.get('cpu_limit', 1.0)

            # Create Deployment manifest
            deployment = client.V1Deployment(
                metadata=client.V1ObjectMeta(
                    name=instance_name,
                    namespace=ns,
                    labels={
                        "app": "odoo",
                        "saasodoo.io/instance-id": instance_id,
                        "saasodoo.io/instance-name": instance['name'],
                        "saasodoo.io/customer-id": str(instance['customer_id']),
                        "saasodoo.io/managed": "true"
                    }
                ),
                spec=client.V1DeploymentSpec(
                    replicas=1,
                    selector=client.V1LabelSelector(
                        match_labels={
                            "app": "odoo",
                            "saasodoo.io/instance-id": instance_id
                        }
                    ),
                    template=client.V1PodTemplateSpec(
                        metadata=client.V1ObjectMeta(
                            labels={
                                "app": "odoo",
                                "saasodoo.io/instance-id": instance_id,
                                "saasodoo.io/instance-name": instance['name'],
                                "saasodoo.io/customer-id": str(instance['customer_id'])
                            }
                        ),
                        spec=client.V1PodSpec(
                            containers=[
                                client.V1Container(
                                    name="odoo",
                                    image=f"bitnamilegacy/odoo:{instance.get('odoo_version', '17')}",
                                    ports=[client.V1ContainerPort(container_port=8069)],
                                    env=env_vars,
                                    volume_mounts=[
                                        client.V1VolumeMount(
                                            name="odoo-data",
                                            mount_path="/bitnami/odoo"
                                        )
                                    ],
                                    resources=client.V1ResourceRequirements(
                                        requests={
                                            "cpu": f"{int(cpu_limit * 1000)}m",
                                            "memory": memory_limit
                                        },
                                        limits={
                                            "cpu": f"{int(cpu_limit * 1000)}m",
                                            "memory": memory_limit
                                        }
                                    ),
                                    liveness_probe=client.V1Probe(
                                        http_get=client.V1HTTPGetAction(
                                            path="/",
                                            port=8069
                                        ),
                                        initial_delay_seconds=60,
                                        period_seconds=10,
                                        timeout_seconds=5,
                                        failure_threshold=3
                                    ),
                                    readiness_probe=client.V1Probe(
                                        http_get=client.V1HTTPGetAction(
                                            path="/",
                                            port=8069
                                        ),
                                        initial_delay_seconds=30,
                                        period_seconds=5,
                                        timeout_seconds=5,
                                        failure_threshold=3
                                    )
                                )
                            ],
                            volumes=[
                                client.V1Volume(
                                    name="odoo-data",
                                    persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                        claim_name=pvc_info['pvc_name']
                                    )
                                )
                            ],
                            restart_policy="Always"
                        )
                    )
                )
            )

            # Create Deployment
            created_deployment = self.apps_v1.create_namespaced_deployment(
                namespace=ns,
                body=deployment
            )

            logger.info("Created Odoo deployment", deployment_name=instance_name, namespace=ns)

            # Create Service for the instance
            service_info = self._create_instance_service(instance_id, instance_name, ns)

            # Create Ingress for the instance
            ingress_info = self._create_instance_ingress(
                instance_id,
                instance_name,
                instance['database_name'],
                ns
            )

            return {
                "deployment_name": instance_name,
                "namespace": ns,
                "pvc_name": pvc_info['pvc_name'],
                "service_name": service_info['service_name'],
                "internal_url": service_info['internal_url'],
                "external_url": ingress_info['external_url'],
                "admin_password": admin_password
            }

        except Exception as e:
            logger.error("Failed to create Odoo deployment", error=str(e))
            raise

    def _create_instance_service(
        self,
        instance_id: str,
        deployment_name: str,
        namespace: str
    ) -> Dict[str, Any]:
        """
        Create Kubernetes Service for Odoo instance

        Args:
            instance_id: Instance ID
            deployment_name: Name of the deployment
            namespace: Namespace

        Returns:
            Service information
        """
        try:
            service_name = deployment_name

            service = client.V1Service(
                metadata=client.V1ObjectMeta(
                    name=service_name,
                    namespace=namespace,
                    labels={
                        "app": "odoo",
                        "saasodoo.io/instance-id": instance_id
                    }
                ),
                spec=client.V1ServiceSpec(
                    selector={
                        "app": "odoo",
                        "saasodoo.io/instance-id": instance_id
                    },
                    ports=[
                        client.V1ServicePort(
                            port=8069,
                            target_port=8069,
                            name="http"
                        )
                    ],
                    type="ClusterIP"
                )
            )

            created_service = self.core_v1.create_namespaced_service(
                namespace=namespace,
                body=service
            )

            internal_url = f"http://{service_name}.{namespace}.svc.cluster.local:8069"

            logger.info("Created service", service_name=service_name, internal_url=internal_url)

            return {
                "service_name": service_name,
                "internal_url": internal_url
            }

        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.debug("Service already exists", service_name=service_name)
                return {
                    "service_name": service_name,
                    "internal_url": f"http://{service_name}.{namespace}.svc.cluster.local:8069"
                }
            logger.error("Failed to create service", error=str(e))
            raise

    def _create_instance_ingress(
        self,
        instance_id: str,
        deployment_name: str,
        subdomain: str,
        namespace: str
    ) -> Dict[str, Any]:
        """
        Create Traefik IngressRoute for Odoo instance

        Args:
            instance_id: Instance ID
            deployment_name: Name of the deployment
            subdomain: Subdomain for instance
            namespace: Namespace

        Returns:
            Ingress information
        """
        try:
            ingress_name = deployment_name
            base_domain = os.getenv('BASE_DOMAIN', 'saasodoo.local')
            external_url = f"http://{subdomain}.{base_domain}"

            # Create IngressRoute using Traefik CRD
            # Note: This requires traefik CRD to be installed
            # We'll use a standard Ingress as fallback

            ingress = client.V1Ingress(
                metadata=client.V1ObjectMeta(
                    name=ingress_name,
                    namespace=namespace,
                    labels={
                        "app": "odoo",
                        "saasodoo.io/instance-id": instance_id
                    },
                    annotations={
                        "traefik.ingress.kubernetes.io/router.entrypoints": "web"
                    }
                ),
                spec=client.V1IngressSpec(
                    rules=[
                        client.V1IngressRule(
                            host=f"{subdomain}.{base_domain}",
                            http=client.V1HTTPIngressRuleValue(
                                paths=[
                                    client.V1HTTPIngressPath(
                                        path="/",
                                        path_type="Prefix",
                                        backend=client.V1IngressBackend(
                                            service=client.V1IngressServiceBackend(
                                                name=deployment_name,
                                                port=client.V1ServiceBackendPort(
                                                    number=8069
                                                )
                                            )
                                        )
                                    )
                                ]
                            )
                        )
                    ]
                )
            )

            created_ingress = self.networking_v1.create_namespaced_ingress(
                namespace=namespace,
                body=ingress
            )

            logger.info("Created ingress", ingress_name=ingress_name, external_url=external_url)

            return {
                "ingress_name": ingress_name,
                "external_url": external_url
            }

        except ApiException as e:
            if e.status == 409:  # Already exists
                logger.debug("Ingress already exists", ingress_name=ingress_name)
                return {"ingress_name": ingress_name, "external_url": external_url}
            logger.error("Failed to create ingress", error=str(e))
            raise

    def scale_deployment(
        self,
        deployment_name: str,
        replicas: int,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Scale deployment to specified number of replicas

        Args:
            deployment_name: Name of deployment
            replicas: Number of replicas (0 = stop, 1 = start)
            namespace: Namespace

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace

            # Get deployment
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=ns
            )

            # Update replicas
            deployment.spec.replicas = replicas

            # Patch deployment
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=ns,
                body=deployment
            )

            logger.info("Scaled deployment",
                       deployment_name=deployment_name,
                       replicas=replicas)

            return True

        except ApiException as e:
            logger.error("Failed to scale deployment",
                        deployment_name=deployment_name,
                        error=str(e))
            return False

    def start_instance(
        self,
        instance_id: str,
        deployment_name: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start Odoo instance (scale to 1 replica)

        Args:
            instance_id: Instance ID
            deployment_name: Name of deployment
            namespace: Namespace

        Returns:
            Instance information
        """
        try:
            ns = namespace or self.namespace

            # Scale to 1 replica
            success = self.scale_deployment(deployment_name, replicas=1, namespace=ns)

            if not success:
                raise Exception("Failed to scale deployment to 1")

            # Wait for pod to be ready
            self._wait_for_pod_ready(instance_id, ns, timeout=120)

            # Get pod IP
            pod_info = self._get_pod_info(instance_id, ns)

            return {
                "deployment_name": deployment_name,
                "status": "running",
                "internal_ip": pod_info['pod_ip'],
                "internal_url": f"http://{deployment_name}.{ns}.svc.cluster.local:8069",
                "external_url": pod_info['external_url']
            }

        except Exception as e:
            logger.error("Failed to start instance", instance_id=instance_id, error=str(e))
            raise

    def stop_instance(
        self,
        deployment_name: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Stop Odoo instance (scale to 0 replicas)

        Args:
            deployment_name: Name of deployment
            namespace: Namespace

        Returns:
            True if successful
        """
        try:
            ns = namespace or self.namespace

            # Scale to 0 replicas
            success = self.scale_deployment(deployment_name, replicas=0, namespace=ns)

            return success

        except Exception as e:
            logger.error("Failed to stop instance",
                        deployment_name=deployment_name,
                        error=str(e))
            return False

    def delete_instance(
        self,
        instance_id: str,
        deployment_name: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Delete Odoo instance and all resources

        Args:
            instance_id: Instance ID
            deployment_name: Name of deployment
            namespace: Namespace

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace

            # Delete deployment
            try:
                self.apps_v1.delete_namespaced_deployment(
                    name=deployment_name,
                    namespace=ns
                )
                logger.info("Deleted deployment", deployment_name=deployment_name)
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete service
            try:
                self.core_v1.delete_namespaced_service(
                    name=deployment_name,
                    namespace=ns
                )
                logger.info("Deleted service", service_name=deployment_name)
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete ingress
            try:
                self.networking_v1.delete_namespaced_ingress(
                    name=deployment_name,
                    namespace=ns
                )
                logger.info("Deleted ingress", ingress_name=deployment_name)
            except ApiException as e:
                if e.status != 404:
                    raise

            # Delete PVC (optional - set reclaimPolicy to Retain in StorageClass)
            pvc_name = f"odoo-data-{instance_id[:8]}"
            try:
                self.core_v1.delete_namespaced_persistent_volume_claim(
                    name=pvc_name,
                    namespace=ns
                )
                logger.info("Deleted PVC", pvc_name=pvc_name)
            except ApiException as e:
                if e.status != 404:
                    raise

            return True

        except Exception as e:
            logger.error("Failed to delete instance",
                        instance_id=instance_id,
                        error=str(e))
            return False

    def get_instance_status(
        self,
        instance_id: str,
        namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get status of Odoo instance

        Args:
            instance_id: Instance ID
            namespace: Namespace

        Returns:
            Status information
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace

            # Get pods with instance label
            pods = self.core_v1.list_namespaced_pod(
                namespace=ns,
                label_selector=f"saasodoo.io/instance-id={instance_id}"
            )

            if not pods.items:
                return {
                    "status": "not_found",
                    "message": "No pods found for instance"
                }

            pod = pods.items[0]

            # Extract status
            phase = pod.status.phase  # Pending, Running, Succeeded, Failed, Unknown

            # Get container status
            container_status = None
            if pod.status.container_statuses:
                container_status = pod.status.container_statuses[0]

            ready = container_status.ready if container_status else False
            restart_count = container_status.restart_count if container_status else 0

            return {
                "status": phase.lower(),
                "ready": ready,
                "restart_count": restart_count,
                "pod_ip": pod.status.pod_ip,
                "node_name": pod.spec.node_name,
                "started_at": pod.status.start_time.isoformat() if pod.status.start_time else None
            }

        except Exception as e:
            logger.error("Failed to get instance status",
                        instance_id=instance_id,
                        error=str(e))
            return {
                "status": "error",
                "message": str(e)
            }

    def _wait_for_pod_ready(
        self,
        instance_id: str,
        namespace: str,
        timeout: int = 120
    ):
        """
        Wait for pod to be ready

        Args:
            instance_id: Instance ID
            namespace: Namespace
            timeout: Timeout in seconds
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_instance_status(instance_id, namespace)

            if status['status'] == 'running' and status.get('ready'):
                logger.info("Pod is ready", instance_id=instance_id)
                return

            if status['status'] == 'failed':
                raise Exception(f"Pod failed to start: {status.get('message')}")

            time.sleep(5)

        raise TimeoutError(f"Pod did not become ready within {timeout} seconds")

    def _get_pod_info(
        self,
        instance_id: str,
        namespace: str
    ) -> Dict[str, Any]:
        """Get pod information"""
        try:
            pods = self.core_v1.list_namespaced_pod(
                namespace=namespace,
                label_selector=f"saasodoo.io/instance-id={instance_id}"
            )

            if not pods.items:
                raise Exception("No pods found")

            pod = pods.items[0]

            # Get external URL from ingress
            ingresses = self.networking_v1.list_namespaced_ingress(
                namespace=namespace,
                label_selector=f"saasodoo.io/instance-id={instance_id}"
            )

            external_url = None
            if ingresses.items:
                ingress = ingresses.items[0]
                if ingress.spec.rules:
                    host = ingress.spec.rules[0].host
                    external_url = f"http://{host}"

            return {
                "pod_name": pod.metadata.name,
                "pod_ip": pod.status.pod_ip,
                "node_name": pod.spec.node_name,
                "external_url": external_url
            }

        except Exception as e:
            logger.error("Failed to get pod info", instance_id=instance_id, error=str(e))
            raise

    def get_pod_logs(
        self,
        instance_id: str,
        namespace: Optional[str] = None,
        tail_lines: int = 100
    ) -> Optional[str]:
        """
        Get logs from Odoo pod

        Args:
            instance_id: Instance ID
            namespace: Namespace
            tail_lines: Number of lines to retrieve

        Returns:
            Log content
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace

            # Get pods
            pods = self.core_v1.list_namespaced_pod(
                namespace=ns,
                label_selector=f"saasodoo.io/instance-id={instance_id}"
            )

            if not pods.items:
                return None

            pod = pods.items[0]

            # Get logs
            logs = self.core_v1.read_namespaced_pod_log(
                name=pod.metadata.name,
                namespace=ns,
                tail_lines=tail_lines,
                timestamps=True
            )

            return logs

        except Exception as e:
            logger.error("Failed to get pod logs", instance_id=instance_id, error=str(e))
            return None

    def update_instance_resources(
        self,
        deployment_name: str,
        cpu_limit: float,
        memory_limit: str,
        namespace: Optional[str] = None
    ) -> bool:
        """
        Update instance resource limits

        Args:
            deployment_name: Name of deployment
            cpu_limit: CPU limit in cores (e.g., 2.0)
            memory_limit: Memory limit (e.g., "4Gi")
            namespace: Namespace

        Returns:
            True if successful
        """
        try:
            self._ensure_connection()
            ns = namespace or self.namespace

            # Get deployment
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=ns
            )

            # Update resources
            container = deployment.spec.template.spec.containers[0]
            container.resources.requests = {
                "cpu": f"{int(cpu_limit * 1000)}m",
                "memory": memory_limit
            }
            container.resources.limits = {
                "cpu": f"{int(cpu_limit * 1000)}m",
                "memory": memory_limit
            }

            # Patch deployment
            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=ns,
                body=deployment
            )

            logger.info("Updated instance resources",
                       deployment_name=deployment_name,
                       cpu_limit=cpu_limit,
                       memory_limit=memory_limit)

            return True

        except Exception as e:
            logger.error("Failed to update instance resources",
                        deployment_name=deployment_name,
                        error=str(e))
            return False


# Global instance
_k8s_client = None


def get_k8s_client() -> KubernetesClientWrapper:
    """Get or create global Kubernetes client instance"""
    global _k8s_client
    if _k8s_client is None:
        namespace = os.getenv('ODOO_INSTANCES_NAMESPACE', 'odoo-instances')
        _k8s_client = KubernetesClientWrapper(namespace=namespace)
    return _k8s_client
```

---

### Step 4.3: Update Provisioning Tasks

**Modify provisioning.py to use Kubernetes:**

```python
# services/instance-service/app/tasks/provisioning.py
"""
Instance provisioning background tasks - Kubernetes version
"""

import os
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from celery import current_task
from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import (
    send_instance_provisioning_started_email,
    send_instance_ready_email,
    send_instance_provisioning_failed_email
)
from app.utils.password_generator import generate_secure_password
from app.utils.k8s_client import get_k8s_client
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True)
def provision_instance_task(self, instance_id: str):
    """
    Background task to provision a new Odoo instance on Kubernetes
    """
    try:
        logger.info("Starting instance provisioning (Kubernetes)",
                   instance_id=instance_id,
                   task_id=self.request.id)

        # Use sync version for Celery compatibility
        result = asyncio.run(_provision_instance_workflow(instance_id))

        logger.info("Instance provisioning completed", instance_id=instance_id, result=result)
        return result

    except Exception as e:
        logger.error("Instance provisioning failed", instance_id=instance_id, error=str(e))

        # Update instance status to ERROR
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))

        # Re-raise for Celery to mark task as failed
        raise


async def _provision_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Main provisioning workflow for Kubernetes"""

    # Step 1: Get instance details from database
    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    logger.info("Provisioning workflow started (Kubernetes)", instance_name=instance['name'])

    # Get user information for email notifications
    user_info = await _get_user_info(instance['customer_id'])

    try:
        # Step 2: Send provisioning started email
        if user_info:
            try:
                await send_instance_provisioning_started_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    estimated_time="10-15 minutes"
                )
                logger.info("Provisioning started email sent", email=user_info['email'])
            except Exception as e:
                logger.warning("Failed to send provisioning started email", error=str(e))

        # Step 3: Update status to STARTING
        await _update_instance_status(instance_id, InstanceStatus.STARTING)

        # Step 4: Create dedicated Odoo database
        db_info = await _create_odoo_database(instance)
        logger.info("Database created", database=instance['database_name'])

        # Step 5: Generate secure admin password
        admin_password = generate_secure_password()
        logger.info("Generated secure password for instance")

        # Step 6: Deploy Odoo on Kubernetes
        k8s_client = get_k8s_client()
        deployment_info = k8s_client.create_odoo_deployment(
            instance=instance,
            db_info=db_info,
            admin_password=admin_password
        )
        logger.info("Kubernetes deployment created",
                   deployment_name=deployment_info['deployment_name'])

        # Step 7: Wait for pod to be ready and Odoo to start
        await _wait_for_odoo_startup(deployment_info, timeout=300)
        logger.info("Odoo startup confirmed")

        # Step 8: Update instance with connection details
        await _update_instance_network_info(instance_id, deployment_info)

        # Step 9: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)

        # Step 10: Send instance ready email with password
        if user_info:
            try:
                await send_instance_ready_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    instance_url=deployment_info['external_url'],
                    admin_email=instance['admin_email'],
                    admin_password=admin_password
                )
                logger.info("Instance ready email sent with password", email=user_info['email'])
            except Exception as e:
                logger.warning("Failed to send instance ready email", error=str(e))

        return {
            "status": "success",
            "deployment_name": deployment_info['deployment_name'],
            "external_url": deployment_info['external_url'],
            "message": "Instance provisioned successfully on Kubernetes"
        }

    except Exception as e:
        # Cleanup on failure
        logger.error("Provisioning failed, starting cleanup", error=str(e))

        # Send provisioning failed email
        if user_info:
            try:
                await send_instance_provisioning_failed_email(
                    email=user_info['email'],
                    first_name=user_info['first_name'],
                    instance_name=instance['name'],
                    error_reason=str(e)[:200],
                    support_url=f"{os.getenv('FRONTEND_URL', 'http://app.saasodoo.local')}/support"
                )
                logger.info("Provisioning failed email sent", email=user_info['email'])
            except Exception as email_error:
                logger.warning("Failed to send provisioning failed email", error=str(email_error))

        await _cleanup_failed_provisioning(instance_id, instance)
        raise


async def _wait_for_odoo_startup(deployment_info: Dict[str, Any], timeout: int = 300):
    """Wait for Odoo to start up and be accessible"""
    import httpx

    url = deployment_info['internal_url']
    start_time = datetime.utcnow()

    logger.info("Waiting for Odoo startup on Kubernetes", url=url, timeout=timeout)

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(url, timeout=10)
                if response.status_code in [200, 303, 302]:
                    logger.info("Odoo is accessible")
                    return True
            except Exception:
                pass  # Continue waiting

            await asyncio.sleep(10)

    raise TimeoutError(f"Odoo did not start within {timeout} seconds")


async def _cleanup_failed_provisioning(instance_id: str, instance: Dict[str, Any]):
    """Clean up Kubernetes resources after failed provisioning"""
    logger.info("Starting Kubernetes cleanup", instance_id=instance_id)

    try:
        k8s_client = get_k8s_client()
        deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

        # Delete all Kubernetes resources
        k8s_client.delete_instance(
            instance_id=str(instance['id']),
            deployment_name=deployment_name
        )

        # Remove database if created
        await _delete_odoo_database(instance)

        logger.info("Kubernetes cleanup completed", instance_id=instance_id)

    except Exception as e:
        logger.error("Kubernetes cleanup failed", instance_id=instance_id, error=str(e))


# Keep database helper functions unchanged from original
async def _get_instance_from_db(instance_id: str) -> Dict[str, Any]:
    """Get instance details from database (unchanged)"""
    # ... (keep original implementation)
    pass


async def _update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    """Update instance status in database (unchanged)"""
    # ... (keep original implementation)
    pass


async def _create_odoo_database(instance: Dict[str, Any]) -> Dict[str, str]:
    """Create dedicated PostgreSQL database for Odoo instance (unchanged)"""
    # ... (keep original implementation)
    pass


async def _delete_odoo_database(instance: Dict[str, Any]):
    """Delete Odoo database"""
    admin_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database='postgres',
        user=os.getenv('POSTGRES_USER', 'saasodoo'),
        password=os.getenv('POSTGRES_PASSWORD', 'saasodoo123')
    )

    try:
        database_name = instance['database_name']
        db_user = f"odoo_{database_name}"

        # Terminate connections and drop database
        await admin_conn.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{database_name}'
            AND pid <> pg_backend_pid()
        """)

        await admin_conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
        await admin_conn.execute(f'DROP USER IF EXISTS "{db_user}"')
        logger.info("Database cleaned up", database=database_name)

    finally:
        await admin_conn.close()


async def _update_instance_network_info(instance_id: str, deployment_info: Dict[str, Any]):
    """Update instance with network and deployment information"""
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )

    try:
        await conn.execute("""
            UPDATE instances
            SET deployment_name = $1, service_name = $2,
                internal_url = $3, external_url = $4, updated_at = $5
            WHERE id = $6
        """,
            deployment_info['deployment_name'],
            deployment_info['service_name'],
            deployment_info['internal_url'],
            deployment_info['external_url'],
            datetime.utcnow(),
            UUID(instance_id)
        )

        logger.info("Instance network info updated", instance_id=instance_id)
    finally:
        await conn.close()


async def _get_user_info(customer_id: str) -> Dict[str, Any]:
    """Get user information from user-service (unchanged)"""
    # ... (keep original implementation)
    pass
```

---

### Step 4.4: Update Lifecycle Tasks

**Modify lifecycle.py:**

```python
# services/instance-service/app/tasks/lifecycle.py
"""
Instance lifecycle management tasks (start, stop, restart) - Kubernetes version
"""

import os
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, Any
from uuid import UUID

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.notification_client import get_notification_client
from app.utils.k8s_client import get_k8s_client
import structlog

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True)
def start_instance_task(self, instance_id: str):
    """Background task to start instance on Kubernetes"""
    try:
        logger.info("Starting instance start workflow (Kubernetes)",
                   instance_id=instance_id,
                   task_id=self.request.id)
        result = asyncio.run(_start_instance_workflow(instance_id))
        logger.info("Instance start completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance start failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


@celery_app.task(bind=True)
def stop_instance_task(self, instance_id: str):
    """Background task to stop instance on Kubernetes"""
    try:
        logger.info("Starting instance stop workflow (Kubernetes)",
                   instance_id=instance_id,
                   task_id=self.request.id)
        result = asyncio.run(_stop_instance_workflow(instance_id))
        logger.info("Instance stop completed", instance_id=instance_id, result=result)
        return result
    except Exception as e:
        logger.error("Instance stop failed", instance_id=instance_id, error=str(e))
        asyncio.run(_update_instance_status(instance_id, InstanceStatus.ERROR, str(e)))
        raise


async def _start_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Start instance workflow for Kubernetes"""

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    logger.info("Starting start workflow (Kubernetes)", instance_name=instance['name'])

    user_info = await _get_user_info(instance['customer_id'])

    try:
        # Step 1: Update status to STARTING
        await _update_instance_status(instance_id, InstanceStatus.STARTING)

        # Step 2: Start Kubernetes deployment (scale to 1)
        k8s_client = get_k8s_client()
        deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

        result = k8s_client.start_instance(
            instance_id=str(instance['id']),
            deployment_name=deployment_name
        )

        logger.info("Kubernetes deployment started", deployment_name=deployment_name)

        # Step 3: Update instance network info
        await _update_instance_network_info(instance_id, result)

        # Step 4: Mark as RUNNING
        await _update_instance_status(instance_id, InstanceStatus.RUNNING)

        # Step 5: Send notification email
        if user_info:
            try:
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[user_info['email']],
                    template_name="instance_started",
                    template_variables={
                        "first_name": user_info['first_name'],
                        "instance_name": instance['name'],
                        "instance_url": result['external_url']
                    },
                    tags=["instance", "lifecycle", "started"]
                )
                logger.info("Instance started email sent", email=user_info['email'])
            except Exception as e:
                logger.error("Failed to send email", error=str(e))

        return {
            "status": "success",
            "deployment_name": deployment_name,
            "external_url": result['external_url'],
            "message": "Instance started successfully on Kubernetes"
        }

    except Exception as e:
        logger.error("Start workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


async def _stop_instance_workflow(instance_id: str) -> Dict[str, Any]:
    """Stop instance workflow for Kubernetes"""

    instance = await _get_instance_from_db(instance_id)
    if not instance:
        raise ValueError(f"Instance {instance_id} not found")

    logger.info("Starting stop workflow (Kubernetes)", instance_name=instance['name'])

    user_info = await _get_user_info(instance['customer_id'])

    try:
        # Step 1: Update status to STOPPING
        await _update_instance_status(instance_id, InstanceStatus.STOPPING)

        # Step 2: Stop Kubernetes deployment (scale to 0)
        k8s_client = get_k8s_client()
        deployment_name = f"odoo-{instance['database_name']}-{instance['id'].hex[:8]}"

        success = k8s_client.stop_instance(deployment_name=deployment_name)

        if not success:
            raise Exception("Failed to stop Kubernetes deployment")

        logger.info("Kubernetes deployment stopped", deployment_name=deployment_name)

        # Step 3: Mark as STOPPED
        await _update_instance_status(instance_id, InstanceStatus.STOPPED)

        # Step 4: Send notification email
        if user_info:
            try:
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[user_info['email']],
                    template_name="instance_stopped",
                    template_variables={
                        "first_name": user_info['first_name'],
                        "instance_name": instance['name'],
                        "reason": "Instance stopped by user request"
                    },
                    tags=["instance", "lifecycle", "stopped"]
                )
                logger.info("Instance stopped email sent", email=user_info['email'])
            except Exception as e:
                logger.error("Failed to send email", error=str(e))

        return {
            "status": "success",
            "message": "Instance stopped successfully on Kubernetes"
        }

    except Exception as e:
        logger.error("Stop workflow failed", error=str(e))
        await _update_instance_status(instance_id, InstanceStatus.ERROR, str(e))
        raise


# Keep database helper functions unchanged
async def _get_instance_from_db(instance_id: str) -> Dict[str, Any]:
    """Get instance from database (unchanged)"""
    # ... (keep original implementation)
    pass


async def _update_instance_status(instance_id: str, status: InstanceStatus, error_message: str = None):
    """Update instance status (unchanged)"""
    # ... (keep original implementation)
    pass


async def _update_instance_network_info(instance_id: str, result: Dict[str, Any]):
    """Update instance network info"""
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'postgres'),
        port=5432,
        database=os.getenv('POSTGRES_DB', 'instance'),
        user=os.getenv('DB_SERVICE_USER', 'instance_service'),
        password=os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me')
    )

    try:
        await conn.execute("""
            UPDATE instances
            SET internal_url = $1, external_url = $2, updated_at = $3
            WHERE id = $4
        """,
            result.get('internal_url'),
            result.get('external_url'),
            datetime.utcnow(),
            UUID(instance_id)
        )

        logger.info("Instance network info updated", instance_id=instance_id)
    finally:
        await conn.close()


async def _get_user_info(customer_id: str) -> Dict[str, Any]:
    """Get user info (unchanged)"""
    # ... (keep original implementation)
    pass
```

---

## Phase 5: Helm Charts

Create Helm chart for easier deployment management.

**Create Helm chart structure:**

```bash
mkdir -p infrastructure/helm/saasodoo-platform
cd infrastructure/helm/saasodoo-platform

# Create chart structure
mkdir -p templates/{services,monitoring,storage}
```

**Chart.yaml:**

```yaml
# infrastructure/helm/saasodoo-platform/Chart.yaml
apiVersion: v2
name: saasodoo-platform
description: SaaS Odoo Platform on Kubernetes
type: application
version: 1.0.0
appVersion: "1.0.0"
keywords:
  - odoo
  - saas
  - multi-tenant
maintainers:
  - name: SaaS Odoo Team
    email: support@saasodoo.com
```

**values.yaml:**

```yaml
# infrastructure/helm/saasodoo-platform/values.yaml

global:
  baseDomain: saasodoo.local
  namespace: saasodoo
  storageClass: cephfs-quota

postgres:
  enabled: true
  image:
    repository: postgres
    tag: 15-alpine
  storage: 50Gi
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi

redis:
  enabled: true
  image:
    repository: redis
    tag: 7-alpine
  storage: 10Gi
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 1Gi

rabbitmq:
  enabled: true
  image:
    repository: rabbitmq
    tag: 3-management-alpine
  storage: 20Gi
  resources:
    requests:
      cpu: 200m
      memory: 512Mi
    limits:
      cpu: 1000m
      memory: 2Gi

userService:
  enabled: true
  image:
    repository: your-registry/user-service
    tag: latest
  replicas: 2
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 1Gi

billingService:
  enabled: true
  image:
    repository: your-registry/billing-service
    tag: latest
  replicas: 2
  resources:
    requests:
      cpu: 200m
      memory: 256Mi
    limits:
      cpu: 1000m
      memory: 1Gi

instanceService:
  enabled: true
  image:
    repository: your-registry/instance-service
    tag: latest
  replicas: 2
  resources:
    requests:
      cpu: 500m
      memory: 512Mi
    limits:
      cpu: 2000m
      memory: 2Gi

  worker:
    replicas: 3
    resources:
      requests:
        cpu: 500m
        memory: 512Mi
      limits:
        cpu: 2000m
        memory: 2Gi

odooInstances:
  namespace: odoo-instances
  defaultVersion: "17"
  defaultResources:
    cpu: 1.0
    memory: 2Gi
    storage: 10Gi
```

**Install Helm chart:**

```bash
helm install saasodoo ./infrastructure/helm/saasodoo-platform \
  --namespace saasodoo \
  --create-namespace \
  --values ./infrastructure/helm/saasodoo-platform/values.yaml
```

---

## Phase 6: Testing & Validation

### Test 1: Create Instance via API

```bash
# Test instance provisioning
curl -X POST http://api.localhost/instance/instances \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "name": "test-instance",
    "odoo_version": "17",
    "admin_email": "admin@test.com",
    "demo_data": true,
    "cpu_limit": 1.0,
    "memory_limit": "2Gi",
    "storage_limit": "10Gi"
  }'

# Get instance status
INSTANCE_ID="<returned-instance-id>"
curl http://api.localhost/instance/instances/$INSTANCE_ID \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Test 2: Verify Kubernetes Resources

```bash
# Check deployment
kubectl get deployments -n odoo-instances

# Check pods
kubectl get pods -n odoo-instances

# Check PVCs
kubectl get pvc -n odoo-instances

# Check services
kubectl get services -n odoo-instances

# Check ingresses
kubectl get ingresses -n odoo-instances

# Get pod logs
POD_NAME=$(kubectl get pods -n odoo-instances -l saasodoo.io/instance-id=$INSTANCE_ID -o name)
kubectl logs -n odoo-instances $POD_NAME --tail=100
```

### Test 3: Test Instance Lifecycle

```bash
# Stop instance
curl -X POST http://api.localhost/instance/instances/$INSTANCE_ID/stop \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Verify scaled to 0
kubectl get deployments -n odoo-instances

# Start instance
curl -X POST http://api.localhost/instance/instances/$INSTANCE_ID/start \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Verify scaled to 1
kubectl get deployments -n odoo-instances

# Access instance
curl http://test-instance.saasodoo.local
```

### Test 4: Load Test

```bash
# Create 10 test instances concurrently
for i in {1..10}; do
  curl -X POST http://api.localhost/instance/instances \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer YOUR_JWT_TOKEN" \
    -d "{
      \"name\": \"load-test-$i\",
      \"odoo_version\": \"17\",
      \"admin_email\": \"admin@test.com\",
      \"demo_data\": false,
      \"cpu_limit\": 0.5,
      \"memory_limit\": \"1Gi\",
      \"storage_limit\": \"5Gi\"
    }" &
done

wait

# Check all instances
kubectl get pods -n odoo-instances
```

---

## Summary of Code Changes

### What Changed:
1. **Docker SDK → Kubernetes Python Client**: Completely removed `docker` library, replaced all calls with `kubernetes` library
2. **Services → Deployments**: Swarm services became Kubernetes Deployments
3. **Volumes → PVCs**: Docker volumes became PersistentVolumeClaims
4. **Traefik Labels → Ingress**: Service labels became Ingress resources
5. **Scale Operations**: `service.update(replicas=N)` became `deployment.spec.replicas = N`

### What Stayed the Same:
1. **Database operations**: PostgreSQL interactions unchanged
2. **Business logic**: Instance lifecycle logic unchanged
3. **Celery tasks**: Task structure unchanged, only orchestration changed
4. **API endpoints**: FastAPI routes unchanged
5. **Environment variables**: Configuration approach unchanged

### Files to Delete Completely:
- `services/instance-service/app/utils/docker_client.py` - DELETE (no longer needed)
- All Docker SDK imports from provisioning/lifecycle tasks

### Files to Modify:
- `services/instance-service/requirements.txt` - Remove `docker==7.0.0`
- `services/instance-service/app/tasks/provisioning.py` - Remove all Docker imports, replace with K8s
- `services/instance-service/app/tasks/lifecycle.py` - Remove all Docker imports, replace with K8s
- `services/instance-service/app/tasks/maintenance.py` - Remove all Docker imports, replace with K8s

### Migration Effort:
- **Low effort**: Supporting services (postgres, redis, rabbitmq)
- **Medium effort**: Microservices (user, billing, frontend, notification)
- **High effort**: Instance service (core provisioning logic)

**Total estimated time**: 8-10 weeks for complete migration to production with 10,000 instances.

---

## Docker SDK Removal Checklist

**Step 1: Remove Docker SDK dependency**
```bash
cd services/instance-service
pip uninstall docker -y
# Edit requirements.txt and remove the docker==7.0.0 line
```

**Step 2: Delete docker_client.py**
```bash
rm services/instance-service/app/utils/docker_client.py
```

**Step 3: Update all imports**
Replace all occurrences of:
```python
# OLD - DELETE THESE
import docker
from docker import types
from app.utils.docker_client import get_docker_client, DockerClientWrapper

# NEW - USE THESE
from kubernetes import client, config
from app.utils.k8s_client import get_k8s_client, KubernetesClientWrapper
```

**Step 4: Update provisioning.py**
Remove these lines:
```python
import docker  # DELETE
from app.utils.docker_client import get_docker_client  # DELETE
```

Replace Docker operations with Kubernetes operations (see full code above).

**Step 5: Update lifecycle.py**
Remove these lines:
```python
import docker  # DELETE
from app.utils.docker_client import get_docker_client  # DELETE
```

Replace Docker operations with Kubernetes operations (see full code above).

**Step 6: Update maintenance.py**
If it exists and uses Docker, apply same changes.

**Step 7: Verify no Docker references remain**
```bash
cd services/instance-service
grep -r "import docker" . --exclude-dir=venv
grep -r "docker.from_env" . --exclude-dir=venv
grep -r "docker_client" . --exclude-dir=venv
# Should return no results
```
