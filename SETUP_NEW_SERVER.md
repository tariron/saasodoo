# Setup SaaSOdoo on New Server

This guide walks you through setting up the SaaSOdoo platform on a fresh server.

## Prerequisites

- Kubernetes cluster running (k3s, k0s, or full Kubernetes)
- Docker installed and running
- `kubectl` configured to access your cluster
- `openssl` installed (for generating secrets)

## Step 1: Clone the Repository

```bash
cd ~/Projects
git clone <your-repo-url> saasodoo
cd saasodoo
```

## Step 2: Generate All Secrets

The secrets were not cloned (correctly, they're in `.gitignore`). Generate new ones:

```bash
# Make the script executable
chmod +x infrastructure/scripts/generate-secrets.sh

# Run the secrets generator
./infrastructure/scripts/generate-secrets.sh
```

**What this script does:**
- Generates secure random passwords for all services
- Prompts you for PayNow payment gateway credentials (optional)
- Prompts you for SMTP email credentials (optional, leave blank to use MailHog)
- Creates all required secret files:
  - `infrastructure/secrets/00-secrets.yaml` (main secrets)
  - `services/user-service/00-secret.yaml`
  - `services/billing-service/00-secret.yaml`
  - `services/instance-service/00-secret.yaml`
  - `services/database-service/00-secret.yaml`
  - `services/notification-service/00-secret.yaml`

**⚠️ IMPORTANT:** Save the passwords printed at the end somewhere secure!

## Step 3: Update Configuration (Optional)

If your server IP is different from `62.171.153.219`, update these files:

```bash
# Find all references to the old IP
grep -r "62.171.153.219" infrastructure/

# Update DNS entries in ingress routes
# Edit: infrastructure/networking/traefik/06-*.yaml files
# Replace: 62.171.153.219.nip.io with YOUR_IP.nip.io
```

## Step 4: Build and Push Docker Images

```bash
# Make the script executable
chmod +x infrastructure/scripts/build-and-push.sh

# Update PROJECT_ROOT in the script if needed
nano infrastructure/scripts/build-and-push.sh
# Change: PROJECT_ROOT="/root/Projects/saasodoo"
# To:     PROJECT_ROOT="$(pwd)"

# Run the build script
./infrastructure/scripts/build-and-push.sh
```

This builds and pushes all images to your local registry at `registry.YOUR_IP.nip.io`.

## Step 5: Deploy the Platform

```bash
# Make the deploy script executable
chmod +x infrastructure/scripts/deploy.sh

# Deploy everything
./infrastructure/scripts/deploy.sh
```

The deployment happens in layers:
1. **Layer 0:** Namespaces, secrets, storage, RBAC
2. **Layer 1:** Networking (Traefik)
3. **Layer 2:** Image building (you did this in Step 4)
4. **Layer 3:** Infrastructure (PostgreSQL, Redis, RabbitMQ)
5. **Layer 4:** Application stack (KillBill, microservices)

## Step 6: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n saasodoo

# Check services
kubectl get svc -n saasodoo

# Check ingress routes
kubectl get ingressroute -n saasodoo

# View logs if something fails
kubectl logs -n saasodoo -l app.kubernetes.io/name=user-service --tail=50
```

## Step 7: Access the Platform

### Update /etc/hosts (if using .nip.io locally)

```bash
# On your local machine (not the server)
sudo nano /etc/hosts

# Add these lines (replace YOUR_IP)
YOUR_IP api.saasodoo.local
YOUR_IP app.saasodoo.local
YOUR_IP billing.saasodoo.local
YOUR_IP billing-admin.saasodoo.local
YOUR_IP rabbitmq.saasodoo.local
YOUR_IP mail.saasodoo.local
```

### Access URLs

- **Frontend:** `http://app.YOUR_IP.nip.io`
- **API:** `http://api.YOUR_IP.nip.io/user/docs`
- **Traefik Dashboard:** `http://YOUR_IP:8080/dashboard/`
- **KillBill Admin (Kaui):** `http://billing-admin.YOUR_IP.nip.io` (admin/password)
- **RabbitMQ:** `http://rabbitmq.YOUR_IP.nip.io` (guest/saasodoo123)
- **MailHog:** `http://mail.YOUR_IP.nip.io`

## Troubleshooting

### Pods not starting

```bash
# Describe the pod
kubectl describe pod -n saasodoo <pod-name>

# View logs
kubectl logs -n saasodoo <pod-name> --tail=100
```

### Database connection issues

```bash
# Check PostgreSQL is running
kubectl get pods -n saasodoo -l app.kubernetes.io/name=postgres

# Exec into postgres pod
kubectl exec -it -n saasodoo postgres-0 -- bash

# Test database connection
psql -U postgres -c "SELECT version();"
```

### Image pull errors

```bash
# Check registry is accessible
curl http://registry.YOUR_IP.nip.io/v2/_catalog

# Rebuild and push images
./infrastructure/scripts/build-and-push.sh
```

### Secrets not found

```bash
# Verify secrets exist
kubectl get secrets -n saasodoo

# Re-run secrets generator if missing
./infrastructure/scripts/generate-secrets.sh
```

## Quick Reference Commands

```bash
# View all resources
kubectl get all -n saasodoo

# Restart a service
kubectl rollout restart deployment/user-service -n saasodoo

# Scale a service
kubectl scale deployment/instance-worker --replicas=3 -n saasodoo

# Delete everything and start over
./infrastructure/scripts/teardown.sh
./infrastructure/scripts/deploy.sh

# Check resource usage
kubectl top pods -n saasodoo
kubectl top nodes
```

## Production Checklist

Before going to production:

- [ ] Change all default passwords in secrets
- [ ] Configure real SMTP credentials (not MailHog)
- [ ] Set up proper DNS (not .nip.io)
- [ ] Configure SSL/TLS certificates
- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Configure backups for PostgreSQL
- [ ] Set resource limits on all deployments
- [ ] Review and harden RBAC permissions
- [ ] Enable authentication on RabbitMQ management UI
- [ ] Set up log aggregation (ELK/Loki)

## Support

See documentation in `docs/` directory:
- `SAASODOO_PROJECT_SUMMARY.md` - Architecture overview
- `ISSUES_LOG.md` - Known issues and solutions
- `KUBERNETES_MIGRATION_PLAN.md` - Deployment details
