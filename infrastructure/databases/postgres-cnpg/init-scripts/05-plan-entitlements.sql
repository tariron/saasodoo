-- Plan entitlements table with versioning
-- This table stores resource allocations (CPU, memory, storage) for each billing plan
-- Multiple rows per plan_name enable versioning via effective_date

CREATE TABLE IF NOT EXISTS plan_entitlements (
    id SERIAL PRIMARY KEY,
    plan_name VARCHAR(100) NOT NULL,
    effective_date TIMESTAMP NOT NULL,
    cpu_limit DECIMAL(4,2) NOT NULL,
    memory_limit VARCHAR(10) NOT NULL,
    storage_limit VARCHAR(10) NOT NULL,
    description TEXT,
    created_by VARCHAR(100) DEFAULT 'system',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(plan_name, effective_date)
);

-- Index for efficient lookups of current/historical entitlements
CREATE INDEX IF NOT EXISTS idx_plan_entitlements_lookup ON plan_entitlements(plan_name, effective_date DESC);

-- Seed initial entitlements (effective from project start)
INSERT INTO plan_entitlements (plan_name, effective_date, cpu_limit, memory_limit, storage_limit, description) VALUES
('basic-monthly', '2024-01-01 00:00:00', 1.0, '2G', '10G', 'Basic tier - Small workloads'),
('basic-immediate', '2024-01-01 00:00:00', 1.0, '2G', '10G', 'Basic tier - Immediate billing'),
('basic-test-trial', '2024-01-01 00:00:00', 1.0, '2G', '10G', 'Basic tier - Testing'),
('standard-monthly', '2024-01-01 00:00:00', 2.0, '4G', '20G', 'Standard tier - Medium workloads'),
('premium-monthly', '2024-01-01 00:00:00', 4.0, '8G', '50G', 'Premium tier - Large workloads')
ON CONFLICT (plan_name, effective_date) DO NOTHING;

-- Grant permissions to billing service
GRANT SELECT ON plan_entitlements TO billing_service;
GRANT INSERT, UPDATE ON plan_entitlements TO billing_service;
GRANT USAGE, SELECT ON SEQUENCE plan_entitlements_id_seq TO billing_service;
