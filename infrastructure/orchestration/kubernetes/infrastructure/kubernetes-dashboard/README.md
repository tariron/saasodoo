# Kubernetes Dashboard

Official web-based UI for managing and monitoring Kubernetes clusters.

## Features

- View cluster resources (pods, deployments, services, etc.)
- Monitor resource usage (CPU, memory)
- View logs and exec into containers
- Create, edit, and delete resources
- View events and troubleshoot issues

## Installation

### Step 1: Deploy Kubernetes Dashboard

```bash
# Apply official Kubernetes Dashboard manifests
kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml

# Wait for dashboard to be ready
kubectl wait --for=condition=ready pod -l k8s-app=kubernetes-dashboard -n kubernetes-dashboard --timeout=120s
```

### Step 2: Create Admin User

```bash
cd /root/Projects/saasodoo/infrastructure/orchestration/kubernetes/infrastructure/kubernetes-dashboard

# Create admin ServiceAccount and ClusterRoleBinding
kubectl apply -f 01-serviceaccount.yaml
kubectl apply -f 02-clusterrolebinding.yaml
```

### Step 3: Expose via Traefik

```bash
# Create ServersTransport (allows HTTPS with self-signed cert)
kubectl apply -f 00-serverstransport.yaml

# Create IngressRoute
kubectl apply -f 03-ingressroute.yaml
```

### Step 4: Get Access Token

```bash
# Run the token generation script
./get-token.sh

# Or manually:
kubectl -n kubernetes-dashboard create token admin-user --duration=87600h
```

## Access

**Dashboard URL:** http://dashboard.62.171.153.219.nip.io

1. Open the URL in your browser
2. Select "Token" login method
3. Paste the token from `get-token.sh`
4. Click "Sign In"

## Usage

### View Resources
- **Workloads** - Pods, Deployments, StatefulSets, etc.
- **Services** - Services, Ingresses
- **Config** - ConfigMaps, Secrets
- **Storage** - PVCs, PVs
- **Cluster** - Nodes, Namespaces

### Common Tasks

**View Logs:**
1. Navigate to Pods
2. Click on a pod
3. Click "Logs" icon (top right)

**Exec into Container:**
1. Navigate to Pods
2. Click on a pod
3. Click "Exec" icon (top right)

**Edit Resources:**
1. Navigate to resource
2. Click on the resource name
3. Click "Edit" icon (top right)

**Delete Resources:**
1. Navigate to resource
2. Check the checkbox next to resource
3. Click "Delete" icon (top)

## Troubleshooting

### Dashboard not accessible

```bash
# Check dashboard pod status
kubectl get pods -n kubernetes-dashboard

# Check dashboard service
kubectl get svc -n kubernetes-dashboard

# Check IngressRoute
kubectl get ingressroute -n kubernetes-dashboard

# Check Traefik logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=traefik
```

### Token expired

```bash
# Generate new token
./get-token.sh
```

### Permission denied errors

```bash
# Verify admin-user has cluster-admin role
kubectl get clusterrolebinding admin-user

# Re-apply role binding if needed
kubectl apply -f 02-clusterrolebinding.yaml
```

### Cannot see resources

Make sure you're logged in with the admin token, not the default dashboard service account.

## Security Notes

- ⚠️ The admin-user has **cluster-admin** privileges (full access)
- 🔒 Dashboard is exposed via HTTP (for development)
- 🔐 For production, configure TLS/HTTPS
- 👤 Consider creating limited-access users for different roles

## Uninstall

```bash
# Delete admin user and access
kubectl delete -f 02-clusterrolebinding.yaml
kubectl delete -f 01-serviceaccount.yaml
kubectl delete -f 03-ingressroute.yaml

# Delete dashboard
kubectl delete -f https://raw.githubusercontent.com/kubernetes/dashboard/v2.7.0/aio/deploy/recommended.yaml
```

## References

- [Kubernetes Dashboard Documentation](https://kubernetes.io/docs/tasks/access-application-cluster/web-ui-dashboard/)
- [Kubernetes Dashboard GitHub](https://github.com/kubernetes/dashboard)
- [Dashboard User Guide](https://github.com/kubernetes/dashboard/blob/master/docs/user/README.md)
