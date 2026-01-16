# Sealed Secrets

Encrypt secrets so they can be safely stored in git.

## Install

```bash
# 1. Install controller
kubectl apply -f infrastructure/cluster/addons/sealed-secrets/

# 2. Install kubeseal CLI
wget https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.27.3/kubeseal-0.27.3-linux-amd64.tar.gz
tar xzf kubeseal-0.27.3-linux-amd64.tar.gz
sudo mv kubeseal /usr/local/bin/
rm kubeseal-0.27.3-linux-amd64.tar.gz
```

## Seal a Secret

```bash
# Convert plain secret to sealed secret
kubeseal --format yaml < deploy/00-secrets.yaml > deploy/00-sealed-secrets.yaml

# Apply sealed secret (controller creates real Secret)
kubectl apply -f deploy/00-sealed-secrets.yaml
```

## Unseal / View a Secret

**Option 1: From cluster (if secret exists)**
```bash
# View decoded secret from cluster
kubectl get secret saasodoo-secrets -n saasodoo -o jsonpath='{.data.DB_PASSWORD}' | base64 -d

# Export entire secret to YAML
kubectl get secret saasodoo-secrets -n saasodoo -o yaml > /tmp/secret.yaml
```

**Option 2: Keep original plain secret locally**
```bash
# Best practice: keep plain secrets locally (gitignored), only commit sealed versions
# Edit: deploy/00-secrets.yaml (plain, gitignored)
# Commit: deploy/00-sealed-secrets.yaml (encrypted)
```

## Edit and Reseal

```bash
# 1. Edit your plain secret file (gitignored)
nano deploy/00-secrets.yaml

# 2. Reseal it
kubeseal --format yaml < deploy/00-secrets.yaml > deploy/00-sealed-secrets.yaml

# 3. Apply
kubectl apply -f deploy/00-sealed-secrets.yaml

# 4. Commit the sealed version
git add deploy/00-sealed-secrets.yaml
git commit -m "Update secrets"
```

## Backup Encryption Key

```bash
# IMPORTANT: Backup the controller's private key
# Without this key, you cannot decrypt secrets if cluster is rebuilt

kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > sealed-secrets-key-backup.yaml

# Store this backup securely (NOT in git)
```

## Restore Key (Disaster Recovery)

```bash
# Restore key before installing controller on new cluster
kubectl apply -f sealed-secrets-key-backup.yaml
kubectl apply -f infrastructure/cluster/addons/sealed-secrets/
```

## Workflow Summary

```
┌─────────────────┐     kubeseal      ┌──────────────────┐
│  00-secrets.yaml │ ───────────────> │ 00-sealed-secrets│
│  (plain, local)  │                  │ (encrypted, git) │
│  .gitignore      │                  │                  │
└─────────────────┘                   └────────┬─────────┘
                                               │
                                         kubectl apply
                                               │
                                               ▼
                                      ┌─────────────────┐
                                      │ Secret (cluster)│
                                      │ (auto-created)  │
                                      └─────────────────┘
```
