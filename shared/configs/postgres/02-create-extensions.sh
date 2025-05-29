#!/bin/bash
set -e

# PostgreSQL Extensions Installation Wrapper Script
# Substitutes environment variables and executes the SQL script

echo "Installing PostgreSQL extensions with environment variables..."

# Set default database name if not set
export POSTGRES_DB="${POSTGRES_DB:-saas_odoo}"

# Create temporary SQL file with substituted variables
TEMP_SQL_FILE="/tmp/create-extensions-substituted.sql"

# Use shell substitution instead of envsubst
sed "s/\${POSTGRES_DB}/$POSTGRES_DB/g" /docker-entrypoint-initdb.d/02-create-extensions.sql.template > "$TEMP_SQL_FILE"

# Execute the substituted SQL script
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$TEMP_SQL_FILE"

# Clean up
rm -f "$TEMP_SQL_FILE"

echo "✅ PostgreSQL extensions installed successfully!" 