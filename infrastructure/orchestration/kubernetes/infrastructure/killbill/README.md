# KillBill Billing System

KillBill is an open-source subscription billing and payment platform.

## Components

### 1. MariaDB (`mariadb/`)
- Pre-configured MariaDB database with KillBill schemas
- Image: `killbill/mariadb:0.24`
- Databases: `killbill`, `kaui`
- Storage: CephFS at `/mnt/cephfs/killbill_db_data`

### 2. KillBill (`killbill/`)
- Subscription billing engine
- Image: `killbill/killbill:0.24.15`
- API URL: `http://billing.62.171.153.219.nip.io`
- Webhook URL: `http://billing-service:8004/api/billing/webhooks/killbill`

### 3. Kaui (`kaui/`)
- KillBill admin web UI
- Image: `killbill/kaui:3.0.23`
- Admin URL: `http://billing-admin.62.171.153.219.nip.io`
- Default credentials: `admin / password`

## Deployment Order

```bash
cd /root/Projects/saasodoo/infrastructure/orchestration/kubernetes

# 1. Deploy MariaDB first
kubectl apply -f infrastructure/killbill/mariadb/

# 2. Wait for MariaDB to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=killbill-db -n saasodoo --timeout=120s

# 3. Deploy KillBill
kubectl apply -f infrastructure/killbill/killbill/

# 4. Wait for KillBill to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=killbill -n saasodoo --timeout=300s

# 5. Deploy Kaui (optional - admin UI)
kubectl apply -f infrastructure/killbill/kaui/
```

## Configuration

### Test Mode
KillBill is configured in test mode (`KILLBILL_SERVER_TEST_MODE=true`) which enables:
- Clock manipulation for testing subscription events
- Test mode APIs

### Multi-tenancy
Enabled via `KILLBILL_SERVER_MULTITENANT=true`

### API Credentials
- API Key: From `KILLBILL_API_KEY` in ConfigMap
- API Secret: From `KILLBILL_API_SECRET` in Secrets
- Username: From `KILLBILL_USERNAME` in ConfigMap
- Password: From `KILLBILL_PASSWORD` in Secrets

## Access

### KillBill API
```bash
# Health check
curl http://billing.62.171.153.219.nip.io/1.0/healthcheck

# Get tenant info (requires auth)
curl -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  http://billing.62.171.153.219.nip.io/1.0/kb/tenants
```

### Kaui Admin UI
1. Open: http://billing-admin.62.171.153.219.nip.io
2. Login with: `admin / password`

## Troubleshooting

```bash
# Check MariaDB logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=killbill-db

# Check KillBill logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=killbill

# Check Kaui logs
kubectl logs -n saasodoo -l app.kubernetes.io/name=kaui

# Check database connectivity
kubectl exec -it -n saasodoo killbill-db-0 -- mysql -u root -p
```

## References
- [KillBill Documentation](https://docs.killbill.io/)
- [KillBill GitHub](https://github.com/killbill/killbill)
- [Kaui GitHub](https://github.com/killbill/killbill-admin-ui)
