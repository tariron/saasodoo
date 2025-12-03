# SaaSOdoo Kubernetes Migration Plan - RKE2 Production Deployment

## Executive Summary

**Migration Strategy**: Fresh deployment - Build production RKE2 cluster, migrate data from Docker Swarm

**Timeline**: 10 weeks (3 phases)
- Phase 1 (Weeks 1-3): Infrastructure & Core Services
- Phase 2 (Weeks 4-7): Application Migration & Testing
- Phase 3 (Weeks 8-10): Production Hardening & Scale Testing

**Current State**: Docker Swarm on 3 nodes with CephFS storage
**Target State**: RKE2 Kubernetes cluster, scalable to 10,000 Odoo instances

**No Clients Yet**: Fresh start - no migration downtime concerns

---

## Technology Stack (November 2025)

| Component          | Version        | Purpose                          |
| ------------------ | -------------- | -------------------------------- |
| **RKE2**           | v1.32.1+rke2r1 | Production Kubernetes with etcd  |
| **Kubernetes**     | v1.32.2        | Container orchestration          |
| **Cilium**         | v1.17.0        | eBPF CNI, kube-proxy replacement |
| **Rook-Ceph**      | v1.18.7        | CephFS CSI driver                |
| **MetalLB**        | v0.15.2        | L2 load-balancer                 |
| **Traefik**        | v3.5.1         | Ingress controller (CRD-only)    |
| **Sealed Secrets** | v0.27.0        | Encrypted secrets in Git         |
| **Velero**         | v1.11.1        | Cluster backup & DR              |
| **Prometheus**     | v2.53.0        | Metrics collection               |
| **Grafana**        | v11.4.0        | Dashboards & visualization       |
| **Loki**           | v3.6.2         | Log aggregation                  |

---

## Directory Structure

```
kubernetes/
├── README.md                           # Quick start guide
├── Makefile                            # Deployment automation
├── .gitignore                          # Exclude secrets/
├── cluster/
│   ├── rke2-config.yaml               # RKE2 configuration template
│   ├── install-server.sh              # Control plane installation
│   ├── install-agent.sh               # Worker node installation
│   └── cilium-config.yaml             # Cilium CNI configuration
├── infrastructure/
│   ├── 00-namespaces.yaml             # saasodoo, monitoring, backup
│   ├── storage/
│   │   └── rook-ceph/
│   │       ├── 01-operator.yaml       # Rook operator
│   │       ├── 02-cluster.yaml        # Connect to existing Ceph
│   │       ├── 03-filesystem.yaml     # CephFS configuration
│   │       └── 04-storageclass.yaml   # PVC provisioner
│   ├── networking/
│   │   ├── metallb/
│   │   │   ├── 01-namespace.yaml
│   │   │   ├── 02-ip-pool.yaml
│   │   │   └── 03-l2-advert.yaml
│   │   └── traefik/
│   │       ├── 01-crds.yaml           # Traefik CRDs
│   │       ├── 02-rbac.yaml
│   │       ├── 03-deployment.yaml
│   │       ├── 04-service.yaml
│   │       └── 05-middlewares.yaml    # CORS, strip-prefix, etc.
│   ├── databases/
│   │   ├── 01-postgres-platform.yaml  # auth, billing, instance DBs
│   │   ├── 02-postgres-instances.yaml # Odoo databases
│   │   ├── 03-redis.yaml
│   │   ├── 04-rabbitmq.yaml
│   │   ├── 05-killbill-db.yaml        # MariaDB
│   │   └── 06-killbill.yaml           # Billing engine
│   └── secrets/
│       ├── 00-sealed-secrets-controller.yaml
│       ├── 01-create-sealed-secret.sh
│       └── README.md                  # How to seal secrets
├── services/
│   ├── user-service/
│   │   ├── 01-deployment.yaml
│   │   ├── 02-service.yaml
│   │   ├── 03-ingressroute.yaml
│   │   └── 04-hpa.yaml                # Horizontal pod autoscaler
│   ├── instance-service/
│   │   ├── 01-rbac.yaml               # ServiceAccount, Role, RoleBinding
│   │   ├── 02-deployment.yaml
│   │   ├── 03-service.yaml
│   │   └── 04-ingressroute.yaml
│   ├── instance-worker/
│   │   ├── 01-deployment.yaml
│   │   └── 02-hpa.yaml
│   ├── billing-service/
│   │   ├── 01-deployment.yaml
│   │   ├── 02-service.yaml
│   │   └── 03-ingressroute.yaml
│   ├── notification-service/
│   │   ├── 01-deployment.yaml
│   │   ├── 02-service.yaml
│   │   └── 03-ingressroute.yaml
│   └── frontend-service/
│       ├── 01-deployment.yaml
│       ├── 02-service.yaml
│       └── 03-ingressroute.yaml
├── instances/
│   ├── templates/
│   │   ├── deployment.yaml.j2         # Jinja2 template
│   │   ├── service.yaml.j2
│   │   ├── pvc.yaml.j2
│   │   └── ingressroute.yaml.j2
│   └── README.md                      # Instance provisioning guide
├── monitoring/
│   ├── prometheus/
│   │   ├── 01-namespace.yaml
│   │   ├── 02-operator.yaml
│   │   ├── 03-prometheus.yaml
│   │   └── 04-servicemonitors.yaml
│   ├── grafana/
│   │   ├── 01-deployment.yaml
│   │   ├── 02-service.yaml
│   │   ├── 03-ingressroute.yaml
│   │   └── 04-dashboards-configmap.yaml
│   └── loki/
│       ├── 01-deployment.yaml
│       ├── 02-service.yaml
│       └── 03-promtail-daemonset.yaml
├── backup/
│   └── velero/
│       ├── 01-install.sh
│       ├── 02-minio.yaml              # S3-compatible storage
│       └── 03-schedule.yaml           # Daily backups
├── tests/
│   ├── smoke-test.sh                  # Verify all services
│   ├── provision-test-instance.sh     # Create 1 Odoo instance
│   ├── provision-100-instances.sh     # Load test
│   └── cleanup.sh                     # Remove test resources
└── secrets/                           # GITIGNORED - never commit!
    ├── saasodoo.env                   # Copy your .env here
    └── kubeconfig                     # RKE2 kubeconfig
```

---

## Phase 1: Infrastructure Setup (Weeks 1-3)

### Week 1: RKE2 Cluster Installation

#### Prerequisites

**Hardware:**
- 3 nodes minimum (control plane + workers)
- 16GB RAM per node (minimum 8GB)
- 100GB disk per node
- Ubuntu 22.04 LTS or RHEL 9
- Static IPs or DHCP reservations
- CephFS already mounted at `/mnt/cephfs`

#### Day 1-2: Install RKE2 Control Plane

**Create RKE2 configuration:**

`kubernetes/cluster/rke2-config.yaml`:
```yaml
# /etc/rancher/rke2/config.yaml on server nodes
write-kubeconfig-mode: "0644"
cni: cilium
disable:
  - rke2-ingress-nginx
  - rke2-metrics-server
disable-kube-proxy: true  # Cilium replaces kube-proxy

# etcd tuning for 10,000 pods
etcd-arg:
  - "quota-backend-bytes=8589934592"      # 8GB
  - "max-request-bytes=33554432"          # 32MB
  - "heartbeat-interval=500"
  - "election-timeout=5000"

# API server tuning
kube-apiserver-arg:
  - "max-requests-inflight=3000"
  - "max-mutating-requests-inflight=1000"
  - "watch-cache-sizes=deployments.apps#2000,services#2000,pods#10000"
  - "default-watch-cache-size=1000"

# Controller manager tuning
kube-controller-manager-arg:
  - "concurrent-deployment-syncs=20"
  - "concurrent-statefulset-syncs=10"
  - "concurrent-gc-syncs=30"
  - "kube-api-qps=200"
  - "kube-api-burst=400"
  - "node-cidr-mask-size=23"  # Allows 512 IPs per node

# Kubelet tuning
kubelet-arg:
  - "max-pods=250"            # Up from 110 default
  - "pods-per-core=0"         # No CPU-based limit
  - "eviction-hard=memory.available<500Mi,nodefs.available<10%"
  - "kube-api-qps=100"
  - "kube-api-burst=200"

# TLS SAN for API access
tls-san:
  - "api.yourdomain.com"
  - "192.168.1.10"  # Your load balancer IP
```

**Installation script:**

`kubernetes/cluster/install-server.sh`:
```bash
#!/bin/bash
set -e

# Install RKE2 server (control plane)
NODE_NUM=${1:-1}
echo "Installing RKE2 server node $NODE_NUM"

# Copy config
sudo mkdir -p /etc/rancher/rke2
sudo cp rke2-config.yaml /etc/rancher/rke2/config.yaml

if [ "$NODE_NUM" -eq 1 ]; then
    # First server node
    curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION=v1.32.1+rke2r1 sh -
    sudo systemctl enable rke2-server.service
    sudo systemctl start rke2-server.service

    # Wait for cluster to be ready
    sleep 30

    # Get token for other nodes
    sudo cat /var/lib/rancher/rke2/server/node-token > /tmp/rke2-token
    echo "Token saved to /tmp/rke2-token"
    echo "Copy this token to other server nodes"

    # Install kubectl
    sudo cp /var/lib/rancher/rke2/bin/kubectl /usr/local/bin/
    mkdir -p ~/.kube
    sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config
    sudo chown $(id -u):$(id -g) ~/.kube/config

    echo "RKE2 server node 1 installed successfully"
    kubectl get nodes
else
    # Additional server nodes (HA)
    echo "Enter the IP of the first server node:"
    read FIRST_SERVER_IP
    echo "Enter the token from /tmp/rke2-token on server 1:"
    read RKE2_TOKEN

    echo "server: https://${FIRST_SERVER_IP}:9345" | sudo tee -a /etc/rancher/rke2/config.yaml
    echo "token: ${RKE2_TOKEN}" | sudo tee -a /etc/rancher/rke2/config.yaml

    curl -sfL https://get.rke2.io | INSTALL_RKE2_VERSION=v1.32.1+rke2r1 sh -
    sudo systemctl enable rke2-server.service
    sudo systemctl start rke2-server.service

    echo "RKE2 server node $NODE_NUM joined successfully"
fi
```

**Run installation:**
```bash
cd kubernetes/cluster

# On first node
chmod +x install-server.sh
sudo ./install-server.sh 1

# Verify
kubectl get nodes
kubectl get pods -A
```

**For HA (3 control plane nodes):**
```bash
# On node 2 and 3
sudo ./install-server.sh 2
sudo ./install-server.sh 3
```

#### Day 3: Add Worker Nodes

`kubernetes/cluster/install-agent.sh`:
```bash
#!/bin/bash
set -e

echo "Installing RKE2 agent (worker node)"
echo "Enter the IP of a server node:"
read SERVER_IP
echo "Enter the RKE2 token:"
read RKE2_TOKEN

# Create config
sudo mkdir -p /etc/rancher/rke2
cat <<EOF | sudo tee /etc/rancher/rke2/config.yaml
server: https://${SERVER_IP}:9345
token: ${RKE2_TOKEN}
kubelet-arg:
  - "max-pods=250"
  - "kube-api-qps=100"
EOF

# Install
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE="agent" INSTALL_RKE2_VERSION=v1.32.1+rke2r1 sh -
sudo systemctl enable rke2-agent.service
sudo systemctl start rke2-agent.service

echo "RKE2 agent installed successfully"
```

**Add workers:**
```bash
# On each worker node
sudo ./install-agent.sh

# Verify on control plane
kubectl get nodes
# Should show all nodes Ready
```

#### Day 4-5: Install Cilium CNI

**Why Cilium?**
- eBPF-based networking (faster than traditional CNI)
- Replaces kube-proxy (better performance)
- Built-in network policies
- Hubble observability

`kubernetes/cluster/cilium-config.yaml`:
```yaml
# Cilium Helm values
# Install with: helm install cilium cilium/cilium --version 1.17.0 -n kube-system -f cilium-config.yaml

kubeProxyReplacement: true  # eBPF kube-proxy replacement
k8sServiceHost: 192.168.1.10  # Your control plane IP
k8sServicePort: 6443

# Performance optimizations
bpf:
  masquerade: true
  tproxy: true
  hostLegacyRouting: false

# Enable Hubble for observability (optional)
hubble:
  enabled: true
  relay:
    enabled: true
  ui:
    enabled: true

# Resource limits
resources:
  limits:
    cpu: 4000m
    memory: 4Gi
  requests:
    cpu: 100m
    memory: 512Mi

# Enable Bandwidth Manager for better performance
bandwidthManager:
  enabled: true
  bbr: true

# IPv4 native routing
ipam:
  mode: kubernetes
tunnel: disabled
autoDirectNodeRoutes: true
ipv4NativeRoutingCIDR: 10.42.0.0/16  # RKE2 default pod CIDR
```

**Install Cilium:**
```bash
# Add Cilium Helm repo
helm repo add cilium https://helm.cilium.io/
helm repo update

# Install
helm install cilium cilium/cilium \
  --version 1.17.0 \
  --namespace kube-system \
  -f kubernetes/cluster/cilium-config.yaml

# Wait for Cilium to be ready
kubectl -n kube-system rollout status ds/cilium

# Verify
kubectl -n kube-system get pods -l k8s-app=cilium
cilium status
```

**Verify cluster health:**
```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl cluster-info
```

---

### Week 2: Storage & Networking

#### Day 1-2: Rook-Ceph Storage Integration

**Connect to existing CephFS:**

`kubernetes/infrastructure/storage/rook-ceph/01-operator.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: rook-ceph
---
# Download official operator manifest
# kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/crds.yaml
# kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/common.yaml
# kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/operator.yaml
```

`kubernetes/infrastructure/storage/rook-ceph/02-cluster.yaml`:
```yaml
# External Ceph cluster connection
# This connects to your existing Ceph cluster at /mnt/cephfs
apiVersion: ceph.rook.io/v1
kind: CephCluster
metadata:
  name: rook-ceph-external
  namespace: rook-ceph
spec:
  external:
    enable: true
  dataDirHostPath: /var/lib/rook
```

`kubernetes/infrastructure/storage/rook-ceph/03-filesystem.yaml`:
```yaml
apiVersion: ceph.rook.io/v1
kind: CephFilesystem
metadata:
  name: saasodoo-cephfs
  namespace: rook-ceph
spec:
  metadataPool:
    replicated:
      size: 3
      requireSafeReplicaSize: true
  dataPools:
    - name: replicated
      replicated:
        size: 3
        requireSafeReplicaSize: true
  preserveFilesystemOnDelete: true
  metadataServer:
    activeCount: 1
    activeStandby: true
    resources:
      limits:
        cpu: "2"
        memory: 4Gi
      requests:
        cpu: "1"
        memory: 2Gi
```

`kubernetes/infrastructure/storage/rook-ceph/04-storageclass.yaml`:
```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cephfs-odoo
provisioner: rook-ceph.cephfs.csi.ceph.com
parameters:
  clusterID: rook-ceph
  fsName: saasodoo-cephfs
  pool: saasodoo-cephfs-replicated
  csi.storage.k8s.io/provisioner-secret-name: rook-csi-cephfs-provisioner
  csi.storage.k8s.io/provisioner-secret-namespace: rook-ceph
  csi.storage.k8s.io/controller-expand-secret-name: rook-csi-cephfs-provisioner
  csi.storage.k8s.io/controller-expand-secret-namespace: rook-ceph
  csi.storage.k8s.io/node-stage-secret-name: rook-csi-cephfs-node
  csi.storage.k8s.io/node-stage-secret-namespace: rook-ceph
reclaimPolicy: Retain
allowVolumeExpansion: true
volumeBindingMode: Immediate
---
# Local storage for platform services (faster)
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: local-path
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: rancher.io/local-path
volumeBindingMode: WaitForFirstConsumer
reclaimPolicy: Delete
```

**Deploy storage:**
```bash
cd kubernetes/infrastructure/storage/rook-ceph

# Install Rook operator
kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/crds.yaml
kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/common.yaml
kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/operator.yaml

# Wait for operator
kubectl -n rook-ceph get pods -w

# Apply cluster configuration
kubectl apply -f 02-cluster.yaml
kubectl apply -f 03-filesystem.yaml
kubectl apply -f 04-storageclass.yaml

# Verify
kubectl get sc
kubectl get cephfilesystem -n rook-ceph
```

#### Day 3: MetalLB Load Balancer

`kubernetes/infrastructure/networking/metallb/01-namespace.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: metallb-system
```

`kubernetes/infrastructure/networking/metallb/02-ip-pool.yaml`:
```yaml
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
  - 192.168.1.240-192.168.1.250  # CHANGE THIS to your network range
```

`kubernetes/infrastructure/networking/metallb/03-l2-advert.yaml`:
```yaml
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default-l2-advert
  namespace: metallb-system
spec:
  ipAddressPools:
  - default-pool
```

**Deploy MetalLB:**
```bash
cd kubernetes/infrastructure/networking/metallb

# Install MetalLB
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.15.2/config/manifests/metallb-native.yaml

# Wait for pods
kubectl -n metallb-system wait --for=condition=ready pod -l app=metallb --timeout=300s

# Apply configuration
kubectl apply -f 01-namespace.yaml
kubectl apply -f 02-ip-pool.yaml
kubectl apply -f 03-l2-advert.yaml

# Verify
kubectl -n metallb-system get pods
kubectl get ipaddresspools -n metallb-system
```

#### Day 4-5: Traefik Ingress Controller

`kubernetes/infrastructure/networking/traefik/01-crds.yaml`:
```yaml
# Download Traefik CRDs
# kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.5/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
```

`kubernetes/infrastructure/networking/traefik/02-rbac.yaml`:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: traefik
  namespace: kube-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: traefik
rules:
  - apiGroups:
      - ""
    resources:
      - services
      - secrets
    verbs:
      - get
      - list
      - watch
  - apiGroups:
      - traefik.io
    resources:
      - ingressroutes
      - middlewares
      - tlsoptions
      - ingressroutetcps
      - ingressrouteudps
      - tlsstores
      - serverstransports
    verbs:
      - get
      - list
      - watch
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: traefik
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: traefik
subjects:
  - kind: ServiceAccount
    name: traefik
    namespace: kube-system
```

`kubernetes/infrastructure/networking/traefik/03-deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: traefik
  namespace: kube-system
  labels:
    app: traefik
spec:
  replicas: 2
  selector:
    matchLabels:
      app: traefik
  template:
    metadata:
      labels:
        app: traefik
    spec:
      serviceAccountName: traefik
      containers:
      - name: traefik
        image: traefik:v3.5.1
        args:
          - --log.level=INFO
          - --accesslog=true
          - --api.insecure=true
          - --api.dashboard=true
          - --ping=true
          - --providers.kubernetescrd=true
          - --providers.kubernetescrd.allowCrossNamespace=true
          - --entrypoints.web.address=:80
          - --entrypoints.websecure.address=:443
          - --metrics.prometheus=true
          - --metrics.prometheus.addEntryPointsLabels=true
          - --metrics.prometheus.addServicesLabels=true
        ports:
        - name: web
          containerPort: 80
        - name: websecure
          containerPort: 443
        - name: admin
          containerPort: 8080
        - name: metrics
          containerPort: 9100
        livenessProbe:
          httpGet:
            path: /ping
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 10
        resources:
          limits:
            cpu: 2
            memory: 1Gi
          requests:
            cpu: 100m
            memory: 256Mi
```

`kubernetes/infrastructure/networking/traefik/04-service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: traefik
  namespace: kube-system
  labels:
    app: traefik
spec:
  type: LoadBalancer
  selector:
    app: traefik
  ports:
  - name: web
    port: 80
    targetPort: 80
  - name: websecure
    port: 443
    targetPort: 443
```

`kubernetes/infrastructure/networking/traefik/05-middlewares.yaml`:
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-user-prefix
  namespace: saasodoo
spec:
  stripPrefix:
    prefixes:
      - /user
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-billing-prefix
  namespace: saasodoo
spec:
  stripPrefix:
    prefixes:
      - /billing
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: strip-instance-prefix
  namespace: saasodoo
spec:
  stripPrefix:
    prefixes:
      - /instance
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: api-cors
  namespace: saasodoo
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
---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: security-headers
  namespace: saasodoo
spec:
  headers:
    frameDeny: true
    browserXssFilter: true
    contentTypeNosniff: true
    sslRedirect: false
```

**Deploy Traefik:**
```bash
cd kubernetes/infrastructure/networking/traefik

# Install CRDs
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.5/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml

# Deploy Traefik
kubectl apply -f 02-rbac.yaml
kubectl apply -f 03-deployment.yaml
kubectl apply -f 04-service.yaml

# Wait for LoadBalancer IP
kubectl -n kube-system get svc traefik -w

# Get IP and update DNS
TRAEFIK_IP=$(kubectl -n kube-system get svc traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo "Traefik LoadBalancer IP: $TRAEFIK_IP"

# Update your DNS:
# *.yourdomain.com -> $TRAEFIK_IP
# api.yourdomain.com -> $TRAEFIK_IP
# app.yourdomain.com -> $TRAEFIK_IP
```

---

### Week 3: Secrets Management

#### Sealed Secrets Setup

**Why Sealed Secrets?**
- Encrypt secrets before committing to Git
- Only cluster can decrypt
- GitOps-friendly

`kubernetes/infrastructure/secrets/00-sealed-secrets-controller.yaml`:
```bash
#!/bin/bash
# Download and install sealed secrets controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.0/controller.yaml

# Install kubeseal CLI
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.0/kubeseal-0.27.0-linux-amd64.tar.gz
tar -xvzf kubeseal-0.27.0-linux-amd64.tar.gz
sudo mv kubeseal /usr/local/bin/
rm kubeseal-0.27.0-linux-amd64.tar.gz
```

`kubernetes/infrastructure/secrets/01-create-sealed-secret.sh`:
```bash
#!/bin/bash
set -e

# This script creates a sealed secret from your .env file
# The sealed secret can be safely committed to Git

ENV_FILE="../../secrets/saasodoo.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    echo "Please copy your .env file to kubernetes/secrets/saasodoo.env"
    exit 1
fi

echo "Creating Kubernetes secret from $ENV_FILE..."

# Create namespace first
kubectl create namespace saasodoo --dry-run=client -o yaml | kubectl apply -f -

# Create secret from .env file (not applied to cluster yet)
kubectl create secret generic saasodoo-env \
  --from-env-file="$ENV_FILE" \
  --namespace=saasodoo \
  --dry-run=client \
  -o yaml > /tmp/saasodoo-secret.yaml

# Seal the secret
echo "Sealing secret with cluster's public key..."
kubeseal --format=yaml \
  --cert=/dev/null \
  < /tmp/saasodoo-secret.yaml \
  > 02-saasodoo-secret.sealed.yaml

echo "✅ Sealed secret created: 02-saasodoo-secret.sealed.yaml"
echo "This file can be safely committed to Git"

# Clean up temp file
rm /tmp/saasodoo-secret.yaml
```

**Create sealed secret:**
```bash
cd kubernetes/infrastructure/secrets

# Copy your .env file
cp /root/saasodoo/.env ../../secrets/saasodoo.env

# Install sealed secrets controller
bash 00-sealed-secrets-controller.yaml

# Create sealed secret
bash 01-create-sealed-secret.sh

# Apply to cluster
kubectl apply -f 02-saasodoo-secret.sealed.yaml

# Verify
kubectl -n saasodoo get secret saasodoo-env
```

---

## Phase 2: Application Migration (Weeks 4-7)

### Week 4: Database Deployments

#### Create Namespace

`kubernetes/infrastructure/00-namespaces.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: saasodoo
---
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
---
apiVersion: v1
kind: Namespace
metadata:
  name: backup
```

```bash
kubectl apply -f kubernetes/infrastructure/00-namespaces.yaml
```

#### PostgreSQL Platform (auth, billing, instance, communication)

`kubernetes/infrastructure/databases/01-postgres-platform.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: postgres-platform-init
  namespace: saasodoo
data:
  init-databases.sh: |
    #!/bin/bash
    set -e
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
        CREATE DATABASE auth;
        CREATE DATABASE billing;
        CREATE DATABASE instance;
        CREATE DATABASE communication;

        -- Create service users
        CREATE USER auth_service WITH PASSWORD '$POSTGRES_AUTH_SERVICE_PASSWORD';
        CREATE USER billing_service WITH PASSWORD '$POSTGRES_BILLING_SERVICE_PASSWORD';
        CREATE USER instance_service WITH PASSWORD '$POSTGRES_INSTANCE_SERVICE_PASSWORD';
        CREATE USER notification_service WITH PASSWORD '$POSTGRES_NOTIFICATION_SERVICE_PASSWORD';

        -- Grant privileges
        GRANT ALL PRIVILEGES ON DATABASE auth TO auth_service;
        GRANT ALL PRIVILEGES ON DATABASE billing TO billing_service;
        GRANT ALL PRIVILEGES ON DATABASE instance TO instance_service;
        GRANT ALL PRIVILEGES ON DATABASE communication TO notification_service;
    EOSQL
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres-platform
  namespace: saasodoo
spec:
  serviceName: postgres-platform
  replicas: 1
  selector:
    matchLabels:
      app: postgres-platform
  template:
    metadata:
      labels:
        app: postgres-platform
    spec:
      containers:
      - name: postgres
        image: postgres:18-alpine
        envFrom:
        - secretRef:
            name: saasodoo-env
        env:
        - name: POSTGRES_DB
          value: "postgres"
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        ports:
        - containerPort: 5432
          name: postgres
        volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql
        - name: init-script
          mountPath: /docker-entrypoint-initdb.d
        resources:
          limits:
            cpu: "2"
            memory: 4Gi
          requests:
            cpu: "500m"
            memory: 1Gi
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - postgres
          initialDelaySeconds: 30
          periodSeconds: 10
      volumes:
      - name: init-script
        configMap:
          name: postgres-platform-init
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: local-path
      resources:
        requests:
          storage: 50Gi
---
apiVersion: v1
kind: Service
metadata:
  name: postgres-platform
  namespace: saasodoo
spec:
  selector:
    app: postgres-platform
  ports:
  - port: 5432
    targetPort: 5432
  clusterIP: None
```

Apply similar patterns for:
- `02-postgres-instances.yaml` (Odoo databases)
- `03-redis.yaml`
- `04-rabbitmq.yaml`
- `05-killbill-db.yaml`
- `06-killbill.yaml`

**Deploy databases:**
```bash
cd kubernetes/infrastructure/databases

kubectl apply -f 01-postgres-platform.yaml
kubectl apply -f 02-postgres-instances.yaml
kubectl apply -f 03-redis.yaml
kubectl apply -f 04-rabbitmq.yaml
kubectl apply -f 05-killbill-db.yaml

# Wait for databases to be ready
kubectl -n saasodoo get pods -w

# Deploy KillBill (depends on killbill-db)
kubectl apply -f 06-killbill.yaml
```

---

### Week 5-6: Microservices Deployment

#### Instance Service with RBAC

`kubernetes/services/instance-service/01-rbac.yaml`:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: instance-service
  namespace: saasodoo
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: instance-service
  namespace: saasodoo
rules:
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: [""]
  resources: ["services", "pods", "persistentvolumeclaims", "configmaps"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
- apiGroups: ["traefik.io"]
  resources: ["ingressroutes", "middlewares"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: instance-service
  namespace: saasodoo
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: instance-service
subjects:
- kind: ServiceAccount
  name: instance-service
  namespace: saasodoo
```

`kubernetes/services/instance-service/02-deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: instance-service
  namespace: saasodoo
  labels:
    app: instance-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: instance-service
  template:
    metadata:
      labels:
        app: instance-service
    spec:
      serviceAccountName: instance-service
      containers:
      - name: instance-service
        image: registry.yourdomain.com/saasodoo-instance-service:latest
        envFrom:
        - secretRef:
            name: saasodoo-env
        env:
        - name: KUBERNETES_NAMESPACE
          value: saasodoo
        - name: IN_CLUSTER
          value: "true"
        ports:
        - containerPort: 8003
          name: http
        livenessProbe:
          httpGet:
            path: /health
            port: 8003
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8003
          initialDelaySeconds: 10
          periodSeconds: 5
        resources:
          limits:
            cpu: "1"
            memory: 1Gi
          requests:
            cpu: "200m"
            memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: instance-service
  namespace: saasodoo
spec:
  selector:
    app: instance-service
  ports:
  - port: 8003
    targetPort: 8003
```

`kubernetes/services/instance-service/04-ingressroute.yaml`:
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: instance-service
  namespace: saasodoo
spec:
  entryPoints:
    - web
  routes:
  - match: Host(`api.yourdomain.com`) && PathPrefix(`/instance`)
    kind: Rule
    services:
    - name: instance-service
      port: 8003
    middlewares:
    - name: strip-instance-prefix
    - name: api-cors
    - name: security-headers
```

**Deploy all services:**
```bash
cd kubernetes/services

# Deploy in order
kubectl apply -f instance-service/
kubectl apply -f instance-worker/
kubectl apply -f user-service/
kubectl apply -f billing-service/
kubectl apply -f notification-service/
kubectl apply -f frontend-service/

# Verify
kubectl -n saasodoo get pods
kubectl -n saasodoo get svc
kubectl -n saasodoo get ingressroute
```

---

### Week 7: Code Changes - Instance Service

#### Update requirements.txt

`services/instance-service/requirements.txt`:
```txt
# Remove
# docker==7.1.0

# Add
kubernetes==31.0.0
jinja2==3.1.4
```

#### Create Kubernetes Client

`services/instance-service/app/utils/k8s_client.py`:
```python
"""
Kubernetes client for managing Odoo instance deployments.
Replaces Docker SDK with Kubernetes Python client.
"""

import os
import logging
from typing import Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from jinja2 import Template

logger = logging.getLogger(__name__)


class KubernetesClient:
    """Kubernetes API client for Odoo instance management."""

    def __init__(self, namespace: str = "saasodoo"):
        """Initialize Kubernetes client."""
        self.namespace = namespace

        # Load config: in-cluster if running in K8s, otherwise use kubeconfig
        try:
            if os.getenv("IN_CLUSTER", "false").lower() == "true":
                config.load_incluster_config()
                logger.info("Loaded in-cluster Kubernetes config")
            else:
                config.load_kube_config()
                logger.info("Loaded kubeconfig from file")
        except Exception as e:
            logger.error(f"Failed to load Kubernetes config: {e}")
            raise

        # Initialize API clients
        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        self.custom_objects = client.CustomObjectsApi()

    def create_odoo_deployment(
        self,
        instance_id: str,
        database_name: str,
        customer_id: str,
        odoo_version: str,
        admin_email: str,
        admin_password: str,
        db_config: Dict[str, str],
        cpu_limit: float,
        memory_limit: str,
        storage_limit: str,
        demo_data: bool,
        environment_vars: Optional[Dict[str, str]] = None,
        subdomain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create Kubernetes Deployment for Odoo instance.

        Args:
            instance_id: UUID of the instance
            database_name: Postgres database name
            customer_id: Customer UUID
            odoo_version: Odoo version (e.g., "17")
            admin_email: Admin user email
            admin_password: Generated admin password
            db_config: Database connection info
            cpu_limit: CPU limit (cores)
            memory_limit: Memory limit (e.g., "2G")
            storage_limit: Storage limit (e.g., "10G")
            demo_data: Whether to load demo data
            environment_vars: Additional env vars
            subdomain: Custom subdomain (defaults to database_name)

        Returns:
            Dict with deployment info
        """
        instance_id_short = instance_id.replace("-", "")[:8]
        deployment_name = f"odoo-{database_name}-{instance_id_short}"
        subdomain = subdomain or database_name

        logger.info(f"Creating Odoo deployment: {deployment_name}")

        try:
            # 1. Create PVC for instance data
            self._create_pvc(deployment_name, storage_limit)

            # 2. Create Deployment
            self._create_deployment(
                deployment_name=deployment_name,
                instance_id=instance_id,
                customer_id=customer_id,
                database_name=database_name,
                odoo_version=odoo_version,
                admin_email=admin_email,
                admin_password=admin_password,
                db_config=db_config,
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                demo_data=demo_data,
                environment_vars=environment_vars
            )

            # 3. Create Service
            self._create_service(deployment_name, instance_id)

            # 4. Create IngressRoute (Traefik)
            self._create_ingress_route(deployment_name, subdomain)

            # 5. Get external URL
            base_domain = os.getenv("BASE_DOMAIN", "yourdomain.com")
            url = f"http://{subdomain}.{base_domain}"

            logger.info(f"Successfully created deployment: {deployment_name}")

            return {
                "deployment_name": deployment_name,
                "url": url,
                "status": "creating"
            }

        except ApiException as e:
            logger.error(f"Kubernetes API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating deployment: {e}")
            raise

    def _create_pvc(self, deployment_name: str, storage_limit: str):
        """Create PersistentVolumeClaim for Odoo instance data."""
        pvc = client.V1PersistentVolumeClaim(
            metadata=client.V1ObjectMeta(
                name=f"{deployment_name}-data",
                namespace=self.namespace,
                labels={
                    "app": "odoo",
                    "deployment": deployment_name
                }
            ),
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=["ReadWriteMany"],
                storage_class_name="cephfs-odoo",
                resources=client.V1ResourceRequirements(
                    requests={"storage": storage_limit}
                )
            )
        )

        self.core_v1.create_namespaced_persistent_volume_claim(
            namespace=self.namespace,
            body=pvc
        )
        logger.info(f"Created PVC: {deployment_name}-data ({storage_limit})")

    def _create_deployment(
        self,
        deployment_name: str,
        instance_id: str,
        customer_id: str,
        database_name: str,
        odoo_version: str,
        admin_email: str,
        admin_password: str,
        db_config: Dict[str, str],
        cpu_limit: float,
        memory_limit: str,
        demo_data: bool,
        environment_vars: Optional[Dict[str, str]]
    ):
        """Create Kubernetes Deployment for Odoo."""

        # Environment variables
        env = [
            client.V1EnvVar(name="POSTGRES_HOST", value=db_config["host"]),
            client.V1EnvVar(name="POSTGRES_PORT", value=str(db_config["port"])),
            client.V1EnvVar(name="POSTGRES_DB", value=database_name),
            client.V1EnvVar(name="POSTGRES_USER", value=db_config["user"]),
            client.V1EnvVar(name="POSTGRES_PASSWORD", value=db_config["password"]),
            client.V1EnvVar(name="ODOO_ADMIN_EMAIL", value=admin_email),
            client.V1EnvVar(name="ODOO_ADMIN_PASSWD", value=admin_password),
            client.V1EnvVar(name="ODOO_INIT", value="True" if demo_data else "False"),
            client.V1EnvVar(name="ODOO_DEMO", value="True" if demo_data else "False"),
        ]

        # Add custom env vars
        if environment_vars:
            for key, value in environment_vars.items():
                env.append(client.V1EnvVar(name=key, value=value))

        # Container
        container = client.V1Container(
            name="odoo",
            image=f"odoo:{odoo_version}",
            ports=[client.V1ContainerPort(container_port=8069, name="http")],
            env=env,
            volume_mounts=[
                client.V1VolumeMount(
                    name="odoo-data",
                    mount_path="/var/lib/odoo"
                ),
                client.V1VolumeMount(
                    name="odoo-addons",
                    mount_path="/mnt/extra-addons"
                )
            ],
            resources=client.V1ResourceRequirements(
                limits={
                    "cpu": str(cpu_limit),
                    "memory": memory_limit
                },
                requests={
                    "cpu": str(cpu_limit / 2),
                    "memory": str(int(memory_limit.rstrip("GMK")) // 2) + memory_limit[-1]
                }
            ),
            liveness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path="/web/health",
                    port=8069
                ),
                initial_delay_seconds=60,
                period_seconds=30,
                timeout_seconds=10,
                failure_threshold=3
            ),
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(
                    path="/web/health",
                    port=8069
                ),
                initial_delay_seconds=30,
                period_seconds=10,
                timeout_seconds=5,
                failure_threshold=3
            )
        )

        # Pod template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": "odoo",
                    "deployment": deployment_name,
                    "instance-id": instance_id,
                    "customer-id": customer_id
                }
            ),
            spec=client.V1PodSpec(
                containers=[container],
                volumes=[
                    client.V1Volume(
                        name="odoo-data",
                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=f"{deployment_name}-data"
                        )
                    ),
                    client.V1Volume(
                        name="odoo-addons",
                        persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                            claim_name=f"{deployment_name}-data"
                        )
                    )
                ],
                restart_policy="Always"
            )
        )

        # Deployment spec
        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=self.namespace,
                labels={
                    "app": "odoo",
                    "instance-id": instance_id,
                    "customer-id": customer_id
                }
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(
                    match_labels={"deployment": deployment_name}
                ),
                template=template,
                strategy=client.V1DeploymentStrategy(
                    type="Recreate"  # Don't run 2 Odoo instances at once
                )
            )
        )

        self.apps_v1.create_namespaced_deployment(
            namespace=self.namespace,
            body=deployment
        )
        logger.info(f"Created Deployment: {deployment_name}")

    def _create_service(self, deployment_name: str, instance_id: str):
        """Create Kubernetes Service for Odoo instance."""
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=deployment_name,
                namespace=self.namespace,
                labels={
                    "app": "odoo",
                    "instance-id": instance_id
                }
            ),
            spec=client.V1ServiceSpec(
                selector={"deployment": deployment_name},
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

        self.core_v1.create_namespaced_service(
            namespace=self.namespace,
            body=service
        )
        logger.info(f"Created Service: {deployment_name}")

    def _create_ingress_route(self, deployment_name: str, subdomain: str):
        """Create Traefik IngressRoute for external access."""
        base_domain = os.getenv("BASE_DOMAIN", "yourdomain.com")

        ingress_route = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {
                "name": deployment_name,
                "namespace": self.namespace,
                "labels": {
                    "app": "odoo",
                    "deployment": deployment_name
                }
            },
            "spec": {
                "entryPoints": ["web"],
                "routes": [
                    {
                        "match": f"Host(`{subdomain}.{base_domain}`)",
                        "kind": "Rule",
                        "services": [
                            {
                                "name": deployment_name,
                                "port": 8069
                            }
                        ]
                    }
                ]
            }
        }

        self.custom_objects.create_namespaced_custom_object(
            group="traefik.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="ingressroutes",
            body=ingress_route
        )
        logger.info(f"Created IngressRoute: {subdomain}.{base_domain}")

    def start_deployment(self, deployment_name: str) -> Dict[str, Any]:
        """Start Odoo instance (scale to 1)."""
        try:
            # Scale deployment to 1 replica
            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={"spec": {"replicas": 1}}
            )
            logger.info(f"Started deployment: {deployment_name}")
            return {"status": "starting", "replicas": 1}
        except ApiException as e:
            logger.error(f"Failed to start deployment: {e}")
            raise

    def stop_deployment(self, deployment_name: str):
        """Stop Odoo instance (scale to 0)."""
        try:
            # Scale deployment to 0 replicas
            self.apps_v1.patch_namespaced_deployment_scale(
                name=deployment_name,
                namespace=self.namespace,
                body={"spec": {"replicas": 0}}
            )
            logger.info(f"Stopped deployment: {deployment_name}")
        except ApiException as e:
            logger.error(f"Failed to stop deployment: {e}")
            raise

    def restart_deployment(self, deployment_name: str) -> Dict[str, Any]:
        """Restart Odoo instance (rolling restart)."""
        try:
            # Trigger rolling update by updating annotation
            import datetime
            now = datetime.datetime.utcnow().isoformat()

            patch = {
                "spec": {
                    "template": {
                        "metadata": {
                            "annotations": {
                                "kubectl.kubernetes.io/restartedAt": now
                            }
                        }
                    }
                }
            }

            self.apps_v1.patch_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace,
                body=patch
            )
            logger.info(f"Restarted deployment: {deployment_name}")
            return {"status": "restarting"}
        except ApiException as e:
            logger.error(f"Failed to restart deployment: {e}")
            raise

    def delete_deployment(self, deployment_name: str):
        """Delete Odoo instance (Deployment, Service, PVC, IngressRoute)."""
        try:
            # Delete Deployment
            self.apps_v1.delete_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace
            )
            logger.info(f"Deleted Deployment: {deployment_name}")

            # Delete Service
            self.core_v1.delete_namespaced_service(
                name=deployment_name,
                namespace=self.namespace
            )
            logger.info(f"Deleted Service: {deployment_name}")

            # Delete PVC
            self.core_v1.delete_namespaced_persistent_volume_claim(
                name=f"{deployment_name}-data",
                namespace=self.namespace
            )
            logger.info(f"Deleted PVC: {deployment_name}-data")

            # Delete IngressRoute
            self.custom_objects.delete_namespaced_custom_object(
                group="traefik.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="ingressroutes",
                name=deployment_name
            )
            logger.info(f"Deleted IngressRoute: {deployment_name}")

        except ApiException as e:
            logger.error(f"Failed to delete deployment: {e}")
            raise

    def get_deployment_status(self, deployment_name: str) -> Dict[str, Any]:
        """Get status of Odoo deployment."""
        try:
            deployment = self.apps_v1.read_namespaced_deployment(
                name=deployment_name,
                namespace=self.namespace
            )

            status = {
                "name": deployment_name,
                "replicas": deployment.spec.replicas,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
                "updated_replicas": deployment.status.updated_replicas or 0,
                "conditions": []
            }

            if deployment.status.conditions:
                for condition in deployment.status.conditions:
                    status["conditions"].append({
                        "type": condition.type,
                        "status": condition.status,
                        "reason": condition.reason,
                        "message": condition.message
                    })

            # Determine overall status
            if status["ready_replicas"] == status["replicas"] and status["replicas"] > 0:
                status["overall_status"] = "running"
            elif status["replicas"] == 0:
                status["overall_status"] = "stopped"
            else:
                status["overall_status"] = "starting"

            return status
        except ApiException as e:
            if e.status == 404:
                return {"overall_status": "not_found"}
            logger.error(f"Failed to get deployment status: {e}")
            raise


# Singleton instance
_k8s_client = None

def get_k8s_client() -> KubernetesClient:
    """Get singleton Kubernetes client instance."""
    global _k8s_client
    if _k8s_client is None:
        namespace = os.getenv("KUBERNETES_NAMESPACE", "saasodoo")
        _k8s_client = KubernetesClient(namespace=namespace)
    return _k8s_client
```

#### Update provisioning tasks

`services/instance-service/app/tasks/provisioning.py`:
```python
# Replace
# from app.utils.docker_client import get_docker_client

# With
from app.utils.k8s_client import get_k8s_client

# Update _deploy_odoo_container function
async def _deploy_odoo_container(instance: Dict[str, Any], db_info: Dict[str, str]) -> Dict[str, Any]:
    """Deploy Odoo as Kubernetes Deployment"""
    k8s_client = get_k8s_client()

    from app.utils.password_generator import generate_secure_password
    generated_password = generate_secure_password()

    result = k8s_client.create_odoo_deployment(
        instance_id=str(instance['id']),
        database_name=instance['database_name'],
        customer_id=str(instance['customer_id']),
        odoo_version=instance.get('odoo_version', '17'),
        admin_email=instance['admin_email'],
        admin_password=generated_password,
        db_config=db_info,
        cpu_limit=instance['cpu_limit'],
        memory_limit=instance['memory_limit'],
        storage_limit=instance.get('storage_limit', '10G'),
        demo_data=instance['demo_data'],
        environment_vars=instance.get('environment_vars'),
        subdomain=instance.get('subdomain')
    )

    return result
```

#### Update lifecycle tasks

`services/instance-service/app/tasks/lifecycle.py`:
```python
from app.utils.k8s_client import get_k8s_client

async def _start_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    k8s_client = get_k8s_client()
    instance_id_hex = instance['id'].hex[:8]
    deployment_name = f"odoo-{instance['database_name']}-{instance_id_hex}"
    return k8s_client.start_deployment(deployment_name)

async def _stop_docker_container(instance: Dict[str, Any]):
    k8s_client = get_k8s_client()
    instance_id_hex = instance['id'].hex[:8]
    deployment_name = f"odoo-{instance['database_name']}-{instance_id_hex}"
    k8s_client.stop_deployment(deployment_name)

async def _restart_docker_container(instance: Dict[str, Any]) -> Dict[str, Any]:
    k8s_client = get_k8s_client()
    instance_id_hex = instance['id'].hex[:8]
    deployment_name = f"odoo-{instance['database_name']}-{instance_id_hex}"
    return k8s_client.restart_deployment(deployment_name)
```

#### Delete docker_client.py

```bash
rm services/instance-service/app/utils/docker_client.py
```

---

## Kubernetes-Native Deployment Workflow

### Makefile for Easy Deployment

`kubernetes/Makefile`:
```makefile
.PHONY: help install-cluster install-storage install-networking install-databases \
        install-secrets install-services install-monitoring install-all \
        destroy-all status test

help:
	@echo "SaaSOdoo Kubernetes Deployment"
	@echo ""
	@echo "Usage:"
	@echo "  make install-all        - Install everything (cluster -> services)"
	@echo "  make install-cluster    - Install RKE2 cluster"
	@echo "  make install-storage    - Install Rook-Ceph storage"
	@echo "  make install-networking - Install MetalLB + Traefik"
	@echo "  make install-secrets    - Create sealed secrets"
	@echo "  make install-databases  - Deploy databases"
	@echo "  make install-services   - Deploy microservices"
	@echo "  make install-monitoring - Deploy Prometheus/Grafana/Loki"
	@echo "  make status             - Show cluster status"
	@echo "  make test               - Run smoke tests"
	@echo "  make destroy-all        - Delete everything (DANGEROUS)"

install-cluster:
	@echo "==> Installing RKE2 cluster..."
	cd cluster && sudo ./install-server.sh 1

install-storage:
	@echo "==> Installing Rook-Ceph storage..."
	kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/crds.yaml
	kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/common.yaml
	kubectl apply -f https://raw.githubusercontent.com/rook/rook/v1.18.7/deploy/examples/operator.yaml
	@echo "Waiting for Rook operator..."
	kubectl -n rook-ceph wait --for=condition=ready pod -l app=rook-ceph-operator --timeout=300s
	kubectl apply -f infrastructure/storage/rook-ceph/

install-networking:
	@echo "==> Installing MetalLB..."
	kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.15.2/config/manifests/metallb-native.yaml
	kubectl -n metallb-system wait --for=condition=ready pod -l app=metallb --timeout=300s
	kubectl apply -f infrastructure/networking/metallb/
	@echo "==> Installing Traefik..."
	kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.5/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
	kubectl apply -f infrastructure/networking/traefik/
	@echo "Waiting for Traefik..."
	kubectl -n kube-system wait --for=condition=ready pod -l app=traefik --timeout=300s
	@echo "Traefik LoadBalancer IP:"
	@kubectl -n kube-system get svc traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
	@echo ""

install-secrets:
	@echo "==> Installing Sealed Secrets controller..."
	kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.0/controller.yaml
	kubectl -n kube-system wait --for=condition=ready pod -l app.kubernetes.io/name=sealed-secrets --timeout=300s
	@echo "==> Creating sealed secret from .env file..."
	cd infrastructure/secrets && bash 01-create-sealed-secret.sh
	kubectl apply -f infrastructure/secrets/02-saasodoo-secret.sealed.yaml

install-databases:
	@echo "==> Creating namespaces..."
	kubectl apply -f infrastructure/00-namespaces.yaml
	@echo "==> Deploying databases..."
	kubectl apply -f infrastructure/databases/
	@echo "Waiting for databases to be ready..."
	kubectl -n saasodoo wait --for=condition=ready pod -l app=postgres-platform --timeout=300s
	kubectl -n saasodoo wait --for=condition=ready pod -l app=redis --timeout=300s
	kubectl -n saasodoo wait --for=condition=ready pod -l app=rabbitmq --timeout=300s

install-services:
	@echo "==> Deploying Traefik middlewares..."
	kubectl apply -f infrastructure/networking/traefik/05-middlewares.yaml
	@echo "==> Deploying microservices..."
	kubectl apply -f services/instance-service/
	kubectl apply -f services/instance-worker/
	kubectl apply -f services/user-service/
	kubectl apply -f services/billing-service/
	kubectl apply -f services/notification-service/
	kubectl apply -f services/frontend-service/
	@echo "Waiting for services..."
	kubectl -n saasodoo wait --for=condition=available deployment --all --timeout=300s

install-monitoring:
	@echo "==> Installing Prometheus Operator..."
	helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
	helm repo update
	helm install prometheus prometheus-community/kube-prometheus-stack \
		--namespace monitoring \
		--create-namespace \
		--set prometheus.prometheusSpec.retention=30d \
		--set grafana.adminPassword=admin
	@echo "==> Installing Loki..."
	helm repo add grafana https://grafana.github.io/helm-charts
	helm install loki grafana/loki-stack --namespace monitoring
	@echo "Monitoring installed. Access Grafana:"
	@echo "kubectl -n monitoring port-forward svc/prometheus-grafana 3000:80"

install-all: install-storage install-networking install-secrets install-databases install-services
	@echo ""
	@echo "✅ SaaSOdoo Kubernetes installation complete!"
	@echo ""
	@echo "Next steps:"
	@echo "1. Update DNS to point to Traefik IP:"
	@kubectl -n kube-system get svc traefik -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
	@echo ""
	@echo "2. Test the deployment:"
	@echo "   make test"
	@echo ""
	@echo "3. Access services:"
	@echo "   http://app.yourdomain.com  - Frontend"
	@echo "   http://api.yourdomain.com  - API"

status:
	@echo "==> Cluster Nodes:"
	@kubectl get nodes
	@echo ""
	@echo "==> Namespaces:"
	@kubectl get ns
	@echo ""
	@echo "==> SaaSOdoo Pods:"
	@kubectl -n saasodoo get pods
	@echo ""
	@echo "==> Services:"
	@kubectl -n saasodoo get svc
	@echo ""
	@echo "==> Ingress Routes:"
	@kubectl -n saasodoo get ingressroute
	@echo ""
	@echo "==> Traefik LoadBalancer IP:"
	@kubectl -n kube-system get svc traefik

test:
	@echo "==> Running smoke tests..."
	cd tests && bash smoke-test.sh

destroy-all:
	@echo "WARNING: This will delete EVERYTHING in the cluster!"
	@read -p "Are you sure? Type 'yes' to continue: " confirm && [ "$$confirm" = "yes" ]
	kubectl delete namespace saasodoo monitoring backup --wait=true
	kubectl delete -f infrastructure/networking/traefik/
	kubectl delete -f infrastructure/networking/metallb/
	kubectl delete -f infrastructure/storage/rook-ceph/
	@echo "Cluster resources deleted. RKE2 still running."
	@echo "To completely remove RKE2, run: /usr/local/bin/rke2-uninstall.sh"
```

### Quick Deploy Script

`kubernetes/README.md`:
```markdown
# SaaSOdoo Kubernetes Deployment

## Prerequisites

- 3+ nodes with Ubuntu 22.04 LTS
- 16GB RAM per node minimum
- CephFS mounted at `/mnt/cephfs`
- Static IPs configured
- `make`, `helm`, `kubectl` installed

## Quick Start

### 1. Install RKE2 Cluster

On first control plane node:
\`\`\`bash
cd kubernetes/cluster
sudo ./install-server.sh 1
\`\`\`

Copy `/tmp/rke2-token` to other nodes, then on each:
\`\`\`bash
sudo ./install-server.sh 2  # Or 3 for third node
\`\`\`

### 2. Install Cilium CNI

\`\`\`bash
helm install cilium cilium/cilium --version 1.17.0 -n kube-system -f cluster/cilium-config.yaml
\`\`\`

### 3. Prepare Secrets

\`\`\`bash
# Copy your .env file
cp /path/to/.env secrets/saasodoo.env

# Add to .gitignore
echo "secrets/" >> .gitignore
\`\`\`

### 4. Deploy Everything

\`\`\`bash
make install-all
\`\`\`

This will:
1. Install Rook-Ceph storage
2. Install MetalLB + Traefik
3. Create sealed secrets
4. Deploy databases
5. Deploy microservices

### 5. Update DNS

Point your domain to Traefik LoadBalancer IP:
\`\`\`bash
kubectl -n kube-system get svc traefik
\`\`\`

Create DNS records:
- `*.yourdomain.com` → Traefik IP
- `api.yourdomain.com` → Traefik IP
- `app.yourdomain.com` → Traefik IP

### 6. Test

\`\`\`bash
make test
curl http://api.yourdomain.com/user/health
curl http://api.yourdomain.com/instance/health
\`\`\`

## Common Operations

### Check Cluster Status

\`\`\`bash
make status
\`\`\`

### Deploy Single Service

\`\`\`bash
kubectl apply -f services/user-service/
\`\`\`

### View Logs

\`\`\`bash
kubectl -n saasodoo logs -f -l app=instance-service
\`\`\`

### Scale Deployment

\`\`\`bash
kubectl -n saasodoo scale deployment instance-worker --replicas=5
\`\`\`

### Rollback Deployment

\`\`\`bash
kubectl -n saasodoo rollout undo deployment/user-service
\`\`\`

## Monitoring

Install monitoring stack:
\`\`\`bash
make install-monitoring
\`\`\`

Access Grafana:
\`\`\`bash
kubectl -n monitoring port-forward svc/prometheus-grafana 3000:80
# Open http://localhost:3000 (admin/admin)
\`\`\`

## Backup & Restore

Install Velero:
\`\`\`bash
cd backup/velero
bash 01-install.sh
\`\`\`

Create backup:
\`\`\`bash
velero backup create saasodoo-backup --include-namespaces saasodoo
\`\`\`

Restore:
\`\`\`bash
velero restore create --from-backup saasodoo-backup
\`\`\`

## Troubleshooting

### Pods not starting

\`\`\`bash
kubectl -n saasodoo describe pod <pod-name>
kubectl -n saasodoo logs <pod-name>
\`\`\`

### Storage issues

\`\`\`bash
kubectl -n rook-ceph get pods
kubectl -n rook-ceph logs -l app=rook-ceph-operator
\`\`\`

### Networking issues

\`\`\`bash
kubectl -n kube-system logs -l app=traefik
kubectl -n metallb-system logs -l app=metallb
\`\`\`
```

---

## Summary

This plan provides:

1. **Production-ready RKE2 cluster** with Kubernetes 1.32
2. **Complete directory structure** with all manifests
3. **Declarative configuration** - everything in Git
4. **Sealed Secrets** - safe to commit encrypted secrets
5. **Makefile automation** - deploy with `make install-all`
6. **Kubernetes-native workflow** - no more docker-compose
7. **Code changes documented** - k8s_client.py replaces docker_client.py
8. **Scalable architecture** - ready for 10,000 instances

**Total Timeline**: 10 weeks to production-ready Kubernetes platform.

**Next Step**: Review this plan, then I'll start creating the actual manifest files!
