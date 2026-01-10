# Insecure Registry Configuration

This configuration is required because the local Docker registry does not use TLS/HTTPS.
All nodes must be configured to allow pulling from the insecure registry.

## Registry Details

| Setting | Value |
|---------|-------|
| Registry URL | `registry.<BASE_DOMAIN>` |
| Protocol | HTTP (insecure) |
| Port | 80 (via Traefik ingress) |
| Internal Service | `docker-registry.saasodoo.svc.cluster.local:5000` |

---

## 1. Build Node Configuration (Docker)

The build node needs Docker installed to build and push images.

### 1.1 Install Docker

```bash
apt-get update && apt-get install -y docker.io
systemctl enable docker && systemctl start docker
```

### 1.2 Configure Docker for Insecure Registry

Create `/etc/docker/daemon.json`:

```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "insecure-registries": ["registry.<BASE_DOMAIN>"]
}
EOF
```

### 1.3 Restart Docker

```bash
systemctl restart docker
```

### 1.4 Verify

```bash
docker pull hello-world
docker tag hello-world registry.<BASE_DOMAIN>/hello-world:test
docker push registry.<BASE_DOMAIN>/hello-world:test
```

---

## 2. RKE2 Node Configuration (All Nodes)

All Kubernetes nodes need containerd configured to pull from the insecure registry.

### 2.1 Create Registries Configuration

Create `/etc/rancher/rke2/registries.yaml` on **each node**:

```bash
mkdir -p /etc/rancher/rke2
cat > /etc/rancher/rke2/registries.yaml << 'EOF'
mirrors:
  "registry.<BASE_DOMAIN>":
    endpoint:
      - "http://registry.<BASE_DOMAIN>"
configs:
  "registry.<BASE_DOMAIN>":
    tls:
      insecure_skip_verify: true
EOF
```

### 2.2 Restart RKE2 Service

**For control-plane nodes:**
```bash
systemctl restart rke2-server
```

**For worker nodes:**
```bash
systemctl restart rke2-agent
```

### 2.3 Verify Configuration

```bash
cat /etc/rancher/rke2/registries.yaml
systemctl is-active rke2-server  # or rke2-agent for workers
```

---

## 3. Batch Configuration Script

Run from the first control-plane node (10.0.0.1) to configure all other nodes:

```bash
# Define nodes
CONTROL_PLANES="10.0.0.2 10.0.0.3"
WORKERS="10.0.0.4 10.0.0.5 10.0.0.6"

# Configure all nodes
for ip in $CONTROL_PLANES $WORKERS; do
  echo "=== Configuring $ip ==="
  ssh -o StrictHostKeyChecking=no $ip "mkdir -p /etc/rancher/rke2 && cat > /etc/rancher/rke2/registries.yaml << 'EOF'
mirrors:
  \"registry.<BASE_DOMAIN>\":
    endpoint:
      - \"http://registry.<BASE_DOMAIN>\"
configs:
  \"registry.<BASE_DOMAIN>\":
    tls:
      insecure_skip_verify: true
EOF"
done

# Restart workers first
for ip in $WORKERS; do
  echo "=== Restarting rke2-agent on $ip ==="
  ssh $ip "systemctl restart rke2-agent"
done

# Restart control planes one at a time (with delay)
for ip in $CONTROL_PLANES; do
  echo "=== Restarting rke2-server on $ip ==="
  ssh $ip "systemctl restart rke2-server"
  sleep 30
done

# Restart local node last
echo "=== Restarting rke2-server on local node ==="
systemctl restart rke2-server
```

---

## 4. Verification

### Check Registry is Accessible

```bash
curl http://registry.<BASE_DOMAIN>/v2/_catalog
```

### Test K8s Can Pull

```bash
kubectl run test-pull --image=registry.<BASE_DOMAIN>/hello-world:test --restart=Never
kubectl get pod test-pull
kubectl delete pod test-pull
```

---

## 5. Adding New Nodes

When adding a new node to the cluster:

1. Create `/etc/rancher/rke2/registries.yaml` with the content from section 2.1
2. Join the cluster as normal (the registries.yaml will be read at startup)

---

## Notes

- This configuration is required because the registry uses HTTP instead of HTTPS
- The `insecure_skip_verify: true` setting tells containerd to accept the insecure connection
- If migrating to a secure registry with TLS, remove this configuration and restart nodes
- The registry data is stored on a PersistentVolume in the cluster
