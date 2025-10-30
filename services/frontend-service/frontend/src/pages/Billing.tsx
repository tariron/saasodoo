import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI, UserProfile } from '../utils/api';
import { BillingOverview, Subscription, Invoice, OutstandingInvoice } from '../types/billing';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';

const Billing: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [billingData, setBillingData] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);

  // Payment modal state
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

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

  const handlePayInvoice = (invoice: OutstandingInvoice) => {
    // Convert OutstandingInvoice to Invoice format for PaymentModal
    const fullInvoice: Invoice = {
      id: invoice.id,
      invoice_number: invoice.invoice_number,
      invoice_date: invoice.invoice_date,
      amount: invoice.amount,
      balance: invoice.balance,
      currency: invoice.currency,
      status: invoice.status as 'DRAFT' | 'COMMITTED' | 'PAID' | 'VOID' | 'WRITTEN_OFF',
      // Add missing required fields with default values
      account_id: '',
      target_date: invoice.invoice_date,
      credit_adj: 0,
      refund_adj: 0,
      created_at: invoice.invoice_date,
      updated_at: invoice.invoice_date,
    };
    setSelectedInvoice(fullInvoice);
    setShowPaymentModal(true);
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

      {/* Payment Required Section */}
      {(billingData.pending_subscriptions.length > 0 || billingData.outstanding_invoices.length > 0 || billingData.total_outstanding > 0) && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-6 mb-8">
          <div className="flex items-center mb-4">
            <div className="flex-shrink-0">
              <span className="text-2xl">💳</span>
            </div>
            <div className="ml-3">
              <h3 className="text-lg font-medium text-orange-800">
                Payment Required
              </h3>
              <p className="text-orange-700">
                You have pending subscriptions or outstanding invoices that require payment.
              </p>
            </div>
          </div>

          {/* Outstanding Balance Summary */}
          {billingData.total_outstanding > 0 && (
            <div className="bg-white rounded-md p-4 mb-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-gray-900">Total Outstanding Balance</div>
                  <div className="text-2xl font-bold text-red-600">
                    {formatCurrency(billingData.total_outstanding)}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Pending Subscriptions */}
          {billingData.pending_subscriptions.length > 0 && (
            <div className="mb-4">
              <h4 className="text-md font-medium text-orange-800 mb-2">
                Pending Subscriptions ({billingData.pending_subscriptions.length})
              </h4>
              <div className="bg-white rounded-md overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Plan
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Instance
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Created
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Action
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {billingData.pending_subscriptions.map((subscription) => (
                      <tr key={subscription.id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 text-sm">
                          <div className="font-medium text-gray-900">{subscription.plan_name}</div>
                          <div className="text-gray-500">{subscription.billing_period} billing</div>
                        </td>
                        <td className="px-4 py-2 text-sm">
                          {subscription.instance_name ? (
                            <div>
                              <div className="font-medium text-gray-900">{subscription.instance_name}</div>
                              <div className="text-gray-500">Waiting for payment</div>
                            </div>
                          ) : (
                            <span className="text-gray-500">No instance linked</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-500">
                          {formatDate(subscription.created_at)}
                        </td>
                        <td className="px-4 py-2 text-sm text-orange-600">
                          Payment processing not yet implemented
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Outstanding Invoices */}
          {billingData.outstanding_invoices.length > 0 && (
            <div className="mb-4">
              <h4 className="text-md font-medium text-orange-800 mb-2">
                Outstanding Invoices ({billingData.outstanding_invoices.length})
              </h4>
              <div className="bg-white rounded-md overflow-hidden">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Invoice
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Date
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Amount
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Balance Due
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Action
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {billingData.outstanding_invoices.map((invoice) => (
                      <tr key={invoice.id} className="hover:bg-gray-50">
                        <td className="px-4 py-2 text-sm font-medium text-gray-900">
                          {invoice.invoice_number}
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-500">
                          {formatDate(invoice.invoice_date)}
                        </td>
                        <td className="px-4 py-2 text-sm text-gray-900">
                          {formatCurrency(invoice.amount)}
                        </td>
                        <td className="px-4 py-2 text-sm font-medium text-red-600">
                          {formatCurrency(invoice.balance)}
                        </td>
                        <td className="px-4 py-2 text-sm">
                          <button
                            onClick={() => handlePayInvoice(invoice)}
                            className="bg-blue-600 text-white px-3 py-1 rounded-md hover:bg-blue-700 text-xs font-medium"
                          >
                            Pay Now
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Provisioning Blocked Instances Alert */}
          {billingData.provisioning_blocked_instances.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <span className="text-red-500">⚠️</span>
                </div>
                <div className="ml-3">
                  <h4 className="text-sm font-medium text-red-800">
                    Instances Waiting for Payment
                  </h4>
                  <div className="text-sm text-red-700 mt-1">
                    {billingData.provisioning_blocked_instances.length} instance(s) created but not provisioned due to pending payment:
                    <ul className="list-disc list-inside mt-2">
                      {billingData.provisioning_blocked_instances.map((instance) => (
                        <li key={instance.instance_id}>
                          <strong>{instance.instance_name}</strong> ({instance.plan_name} plan) - created {formatDate(instance.created_at)}
                        </li>
                      ))}
                    </ul>
                    <div className="mt-2 font-medium">
                      Complete payment above to provision your instances.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Orphaned Subscriptions (Subscriptions without Instances) */}
      {(() => {
        // Find subscriptions that don't have linked instances
        const orphanedActiveSubscriptions = billingData.active_subscriptions.filter(
          (sub: any) => !sub.instance_id
        );
        const orphanedPendingSubscriptions = billingData.pending_subscriptions.filter(
          (sub: any) => !sub.instance_id
        );
        const allOrphanedSubscriptions = [...orphanedActiveSubscriptions, ...orphanedPendingSubscriptions];

        if (allOrphanedSubscriptions.length === 0) return null;

        return (
          <div className="bg-orange-50 border border-orange-300 rounded-lg p-6 mb-8">
            <div className="flex items-center mb-4">
              <div className="flex-shrink-0">
                <span className="text-3xl">⚠️</span>
              </div>
              <div className="ml-3">
                <h3 className="text-lg font-medium text-orange-900">
                  Subscriptions Without Instances
                </h3>
                <p className="text-orange-800">
                  {allOrphanedSubscriptions.length} subscription(s) exist but instance was never created or creation failed.
                </p>
              </div>
            </div>

            <div className="bg-white rounded-lg overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Subscription ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Plan
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Created
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {allOrphanedSubscriptions.map((subscription: any) => (
                    <tr key={subscription.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-mono text-gray-900">
                          {subscription.id.substring(0, 8)}...
                        </div>
                        <div className="text-xs text-gray-500">
                          Full ID: {subscription.id}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-bold text-gray-900">
                          {subscription.plan_name}
                        </div>
                        <div className="text-sm text-gray-500">
                          {subscription.billing_period} billing
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-3 py-1 text-xs font-medium rounded-full ${
                          subscription.state === 'ACTIVE' ? 'text-blue-700 bg-blue-100' :
                          subscription.state === 'COMMITTED' ? 'text-yellow-700 bg-yellow-100' :
                          'text-gray-700 bg-gray-100'
                        }`}>
                          {subscription.state}
                        </span>
                        <div className="text-xs text-red-600 mt-2 font-medium">
                          ❌ No Instance Created
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDate(subscription.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm">
                        <div className="flex flex-col space-y-2">
                          <a
                            href={`/instances/create?subscription_id=${subscription.id}`}
                            className="text-blue-600 hover:text-blue-800 font-medium"
                          >
                            Create Instance →
                          </a>
                          <button
                            onClick={() => alert('Contact support with subscription ID: ' + subscription.id)}
                            className="text-gray-600 hover:text-gray-800 text-xs"
                          >
                            Contact Support
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4 p-4 bg-orange-100 rounded-lg">
              <p className="text-sm text-orange-900">
                <strong>Why did this happen?</strong> Instance creation may have failed due to invalid configuration,
                reserved names, or system errors. You can retry creating an instance or contact support for assistance.
              </p>
            </div>
          </div>
        );
      })()}

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
                                    : instance.billing_status === 'payment_required'
                                    ? 'text-red-700 bg-red-100'
                                    : 'text-yellow-700 bg-yellow-100'
                                }`}>
                                  {instance.billing_status === 'paid' ? 'Paid' : 
                                   instance.billing_status === 'payment_required' ? 'Payment Required' : 'Trial'}
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

      {/* Payment Modal */}
      {showPaymentModal && selectedInvoice && profile && (
        <PaymentModal
          invoice={selectedInvoice}
          customerEmail={profile.email}
          onClose={() => {
            setShowPaymentModal(false);
            setSelectedInvoice(null);
          }}
          onSuccess={() => {
            window.location.href = '/instances';
          }}
        />
      )}
      </div>
      </>
    );
};

export default Billing;