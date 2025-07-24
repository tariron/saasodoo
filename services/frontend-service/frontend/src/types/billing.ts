// Billing Types for Frontend

export interface BillingAccount {
  id: string;
  customer_id: string;
  external_key: string;
  name: string;
  email: string;
  currency: string;
  company?: string;
  created_at: string;
  updated_at: string;
}

export interface Subscription {
  id: string;
  account_id: string;
  plan_name: string;
  product_name: string;
  product_category: string;
  billing_period: 'MONTHLY' | 'ANNUAL';
  state: 'ACTIVE' | 'CANCELLED' | 'PENDING' | 'PAUSED' | 'COMMITTED';
  start_date: string;
  charged_through_date?: string;
  billing_start_date: string;
  billing_end_date?: string;
  trial_start_date?: string;
  trial_end_date?: string;
  metadata?: {
    instance_id?: string;
    [key: string]: any;
  };
  created_at: string;
  updated_at: string;
  // Cancellation information
  cancelled_date?: string;
  is_scheduled_for_cancellation?: boolean;
  cancellation_reason?: string;
  // Per-instance information
  instance_id?: string;
  instance_name?: string;
  instance_status?: string;
  instance_billing_status?: 'trial' | 'paid' | 'pending_payment';
  // Payment status
  awaiting_payment?: boolean;
}

export interface PendingSubscription {
  id: string;
  account_id: string;
  plan_name: string;
  product_name: string;
  billing_period: 'MONTHLY' | 'ANNUAL';
  state: 'COMMITTED' | 'PENDING';
  start_date: string;
  created_at: string;
  instance_id?: string;
  instance_name?: string;
  instance_status?: string;
  awaiting_payment: boolean;
}

export interface OutstandingInvoice {
  id: string;
  invoice_number: string;
  invoice_date: string;
  amount: number;
  balance: number;
  currency: string;
  status: string;
}

export interface ProvisioningBlockedInstance {
  instance_id: string;
  instance_name: string;
  subscription_id: string;
  plan_name: string;
  created_at: string;
}

export interface Invoice {
  id: string;
  account_id: string;
  invoice_number: string;
  invoice_date: string;
  target_date: string;
  amount: number;
  currency: string;
  status: 'DRAFT' | 'COMMITTED' | 'PAID' | 'VOID' | 'WRITTEN_OFF';
  balance: number;
  credit_adj: number;
  refund_adj: number;
  created_at: string;
  updated_at: string;
  subscription_id?: string; // For linking invoices to subscriptions
  payments?: Payment[]; // Payment data for this invoice
  payment_status?: 'paid' | 'unpaid' | 'no_payments'; // Payment status summary
}

export interface InvoiceItem {
  id: string;
  invoice_id: string;
  description: string;
  amount: number;
  currency: string;
  start_date: string;
  end_date: string;
  usage_name?: string;
  rate?: number;
  quantity?: number;
}

export interface Payment {
  id: string;
  account_id: string;
  invoice_id?: string;
  amount: number;
  currency: string;
  status: 'SUCCESS' | 'PENDING' | 'FAILED' | 'CANCELLED';
  gateway_error_code?: string;
  gateway_error_msg?: string;
  payment_method_id?: string;
  external_payment_id?: string;
  created_at: string;
  updated_at: string;
}

export interface PaymentMethod {
  id: string;
  account_id: string;
  plugin_name: string;
  is_default: boolean;
  plugin_info: {
    type: 'CREDIT_CARD' | 'PAYPAL' | 'BANK_TRANSFER';
    card_type?: string;
    exp_month?: number;
    exp_year?: number;
    last_4?: string;
    email?: string;
    account_name?: string;
  };
  created_at: string;
  updated_at: string;
}

export interface Plan {
  name: string;
  product: string;
  type: string;
  description: string;
  billing_period: string;
  trial_length: number;
  trial_time_unit: string;
  price: number | null;
  currency: string;
  available: boolean;
  fallback?: boolean;
}

export interface CreateSubscriptionRequest {
  account_id: string;
  plan_name: string;
  billing_period?: 'MONTHLY' | 'ANNUAL';
}

export interface CreatePaymentMethodRequest {
  account_id: string;
  plugin_name: string;
  plugin_info: {
    type: 'CREDIT_CARD' | 'PAYPAL' | 'BANK_TRANSFER';
    card_number?: string;
    exp_month?: number;
    exp_year?: number;
    cvv?: string;
    card_holder_name?: string;
    email?: string;
    account_name?: string;
    routing_number?: string;
    account_number?: string;
  };
  is_default?: boolean;
}

export interface CustomerInstance {
  id: string;
  name: string;
  status: string;
  instance_type: string;
  billing_status: 'trial' | 'paid';
  external_url?: string;
  created_at: string;
  [key: string]: any;
}

export interface BillingOverview {
  account: BillingAccount;
  active_subscriptions: Subscription[];
  pending_subscriptions: PendingSubscription[];
  outstanding_invoices: OutstandingInvoice[];
  total_outstanding: number;
  provisioning_blocked_instances: ProvisioningBlockedInstance[];
  recent_invoices?: Invoice[];
  next_billing_date?: string;
  next_billing_amount?: number;
  payment_methods: PaymentMethod[];
  account_balance: number;
  trial_info?: {
    is_trial: boolean;
    trial_end_date?: string;
    days_remaining?: number;
  };
  customer_instances?: CustomerInstance[];
}

// API Response types
export interface CreateSubscriptionResponse {
  success: boolean;
  subscription: Subscription;
  message: string;
}

export interface CreatePaymentMethodResponse {
  success: boolean;
  payment_method: PaymentMethod;
  message: string;
}

export interface BillingAccountResponse {
  success: boolean;
  account: BillingAccount;
  message: string;
}

export interface SubscriptionsResponse {
  success: boolean;
  subscriptions: Subscription[];
  total: number;
}

export interface InvoicesResponse {
  success: boolean;
  invoices: Invoice[];
  total: number;
}

export interface PaymentsResponse {
  success: boolean;
  payments: Payment[];
  total: number;
}

export interface PaymentMethodsResponse {
  success: boolean;
  payment_methods: PaymentMethod[];
  total: number;
}

export interface PlansResponse {
  success: boolean;
  plans: Plan[];
}