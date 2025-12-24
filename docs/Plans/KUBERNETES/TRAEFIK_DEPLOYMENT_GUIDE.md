# Traefik v3 Deployment Guide for Kubernetes

**Date:** 2025-12-23
**Status:** ✅ Working
**Environment:** Docker Desktop Kubernetes on WSL2

---

## Overview

This guide documents the successful deployment of Traefik v3.0 as an ingress controller on Kubernetes, replacing the Docker Swarm label-based routing with Kubernetes-native IngressRoute CRDs.

## Architecture Comparison

### Docker Swarm (Previous)
```yaml
# Services use labels for routing
labels:
  - "traefik.http.routers.frontend.rule=Host(`app.${BASE_DOMAIN}`)"
  - "traefik.http.services.frontend.loadbalancer.server.port=3000"

# BASE_DOMAIN passed as environment variable
environment:
  - BASE_DOMAIN=${BASE_DOMAIN}
```

### Kubernetes (Current)
```yaml
# Services use IngressRoute CRDs
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: frontend
spec:
  routes:
    - match: Host(`app.saasodoo.local`)
      services:
        - name: frontend-service
          port: 3000
```

---

## Deployment Structure

```
infrastructure/orchestration/kubernetes/networking/traefik/
├── 00-crds.yaml          # Documentation (points to official CRDs)
├── 01-rbac.yaml          # ServiceAccount, ClusterRole, ClusterRoleBinding
├── 02-configmap.yaml     # Traefik static configuration
├── 03-deployment.yaml    # Traefik Deployment
├── 04-service.yaml       # LoadBalancer Service
└── 05-dashboard.yaml     # Dashboard IngressRoute
```

---

## File Breakdown

### 1. CRDs (Custom Resource Definitions)

**File:** `00-crds.yaml` (Documentation only)

**Action:** Apply official CRDs from Traefik repository:
```bash
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.0/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
```

**CRDs Installed:**
- `IngressRoute` - HTTP routing rules
- `IngressRouteTCP` - TCP routing
- `IngressRouteUDP` - UDP routing
- `Middleware` - HTTP middleware (stripPrefix, auth, etc.)
- `MiddlewareTCP` - TCP middleware
- `ServersTransport` - HTTP transport settings
- `ServersTransportTCP` - TCP transport settings
- `TLSOption` - TLS configuration
- `TLSStore` - Certificate storage
- `TraefikService` - Service load balancing

---

### 2. RBAC (Role-Based Access Control)

**File:** `01-rbac.yaml`

**Components:**
- **ServiceAccount:** `traefik` in `saasodoo` namespace
- **ClusterRole:** Permissions to read Services, Endpoints, Secrets, and all Traefik CRDs
- **ClusterRoleBinding:** Links ServiceAccount to ClusterRole

**Key Permissions:**
```yaml
rules:
  - apiGroups: [""]
    resources: [services, endpoints, secrets]
    verbs: [get, list, watch]

  - apiGroups: [traefik.io]
    resources: [ingressroutes, middlewares, ...]
    verbs: [get, list, watch]
```

---

### 3. Configuration

**File:** `02-configmap.yaml`

**Key Settings:**

```yaml
# API & Dashboard
api:
  dashboard: true
  insecure: true  # Dev mode - secure in production

# Health Check Endpoint (CRITICAL!)
ping:
  entryPoint: traefik  # Required for liveness/readiness probes

# Entry Points
entryPoints:
  web:
    address: ":80"      # HTTP traffic
  traefik:
    address: ":8080"    # Admin/Dashboard

# Providers
providers:
  kubernetesCRD:
    namespaces:
      - saasodoo
```

**Important Notes:**
- `ping` endpoint is **required** for Kubernetes health probes
- Without it, pods will fail liveness checks and restart continuously
- The `enabled: true` syntax is invalid in Traefik v3 - remove it

---

### 4. Deployment

**File:** `03-deployment.yaml`

**Deployment Spec:**
```yaml
replicas: 1
image: traefik:v3.0

# Health Probes (uses /ping endpoint)
livenessProbe:
  httpGet:
    path: /ping
    port: 8080

readinessProbe:
  httpGet:
    path: /ping
    port: 8080

# Security Context
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
    add: [NET_BIND_SERVICE]
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 65532

# Resources
resources:
  limits:
    cpu: "1000m"
    memory: "512Mi"
  requests:
    cpu: "100m"
    memory: "128Mi"
```

---

### 5. Service

**File:** `04-service.yaml`

**Service Type:** `LoadBalancer`

**Ports:**
- **80** → HTTP traffic (web entrypoint)
- **8080** → Dashboard & API (admin entrypoint)

**Docker Desktop Behavior:**
- LoadBalancer stays in `<pending>` state
- Ports exposed via NodePort instead
- Port 80: accessible via `http://localhost`
- Port 8080: requires port-forward

---

### 6. Dashboard IngressRoute

**File:** `05-dashboard.yaml`

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: traefik-dashboard
spec:
  entryPoints:
    - traefik  # Port 8080
  routes:
    - match: PathPrefix(`/dashboard`) || PathPrefix(`/api`)
      kind: Rule
      services:
        - kind: TraefikService
          name: api@internal  # Special Traefik internal service
```

**Access Methods:**

**Docker Desktop (Development):**
```bash
kubectl port-forward -n saasodoo svc/traefik 8080:8080
# Then: http://localhost:8080/dashboard/
```

**VPS/Cloud (Production):**
```bash
# Option 1: NodePort (if LoadBalancer unavailable)
kubectl get svc traefik -n saasodoo
# Access via: http://<node-ip>:<nodeport>/dashboard/

# Option 2: Domain-based (recommended)
# Create IngressRoute on port 80:
# Host(`traefik.yourdomain.com`)
```

---

## Deployment Commands

### Full Deployment

```bash
# 1. Create namespace
kubectl create namespace saasodoo

# 2. Apply CRDs
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.0/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml

# 3. Apply Traefik manifests
kubectl apply -f infrastructure/orchestration/kubernetes/networking/traefik/

# 4. Verify deployment
kubectl get pods,svc,ingressroute -n saasodoo

# 5. Access dashboard (Docker Desktop)
kubectl port-forward -n saasodoo svc/traefik 8080:8080
# Open: http://localhost:8080/dashboard/
```

### Teardown

```bash
# Delete namespace (removes everything)
kubectl delete namespace saasodoo

# Delete CRDs
kubectl delete crd \
  ingressroutes.traefik.io \
  middlewares.traefik.io \
  traefikservices.traefik.io \
  ingressroutetcps.traefik.io \
  ingressrouteudps.traefik.io \
  tlsoptions.traefik.io \
  tlsstores.traefik.io \
  serverstransports.traefik.io \
  middlewaretcps.traefik.io \
  serverstransporttcps.traefik.io

# Delete cluster-level RBAC
kubectl delete clusterrole traefik
kubectl delete clusterrolebinding traefik
```

---

## Troubleshooting

### Pod CrashLoopBackOff

**Symptom:** Traefik pod keeps restarting

**Common Causes:**
1. **Missing `/ping` endpoint** in config
   - Solution: Add `ping: { entryPoint: traefik }` to ConfigMap

2. **Invalid config syntax**
   - Check: `kubectl logs -n saasodoo deployment/traefik`
   - Look for: `"error":"command traefik error: field not found"`

3. **RBAC permissions missing**
   - Ensure ClusterRole includes all CRD types
   - Include: `middlewaretcps`, `serverstransporttcps`

### Dashboard Not Accessible

**Symptom:** 404 or connection refused on port 8080

**Solutions:**

1. **LoadBalancer pending (Docker Desktop):**
   ```bash
   # Use port-forward instead
   kubectl port-forward -n saasodoo svc/traefik 8080:8080
   ```

2. **Check IngressRoute:**
   ```bash
   kubectl get ingressroute -n saasodoo -o yaml
   # Verify: entryPoints: [traefik]
   # Verify: services.kind: TraefikService
   # Verify: services.name: api@internal
   ```

3. **Check service:**
   ```bash
   kubectl get svc traefik -n saasodoo
   # Should show port 8080
   ```

### CRD Validation Errors

**Symptom:** `unknown field "spec.routes[0].services[0].kind"`

**Cause:** Using custom CRDs instead of official ones

**Solution:**
```bash
# Delete custom CRDs
kubectl delete crd ingressroutes.traefik.io

# Apply official CRDs
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v3.0/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
```

---

## Key Differences: Docker Swarm vs Kubernetes

| Feature | Docker Swarm | Kubernetes |
|---------|-------------|------------|
| **Routing** | Labels on services | IngressRoute CRDs |
| **Config** | File provider + labels | ConfigMap + CRDs |
| **Discovery** | Docker socket | Kubernetes API |
| **Variables** | `${BASE_DOMAIN}` in labels | Hardcoded in manifests |
| **Dashboard** | `traefik.${BASE_DOMAIN}` | Port-forward or IngressRoute |
| **SSL** | Let's Encrypt automatic | Manual cert-manager setup |

---

## Production Considerations

### 1. Domain Configuration

**Challenge:** Kubernetes IngressRoutes don't support environment variable substitution like Docker Swarm labels.

**Options:**

**A. Templating (Recommended for simple cases):**
```bash
export BASE_DOMAIN="yourdomain.com"
envsubst < ingressroute.yaml.template | kubectl apply -f -
```

**B. Kustomize (Recommended for multiple environments):**
```yaml
# base/kustomization.yaml
resources:
  - traefik/

# overlays/prod/kustomization.yaml
bases:
  - ../../base
patches:
  - target:
      kind: IngressRoute
    patch: |-
      - op: replace
        path: /spec/routes/0/match
        value: Host(`app.yourdomain.com`)
```

**C. Helm Charts (Most flexible, most complex):**
```yaml
# values.yaml
baseDomain: yourdomain.com

# template:
match: Host(`app.{{ .Values.baseDomain }}`)
```

### 2. TLS/SSL

**Docker Swarm:**
```yaml
labels:
  - "traefik.http.routers.frontend.tls.certresolver=letsencrypt"
```

**Kubernetes:**
```yaml
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@yourdomain.com
    privateKeySecretRef:
      name: letsencrypt-key
    solvers:
      - http01:
          ingress:
            class: traefik
```

### 3. Dashboard Security

**Development (Current):**
```yaml
api:
  dashboard: true
  insecure: true  # ⚠️ NOT SECURE
```

**Production (Required):**
```yaml
# 1. Disable insecure mode
api:
  dashboard: true
  insecure: false

# 2. Create BasicAuth Middleware
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: dashboard-auth
spec:
  basicAuth:
    secret: dashboard-users  # htpasswd secret

# 3. Apply to IngressRoute
spec:
  routes:
    - match: Host(`traefik.yourdomain.com`)
      middlewares:
        - name: dashboard-auth
      services:
        - kind: TraefikService
          name: api@internal
```

### 4. High Availability

```yaml
# Increase replicas
spec:
  replicas: 3

# Add pod anti-affinity
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchLabels:
              app.kubernetes.io/name: traefik
          topologyKey: kubernetes.io/hostname
```

---

## Migration from Swarm

### Step 1: Extract Routing Rules

From Swarm labels:
```yaml
labels:
  - "traefik.http.routers.frontend.rule=Host(`app.${BASE_DOMAIN}`)"
  - "traefik.http.routers.frontend.middlewares=cors"
  - "traefik.http.services.frontend.loadbalancer.server.port=3000"
```

To Kubernetes IngressRoute:
```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: frontend
spec:
  entryPoints:
    - web
  routes:
    - match: Host(`app.yourdomain.com`)
      kind: Rule
      middlewares:
        - name: cors
      services:
        - name: frontend-service
          port: 3000
```

### Step 2: Convert Middlewares

From Swarm labels:
```yaml
labels:
  - "traefik.http.middlewares.user-strip.stripprefix.prefixes=/user"
```

To Kubernetes Middleware:
```yaml
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: user-stripprefix
spec:
  stripPrefix:
    prefixes:
      - /user
```

### Step 3: Update Services

Services need:
1. Kubernetes Service (ClusterIP)
2. IngressRoute pointing to that Service

---

## Next Steps

1. **Deploy Infrastructure Layer**
   - PostgreSQL with PVCs
   - Redis with PVCs
   - RabbitMQ with IngressRoute
   - KillBill + Kaui with IngressRoutes

2. **Deploy Application Services**
   - user-service → `api.domain.com/user`
   - billing-service → `api.domain.com/billing`
   - instance-service → `api.domain.com/instance`
   - frontend-service → `app.domain.com`

3. **Configure Domain Routing**
   - Solve BASE_DOMAIN templating
   - Create all IngressRoutes
   - Test end-to-end routing

4. **Add TLS/SSL**
   - Install cert-manager
   - Configure Let's Encrypt
   - Update IngressRoutes with TLS

5. **Production Hardening**
   - Secure dashboard with BasicAuth
   - Set resource limits
   - Configure monitoring/logging
   - Set up backup strategy

---

## Verification Checklist

- [x] Namespace created
- [x] CRDs installed from official source
- [x] RBAC configured with all permissions
- [x] Traefik ConfigMap with ping endpoint
- [x] Traefik Deployment running (1/1 Ready)
- [x] Service created (LoadBalancer type)
- [x] Dashboard IngressRoute created
- [x] Dashboard accessible via port-forward
- [ ] TLS/SSL configured
- [ ] Production domains configured
- [ ] High availability setup
- [ ] Monitoring configured

---

## References

- [Traefik v3 Documentation](https://doc.traefik.io/traefik/v3.0/)
- [Kubernetes CRD Provider](https://doc.traefik.io/traefik/providers/kubernetes-crd/)
- [Official CRD Definitions](https://github.com/traefik/traefik/tree/v3.0/docs/content/reference/dynamic-configuration)
- [Docker Swarm Migration Guide](https://doc.traefik.io/traefik/migration/v2-to-v3/)

---

**Document Version:** 1.0
**Last Updated:** 2025-12-23
**Tested On:** Docker Desktop Kubernetes v1.33 (WSL2)
