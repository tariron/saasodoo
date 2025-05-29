#!/bin/bash
set -e

# PostgreSQL Database Initialization Script
# Creates multiple databases for Odoo SaaS Kit

echo "Creating multiple databases for Odoo SaaS Kit..."

# Function to create database if it doesn't exist
create_database() {
    local db_name=$1
    echo "Creating database: $db_name"
    
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
        SELECT 'CREATE DATABASE $db_name' 
        WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db_name')\gexec
        
        -- Grant privileges to the main user
        GRANT ALL PRIVILEGES ON DATABASE $db_name TO $POSTGRES_USER;
EOSQL
}

# Create databases from environment variable or defaults
if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    # Split the comma-separated list and create each database
    IFS=',' read -ra DATABASES <<< "$POSTGRES_MULTIPLE_DATABASES"
    for db in "${DATABASES[@]}"; do
        # Trim whitespace
        db=$(echo "$db" | xargs)
        create_database "$db"
    done
else
    # Default databases for Odoo SaaS Kit
    echo "POSTGRES_MULTIPLE_DATABASES not set, creating default databases..."
    create_database "auth"
    create_database "billing"
    create_database "tenant"
    create_database "communication"
    create_database "analytics"
fi

echo "✅ Multiple database creation completed!" 