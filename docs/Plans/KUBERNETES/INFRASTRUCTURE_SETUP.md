# Kubernetes Infrastructure Setup Guide

**Target Audience**: DevOps/Infrastructure implementers (beginner-friendly)
**Timeline**: Weeks 1-3 of migration
**Prerequisites**: Basic Linux command-line knowledge

---

## Table of Contents

1. [Prerequisites & Environment Setup](#prerequisites--environment-setup)
2. [RKE2 Cluster Installation](#rke2-cluster-installation)
3. [Cilium CNI Configuration](#cilium-cni-configuration)
4. [Rook-Ceph Storage Integration](#rook-ceph-storage-integration)
5. [MetalLB Load Balancer](#metallb-load-balancer)
6. [Traefik Ingress Controller](#traefik-ingress-controller)
7. [Sealed Secrets Setup](#sealed-secrets-setup)
8. [DNS Configuration](#dns-configuration)
9. [Validation & Testing](#validation--testing)
10. [Troubleshooting Guide](#troubleshooting-guide)

---

## Prerequisites & Environment Setup

### Hardware Requirements

**Minimum for Development/Testing:**
- 3 control plane nodes: 4 CPU, 8GB RAM, 100GB disk each
- 3 worker nodes: 8 CPU, 16GB RAM, 200GB disk each
- Total: 36 CPU cores, 72GB RAM

**Production (10,000+ instances target):**
- 3 control plane nodes: 8 CPU, 16GB RAM, 200GB SSD each
- 10+ worker nodes: 32 CPU, 64GB RAM, 500GB SSD each
- Separate CephFS storage nodes with dedicated disks

### Operating System

- **Supported**: Ubuntu 22.04 LTS, Rocky Linux 9, RHEL 9
- **Kernel**: 5.15+ (for eBPF/Cilium support)
- **Firewall**: Disabled or properly configured (see firewall rules below)

### Network Requirements

- All nodes must have static IP addresses
- Private network for cluster communication (recommended: 10.0.0.0/16)
- Public IP or load balancer for ingress traffic
- DNS resolution between nodes
- NTP synchronized across all nodes

### Firewall Rules (if enabled)

**Control Plane Nodes:**
```bash
# RKE2 API Server
sudo firewall-cmd --permanent --add-port=6443/tcp
# etcd
sudo firewall-cmd --permanent --add-port=2379-2380/tcp
# Kubelet metrics
sudo firewall-cmd --permanent --add-port=10250/tcp
# Cilium health checks
sudo firewall-cmd --permanent --add-port=4240/tcp
# Reload
sudo firewall-cmd --reload
```

**Worker Nodes:**
```bash
# Kubelet
sudo firewall-cmd --permanent --add-port=10250/tcp
# NodePort services
sudo firewall-cmd --permanent --add-port=30000-32767/tcp
# Cilium
sudo firewall-cmd --permanent --add-port=4240/tcp
sudo firewall-cmd --permanent --add-port=8472/udp
sudo firewall-cmd --reload
```

### Pre-Installation Validation Checklist

Run these commands on ALL nodes:

```bash
# 1. Check kernel version (must be 5.15+)
uname -r

# 2. Disable swap (Kubernetes requirement)
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# 3. Enable IPv4 forwarding
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
EOF
sudo sysctl --system

# 4. Verify connectivity to all nodes
ping -c 3 <other-node-ip>

# 5. Verify NTP sync
timedatectl status

# 6. Check available disk space
df -h
```

**Expected Results:**
- Kernel: 5.15 or higher
- Swap: should show as disabled in `free -h`
- All nodes should be pingable
- NTP: "System clock synchronized: yes"
- Disk: At least 50GB free on root partition

---

## RKE2 Cluster Installation

### Step 1: Install RKE2 on First Control Plane Node

```bash
# Download and install RKE2
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server sh -

# Enable and start RKE2
sudo systemctl enable rke2-server.service
```

**Create configuration file:**

```bash
sudo mkdir -p /etc/rancher/rke2
sudo tee /etc/rancher/rke2/config.yaml > /dev/null <<EOF
token: your-secure-cluster-token-change-me
tls-san:
  - kubernetes.yourdomain.com
  - 10.0.0.10  # Replace with your control plane VIP/IP
cni: cilium
disable:
  - rke2-ingress-nginx  # We'll use Traefik
cluster-cidr: 10.42.0.0/16
service-cidr: 10.43.0.0/16
etcd-snapshot-schedule-cron: "0 */6 * * *"  # Backup every 6 hours
etcd-snapshot-retention: 10
EOF
```

**Start the cluster:**

```bash
sudo systemctl start rke2-server.service

# Monitor startup (takes 2-5 minutes)
sudo journalctl -u rke2-server -f

# Wait until you see: "Wrote kubeconfig" in logs
```

**Validation:**

```bash
# Set up kubectl access
export KUBECONFIG=/etc/rancher/rke2/rke2.yaml
export PATH=$PATH:/var/lib/rancher/rke2/bin

# Verify node is ready
kubectl get nodes

# Expected output:
# NAME            STATUS   ROLES                       AGE   VERSION
# control-node-1  Ready    control-plane,etcd,master   2m    v1.28.x
```

**Troubleshooting - Node Not Ready:**

```bash
# Check RKE2 service status
sudo systemctl status rke2-server

# Check detailed logs
sudo journalctl -u rke2-server --no-pager | tail -100

# Common issues:
# - Firewall blocking ports (see firewall rules above)
# - Swap not disabled (run: sudo swapoff -a)
# - Insufficient resources (check: free -h, df -h)
```

### Step 2: Join Additional Control Plane Nodes (HA Setup)

On **control-node-2** and **control-node-3**:

```bash
# Install RKE2
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=server sh -

# Create configuration
sudo mkdir -p /etc/rancher/rke2
sudo tee /etc/rancher/rke2/config.yaml > /dev/null <<EOF
server: https://10.0.0.10:9345  # IP of first control plane node
token: your-secure-cluster-token-change-me  # MUST match first node
tls-san:
  - kubernetes.yourdomain.com
  - 10.0.0.10
cni: cilium
disable:
  - rke2-ingress-nginx
EOF

# Enable and start
sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service

# Monitor (takes 3-5 minutes to join)
sudo journalctl -u rke2-server -f
```

**Validation from first node:**

```bash
kubectl get nodes

# Expected: 3 control plane nodes in Ready state
# NAME            STATUS   ROLES                       AGE     VERSION
# control-node-1  Ready    control-plane,etcd,master   10m     v1.28.x
# control-node-2  Ready    control-plane,etcd,master   5m      v1.28.x
# control-node-3  Ready    control-plane,etcd,master   5m      v1.28.x

# Verify etcd cluster health
kubectl -n kube-system get pods -l component=etcd

# All 3 etcd pods should be Running
```

### Step 3: Join Worker Nodes

On **each worker node**:

```bash
# Install RKE2 agent
curl -sfL https://get.rke2.io | INSTALL_RKE2_TYPE=agent sh -

# Create configuration
sudo mkdir -p /etc/rancher/rke2
sudo tee /etc/rancher/rke2/config.yaml > /dev/null <<EOF
server: https://10.0.0.10:9345  # Control plane VIP or first node IP
token: your-secure-cluster-token-change-me
EOF

# Enable and start
sudo systemctl enable rke2-agent.service
sudo systemctl start rke2-agent.service

# Monitor
sudo journalctl -u rke2-agent -f
```

**Validation:**

```bash
# From control plane node
kubectl get nodes

# Expected: All nodes in Ready state
# NAME            STATUS   ROLES                       AGE   VERSION
# control-node-1  Ready    control-plane,etcd,master   20m   v1.28.x
# control-node-2  Ready    control-plane,etcd,master   15m   v1.28.x
# control-node-3  Ready    control-plane,etcd,master   15m   v1.28.x
# worker-node-1   Ready    <none>                      5m    v1.28.x
# worker-node-2   Ready    <none>                      5m    v1.28.x
# worker-node-3   Ready    <none>                      5m    v1.28.x

# Verify all system pods are running
kubectl get pods -n kube-system

# All pods should be Running (except ingress controller we disabled)
```

**Troubleshooting - Worker Not Joining:**

```bash
# On worker node, check logs
sudo journalctl -u rke2-agent --no-pager | tail -100

# Common issues:
# 1. Wrong token: Verify token matches control plane
# 2. Network connectivity: Test with: telnet 10.0.0.10 9345
# 3. Firewall: Ensure port 9345 is open on control plane
# 4. Certificate issues: Check time sync with: timedatectl
```

### Step 4: Configure kubectl Access for Users

```bash
# Copy kubeconfig from control plane to your workstation
scp root@control-node-1:/etc/rancher/rke2/rke2.yaml ~/.kube/config

# Edit the file and change server address
sed -i 's/127.0.0.1/10.0.0.10/g' ~/.kube/config

# Test access
kubectl get nodes
```

---

## Cilium CNI Configuration

Cilium is already installed by RKE2 with our configuration. Let's verify and configure it.

### Step 1: Verify Cilium Installation

```bash
# Check Cilium pods
kubectl get pods -n kube-system -l k8s-app=cilium

# Expected: One cilium pod per node, all Running
# NAME           READY   STATUS    RESTARTS   AGE
# cilium-xxxxx   1/1     Running   0          10m
# cilium-yyyyy   1/1     Running   0          10m
# cilium-zzzzz   1/1     Running   0          10m
```

### Step 2: Install Cilium CLI (for management)

```bash
# Download Cilium CLI
CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz{,.sha256sum}
sha256sum --check cilium-linux-amd64.tar.gz.sha256sum
sudo tar xzvfC cilium-linux-amd64.tar.gz /usr/local/bin
rm cilium-linux-amd64.tar.gz{,.sha256sum}

# Verify installation
cilium version
```

### Step 3: Run Cilium Connectivity Test

```bash
# This takes 5-10 minutes
cilium connectivity test

# Expected output at end:
# ✅ All tests passed successfully!
```

**If tests fail:**

```bash
# Check Cilium status
cilium status

# View detailed logs
kubectl logs -n kube-system -l k8s-app=cilium --tail=100

# Common issues:
# - Kernel too old: Upgrade to 5.15+
# - eBPF not supported: Check with: mount | grep bpf
# - Network policy blocking: Temporarily disable with: cilium config set enable-policy false
```

### Step 4: Enable Hubble (Observability - Optional but Recommended)

```bash
# Enable Hubble
cilium hubble enable --ui

# Wait for Hubble pods
kubectl wait --for=condition=ready pod -n kube-system -l k8s-app=hubble-ui --timeout=300s

# Port forward to access UI
kubectl port-forward -n kube-system svc/hubble-ui 12000:80

# Access at: http://localhost:12000
```

---

## Rook-Ceph Storage Integration

We'll connect to your existing CephFS cluster rather than deploying a new one.

### Step 1: Install Rook Operator

```bash
# Add Rook Helm repo
helm repo add rook-release https://charts.rook.io/release
helm repo update

# Create namespace
kubectl create namespace rook-ceph

# Install Rook operator
helm install rook-ceph rook-release/rook-ceph \
  --namespace rook-ceph \
  --version v1.13.7 \
  --set csi.enableCephfsDriver=true \
  --set csi.enableRBDDriver=false

# Wait for operator to be ready (2-3 minutes)
kubectl wait --for=condition=ready pod -n rook-ceph -l app=rook-ceph-operator --timeout=300s
```

**Validation:**

```bash
kubectl get pods -n rook-ceph

# Expected:
# NAME                                 READY   STATUS    RESTARTS   AGE
# rook-ceph-operator-xxxxxxxxxx-xxxxx  1/1     Running   0          2m
```

### Step 2: Connect to Existing CephFS Cluster

**Create external cluster configuration:**

```bash
# First, get your Ceph cluster information from existing CephFS setup
# You'll need:
# - Ceph monitors (e.g., 10.0.1.10:6789,10.0.1.11:6789)
# - Ceph admin key (from /etc/ceph/ceph.client.admin.keyring)
# - Ceph filesystem name (e.g., cephfs)

# Create secret with Ceph credentials
kubectl create secret generic rook-ceph-mon \
  --from-literal=cluster-name=external-ceph \
  --from-literal=fsid=<your-ceph-fsid> \
  --from-literal=mon-secret=<your-mon-secret> \
  --namespace rook-ceph

kubectl create secret generic rook-ceph-admin \
  --from-literal=userID=admin \
  --from-literal=userKey=<your-admin-key> \
  --namespace rook-ceph
```

**Create CephFS StorageClass:**

```bash
cat <<EOF | kubectl apply -f -
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: cephfs-saasodoo
provisioner: rook-ceph.cephfs.csi.ceph.com
parameters:
  clusterID: rook-ceph
  fsName: cephfs  # Your CephFS filesystem name
  pool: cephfs_data
  monitors: 10.0.1.10:6789,10.0.1.11:6789,10.0.1.12:6789  # Your Ceph monitors
  csi.storage.k8s.io/provisioner-secret-name: rook-ceph-admin
  csi.storage.k8s.io/provisioner-secret-namespace: rook-ceph
  csi.storage.k8s.io/node-stage-secret-name: rook-ceph-admin
  csi.storage.k8s.io/node-stage-secret-namespace: rook-ceph
reclaimPolicy: Retain  # IMPORTANT: Don't delete data when PVC is deleted
allowVolumeExpansion: true
mountOptions:
  - debug
EOF
```

### Step 3: Test Storage Provisioning

```bash
# Create test PVC
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-cephfs-pvc
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 1Gi
  storageClassName: cephfs-saasodoo
EOF

# Wait for PVC to be bound
kubectl get pvc test-cephfs-pvc -w

# Expected:
# NAME              STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS      AGE
# test-cephfs-pvc   Bound    pvc-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx   1Gi        RWX            cephfs-saasodoo   10s
```

**Create test pod to mount the PVC:**

```bash
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: test-cephfs-pod
spec:
  containers:
  - name: test
    image: busybox
    command: ["sh", "-c", "echo 'Hello from CephFS' > /mnt/test.txt && sleep 3600"]
    volumeMounts:
    - name: cephfs-volume
      mountPath: /mnt
  volumes:
  - name: cephfs-volume
    persistentVolumeClaim:
      claimName: test-cephfs-pvc
EOF

# Wait for pod to be running
kubectl wait --for=condition=ready pod/test-cephfs-pod --timeout=120s

# Verify file was written
kubectl exec test-cephfs-pod -- cat /mnt/test.txt

# Expected: Hello from CephFS

# Cleanup test resources
kubectl delete pod test-cephfs-pod
kubectl delete pvc test-cephfs-pvc
```

**Troubleshooting - PVC Stuck in Pending:**

```bash
# Check PVC events
kubectl describe pvc test-cephfs-pvc

# Check CSI provisioner logs
kubectl logs -n rook-ceph -l app=csi-cephfsplugin-provisioner

# Common issues:
# 1. Wrong Ceph credentials: Verify admin key
# 2. Network connectivity: Test: telnet <monitor-ip> 6789
# 3. CephFS not available: Check Ceph cluster health
```

---

## MetalLB Load Balancer

MetalLB provides LoadBalancer services in bare-metal environments.

### Step 1: Install MetalLB

```bash
# Install using manifest
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/v0.14.3/config/manifests/metallb-native.yaml

# Wait for MetalLB pods
kubectl wait --for=condition=ready pod -n metallb-system -l app=metallb --timeout=300s
```

### Step 2: Configure IP Address Pool

```bash
# Define IP range for LoadBalancer services
# Use a range from your network (e.g., 10.0.0.100-10.0.0.150)

cat <<EOF | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata:
  name: default-pool
  namespace: metallb-system
spec:
  addresses:
  - 10.0.0.100-10.0.0.150  # Adjust to your network
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata:
  name: default-l2
  namespace: metallb-system
spec:
  ipAddressPools:
  - default-pool
EOF
```

### Step 3: Test LoadBalancer Service

```bash
# Create test service
kubectl create deployment nginx-test --image=nginx
kubectl expose deployment nginx-test --type=LoadBalancer --port=80

# Wait for external IP
kubectl get svc nginx-test -w

# Expected:
# NAME         TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)        AGE
# nginx-test   LoadBalancer   10.43.123.456   10.0.0.100    80:31234/TCP   30s

# Test access
curl http://10.0.0.100

# Expected: Nginx welcome page HTML

# Cleanup
kubectl delete svc nginx-test
kubectl delete deployment nginx-test
```

**Troubleshooting - No External IP Assigned:**

```bash
# Check MetalLB speaker logs
kubectl logs -n metallb-system -l component=speaker

# Check controller logs
kubectl logs -n metallb-system -l component=controller

# Verify IP pool configuration
kubectl get ipaddresspool -n metallb-system

# Common issues:
# 1. IP range already in use: Choose different range
# 2. Network configuration: Ensure L2 connectivity between nodes
# 3. Speaker not running on all nodes: Check node affinity
```

---

## Traefik Ingress Controller

### Step 1: Install Traefik via Helm

```bash
# Add Traefik Helm repo
helm repo add traefik https://traefik.github.io/charts
helm repo update

# Create namespace
kubectl create namespace traefik

# Install Traefik
helm install traefik traefik/traefik \
  --namespace traefik \
  --set ingressClass.enabled=true \
  --set ingressClass.isDefaultClass=true \
  --set ports.web.exposedPort=80 \
  --set ports.websecure.exposedPort=443 \
  --set service.type=LoadBalancer

# Wait for Traefik pod
kubectl wait --for=condition=ready pod -n traefik -l app.kubernetes.io/name=traefik --timeout=300s
```

**Validation:**

```bash
# Check Traefik service
kubectl get svc -n traefik

# Expected: LoadBalancer service with EXTERNAL-IP from MetalLB
# NAME      TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)                      AGE
# traefik   LoadBalancer   10.43.x.x      10.0.0.101    80:30080/TCP,443:30443/TCP   2m

# Access Traefik dashboard (port-forward for now)
kubectl port-forward -n traefik svc/traefik 9000:9000

# Visit: http://localhost:9000/dashboard/
```

### Step 2: Create Test Ingress

```bash
# Deploy test application
kubectl create deployment whoami --image=traefik/whoami
kubectl expose deployment whoami --port=80

# Create IngressRoute (Traefik CRD)
cat <<EOF | kubectl apply -f -
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: whoami-ingress
spec:
  entryPoints:
    - web
  routes:
  - match: Host(\`whoami.test.local\`)
    kind: Rule
    services:
    - name: whoami
      port: 80
EOF

# Test (add entry to /etc/hosts first)
# echo "10.0.0.101 whoami.test.local" | sudo tee -a /etc/hosts

curl http://whoami.test.local

# Expected: Response showing request details

# Cleanup
kubectl delete ingressroute whoami-ingress
kubectl delete svc whoami
kubectl delete deployment whoami
```

---

## Sealed Secrets Setup

Sealed Secrets encrypts Kubernetes Secrets for safe Git storage.

### Step 1: Install Sealed Secrets Controller

```bash
# Install controller
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.24.5/controller.yaml

# Wait for controller
kubectl wait --for=condition=ready pod -n kube-system -l name=sealed-secrets-controller --timeout=300s
```

### Step 2: Install kubeseal CLI

```bash
# Download kubeseal
KUBESEAL_VERSION='0.24.5'
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v${KUBESEAL_VERSION}/kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz
tar -xvzf kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz kubeseal
sudo install -m 755 kubeseal /usr/local/bin/kubeseal
rm kubeseal kubeseal-${KUBESEAL_VERSION}-linux-amd64.tar.gz

# Verify
kubeseal --version
```

### Step 3: Test Sealed Secrets

```bash
# Create a regular secret
kubectl create secret generic test-secret \
  --from-literal=password=mysecretpassword \
  --dry-run=client -o yaml > test-secret.yaml

# Seal the secret
kubeseal -f test-secret.yaml -w test-sealed-secret.yaml

# Apply sealed secret
kubectl apply -f test-sealed-secret.yaml

# Verify secret was created
kubectl get secret test-secret -o jsonpath='{.data.password}' | base64 -d

# Expected: mysecretpassword

# Cleanup
kubectl delete secret test-secret
rm test-secret.yaml test-sealed-secret.yaml
```

**Important Notes:**
- Backup the sealing key: `kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > sealed-secrets-key.yaml`
- Store backup securely (NOT in Git!)
- Only commit `test-sealed-secret.yaml` to Git, never `test-secret.yaml`

---

## DNS Configuration

### Internal DNS (CoreDNS)

CoreDNS is automatically installed by RKE2. Let's verify:

```bash
# Check CoreDNS pods
kubectl get pods -n kube-system -l k8s-app=kube-dns

# Test DNS resolution from within cluster
kubectl run busybox --rm -it --image=busybox --restart=Never -- nslookup kubernetes.default

# Expected: Should resolve to Kubernetes service IP
```

### External DNS Configuration

For production, configure DNS records:

**Option A: Wildcard DNS (Recommended for SaaS)**
```
*.yourdomain.com    A    10.0.0.101  # Traefik LoadBalancer IP
```

**Option B: Individual Records**
```
api.yourdomain.com      A    10.0.0.101
app.yourdomain.com      A    10.0.0.101
*.odoo.yourdomain.com   A    10.0.0.101  # For customer instances
```

**Testing DNS:**
```bash
# From external machine
nslookup api.yourdomain.com

# Should return: 10.0.0.101
```

---

## Validation & Testing

### Comprehensive Cluster Health Check

```bash
# Create validation script
cat > validate-cluster.sh <<'EOF'
#!/bin/bash
set -e

echo "=== Kubernetes Cluster Validation ==="

echo -e "\n1. Node Status:"
kubectl get nodes -o wide

echo -e "\n2. System Pods:"
kubectl get pods -n kube-system

echo -e "\n3. Cilium Health:"
cilium status --wait

echo -e "\n4. Storage Classes:"
kubectl get sc

echo -e "\n5. MetalLB Configuration:"
kubectl get ipaddresspool -n metallb-system

echo -e "\n6. Traefik Service:"
kubectl get svc -n traefik

echo -e "\n7. Sealed Secrets Controller:"
kubectl get pods -n kube-system -l name=sealed-secrets-controller

echo -e "\n8. etcd Cluster Health:"
kubectl -n kube-system get pods -l component=etcd

echo -e "\n9. API Server Responsiveness:"
time kubectl get --raw /healthz

echo -e "\n✅ All validation checks completed!"
EOF

chmod +x validate-cluster.sh
./validate-cluster.sh
```

**Expected Results:**
- All nodes: Ready
- All system pods: Running
- Cilium: Healthy
- Storage class: cephfs-saasodoo available
- MetalLB: IP pool configured
- Traefik: LoadBalancer with external IP
- Sealed Secrets: Running
- etcd: 3 pods running
- API health check: < 100ms

---

## Troubleshooting Guide

### Problem: Pods Stuck in Pending

**Diagnostic:**
```bash
kubectl describe pod <pod-name>
```

**Common Causes:**
1. **Insufficient Resources**: Node doesn't have enough CPU/memory
   - Solution: Add more worker nodes or reduce resource requests
2. **No Nodes Available**: Taints or node selectors preventing scheduling
   - Solution: Check node taints with `kubectl describe node <node-name>`
3. **Storage Issues**: PVC not binding
   - Solution: Check storage class and PVC status

### Problem: Service Unreachable

**Diagnostic:**
```bash
# Check service
kubectl get svc <service-name>

# Check endpoints
kubectl get endpoints <service-name>

# Test from within cluster
kubectl run debug --rm -it --image=nicolaka/netshoot -- bash
# Inside pod: curl http://<service-name>
```

**Common Causes:**
1. **No Endpoints**: No healthy pods backing the service
   - Solution: Check pod status and readiness probes
2. **Network Policy**: Traffic being blocked
   - Solution: Review network policies with `kubectl get networkpolicy`
3. **Port Mismatch**: Service port doesn't match container port
   - Solution: Verify port configuration in service and deployment

### Problem: Storage Mount Failures

**Diagnostic:**
```bash
# Check PVC status
kubectl describe pvc <pvc-name>

# Check CSI driver logs
kubectl logs -n rook-ceph -l app=csi-cephfsplugin
```

**Common Causes:**
1. **Ceph Cluster Unreachable**: Network connectivity issues
   - Solution: Test connectivity to Ceph monitors
2. **Authentication Failed**: Wrong Ceph credentials
   - Solution: Verify secrets contain correct keys
3. **Quota Exceeded**: CephFS quota full
   - Solution: Check Ceph usage with `ceph df`

### Problem: High etcd Memory Usage

**Diagnostic:**
```bash
# Check etcd metrics
kubectl top pod -n kube-system -l component=etcd
```

**Solutions:**
- Reduce retention: `etcdctl --endpoints=<endpoint> compact <revision>`
- Defragment: `etcdctl --endpoints=<endpoint> defrag`
- Increase etcd memory limit in RKE2 config

### Problem: Certificate Errors

**Diagnostic:**
```bash
# Check certificate expiry
kubectl get certificates --all-namespaces
```

**Solutions:**
- RKE2 auto-rotates certificates
- If manually created, renew with cert-manager
- Check cert-manager logs: `kubectl logs -n cert-manager -l app=cert-manager`

### Getting Help

**Logs to Collect:**
```bash
# Node logs
sudo journalctl -u rke2-server -n 500 > rke2-server.log
sudo journalctl -u rke2-agent -n 500 > rke2-agent.log

# Kubernetes logs
kubectl cluster-info dump > cluster-dump.log

# Component logs
kubectl logs -n kube-system -l k8s-app=cilium > cilium.log
kubectl logs -n rook-ceph -l app=rook-ceph-operator > rook.log
```

---

## Next Steps

Once infrastructure is validated:

1. **Proceed to CODE_REFACTORING_GUIDE.md** - Adapt application code for Kubernetes
2. **Set up CI/CD pipeline** - See TESTING_STRATEGY.md
3. **Configure monitoring** - See OBSERVABILITY_SETUP.md
4. **Plan data migration** - See DATABASE_MIGRATION.md

---

## Appendix: Makefile for Automation

Save this as `kubernetes/Makefile` for quick operations:

```makefile
.PHONY: help install-rke2 install-tools validate clean

help:
	@echo "Kubernetes Infrastructure Management"
	@echo ""
	@echo "Available targets:"
	@echo "  install-rke2      Install RKE2 on current node"
	@echo "  install-tools     Install kubectl, helm, cilium CLI"
	@echo "  validate          Run cluster validation checks"
	@echo "  clean             Remove test resources"

install-rke2:
	curl -sfL https://get.rke2.io | sh -
	@echo "RKE2 installed. Configure /etc/rancher/rke2/config.yaml and run: sudo systemctl start rke2-server"

install-tools:
	@echo "Installing kubectl..."
	curl -LO "https://dl.k8s.io/release/$$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
	sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
	@echo "Installing Helm..."
	curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
	@echo "Done!"

validate:
	@./validate-cluster.sh

clean:
	kubectl delete deployment --all
	kubectl delete svc --all --field-selector metadata.name!=kubernetes
	kubectl delete pvc --all
```

Usage:
```bash
make install-tools
make validate
```

---

**Document Version**: 1.0
**Last Updated**: 2025-12-02
**Maintainer**: SaaSOdoo DevOps Team
