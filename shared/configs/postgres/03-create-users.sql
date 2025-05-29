-- PostgreSQL Users and Permissions Setup
-- Create service-specific users for Odoo SaaS Kit

-- Create read-only user for monitoring and analytics
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user WITH LOGIN PASSWORD 'readonly123';
    END IF;
END
$$;

-- Create backup user for database maintenance
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'backup_user') THEN
        CREATE ROLE backup_user WITH LOGIN PASSWORD 'backup123' REPLICATION;
    END IF;
END
$$;

-- Create application-specific users
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'auth_service') THEN
        CREATE ROLE auth_service WITH LOGIN PASSWORD 'auth_service123';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'billing_service') THEN
        CREATE ROLE billing_service WITH LOGIN PASSWORD 'billing_service123';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'tenant_service') THEN
        CREATE ROLE tenant_service WITH LOGIN PASSWORD 'tenant_service123';
    END IF;
END
$$;

-- Grant permissions to read-only user
GRANT CONNECT ON DATABASE saas_odoo TO readonly_user;
GRANT CONNECT ON DATABASE auth TO readonly_user;
GRANT CONNECT ON DATABASE billing TO readonly_user;
GRANT CONNECT ON DATABASE tenant TO readonly_user;
GRANT CONNECT ON DATABASE communication TO readonly_user;
GRANT CONNECT ON DATABASE analytics TO readonly_user;

-- Grant schema permissions (will be applied when schemas are created)
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Grant permissions to service users
GRANT ALL PRIVILEGES ON DATABASE auth TO auth_service;
GRANT ALL PRIVILEGES ON DATABASE billing TO billing_service;
GRANT ALL PRIVILEGES ON DATABASE tenant TO tenant_service;

-- Grant backup permissions
GRANT CONNECT ON DATABASE saas_odoo TO backup_user;
GRANT CONNECT ON DATABASE auth TO backup_user;
GRANT CONNECT ON DATABASE billing TO backup_user;
GRANT CONNECT ON DATABASE tenant TO backup_user;
GRANT CONNECT ON DATABASE communication TO backup_user;
GRANT CONNECT ON DATABASE analytics TO backup_user; 