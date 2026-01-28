# Admin Frontend Deployment

React + Vite + Shadcn/ui admin dashboard served via nginx.

## Architecture

- **Port**: 80 (nginx)
- **URL**: http://admin.109.199.108.243.nip.io
- **Backend API**: http://admin-service.saasodoo.svc.cluster.local:8010
- **API Proxy**: `/api` → admin-service:8010

## Build & Deploy

```bash
# 1. Build Docker image
cd /root/Projects/saasodoo
docker build -t registry.109.199.108.243.nip.io/admin-frontend:latest \
  -f services/admin-frontend/Dockerfile \
  services/admin-frontend/

# 2. Push to registry
docker push registry.109.199.108.243.nip.io/admin-frontend:latest

# 3. Deploy to Kubernetes
kubectl apply -f deploy/platform/admin-frontend/

# 4. Verify deployment
kubectl get pods -n saasodoo -l app.kubernetes.io/name=admin-frontend
kubectl logs -n saasodoo -l app.kubernetes.io/name=admin-frontend --tail=50

# 5. Test health endpoint
kubectl exec -n saasodoo -it $(kubectl get pod -n saasodoo -l app.kubernetes.io/name=admin-frontend -o jsonpath='{.items[0].metadata.name}') -- wget -qO- http://localhost/health
```

## Access

- **Frontend**: http://admin.109.199.108.243.nip.io
- **Health Check**: http://admin.109.199.108.243.nip.io/health
- **Credentials**: Contact system administrator for access

## Features

- **"Data Studio" Aesthetic**: Dark theme with electric cyan accents
- **Authentication**: JWT-based with Zustand persistence
- **Platform Metrics**: Customer count, active instances, MRR, system health
- **Customer Management**: List and view customer details
- **Auto-refresh**: Metrics refresh every 30 seconds

## Troubleshooting

```bash
# Check pod status
kubectl get pods -n saasodoo -l app.kubernetes.io/name=admin-frontend

# View logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=admin-frontend -f

# Check ingress routing
kubectl get ingressroute -n saasodoo admin-frontend -o yaml

# Test backend connectivity from pod
kubectl exec -n saasodoo -it $(kubectl get pod -n saasodoo -l app.kubernetes.io/name=admin-frontend -o jsonpath='{.items[0].metadata.name}') -- wget -qO- http://admin-service.saasodoo.svc.cluster.local:8010/health

# Force redeploy
kubectl rollout restart deployment/admin-frontend -n saasodoo
kubectl rollout status deployment/admin-frontend -n saasodoo
```

## Configuration

Nginx proxies `/api` requests to the admin-service backend. No environment variables required - all configuration is baked into the build.
