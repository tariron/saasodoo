
CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL,
    instance_id UUID, -- Link to specific instance
    killbill_subscription_id VARCHAR(255), -- KillBill subscription ID
    plan_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    subscription_status VARCHAR(50) DEFAULT 'pending', -- pending, trial_active, active, payment_required, cancelled
    current_period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    trial_eligible BOOLEAN DEFAULT TRUE, -- Track if customer can use trial
    trial_used BOOLEAN DEFAULT FALSE, -- Track if customer has used trial
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id UUID REFERENCES subscriptions(id),
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    payment_status VARCHAR(50) DEFAULT 'pending',
    gateway_transaction_id VARCHAR(255),
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Paynow-specific fields
    paynow_reference VARCHAR(255),
    paynow_poll_url TEXT,
    paynow_browser_url TEXT,
    return_url TEXT,
    phone VARCHAR(20),
    paynow_status VARCHAR(50),
    webhook_received_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for billing database
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_instance_id ON subscriptions(instance_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_killbill_id ON subscriptions(killbill_subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_subscription_status ON subscriptions(subscription_status);
CREATE INDEX IF NOT EXISTS idx_payments_subscription_id ON payments(subscription_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_payments_paynow_ref ON payments(paynow_reference);
CREATE INDEX IF NOT EXISTS idx_payments_gateway_tx_id ON payments(gateway_transaction_id);
CREATE INDEX IF NOT EXISTS idx_payments_phone ON payments(phone);


-- Initialize instance database schema
