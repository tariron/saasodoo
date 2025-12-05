-- Add db_type column to plan_entitlements table
-- This enables database-driven allocation (shared vs dedicated) based on plan
-- Stage 4: Instance-Service Integration with Database-Service

-- Connect to billing database
\c billing;

-- Add db_type column with constraint
ALTER TABLE plan_entitlements
ADD COLUMN db_type VARCHAR(20) NOT NULL DEFAULT 'shared'
CHECK (db_type IN ('shared', 'dedicated'));

-- Create index for faster queries on db_type
CREATE INDEX idx_plan_entitlements_db_type ON plan_entitlements(db_type);

-- Update existing plans with db_type values
-- Basic and standard plans use shared databases (cost-effective)
UPDATE plan_entitlements
SET db_type = 'shared'
WHERE plan_name IN ('basic-monthly', 'basic-immediate', 'basic-test-trial', 'standard-monthly');

-- Premium plans get dedicated databases (performance and isolation)
UPDATE plan_entitlements
SET db_type = 'dedicated'
WHERE plan_name IN ('premium-monthly');

-- Verify changes
SELECT plan_name, db_type, cpu_limit, memory_limit, storage_limit, effective_date
FROM plan_entitlements
ORDER BY plan_name, effective_date DESC;

-- Grant permissions (billing_service already has SELECT, INSERT, UPDATE)
-- No additional grants needed
