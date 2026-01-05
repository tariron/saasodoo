# Rancher - Kubernetes Management UI

Multi-cluster Kubernetes management platform with web UI.

## TLS Options

| Option | Use Case | cert-manager Required? |
|--------|----------|------------------------|
| `source: rancher` | nip.io / dev / self-signed | No |
| `source: secret` + cert-manager | Self-signed via cert-manager | Yes |
| `source: letsEncrypt` | Production with real domain | Yes |

## Installation

### Option 1: Self-Signed (Current - nip.io)

```bash
# No cert-manager needed - Rancher generates its own cert
kubectl apply -f infrastructure/rancher/
```

### Option 2: With cert-manager

```bash
# Install cert-manager first
kubectl apply -f infrastructure/cert-manager/

# Wait for cert-manager
kubectl wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=120s

# Then install Rancher
kubectl apply -f infrastructure/rancher/
```

## Access Rancher

```bash
# Wait for Rancher to be ready
kubectl rollout status deployment/rancher -n cattle-system --timeout=300s

# Get bootstrap password (if you forgot)
kubectl get secret --namespace cattle-system bootstrap-secret \
  -o go-template='{{.data.bootstrapPassword|base64decode}}{{"\n"}}'
```

Then access: https://rancher.62.171.153.219.nip.io

**First login:**
1. Accept the self-signed certificate warning
2. Login with `admin` / `admin` (or bootstrap password)
3. Set a new admin password
4. Accept the Rancher server URL

## Configuration

### Change Hostname

Edit `01-rancher.yaml`:
```yaml
hostname: rancher.yourdomain.com
```

### Enable HA (Production)

Edit `01-rancher.yaml`:
```yaml
replicas: 3
```

### Switch to Let's Encrypt (Real Domain)

Edit `01-rancher.yaml`:
```yaml
ingress:
  tls:
    source: letsEncrypt
letsEncrypt:
  email: admin@yourdomain.com
  environment: production
```

## What Rancher Provides

- **Multi-cluster management** - Manage k3s, RKE2, EKS, GKE, AKS
- **App Catalog** - Deploy Helm charts via UI
- **User Management** - RBAC, LDAP/AD, SAML
- **Monitoring** - Built-in Prometheus/Grafana integration
- **Backup/Restore** - Cluster backup management
- **Fleet** - GitOps at scale

## Troubleshooting

```bash
# Check Rancher pods
kubectl get pods -n cattle-system

# Check Rancher logs
kubectl logs -n cattle-system -l app=rancher --tail=100

# Check ingress
kubectl get ingress -n cattle-system
```
