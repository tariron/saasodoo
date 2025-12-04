-- Dynamic Database Allocation Schema Migration
-- Creates db_servers table and extends instances table for dynamic database allocation
-- Author: System
-- Date: 2025
-- Version: 1.0

-- Connect to instance database
\c instance;

-- ============================================================================
-- FORWARD MIGRATION
-- ============================================================================

-- Create db_servers table for managing PostgreSQL database pools
CREATE TABLE IF NOT EXISTS db_servers (
    -- Identity
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INTEGER DEFAULT 5432,

    -- Type & Capacity
    server_type VARCHAR(20) NOT NULL CHECK (server_type IN ('platform', 'shared', 'dedicated')),
    max_instances INTEGER NOT NULL DEFAULT 50,
    current_instances INTEGER NOT NULL DEFAULT 0 CHECK (current_instances >= 0),

    -- Docker Swarm Metadata
    swarm_service_id VARCHAR(255),
    swarm_service_name VARCHAR(255),
    node_placement VARCHAR(255) DEFAULT 'node.labels.role==database',

    -- Status
    status VARCHAR(30) NOT NULL DEFAULT 'provisioning'
        CHECK (status IN ('provisioning', 'initializing', 'active', 'full', 'maintenance', 'error', 'deprovisioning')),
    health_status VARCHAR(20) DEFAULT 'unknown'
        CHECK (health_status IN ('healthy', 'degraded', 'unhealthy', 'unknown')),
    last_health_check TIMESTAMP WITH TIME ZONE,
    health_check_failures INTEGER DEFAULT 0 CHECK (health_check_failures >= 0),

    -- Resources
    cpu_limit VARCHAR(10) DEFAULT '2',
    memory_limit VARCHAR(10) DEFAULT '4G',
    storage_path VARCHAR(500),
    allocated_storage_gb INTEGER DEFAULT 0 CHECK (allocated_storage_gb >= 0),

    -- PostgreSQL Configuration
    postgres_version VARCHAR(10) DEFAULT '18',
    postgres_image VARCHAR(100) DEFAULT 'postgres:18-alpine',
    admin_user VARCHAR(50) DEFAULT 'postgres',
    admin_password VARCHAR(255),

    -- Allocation Strategy
    allocation_strategy VARCHAR(20) DEFAULT 'auto' CHECK (allocation_strategy IN ('auto', 'manual')),
    priority INTEGER DEFAULT 100 CHECK (priority >= 0),

    -- Dedicated Server Tracking (nullable - only for dedicated servers)
    dedicated_to_customer_id UUID,
    dedicated_to_instance_id UUID,

    -- Audit Fields
    provisioned_by VARCHAR(100),
    provisioned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_allocated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT check_capacity CHECK (current_instances <= max_instances),
    CONSTRAINT check_dedicated_fields CHECK (
        (server_type = 'dedicated' AND dedicated_to_customer_id IS NOT NULL)
        OR (server_type != 'dedicated' AND dedicated_to_customer_id IS NULL AND dedicated_to_instance_id IS NULL)
    )
);

-- Create indexes for fast allocation queries
-- This composite index optimizes the pool selection query
CREATE INDEX IF NOT EXISTS idx_db_servers_allocation
    ON db_servers(server_type, status, current_instances, priority)
    WHERE allocation_strategy = 'auto';

-- Index for Docker Swarm operations
CREATE INDEX IF NOT EXISTS idx_db_servers_swarm
    ON db_servers(swarm_service_id)
    WHERE swarm_service_id IS NOT NULL;

-- Index for health monitoring queries
CREATE INDEX IF NOT EXISTS idx_db_servers_health
    ON db_servers(health_status, last_health_check);

-- Index for dedicated server lookups
CREATE INDEX IF NOT EXISTS idx_db_servers_dedicated_customer
    ON db_servers(dedicated_to_customer_id)
    WHERE dedicated_to_customer_id IS NOT NULL;

-- Create trigger function for auto-updating updated_at timestamp
CREATE OR REPLACE FUNCTION update_db_servers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at on row modifications
CREATE TRIGGER db_servers_updated_at
    BEFORE UPDATE ON db_servers
    FOR EACH ROW
    EXECUTE FUNCTION update_db_servers_updated_at();

-- Extend instances table with database allocation fields
ALTER TABLE instances
    ADD COLUMN IF NOT EXISTS db_server_id UUID REFERENCES db_servers(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS plan_tier VARCHAR(30),
    ADD COLUMN IF NOT EXISTS requires_dedicated_db BOOLEAN DEFAULT false;

-- Add index for joining instances with db_servers
CREATE INDEX IF NOT EXISTS idx_instances_db_server
    ON instances(db_server_id)
    WHERE db_server_id IS NOT NULL;

-- Add index for plan tier queries
CREATE INDEX IF NOT EXISTS idx_instances_plan_tier
    ON instances(plan_tier)
    WHERE plan_tier IS NOT NULL;

-- Add comment documentation for the tables
COMMENT ON TABLE db_servers IS 'Manages PostgreSQL database server pools for dynamic allocation';
COMMENT ON COLUMN db_servers.server_type IS 'Type of server: platform (internal), shared (multi-tenant), or dedicated (single customer)';
COMMENT ON COLUMN db_servers.allocation_strategy IS 'auto: available for automatic allocation, manual: admin-controlled only';
COMMENT ON COLUMN db_servers.priority IS 'Lower number = higher priority for allocation (used when multiple pools available)';
COMMENT ON COLUMN db_servers.status IS 'Current lifecycle state of the database server';
COMMENT ON COLUMN db_servers.health_status IS 'Health check result from monitoring tasks';
COMMENT ON COLUMN instances.db_server_id IS 'Foreign key to db_servers - which PostgreSQL server hosts this instance database';
COMMENT ON COLUMN instances.plan_tier IS 'Subscription plan tier (free, starter, standard, professional, premium, enterprise)';
COMMENT ON COLUMN instances.requires_dedicated_db IS 'Whether this instance requires a dedicated database server';

-- Grant permissions to database_service user (must be created separately in 03-create-users.sql.template)
-- This is here for reference - actual user creation happens in 03-create-users.sql.template
-- GRANT ALL PRIVILEGES ON TABLE db_servers TO database_service;
-- GRANT ALL PRIVILEGES ON TABLE instances TO database_service;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO database_service;

\echo 'Database allocation schema migration completed successfully'
\echo 'Created db_servers table with indexes and triggers'
\echo 'Extended instances table with allocation fields'


-- ============================================================================
-- ROLLBACK MIGRATION (commented out - use separate rollback script if needed)
-- ============================================================================

/*
-- Rollback script (run this to undo the migration)

-- Drop triggers
DROP TRIGGER IF EXISTS db_servers_updated_at ON db_servers;

-- Drop trigger functions
DROP FUNCTION IF EXISTS update_db_servers_updated_at();

-- Drop indexes on instances table
DROP INDEX IF EXISTS idx_instances_plan_tier;
DROP INDEX IF EXISTS idx_instances_db_server;

-- Remove columns from instances table
ALTER TABLE instances DROP COLUMN IF EXISTS requires_dedicated_db;
ALTER TABLE instances DROP COLUMN IF EXISTS plan_tier;
ALTER TABLE instances DROP COLUMN IF EXISTS db_server_id;

-- Drop indexes on db_servers table
DROP INDEX IF EXISTS idx_db_servers_dedicated_customer;
DROP INDEX IF EXISTS idx_db_servers_health;
DROP INDEX IF EXISTS idx_db_servers_swarm;
DROP INDEX IF EXISTS idx_db_servers_allocation;

-- Drop db_servers table
DROP TABLE IF EXISTS db_servers;

\echo 'Rollback completed - dynamic database allocation schema removed'
*/
