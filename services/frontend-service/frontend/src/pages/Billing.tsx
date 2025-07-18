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
                      Invoices & Payments
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Payment Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {billingData.customer_instances.map((instance: any) => {
                    // Find linked subscription using multiple methods
                    const linkedSubscription = billingData.active_subscriptions.find(
                      (sub: any) => sub.instance_id === instance.id || sub.id === instance.subscription_id
                    );
                    
                    // Find all invoices for this instance using simplified logic
                    const instanceInvoices = billingData.recent_invoices
                      .filter((invoice: any) => {
                        // Try multiple linking methods
                        return invoice.instance_id === instance.id || 
                               invoice.subscription_id === instance.subscription_id ||
                               (linkedSubscription && invoice.subscription_id === linkedSubscription.id);
                      })
                      .sort((a: any, b: any) => new Date(b.invoice_date).getTime() - new Date(a.invoice_date).getTime());
                    
                    return (
                      <tr key={instance.id} className="hover:bg-gray-50">
                        {/* Instance Column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center mr-3">
                              <span className="text-primary-600 font-medium text-sm">
                                {instance.name[0].toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <div className="text-sm font-medium text-gray-900">{instance.name}</div>
                              <div className="text-sm text-gray-500">
                                {instance.status} • {instance.instance_type}
                              </div>
                            </div>
                          </div>
                        </td>
                        
                        {/* Subscription Column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          {linkedSubscription ? (
                            <div>
                              <div className="text-sm font-medium text-gray-900">
                                {linkedSubscription.plan_name}
                              </div>
                              <div className="text-sm text-gray-500">
                                {linkedSubscription.billing_period} • 
                                <span className={`ml-1 px-2 py-1 text-xs rounded-full ${
                                  instance.billing_status === 'paid' 
                                    ? 'text-green-600 bg-green-100' 
                                    : 'text-yellow-600 bg-yellow-100'
                                }`}>
                                  {instance.billing_status === 'paid' ? 'Paid' : 'Trial'}
                                </span>
                              </div>
                              {linkedSubscription.charged_through_date && (
                                <div className="text-xs text-gray-400">
                                  Next: {formatDate(linkedSubscription.charged_through_date)}
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">
                              No subscription
                              <div>
                                <a href="/billing/subscription" className="text-blue-600 hover:text-blue-800 text-xs">
                                  Add Plan →
                                </a>
                              </div>
                            </div>
                          )}
                        </td>
                        
                        {/* Invoices & Payments Column */}
                        <td className="px-6 py-4">
                          {instanceInvoices.length > 0 ? (
                            <div className="space-y-2">
                              {instanceInvoices.map((invoice: any) => (
                                <div key={invoice.id} className="flex items-center justify-between p-2 bg-gray-50 rounded-lg">
                                  <div className="flex-1">
                                    <div className="flex items-center space-x-2">
                                      <div className="text-sm font-medium text-gray-900">
                                        {formatCurrency(invoice.amount, invoice.currency)}
                                      </div>
                                      {invoice.amount === 0 && (
                                        <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full">
                                          Trial
                                        </span>
                                      )}
                                    </div>
                                    <div className="text-xs text-gray-500">
                                      {formatDate(invoice.invoice_date)} • #{invoice.invoice_number}
                                    </div>
                                    <div className="flex items-center space-x-2 mt-1">
                                      <span className={`text-xs px-2 py-1 rounded-full ${getInvoiceStatusColor(invoice.status)}`}>
                                        {invoice.status}
                                      </span>
                                      <span className={`text-xs px-2 py-1 rounded-full ${
                                        invoice.payment_status === 'paid' ? 'bg-green-100 text-green-800' :
                                        invoice.payment_status === 'unpaid' ? 'bg-orange-100 text-orange-800' :
                                        'bg-gray-100 text-gray-800'
                                      }`}>
                                        {invoice.payment_status === 'paid' ? 'Paid' :
                                         invoice.payment_status === 'unpaid' ? 'Unpaid' :
                                         'No Payment'}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">No invoices</div>
                          )}
                        </td>
                        
                        {/* Payment Status Column */}
                        <td className="px-6 py-4 whitespace-nowrap">
                          {instanceInvoices.length > 0 ? (
                            <div>
                              {(() => {
                                const paidInvoices = instanceInvoices.filter((inv: any) => inv.payment_status === 'paid');
                                const unpaidInvoices = instanceInvoices.filter((inv: any) => inv.payment_status === 'unpaid');
                                const totalPaid = paidInvoices.reduce((sum: number, inv: any) => sum + inv.amount, 0);
                                const totalUnpaid = unpaidInvoices.reduce((sum: number, inv: any) => sum + inv.amount, 0);
                                const totalBalance = instanceInvoices.reduce((sum: number, inv: any) => sum + inv.balance, 0);
                                
                                return (
                                  <div className="space-y-1">
                                    {paidInvoices.length > 0 && (
                                      <div className="text-xs text-green-600">
                                        {paidInvoices.length} paid • {formatCurrency(totalPaid)}
                                      </div>
                                    )}
                                    {unpaidInvoices.length > 0 && (
                                      <div className="text-xs text-orange-600">
                                        {unpaidInvoices.length} unpaid • {formatCurrency(totalUnpaid)}
                                      </div>
                                    )}
                                    {totalBalance > 0 && (
                                      <div className="text-xs text-gray-600">
                                        Balance: {formatCurrency(totalBalance)}
                                      </div>
                                    )}
                                    {instanceInvoices.length === 1 && instanceInvoices[0].amount === 0 && (
                                      <div className="text-xs text-yellow-600">
                                        Trial Period
                                      </div>
                                    )}
                                  </div>
                                );
                              })()}
                            </div>
                          ) : (
                            <div className="text-sm text-gray-500">No invoices</div>
                          )}
                        </td>
                        
                        {/* Actions Column */}
                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <div className="flex space-x-2">
                            {instance.external_url && (
                              <a
                                href={instance.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:text-blue-900 text-xs"
                              >
                                Open
                              </a>
                            )}
                            <a
                              href={`/instances/${instance.id}`}
                              className="text-blue-600 hover:text-blue-900 text-xs"
                            >
                              Manage
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