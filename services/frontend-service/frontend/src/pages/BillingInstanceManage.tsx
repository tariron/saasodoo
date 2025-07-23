import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { billingAPI, instanceAPI, authAPI, UserProfile, Instance } from '../utils/api';
import Navigation from '../components/Navigation';

interface SubscriptionData {
  subscription: any;
  metadata: any;
}

interface SubscriptionInvoices {
  invoices: any[];
  total: number;
}

const BillingInstanceManage: React.FC = () => {
  const { instanceId } = useParams<{ instanceId: string }>();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [instance, setInstance] = useState<Instance | null>(null);
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null);
  const [invoices, setInvoices] = useState<SubscriptionInvoices | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (instanceId) {
      fetchInstanceBillingData();
    }
  }, [instanceId]);

  const fetchUserProfile = async () => {
    try {
      const response = await authAPI.getProfile();
      setProfile(response.data);
      return response.data;
    } catch (err) {
      console.error('Failed to fetch user profile:', err);
      throw err;
    }
  };

  const fetchInstanceBillingData = async () => {
    if (!instanceId) return;
    
    try {
      setLoading(true);
      setError(null);

      // Get user profile
      const userProfile = await fetchUserProfile();

      // Get instance details
      console.log('Fetching instance:', instanceId);
      const instanceResponse = await instanceAPI.get(instanceId);
      const instanceData = instanceResponse.data;
      setInstance(instanceData);
      console.log('Instance data:', instanceData);

      // Check if instance has subscription_id
      if (!instanceData.subscription_id) {
        setError('No subscription found for this instance');
        return;
      }

      // Get subscription details
      console.log('Fetching subscription:', instanceData.subscription_id);
      const subscriptionResponse = await billingAPI.getSubscription(instanceData.subscription_id);
      setSubscriptionData(subscriptionResponse.data);
      console.log('Subscription data:', subscriptionResponse.data);

      // Get subscription invoices
      console.log('Fetching invoices for subscription:', instanceData.subscription_id);
      const invoicesResponse = await billingAPI.getSubscriptionInvoices(instanceData.subscription_id, 1, 20);
      setInvoices(invoicesResponse.data);
      console.log('Invoices data:', invoicesResponse.data);

    } catch (err: any) {
      console.error('Error fetching instance billing data:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to load billing information');
    } finally {
      setLoading(false);
    }
  };

  const handlePauseSubscription = async () => {
    if (!instance?.subscription_id) return;
    
    if (!window.confirm('Are you sure you want to pause this subscription? Your instance will be suspended and billing will stop.')) {
      return;
    }

    try {
      setActionLoading('pause');
      await billingAPI.pauseSubscription(instance.subscription_id);
      alert('Subscription paused successfully. Your instance has been suspended.');
      await fetchInstanceBillingData(); // Refresh data
    } catch (err: any) {
      alert(`Failed to pause subscription: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleResumeSubscription = async () => {
    if (!instance?.subscription_id) return;

    if (!window.confirm('Are you sure you want to resume this subscription? Billing will restart and your instance will be unsuspended.')) {
      return;
    }

    try {
      setActionLoading('resume');
      await billingAPI.resumeSubscription(instance.subscription_id);
      alert('Subscription resumed successfully. Your instance has been unsuspended.');
      await fetchInstanceBillingData(); // Refresh data
    } catch (err: any) {
      alert(`Failed to resume subscription: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelSubscription = async () => {
    if (!instance?.subscription_id) return;

    const reason = window.prompt('Please provide a reason for cancellation (optional):') || 'User requested cancellation';
    
    if (!window.confirm('Are you sure you want to cancel this subscription? This action cannot be undone and your instance will be suspended immediately.')) {
      return;
    }

    try {
      setActionLoading('cancel');
      await billingAPI.cancelSubscriptionById(instance.subscription_id, reason);
      alert('Subscription cancelled successfully. Your instance has been suspended.');
      await fetchInstanceBillingData(); // Refresh data
    } catch (err: any) {
      alert(`Failed to cancel subscription: ${err.response?.data?.detail || err.message}`);
    } finally {
      setActionLoading(null);
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
    switch (status?.toLowerCase()) {
      case 'active':
        return 'text-green-600 bg-green-100';
      case 'cancelled':
        return 'text-red-600 bg-red-100';
      case 'paused':
        return 'text-gray-600 bg-gray-100';
      default:
        return 'text-yellow-600 bg-yellow-100';
    }
  };

  const getInstanceStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'text-green-600 bg-green-100';
      case 'stopped':
        return 'text-gray-600 bg-gray-100';
      case 'paused':
        return 'text-yellow-600 bg-yellow-100';
      case 'error':
        return 'text-red-600 bg-red-100';
      default:
        return 'text-blue-600 bg-blue-100';
    }
  };

  if (loading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="flex flex-col items-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            <p className="mt-4 text-gray-600">Loading billing information...</p>
          </div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <div className="bg-red-100 border border-red-400 text-red-700 px-6 py-4 rounded-lg">
              <h2 className="text-xl font-bold mb-2">Error</h2>
              <p>{error}</p>
              <div className="mt-4 space-x-4">
                <button
                  onClick={() => fetchInstanceBillingData()}
                  className="btn-primary"
                >
                  Retry
                </button>
                <Link to="/billing" className="btn-secondary">
                  Back to Billing
                </Link>
              </div>
            </div>
          </div>
        </div>
      </>
    );
  }

  if (!instance) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="text-center">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Instance Not Found</h2>
            <Link to="/billing" className="btn-primary">
              Back to Billing
            </Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Breadcrumb */}
        <div className="mb-6">
          <nav className="flex" aria-label="Breadcrumb">
            <ol className="flex items-center space-x-4">
              <li>
                <Link to="/billing" className="text-gray-400 hover:text-gray-500">
                  Billing
                </Link>
              </li>
              <li>
                <span className="text-gray-400">/</span>
              </li>
              <li>
                <span className="text-gray-500 font-medium">Instance Billing Management</span>
              </li>
            </ol>
          </nav>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Instance Billing Management</h1>
          <p className="mt-2 text-gray-600">Manage subscription and billing for: {instance.name}</p>
        </div>

        {/* Instance Overview */}
        <div className="bg-white shadow rounded-lg p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Instance Overview</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <div className="text-sm text-gray-500">Instance Name</div>
              <div className="text-lg font-medium text-gray-900">{instance.name}</div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Status</div>
              <div>
                <span className={`px-2 py-1 text-sm font-medium rounded-full ${getInstanceStatusColor(instance.status)}`}>
                  {instance.status}
                </span>
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-500">Billing Status</div>
              <div>
                <span className={`px-2 py-1 text-sm font-medium rounded-full ${
                  instance.billing_status === 'paid' ? 'text-green-600 bg-green-100' : 
                  instance.billing_status === 'trial' ? 'text-yellow-600 bg-yellow-100' :
                  'text-red-600 bg-red-100'
                }`}>
                  {instance.billing_status || 'Unknown'}
                </span>
              </div>
            </div>
          </div>
          
          {instance.external_url && (
            <div className="mt-4">
              <a
                href={instance.external_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 hover:text-blue-800"
              >
                Open Instance →
              </a>
            </div>
          )}
        </div>

        {/* Subscription Billing Context */}
        {subscriptionData && (
          <div className="bg-white shadow rounded-lg p-6 mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-6">Subscription Billing Context</h2>
            
            {/* Cancellation Warning Banner */}
            {subscriptionData.subscription.cancelledDate && (
              <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 mb-6">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-orange-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-orange-800">
                      Subscription Scheduled for Cancellation
                    </h3>
                    <div className="mt-2 text-sm text-orange-700">
                      <p>
                        Your subscription is scheduled to end on{' '}
                        <span className="font-semibold">
                          {formatDate(subscriptionData.subscription.chargedThroughDate || subscriptionData.subscription.cancelledDate)}
                        </span>
                        . You will continue to have access to your service until that date. No future billing will occur.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Billing Overview Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-gray-600">Current Plan</div>
                <div className="text-lg font-bold text-blue-800">
                  {subscriptionData.subscription.planName || 'Unknown Plan'}
                </div>
                <div className="text-sm text-gray-600">
                  {subscriptionData.subscription.billingPeriod || 'MONTHLY'} billing
                </div>
              </div>
              
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-sm text-gray-600">Billing Status</div>
                <div>
                  <span className={`px-3 py-1 text-sm font-bold rounded-full ${
                    subscriptionData.subscription.cancelledDate ? 'bg-orange-100 text-orange-800' : 
                    getSubscriptionStatusColor(subscriptionData.subscription.state)
                  }`}>
                    {subscriptionData.subscription.cancelledDate 
                      ? `${subscriptionData.subscription.state} (Scheduled for Cancellation)`
                      : subscriptionData.subscription.state || 'Unknown'
                    }
                  </span>
                </div>
                <div className="text-sm text-gray-600 mt-1">
                  {instance?.billing_status === 'trial' ? 'Trial Period' : 'Paid Subscription'}
                </div>
              </div>

              <div className={`${subscriptionData.subscription.cancelledDate ? 'bg-orange-50' : 'bg-purple-50'} rounded-lg p-4`}>
                <div className="text-sm text-gray-600">
                  {subscriptionData.subscription.cancelledDate ? 'Service Ends' : 'Next Billing'}
                </div>
                <div className={`text-lg font-bold ${subscriptionData.subscription.cancelledDate ? 'text-orange-800' : 'text-purple-800'}`}>
                  {subscriptionData.subscription.chargedThroughDate 
                    ? formatDate(subscriptionData.subscription.chargedThroughDate)
                    : 'Not Available'
                  }
                </div>
                <div className="text-sm text-gray-600">
                  {subscriptionData.subscription.cancelledDate ? 'Final access date' : 'Auto-renewal date'}
                </div>
              </div>
            </div>

            {/* Billing Period & Details */}
            <div className="border-t border-gray-200 pt-6">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Billing Details</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <div className="text-sm text-gray-500">Subscription Started</div>
                  <div className="text-sm font-medium text-gray-900">
                    {subscriptionData.subscription.startDate 
                      ? formatDate(subscriptionData.subscription.startDate)
                      : 'Not Available'
                    }
                  </div>
                </div>
                
                {subscriptionData.subscription.trialEndDate && (
                  <div>
                    <div className="text-sm text-gray-500">Trial Period</div>
                    <div className="text-sm font-medium text-gray-900">
                      {subscriptionData.subscription.trialStartDate 
                        ? formatDate(subscriptionData.subscription.trialStartDate)
                        : 'Start'
                      } → {formatDate(subscriptionData.subscription.trialEndDate)}
                    </div>
                  </div>
                )}

                <div>
                  <div className="text-sm text-gray-500">Billing Start Date</div>
                  <div className="text-sm font-medium text-gray-900">
                    {subscriptionData.subscription.billingStartDate 
                      ? formatDate(subscriptionData.subscription.billingStartDate)
                      : 'Not Available'
                    }
                  </div>
                </div>

                <div>
                  <div className="text-sm text-gray-500">Current Period</div>
                  <div className="text-sm font-medium text-gray-900">
                    {subscriptionData.subscription.billingStartDate && subscriptionData.subscription.chargedThroughDate
                      ? `${formatDate(subscriptionData.subscription.billingStartDate)} → ${formatDate(subscriptionData.subscription.chargedThroughDate)}`
                      : 'Not Available'
                    }
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Subscription Management Actions */}
        {subscriptionData && (
          <div className="bg-white shadow rounded-lg p-6 mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Subscription Management</h2>
            
            <div className="flex flex-wrap gap-4">
              <button
                onClick={handlePauseSubscription}
                disabled={actionLoading === 'pause' || subscriptionData.subscription.state !== 'ACTIVE'}
                className="btn-secondary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'pause' ? 'Pausing...' : 'Pause Subscription'}
              </button>
              
              <button
                onClick={handleResumeSubscription}
                disabled={actionLoading === 'resume' || subscriptionData.subscription.state === 'ACTIVE'}
                className="btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'resume' ? 'Resuming...' : 'Resume Subscription'}
              </button>
              
              <button
                onClick={handleCancelSubscription}
                disabled={actionLoading === 'cancel' || subscriptionData.subscription.state === 'CANCELLED'}
                className="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'cancel' ? 'Cancelling...' : 'Cancel Subscription'}
              </button>
            </div>
          </div>
        )}

        {/* Invoice History */}
        {invoices && invoices.invoices.length > 0 && (
          <div className="bg-white shadow rounded-lg p-6 mb-8">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Invoice History</h2>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Invoice #
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Date
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Amount
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Balance Due
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {invoices.invoices.map((invoice: any) => (
                    <tr key={invoice.invoiceId} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div className="font-medium">{invoice.invoice_number || `#${invoice.invoiceId?.slice(-8)}`}</div>
                        <div className="text-xs text-gray-500">ID: {invoice.invoiceId?.slice(-12)}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div>{formatDate(invoice.invoiceDate)}</div>
                        {invoice.target_date && invoice.target_date !== invoice.invoiceDate && (
                          <div className="text-xs text-gray-500">Due: {formatDate(invoice.target_date)}</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        <div>{formatCurrency(invoice.amount, invoice.currency)}</div>
                        {invoice.amount === 0 && (
                          <span className="text-xs px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full">
                            Trial
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        <div className={`font-medium ${
                          invoice.balance > 0 ? 'text-red-600' : 'text-green-600'
                        }`}>
                          {formatCurrency(invoice.balance || 0, invoice.currency)}
                        </div>
                        {invoice.balance > 0 && (
                          <div className="text-xs text-red-500">Outstanding</div>
                        )}
                        {invoice.balance === 0 && invoice.amount > 0 && (
                          <div className="text-xs text-green-500">Fully Paid</div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex flex-col space-y-1">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            invoice.status === 'PAID' ? 'text-green-600 bg-green-100' :
                            invoice.status === 'UNPAID' ? 'text-red-600 bg-red-100' :
                            invoice.status === 'COMMITTED' ? 'text-blue-600 bg-blue-100' :
                            'text-gray-600 bg-gray-100'
                          }`}>
                            {invoice.status}
                          </span>
                          {(invoice.credit_adj > 0 || invoice.refund_adj > 0) && (
                            <div className="text-xs text-purple-600">
                              {invoice.credit_adj > 0 && `Credit: ${formatCurrency(invoice.credit_adj, invoice.currency)}`}
                              {invoice.refund_adj > 0 && `Refund: ${formatCurrency(invoice.refund_adj, invoice.currency)}`}
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <div className="flex flex-col space-y-1">
                          <button className="text-blue-600 hover:text-blue-800 text-xs">
                            Download PDF
                          </button>
                          {invoice.items && invoice.items.length > 0 && (
                            <button 
                              className="text-purple-600 hover:text-purple-800 text-xs"
                              onClick={() => {
                                const itemsWindow = window.open('', '_blank');
                                if (itemsWindow) {
                                  itemsWindow.document.write(`
                                    <html>
                                      <head><title>Invoice ${invoice.invoice_number} - Line Items</title></head>
                                      <body>
                                        <h2>Invoice ${invoice.invoice_number} - Line Items</h2>
                                        <table border="1" style="border-collapse: collapse; width: 100%;">
                                          <tr>
                                            <th>Description</th>
                                            <th>Amount</th>
                                            <th>Period</th>
                                          </tr>
                                          ${invoice.items.map((item: any) => `
                                            <tr>
                                              <td>${item.description || item.planName || 'Subscription'}</td>
                                              <td>${formatCurrency(item.amount || 0, invoice.currency)}</td>
                                              <td>${item.startDate || ''} - ${item.endDate || ''}</td>
                                            </tr>
                                          `).join('')}
                                        </table>
                                      </body>
                                    </html>
                                  `);
                                }
                              }}
                            >
                              View Details
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            
            {invoices.total > invoices.invoices.length && (
              <div className="mt-4 text-center">
                <button className="btn-secondary">
                  Load More Invoices
                </button>
              </div>
            )}
          </div>
        )}

        {/* Quick Links */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Link
              to="/billing"
              className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="text-2xl mb-2">📊</div>
              <div className="font-medium">Billing Dashboard</div>
            </Link>
            <Link
              to="/billing/payment"
              className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="text-2xl mb-2">💳</div>
              <div className="font-medium">Payment Methods</div>
            </Link>
            <Link
              to="/instances"
              className="text-center p-4 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <div className="text-2xl mb-2">🖥️</div>
              <div className="font-medium">Instance Management</div>
            </Link>
          </div>
        </div>
      </div>
    </>
  );
};

export default BillingInstanceManage;