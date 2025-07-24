import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI } from '../utils/api';
import { Plan, Subscription, CreateSubscriptionRequest } from '../types/billing';
import Navigation from '../components/Navigation';

const BillingSubscription: React.FC = () => {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [currentSubscriptions, setCurrentSubscriptions] = useState<Subscription[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [billingAccountId, setBillingAccountId] = useState<string | null>(null);
  const [processingPlan, setProcessingPlan] = useState<string | null>(null);

  useEffect(() => {
    fetchUserProfile();
  }, []);

  useEffect(() => {
    if (customerId) {
      Promise.all([
        fetchPlans(),
        fetchCurrentSubscriptions(),
        fetchBillingAccount()
      ]);
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

  const fetchBillingAccount = async () => {
    if (!customerId) return;
    
    try {
      const response = await billingAPI.getAccount(customerId);
      setBillingAccountId(response.data.account.id);
    } catch (err: any) {
      setError('Failed to load billing account');
    }
  };

  const fetchPlans = async () => {
    try {
      const response = await billingAPI.getPlans();
      setPlans(response.data.plans);
    } catch (err: any) {
      setError('Failed to load plans');
    }
  };

  const fetchCurrentSubscriptions = async () => {
    if (!customerId) return;
    
    try {
      const response = await billingAPI.getSubscriptions(customerId);
      setCurrentSubscriptions(response.data.subscriptions);
    } catch (err: any) {
      console.error('Failed to load subscriptions:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectPlan = async (planName: string, billingPeriod: 'MONTHLY' | 'ANNUAL') => {
    if (!billingAccountId) {
      setError('Billing account not found');
      return;
    }

    setProcessingPlan(planName);
    
    try {
      const subscriptionData: CreateSubscriptionRequest = {
        account_id: billingAccountId,
        plan_name: planName,
        billing_period: billingPeriod
      };

      await billingAPI.createSubscription(subscriptionData);
      
      // Refresh subscriptions
      await fetchCurrentSubscriptions();
      
      // Show success message
      alert('Subscription created successfully!');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to create subscription');
    } finally {
      setProcessingPlan(null);
    }
  };

  const handleCancelSubscription = async (subscriptionId: string) => {
    if (!window.confirm('Are you sure you want to cancel this subscription?')) {
      return;
    }

    try {
      await billingAPI.cancelSubscription(subscriptionId, 'User requested cancellation');
      await fetchCurrentSubscriptions();
      alert('Subscription cancelled successfully');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to cancel subscription');
    }
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const getCurrentPlan = () => {
    const activeSubscription = currentSubscriptions.find(sub => sub.state === 'ACTIVE');
    return activeSubscription?.plan_name || null;
  };

  const isCurrentPlan = (planName: string) => {
    return getCurrentPlan() === planName;
  };

  if (loading) {
    return (
      <>
        <Navigation userProfile={undefined} />
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
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded max-w-md">
            <strong className="font-bold">Error: </strong>
            <span>{error}</span>
            <button 
              onClick={() => window.location.reload()} 
              className="ml-4 text-sm underline"
            >
              Retry
            </button>
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
        <h1 className="text-3xl font-bold text-gray-900">Subscription Plans</h1>
        <p className="mt-2 text-gray-600">Choose the perfect plan for your Odoo instances</p>
      </div>

      {/* Current Subscriptions */}
      {currentSubscriptions.length > 0 && (
        <div className="bg-white shadow rounded-lg p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">Current Subscriptions</h2>
          <div className="space-y-4">
            {currentSubscriptions.map((subscription) => (
              <div key={subscription.id} className="border rounded-lg p-4 flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-gray-900">{subscription.plan_name}</h3>
                  <p className="text-sm text-gray-600">
                    Status: <span className="capitalize">{subscription.state.toLowerCase()}</span>
                  </p>
                  <p className="text-sm text-gray-600">
                    Billing: {subscription.billing_period}
                  </p>
                </div>
                {subscription.state === 'ACTIVE' && (
                  <button
                    onClick={() => handleCancelSubscription(subscription.id)}
                    className="px-4 py-2 text-sm font-medium text-red-600 bg-red-100 rounded-md hover:bg-red-200"
                  >
                    Cancel
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Available Plans */}
      <div className="bg-white shadow rounded-lg p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Available Plans</h2>
        
        {plans.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {plans.map((plan) => (
              <div key={plan.name} className={`border rounded-lg p-6 ${isCurrentPlan(plan.name) ? 'border-blue-500 bg-blue-50' : 'border-gray-300'}`}>
                <div className="text-center mb-6">
                  <h3 className="text-xl font-bold text-gray-900 mb-2">{plan.product}</h3>
                  <div className="text-3xl font-bold text-blue-600 mb-1">
                    {plan.price ? formatCurrency(plan.price) : 'Free'}
                  </div>
                  <div className="text-sm text-gray-600">
                    per {plan.billing_period.toLowerCase()}
                  </div>
                  
                  {plan.trial_length > 0 && (
                    <div className="mt-2 text-sm text-green-600 font-medium">
                      {plan.trial_length} {plan.trial_time_unit.toLowerCase()} free trial
                    </div>
                  )}
                </div>

                {/* Description */}
                <div className="mb-6">
                  <p className="text-sm text-gray-600">{plan.description}</p>
                </div>

                {/* Action Buttons */}
                <div className="space-y-2">
                  {isCurrentPlan(plan.name) ? (
                    <div className="w-full py-2 text-center text-sm font-medium text-blue-600 bg-blue-100 rounded-md">
                      Current Plan
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => handleSelectPlan(plan.name, 'MONTHLY')}
                        disabled={processingPlan === plan.name}
                        className="w-full py-2 px-4 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {processingPlan === plan.name ? (
                          <span className="flex items-center justify-center">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                            Processing...
                          </span>
                        ) : (
                          'Select Monthly'
                        )}
                      </button>
                      
                      {plan.billing_period === 'MONTHLY' && (
                        <button
                          onClick={() => handleSelectPlan(plan.name, 'ANNUAL')}
                          disabled={processingPlan === plan.name}
                          className="w-full py-2 px-4 text-sm font-medium text-blue-600 bg-white border border-blue-600 rounded-md hover:bg-blue-50 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Select Annual (Save 20%)
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <p>No plans available at the moment.</p>
          </div>
        )}
      </div>

      {/* Plan Comparison */}
      <div className="bg-white shadow rounded-lg p-6 mt-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-6">Plan Comparison</h2>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Feature
                </th>
                {plans.map((plan) => (
                  <th key={plan.name} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {plan.product}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              <tr>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  Monthly Price
                </td>
                {plans.map((plan) => (
                  <td key={plan.name} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {plan.price ? formatCurrency(plan.price) : 'Free'}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  Free Trial
                </td>
                {plans.map((plan) => (
                  <td key={plan.name} className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    {plan.trial_length > 0 ? `${plan.trial_length} ${plan.trial_time_unit.toLowerCase()}` : 'No'}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Back to Billing */}
      <div className="mt-8 text-center">
        <a
          href="/billing"
          className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
        >
          ← Back to Billing Dashboard
        </a>
      </div>
      </div>
    </>
  );
};

export default BillingSubscription;