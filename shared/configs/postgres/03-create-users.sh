#!/bin/bash
set -e

# PostgreSQL Users Creation Wrapper Script
# Substitutes environment variables and executes the SQL script

echo "Creating PostgreSQL service users with environment variables..."

# Set default values if environment variables are not set
export POSTGRES_READONLY_PASSWORD="${POSTGRES_READONLY_PASSWORD:-readonly123}"
export POSTGRES_BACKUP_PASSWORD="${POSTGRES_BACKUP_PASSWORD:-backup123}"
export POSTGRES_AUTH_SERVICE_PASSWORD="${POSTGRES_AUTH_SERVICE_PASSWORD:-auth_service123}"
export POSTGRES_BILLING_SERVICE_PASSWORD="${POSTGRES_BILLING_SERVICE_PASSWORD:-billing_service123}"
export POSTGRES_TENANT_SERVICE_PASSWORD="${POSTGRES_TENANT_SERVICE_PASSWORD:-tenant_service123}"

# Create temporary SQL file with substituted variables
TEMP_SQL_FILE="/tmp/create-users-substituted.sql"

# Use shell substitution instead of envsubst
sed -e "s/\${POSTGRES_READONLY_PASSWORD}/$POSTGRES_READONLY_PASSWORD/g" \
    -e "s/\${POSTGRES_BACKUP_PASSWORD}/$POSTGRES_BACKUP_PASSWORD/g" \
    -e "s/\${POSTGRES_AUTH_SERVICE_PASSWORD}/$POSTGRES_AUTH_SERVICE_PASSWORD/g" \
    -e "s/\${POSTGRES_BILLING_SERVICE_PASSWORD}/$POSTGRES_BILLING_SERVICE_PASSWORD/g" \
    -e "s/\${POSTGRES_TENANT_SERVICE_PASSWORD}/$POSTGRES_TENANT_SERVICE_PASSWORD/g" \
    /docker-entrypoint-initdb.d/03-create-users.sql.template > "$TEMP_SQL_FILE"

# Execute the substituted SQL script
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$TEMP_SQL_FILE"

# Clean up
rm -f "$TEMP_SQL_FILE"

echo "✅ PostgreSQL service users created successfully!" 