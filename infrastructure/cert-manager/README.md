# cert-manager

Automatic TLS certificate management for Kubernetes using Let's Encrypt.

## Installation

```bash
# Install cert-manager
kubectl apply -f infrastructure/cert-manager/

# Wait for cert-manager to be ready
kubectl wait --for=condition=Available deployment/cert-manager -n cert-manager --timeout=120s
kubectl wait --for=condition=Available deployment/cert-manager-webhook -n cert-manager --timeout=120s

# Verify CRDs are installed
kubectl get crd | grep cert-manager
```

## Configuration

1. Update email address in `02-cluster-issuers.yaml`:
   ```yaml
   email: your-email@yourdomain.com
   ```

2. Apply the issuers:
   ```bash
   kubectl apply -f infrastructure/cert-manager/02-cluster-issuers.yaml
   ```

## Usage

### Request a Certificate for a Service

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: app-example-com
  namespace: saasodoo
spec:
  secretName: app-example-com-tls
  issuerRef:
    name: letsencrypt-prod  # or letsencrypt-staging for testing
    kind: ClusterIssuer
  dnsNames:
    - app.example.com
    - api.example.com
```

### Use with Traefik IngressRoute

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: app-secure
spec:
  entryPoints:
    - websecure
  routes:
    - match: Host(`app.example.com`)
      kind: Rule
      services:
        - name: my-service
          port: 80
  tls:
    secretName: app-example-com-tls
```

## Cluster Issuers

| Issuer | Purpose |
|--------|---------|
| `letsencrypt-staging` | Testing (fake certs, high rate limits) |
| `letsencrypt-prod` | Production (real certs, rate limited) |
| `selfsigned` | Internal services / development |

## Troubleshooting

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app.kubernetes.io/name=cert-manager

# Check certificate status
kubectl get certificates -A
kubectl describe certificate <name> -n <namespace>

# Check certificate requests
kubectl get certificaterequests -A

# Check challenges (for ACME)
kubectl get challenges -A
```
