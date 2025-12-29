
-- Create instances table (moved from tenant-service to instance-service)
CREATE TABLE IF NOT EXISTS instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id UUID NOT NULL, -- Reference to customer (no foreign key across databases)
    subscription_id UUID, -- Link to billing subscription
    name VARCHAR(100) NOT NULL,
    description TEXT,
    odoo_version VARCHAR(10) DEFAULT '17.0',
    instance_type VARCHAR(20) DEFAULT 'development',
    status VARCHAR(20) DEFAULT 'creating',
    
    -- Billing and provisioning status
    billing_status VARCHAR(30) DEFAULT 'pending_payment', -- pending_payment, trial, paid, suspended, payment_required
    provisioning_status VARCHAR(30) DEFAULT 'pending', -- pending, provisioning, completed, failed
    
    -- Resource allocation
    cpu_limit DECIMAL(3,1) DEFAULT 1.0,
    memory_limit VARCHAR(10) DEFAULT '1G',
    storage_limit VARCHAR(10) DEFAULT '10G',
    
    -- Odoo configuration
    admin_email VARCHAR(255) NOT NULL,
    admin_password VARCHAR(255), -- Auto-generated password (not stored, sent via email)
    database_name VARCHAR(50) NOT NULL,
    subdomain VARCHAR(50), -- Custom subdomain or defaults to database_name
    demo_data BOOLEAN DEFAULT false,
    
    -- Service information (Docker Swarm)
    service_id VARCHAR(255),
    service_name VARCHAR(255),
    
    -- Network information
    internal_port INTEGER DEFAULT 8069,
    external_port INTEGER,
    internal_url VARCHAR(255),
    external_url VARCHAR(255),
    
    -- Database information
    db_host VARCHAR(255),
    db_port INTEGER DEFAULT 5432,
    db_name VARCHAR(255), -- Actual database name allocated by database-service
    db_user VARCHAR(255),
    db_type VARCHAR(20) DEFAULT 'shared' CHECK (db_type IN ('shared', 'dedicated')),

    -- Addons and modules (stored as JSON arrays)
    custom_addons JSONB DEFAULT '[]',
    disabled_modules JSONB DEFAULT '[]',
    environment_vars JSONB DEFAULT '{}',
    
    -- Status information
    last_health_check TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for instance database
CREATE INDEX IF NOT EXISTS idx_instances_customer_id ON instances(customer_id);
CREATE INDEX IF NOT EXISTS idx_instances_subscription_id ON instances(subscription_id);
CREATE INDEX IF NOT EXISTS idx_instances_status ON instances(status);
CREATE INDEX IF NOT EXISTS idx_instances_billing_status ON instances(billing_status);
CREATE INDEX IF NOT EXISTS idx_instances_provisioning_status ON instances(provisioning_status);
CREATE INDEX IF NOT EXISTS idx_instances_name ON instances(name);
CREATE INDEX IF NOT EXISTS idx_instances_created_at ON instances(created_at);
CREATE INDEX IF NOT EXISTS idx_instances_database_name ON instances(database_name);
CREATE INDEX IF NOT EXISTS idx_instances_service_id ON instances(service_id);

-- Initialize communication database schema
