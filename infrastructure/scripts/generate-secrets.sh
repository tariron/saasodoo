#!/bin/bash
# Generate all Kubernetes secrets for SaaSOdoo platform
# This script creates secret files from templates with secure random values

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================="
echo "SaaSOdoo Secrets Generator"
echo "========================================="
echo ""

# Function to generate a secure random password
generate_password() {
    local length=${1:-32}
    openssl rand -base64 48 | tr -d "=+/" | cut -c1-${length}
}

# Function to generate JWT secret (64 chars)
generate_jwt_secret() {
    openssl rand -hex 32
}

echo "Generating secure random values..."
echo ""

# Generate passwords
POSTGRES_ADMIN_PASSWORD=$(generate_password 32)
AUTH_SERVICE_PASSWORD=$(generate_password 32)
BILLING_SERVICE_PASSWORD=$(generate_password 32)
INSTANCE_SERVICE_PASSWORD=$(generate_password 32)
DATABASE_SERVICE_PASSWORD=$(generate_password 32)
NOTIFICATION_SERVICE_PASSWORD=$(generate_password 32)
JWT_SECRET=$(generate_jwt_secret)
RABBITMQ_PASSWORD=$(generate_password 24)
KILLBILL_MYSQL_PASSWORD=$(generate_password 32)
GRAFANA_ADMIN_PASSWORD=$(generate_password 24)
GRAFANA_SECRET_KEY=$(generate_jwt_secret)
READONLY_USER_PASSWORD=$(generate_password 24)
BACKUP_USER_PASSWORD=$(generate_password 24)

echo "✓ Generated secure random passwords"
echo ""

# Prompt for PayNow credentials (payment gateway)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Payment Gateway Configuration (PayNow)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Enter PayNow Integration ID (or press Enter to skip): " PAYNOW_INTEGRATION_ID
read -p "Enter PayNow Integration Key (or press Enter to skip): " PAYNOW_INTEGRATION_KEY
read -p "Enter PayNow Merchant Email (or press Enter to skip): " PAYNOW_MERCHANT_EMAIL
echo ""

# Prompt for SMTP (optional)
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Email Configuration (Optional - Leave blank to use MailHog)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Enter SMTP Username (or press Enter to skip): " SMTP_USERNAME
if [ -n "$SMTP_USERNAME" ]; then
    read -sp "Enter SMTP Password: " SMTP_PASSWORD
    echo ""
fi
echo ""

# Create main secrets file
echo "Creating infrastructure/secrets/00-secrets.yaml..."
cat > "$INFRA_ROOT/secrets/00-secrets.yaml" <<EOF
---
apiVersion: v1
kind: Secret
metadata:
  name: saasodoo-secrets
  namespace: saasodoo
type: Opaque
stringData:
  # PostgreSQL Service Users (one per service)
  POSTGRES_AUTH_SERVICE_USER: "auth_service"
  POSTGRES_AUTH_SERVICE_PASSWORD: "${AUTH_SERVICE_PASSWORD}"

  POSTGRES_BILLING_SERVICE_USER: "billing_service"
  POSTGRES_BILLING_SERVICE_PASSWORD: "${BILLING_SERVICE_PASSWORD}"

  POSTGRES_INSTANCE_SERVICE_USER: "instance_service"
  POSTGRES_INSTANCE_SERVICE_PASSWORD: "${INSTANCE_SERVICE_PASSWORD}"

  POSTGRES_DATABASE_SERVICE_USER: "database_service"
  POSTGRES_DATABASE_SERVICE_PASSWORD: "${DATABASE_SERVICE_PASSWORD}"

  # PostgreSQL Admin Credentials (for database management)
  POSTGRES_ADMIN_USER: "postgres"
  POSTGRES_ADMIN_PASSWORD: "${POSTGRES_ADMIN_PASSWORD}"

  # Legacy PostgreSQL credentials (for backward compatibility)
  POSTGRES_USER: "odoo_user"
  POSTGRES_PASSWORD: "${POSTGRES_ADMIN_PASSWORD}"

  # JWT Authentication
  JWT_SECRET_KEY: "${JWT_SECRET}"

  # KillBill Credentials
  KILLBILL_API_KEY: "fresh-tenant"
  KILLBILL_API_SECRET: "fresh-secret"
  KILLBILL_PASSWORD: "password"

  # PayNow Payment Gateway
  PAYNOW_INTEGRATION_ID: "${PAYNOW_INTEGRATION_ID}"
  PAYNOW_INTEGRATION_KEY: "${PAYNOW_INTEGRATION_KEY}"
  PAYNOW_MERCHANT_EMAIL: "${PAYNOW_MERCHANT_EMAIL}"

  # RabbitMQ
  RABBITMQ_PASSWORD: "${RABBITMQ_PASSWORD}"

  # KillBill MariaDB
  KILLBILL_MYSQL_ROOT_PASSWORD: "${KILLBILL_MYSQL_PASSWORD}"

  # SMTP Config for Notifications
  SMTP_USERNAME: "${SMTP_USERNAME}"
  SMTP_PASSWORD: "${SMTP_PASSWORD}"
EOF

echo "✓ Created infrastructure/secrets/00-secrets.yaml"
echo ""

# Create user-service secret
echo "Creating services/user-service/00-secret.yaml..."
cat > "$INFRA_ROOT/services/user-service/00-secret.yaml" <<EOF
---
# User Service Secrets
apiVersion: v1
kind: Secret
metadata:
  name: user-service-secret
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: user-service
    app.kubernetes.io/component: backend
type: Opaque
stringData:
  # Database Credentials
  DB_SERVICE_PASSWORD: "${AUTH_SERVICE_PASSWORD}"

  # JWT Secret
  JWT_SECRET_KEY: "${JWT_SECRET}"
EOF

echo "✓ Created services/user-service/00-secret.yaml"

# Create billing-service secret
echo "Creating services/billing-service/00-secret.yaml..."
cat > "$INFRA_ROOT/services/billing-service/00-secret.yaml" <<EOF
---
# Billing Service Secrets
apiVersion: v1
kind: Secret
metadata:
  name: billing-service-secret
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: billing-service
    app.kubernetes.io/component: backend
type: Opaque
stringData:
  # Database Credentials
  DB_SERVICE_PASSWORD: "${BILLING_SERVICE_PASSWORD}"

  # KillBill Credentials
  KILLBILL_API_SECRET: "fresh-secret"
  KILLBILL_PASSWORD: "password"

  # PayNow Payment Gateway Credentials
  PAYNOW_INTEGRATION_ID: "${PAYNOW_INTEGRATION_ID}"
  PAYNOW_INTEGRATION_KEY: "${PAYNOW_INTEGRATION_KEY}"
EOF

echo "✓ Created services/billing-service/00-secret.yaml"

# Create instance-service secret
echo "Creating services/instance-service/00-secret.yaml..."
cat > "$INFRA_ROOT/services/instance-service/00-secret.yaml" <<EOF
---
# Instance Service Secrets
apiVersion: v1
kind: Secret
metadata:
  name: instance-service-secret
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: instance-service
    app.kubernetes.io/component: backend
type: Opaque
stringData:
  # Database Credentials
  DB_SERVICE_PASSWORD: "${INSTANCE_SERVICE_PASSWORD}"

  # RabbitMQ Password
  RABBITMQ_PASSWORD: "${RABBITMQ_PASSWORD}"
EOF

echo "✓ Created services/instance-service/00-secret.yaml"

# Create database-service secret
echo "Creating services/database-service/00-secret.yaml..."
cat > "$INFRA_ROOT/services/database-service/00-secret.yaml" <<EOF
---
# Database Service Secrets
apiVersion: v1
kind: Secret
metadata:
  name: database-service-secret
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: database-service
    app.kubernetes.io/component: backend
type: Opaque
stringData:
  # Database Credentials
  DB_SERVICE_PASSWORD: "${DATABASE_SERVICE_PASSWORD}"

  # PostgreSQL Admin Credentials (for creating databases)
  POSTGRES_ADMIN_PASSWORD: "${POSTGRES_ADMIN_PASSWORD}"

  # RabbitMQ Password
  RABBITMQ_PASSWORD: "${RABBITMQ_PASSWORD}"
EOF

echo "✓ Created services/database-service/00-secret.yaml"

# Create notification-service secret
echo "Creating services/notification-service/00-secret.yaml..."
cat > "$INFRA_ROOT/services/notification-service/00-secret.yaml" <<EOF
---
# Notification Service Secrets
apiVersion: v1
kind: Secret
metadata:
  name: notification-service-secret
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: notification-service
    app.kubernetes.io/component: backend
type: Opaque
stringData:
  # SMTP Credentials
  SMTP_USERNAME: "${SMTP_USERNAME}"
  SMTP_PASSWORD: "${SMTP_PASSWORD}"
EOF

echo "✓ Created services/notification-service/00-secret.yaml"

# Create Traefik TLS secret (self-signed certificate)
echo "Creating networking/traefik/06-tls-secret.yaml..."
echo "  Generating self-signed TLS certificate..."

# Get server IP from script or use default
SERVER_IP="${SERVER_IP:-62.171.153.219}"
DOMAIN="*.${SERVER_IP}.nip.io"

# Generate certificate files in temp directory
TMP_CERT_DIR=$(mktemp -d)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout "$TMP_CERT_DIR/tls.key" -out "$TMP_CERT_DIR/tls.crt" \
  -subj "/CN=$DOMAIN" \
  -addext "subjectAltName=DNS:$DOMAIN,DNS:${SERVER_IP}.nip.io" 2>/dev/null

# Base64 encode the files
TLS_CRT_B64=$(cat "$TMP_CERT_DIR/tls.crt" | base64 -w 0)
TLS_KEY_B64=$(cat "$TMP_CERT_DIR/tls.key" | base64 -w 0)

cat > "$INFRA_ROOT/networking/traefik/06-tls-secret.yaml" <<EOF
---
# Self-signed TLS certificate for *.${SERVER_IP}.nip.io
# Auto-generated by generate-secrets.sh
apiVersion: v1
kind: Secret
metadata:
  name: traefik-tls
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: traefik
    app.kubernetes.io/component: networking
type: kubernetes.io/tls
data:
  tls.crt: ${TLS_CRT_B64}
  tls.key: ${TLS_KEY_B64}
EOF

# Cleanup temp directory
rm -rf "$TMP_CERT_DIR"

echo "✓ Created networking/traefik/06-tls-secret.yaml"

# Create Grafana secrets
echo "Creating monitoring/grafana/00-secret.yaml..."
cat > "$INFRA_ROOT/monitoring/grafana/00-secret.yaml" <<EOF
---
# Grafana Secrets
apiVersion: v1
kind: Secret
metadata:
  name: grafana-secrets
  namespace: monitoring
  labels:
    app.kubernetes.io/name: grafana
    app.kubernetes.io/component: visualization
    app.kubernetes.io/part-of: saasodoo
type: Opaque
stringData:
  # Admin credentials
  admin-user: admin
  admin-password: ${GRAFANA_ADMIN_PASSWORD}

  # Session secret key
  secret-key: ${GRAFANA_SECRET_KEY}
EOF

echo "✓ Created monitoring/grafana/00-secret.yaml"

# Create RabbitMQ cluster secret
echo "Creating rabbitmq-cluster/00-secret.yaml..."
cat > "$INFRA_ROOT/rabbitmq-cluster/00-secret.yaml" <<EOF
---
# RabbitMQ Admin Credentials
apiVersion: v1
kind: Secret
metadata:
  name: rabbitmq-admin
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: rabbitmq
    app.kubernetes.io/component: messaging
type: Opaque
stringData:
  # Default admin user credentials
  username: saasodoo
  password: "${RABBITMQ_PASSWORD}"

  # Default virtual host
  default_vhost: "saasodoo"
EOF

echo "✓ Created rabbitmq-cluster/00-secret.yaml"

# Create PostgreSQL CNPG secrets
echo "Creating postgres-cnpg/00-secrets.yaml..."
cat > "$INFRA_ROOT/postgres-cnpg/00-secrets.yaml" <<EOF
---
# CloudNativePG Superuser Secret
apiVersion: v1
kind: Secret
metadata:
  name: postgres-cluster-superuser
  namespace: saasodoo
  labels:
    app.kubernetes.io/name: postgres
    app.kubernetes.io/component: database
type: kubernetes.io/basic-auth
stringData:
  username: postgres
  password: "${POSTGRES_ADMIN_PASSWORD}"
---
# CNPG Managed Role Secrets
apiVersion: v1
kind: Secret
metadata:
  name: cnpg-auth-service
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: auth_service
  password: "${AUTH_SERVICE_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: cnpg-billing-service
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: billing_service
  password: "${BILLING_SERVICE_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: cnpg-instance-service
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: instance_service
  password: "${INSTANCE_SERVICE_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: cnpg-database-service
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: database_service
  password: "${DATABASE_SERVICE_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: cnpg-notification-service
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: notification_service
  password: "${NOTIFICATION_SERVICE_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: readonly-user-secret
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: readonly_user
  password: "${READONLY_USER_PASSWORD}"
---
apiVersion: v1
kind: Secret
metadata:
  name: backup-user-secret
  namespace: saasodoo
type: kubernetes.io/basic-auth
stringData:
  username: backup_user
  password: "${BACKUP_USER_PASSWORD}"
EOF

echo "✓ Created postgres-cnpg/00-secrets.yaml"

# Note: Kubernetes Dashboard secret is auto-generated, no need to create it
echo ""

# Summary
echo "========================================="
echo "✅ All secrets generated successfully!"
echo "========================================="
echo ""
echo "Generated files:"
echo "  • infrastructure/secrets/00-secrets.yaml (main secrets)"
echo "  • services/user-service/00-secret.yaml"
echo "  • services/billing-service/00-secret.yaml"
echo "  • services/instance-service/00-secret.yaml"
echo "  • services/database-service/00-secret.yaml"
echo "  • services/notification-service/00-secret.yaml"
echo "  • networking/traefik/06-tls-secret.yaml (TLS certificate)"
echo "  • monitoring/grafana/00-secret.yaml"
echo "  • rabbitmq-cluster/00-secret.yaml"
echo "  • postgres-cnpg/00-secrets.yaml (CNPG cluster secrets)"
echo ""
echo "⚠️  IMPORTANT SECURITY NOTES:"
echo "  1. These files contain sensitive credentials"
echo "  2. They are in .gitignore and will NOT be committed"
echo "  3. Store these passwords securely (password manager recommended)"
echo "  4. Never commit these files to version control"
echo ""
echo "📋 Save these credentials for reference:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "PostgreSQL Admin:        ${POSTGRES_ADMIN_PASSWORD}"
echo "Auth Service:            ${AUTH_SERVICE_PASSWORD}"
echo "Billing Service:         ${BILLING_SERVICE_PASSWORD}"
echo "Instance Service:        ${INSTANCE_SERVICE_PASSWORD}"
echo "Database Service:        ${DATABASE_SERVICE_PASSWORD}"
echo "Notification Service:    ${NOTIFICATION_SERVICE_PASSWORD}"
echo "JWT Secret:              ${JWT_SECRET}"
echo "RabbitMQ:                ${RABBITMQ_PASSWORD}"
echo "KillBill MySQL:          ${KILLBILL_MYSQL_PASSWORD}"
echo "Grafana Admin:           ${GRAFANA_ADMIN_PASSWORD}"
echo "Readonly User:           ${READONLY_USER_PASSWORD}"
echo "Backup User:             ${BACKUP_USER_PASSWORD}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Next step: Run ./infrastructure/scripts/deploy.sh"
echo ""
