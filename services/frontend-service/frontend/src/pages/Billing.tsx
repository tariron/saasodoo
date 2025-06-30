import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI } from '../utils/api';
import { BillingOverview, Subscription, Invoice } from '../types/billing';

const Billing: React.FC = () => {
  const [billingData, setBillingData] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);

  useEffect(() => {
    fetchUserProfile();
  }, []);

  useEffect(() => {
    if (customerId) {
      fetchBillingData();
    }
  }, [customerId]);

  const fetchUserProfile = async () => {
    try {
      const response = await authAPI.getProfile();
      setCustomerId(response.data.id);
    } catch (err) {
      setError('Failed to load user profile');
      setLoading(false);
    }
  };

  const fetchBillingData = async () => {
    if (!customerId) return;
    
    try {
      setLoading(true);
      const response = await billingAPI.getBillingOverview(customerId);
      setBillingData(response.data.data);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to load billing information');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const getSubscriptionStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'active':
        return 'text-green-600 bg-green-100';
      case 'cancelled':
        return 'text-red-600 bg-red-100';
      case 'pending':
        return 'text-yellow-600 bg-yellow-100';
      case 'paused':
        return 'text-gray-600 bg-gray-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const getInvoiceStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'paid':
        return 'text-green-600 bg-green-100';
      case 'committed':
        return 'text-blue-600 bg-blue-100';
      case 'draft':
        return 'text-gray-600 bg-gray-100';
      case 'void':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          <strong className="font-bold">Error: </strong>
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!billingData) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">No Billing Data</h2>
          <p className="text-gray-600">No billing information found for your account.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Billing & Subscriptions</h1>
        <p className="mt-2 text-gray-600">Manage your billing information and subscriptions</p>
      </div>

      {/* Account Overview */}
      <div className="bg-white shadow rounded-lg p-6 mb-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Account Overview</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="text-center p-4 bg-blue-50 rounded-lg">
            <div className="text-2xl font-bold text-blue-600">
              {formatCurrency(billingData.account_balance)}
            </div>
            <div className="text-sm text-gray-600">Account Balance</div>
          </div>
          <div className="text-center p-4 bg-green-50 rounded-lg">
            <div className="text-2xl font-bold text-green-600">
              {billingData.active_subscriptions.length}
            </div>
            <div className="text-sm text-gray-600">Active Subscriptions</div>
          </div>
          <div className="text-center p-4 bg-purple-50 rounded-lg">
            <div className="text-2xl font-bold text-purple-600">
              {billingData.next_billing_amount ? formatCurrency(billingData.next_billing_amount) : 'N/A'}
            </div>
            <div className="text-sm text-gray-600">Next Billing Amount</div>
          </div>
        </div>
      </div>

      {/* Trial Information */}
      {billingData.trial_info?.is_trial && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6 mb-8">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <span className="text-2xl">⏰</span>
            </div>
            <div className="ml-3">
              <h3 className="text-lg font-medium text-yellow-800">
                Trial Period Active
              </h3>
              <p className="text-yellow-700">
                Your trial period ends on {formatDate(billingData.trial_info.trial_end_date!)} 
                ({billingData.trial_info.days_remaining} days remaining)
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Active Subscriptions */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">Active Subscriptions</h2>
            <a
              href="/billing/subscription"
              className="text-blue-600 hover:text-blue-800 text-sm font-medium"
            >
              Manage Plans →
            </a>
          </div>
          
          {billingData.active_subscriptions.length > 0 ? (
            <div className="space-y-4">
              {billingData.active_subscriptions.map((subscription: Subscription) => (
                <div key={subscription.id} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-gray-900">{subscription.plan_name}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getSubscriptionStatusColor(subscription.state)}`}>
                      {subscription.state}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">
                    Billing Period: {subscription.billing_period}
                  </p>
                  <p className="text-sm text-gray-600">
                    Next Billing: {subscription.charged_through_date ? formatDate(subscription.charged_through_date) : 'N/A'}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>No active subscriptions</p>
              <a
                href="/billing/subscription"
                className="mt-2 inline-block text-blue-600 hover:text-blue-800"
              >
                Browse Available Plans
              </a>
            </div>
          )}
        </div>

        {/* Recent Invoices */}
        <div className="bg-white shadow rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">Recent Invoices</h2>
            <a
              href="/billing/invoices"
              className="text-blue-600 hover:text-blue-800 text-sm font-medium"
            >
              View All →
            </a>
          </div>
          
          {billingData.recent_invoices.length > 0 ? (
            <div className="space-y-4">
              {billingData.recent_invoices.slice(0, 5).map((invoice: Invoice) => (
                <div key={invoice.id} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-gray-900">#{invoice.invoice_number}</h3>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${getInvoiceStatusColor(invoice.status)}`}>
                      {invoice.status}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600">
                    Amount: {formatCurrency(invoice.amount, invoice.currency)}
                  </p>
                  <p className="text-sm text-gray-600">
                    Date: {formatDate(invoice.invoice_date)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <p>No invoices yet</p>
            </div>
          )}
        </div>
      </div>

      {/* Payment Methods */}
      <div className="bg-white shadow rounded-lg p-6 mt-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Payment Methods</h2>
          <a
            href="/billing/payment"
            className="text-blue-600 hover:text-blue-800 text-sm font-medium"
          >
            Manage Payment Methods →
          </a>
        </div>
        
        {billingData.payment_methods.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {billingData.payment_methods.map((method) => (
              <div key={method.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium">
                    {method.plugin_info.type === 'CREDIT_CARD' ? '💳' : 
                     method.plugin_info.type === 'PAYPAL' ? '🅿️' : '🏦'} 
                    {method.plugin_info.type.replace('_', ' ')}
                  </span>
                  {method.is_default && (
                    <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
                      Default
                    </span>
                  )}
                </div>
                {method.plugin_info.last_4 && (
                  <p className="text-sm text-gray-600">•••• {method.plugin_info.last_4}</p>
                )}
                {method.plugin_info.exp_month && method.plugin_info.exp_year && (
                  <p className="text-sm text-gray-600">
                    Expires {method.plugin_info.exp_month}/{method.plugin_info.exp_year}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p>No payment methods on file</p>
            <a
              href="/billing/payment"
              className="mt-2 inline-block text-blue-600 hover:text-blue-800"
            >
              Add Payment Method
            </a>
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="bg-white shadow rounded-lg p-6 mt-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <a
            href="/billing/subscription"
            className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="text-2xl mb-2">📊</div>
            <div className="font-medium">Upgrade Plan</div>
          </a>
          <a
            href="/billing/invoices"
            className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="text-2xl mb-2">📄</div>
            <div className="font-medium">View Invoices</div>
          </a>
          <a
            href="/billing/payment"
            className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div className="text-2xl mb-2">💳</div>
            <div className="font-medium">Payment Methods</div>
          </a>
          <div className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer">
            <div className="text-2xl mb-2">📞</div>
            <div className="font-medium">Contact Support</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Billing;