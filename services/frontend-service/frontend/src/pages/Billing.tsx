import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI, UserProfile } from '../utils/api';
import { BillingOverview, Subscription, Invoice } from '../types/billing';
import Navigation from '../components/Navigation';

const Billing: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
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
      setProfile(response.data);
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
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="flex items-center justify-center min-h-screen">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
            <strong className="font-bold">Error: </strong>
            <span>{error}</span>
          </div>
        </div>
      </>
    );
  }

  if (!billingData) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">No Billing Data</h2>
            <p className="text-gray-600">No billing information found for your account.</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
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

      {/* Unified Per-Instance Billing Table */}
      <div className="bg-white shadow rounded-lg mb-8">
        <div className="px-4 py-5 sm:p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-semibold text-gray-900">Instance Billing Overview</h2>
            <a
              href="/instances/create"
              className="text-blue-600 hover:text-blue-800 text-sm font-medium"
            >
              Create Instance →
            </a>
          </div>
          
          {billingData.customer_instances && billingData.customer_instances.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Instance
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Subscription
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {billingData.customer_instances.map((instance: any) => {
                    // Find linked subscription
                    const linkedSubscription = billingData.active_subscriptions.find(
                      (sub: any) => sub.instance_id === instance.id || sub.id === instance.subscription_id
                    );
                    
                    return (
                      <tr key={instance.id} className="hover:bg-gray-50">
                        {/* Instance Column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mr-4">
                              <span className="text-blue-600 font-bold text-lg">
                                {instance.name[0].toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <div className="text-sm font-bold text-gray-900">{instance.name}</div>
                              <div className="text-sm text-gray-500">{instance.description || 'No description'}</div>
                              <div className="flex items-center space-x-2 mt-1">
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                                  instance.status === 'running' ? 'text-green-700 bg-green-100' :
                                  instance.status === 'stopped' ? 'text-gray-700 bg-gray-100' :
                                  instance.status === 'paused' ? 'text-yellow-700 bg-yellow-100' :
                                  'text-blue-700 bg-blue-100'
                                }`}>
                                  {instance.status}
                                </span>
                                <span className="text-xs text-gray-500">•</span>
                                <span className="text-xs text-gray-500">{instance.instance_type}</span>
                              </div>
                            </div>
                          </div>
                        </td>
                        
                        {/* Subscription Column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          {linkedSubscription ? (
                            <div>
                              <div className="text-sm font-bold text-gray-900">
                                {linkedSubscription.plan_name}
                              </div>
                              <div className="text-sm text-gray-500">
                                {linkedSubscription.billing_period} billing
                              </div>
                              <div className="flex items-center space-x-2 mt-2">
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                                  instance.billing_status === 'paid' 
                                    ? 'text-green-700 bg-green-100' 
                                    : 'text-yellow-700 bg-yellow-100'
                                }`}>
                                  {instance.billing_status === 'paid' ? 'Paid' : 'Trial'}
                                </span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                                  linkedSubscription.is_scheduled_for_cancellation ? 'text-orange-700 bg-orange-100' :
                                  linkedSubscription.state === 'ACTIVE' ? 'text-blue-700 bg-blue-100' :
                                  'text-gray-700 bg-gray-100'
                                }`}>
                                  {linkedSubscription.is_scheduled_for_cancellation 
                                    ? `${linkedSubscription.state} (Scheduled for Cancellation)` 
                                    : linkedSubscription.state}
                                </span>
                              </div>
                              {linkedSubscription.charged_through_date && (
                                <div className="text-xs text-gray-600 mt-1">
                                  {linkedSubscription.is_scheduled_for_cancellation ? (
                                    <>
                                      <strong className="text-orange-600">Service ends:</strong> {formatDate(linkedSubscription.charged_through_date)}
                                      <div className="text-orange-600 font-medium mt-1">
                                        ⚠️ No future billing - Service will end
                                      </div>
                                    </>
                                  ) : (
                                    <>
                                      <strong>Next billing:</strong> {formatDate(linkedSubscription.charged_through_date)}
                                    </>
                                  )}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">
                              <div className="text-sm font-medium text-gray-700">No subscription</div>
                              <div className="mt-1">
                                <a href="/billing/subscription" className="text-blue-600 hover:text-blue-800 text-xs font-medium">
                                  Add Plan →
                                </a>
                              </div>
                            </div>
                          )}
                        </td>
                        
                        {/* Actions Column */}
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <div className="flex space-x-3 justify-end">
                            {instance.external_url && (
                              <a
                                href={instance.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-800 font-medium text-sm"
                              >
                                Open Instance
                              </a>
                            )}
                            <a
                              href={`/billing/instance/${instance.id}`}
                              className="bg-blue-600 text-white px-3 py-1 rounded-md hover:bg-blue-700 text-sm font-medium"
                            >
                              Manage Billing
                            </a>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="text-gray-400 text-6xl mb-4">🖥️</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No instances found</h3>
              <p className="text-gray-600 mb-6">Create your first Odoo instance to start billing</p>
              <a
                href="/instances/create"
                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700"
              >
                Create Instance
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Orphaned Subscriptions */}
      {billingData.active_subscriptions && billingData.active_subscriptions.some((sub: any) => !sub.instance_id) && (
        <div className="bg-white shadow rounded-lg mb-8">
          <div className="px-4 py-5 sm:p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Other Subscriptions</h2>
            <p className="text-sm text-gray-600 mb-4">
              Subscriptions not linked to specific instances
            </p>
            <div className="space-y-3">
              {billingData.active_subscriptions
                .filter((sub: any) => !sub.instance_id)
                .map((subscription: any) => (
                  <div key={subscription.id} className="border rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="font-medium text-gray-900">{subscription.plan_name}</h3>
                        <p className="text-sm text-gray-600">
                          {subscription.billing_period} • {subscription.state}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-gray-600">
                          Next: {subscription.charged_through_date ? formatDate(subscription.charged_through_date) : 'N/A'}
                        </p>
                        <a
                          href="/billing/subscription"
                          className="text-blue-600 hover:text-blue-800 text-xs"
                        >
                          Manage →
                        </a>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

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
      </>
    );
};

export default Billing;