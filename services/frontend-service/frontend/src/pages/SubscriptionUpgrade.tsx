import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';
import { billingAPI, instanceAPI, authAPI, UserProfile, Instance } from '../utils/api';
import { Plan, Invoice } from '../types/billing';

interface SubscriptionData {
  subscription: any;
  metadata: any;
  billing_period?: string;
  next_billing_date?: string;
}

const SubscriptionUpgrade: React.FC = () => {
  const { instanceId } = useParams<{ instanceId: string }>();
  const navigate = useNavigate();

  // State management
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [instance, setInstance] = useState<Instance | null>(null);
  const [subscriptionData, setSubscriptionData] = useState<SubscriptionData | null>(null);
  const [allPlans, setAllPlans] = useState<Plan[]>([]);
  const [upgradablePlans, setUpgradablePlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [upgrading, setUpgrading] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [confirmationChecked, setConfirmationChecked] = useState(false);
  const [paymentModalOpen, setPaymentModalOpen] = useState(false);
  const [pendingInvoice, setPendingInvoice] = useState<Invoice | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch user profile
  const fetchUserProfile = async () => {
    try {
      const response = await authAPI.getProfile();
      setProfile(response.data);
    } catch (err: any) {
      console.error('Failed to fetch user profile:', err);
      setError('Failed to load user profile');
    }
  };

  // Fetch instance data
  const fetchInstanceData = async () => {
    if (!instanceId) return;

    try {
      const response = await instanceAPI.get(instanceId);
      setInstance(response.data);

      if (response.data.subscription_id) {
        await fetchSubscriptionData(response.data.subscription_id);
      }
    } catch (err: any) {
      console.error('Failed to fetch instance:', err);
      setError('Failed to load instance data');
    }
  };

  // Fetch subscription data
  const fetchSubscriptionData = async (subscriptionId: string) => {
    try {
      const response = await billingAPI.getSubscription(subscriptionId);
      setSubscriptionData(response.data);
    } catch (err: any) {
      console.error('Failed to fetch subscription:', err);
      setError('Failed to load subscription data');
    }
  };

  // Fetch upgradable plans
  const fetchUpgradablePlans = async () => {
    if (!subscriptionData?.subscription) return;

    try {
      const plansResponse = await billingAPI.getPlans();
      const plans = plansResponse.data.plans;
      setAllPlans(plans);

      const currentPlan = subscriptionData.subscription.planName;
      const currentPlanInfo = plans.find((p: any) => p.name === currentPlan);

      if (!currentPlanInfo || currentPlanInfo.price == null) {
        setUpgradablePlans([]);
        return;
      }

      const currentPrice = currentPlanInfo.price;
      const upgrades = plans.filter((p: any) =>
        p.name !== currentPlan &&
        p.price != null &&
        p.price > currentPrice
      );

      setUpgradablePlans(upgrades);
    } catch (err: any) {
      console.error('Failed to fetch upgradable plans:', err);
      setError('Failed to load available plans');
    }
  };

  // Initial data fetch
  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      await Promise.all([
        fetchUserProfile(),
        fetchInstanceData()
      ]);
      setLoading(false);
    };

    fetchData();
  }, [instanceId]);

  // Fetch upgradable plans when subscription data is loaded
  useEffect(() => {
    if (subscriptionData) {
      fetchUpgradablePlans();
    }
  }, [subscriptionData]);

  // Handle upgrade confirmation
  const handleConfirmUpgrade = async () => {
    if (!instance?.subscription_id || !selectedPlan) return;

    try {
      setUpgrading(true);
      const response = await billingAPI.upgradeSubscription(
        instance.subscription_id,
        {
          target_plan_name: selectedPlan.name,
          reason: 'Customer requested upgrade'
        }
      );

      // Check if invoice was returned in response (same pattern as CreateInstance)
      if (response.data.invoice) {
        // Open payment modal immediately with invoice from response
        setPendingInvoice(response.data.invoice);
        setPaymentModalOpen(true);
      } else {
        // No invoice returned - upgrade completed without payment (shouldn't happen for paid upgrades)
        navigate(`/billing/instance/${instanceId}`, {
          state: { message: 'Upgrade completed successfully!' }
        });
      }
    } catch (err: any) {
      alert(`Upgrade failed: ${err.response?.data?.detail || err.message}`);
      setShowConfirmation(false);
      setConfirmationChecked(false);
    } finally {
      setUpgrading(false);
    }
  };

  // Handle payment success
  const handlePaymentSuccess = () => {
    setPaymentModalOpen(false);
    navigate(`/billing/instance/${instanceId}`, {
      state: { message: 'Upgrade and payment completed successfully!' }
    });
  };

  // Utility functions
  const formatCurrency = (amount: number | null, currency: string = 'USD') => {
    if (amount === null) return 'N/A';
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

  const getPriceDelta = (targetPrice: number | null) => {
    if (!subscriptionData?.subscription || targetPrice === null) return '';

    const currentPlanInfo = allPlans.find(p => p.name === subscriptionData.subscription.planName);
    if (!currentPlanInfo || currentPlanInfo.price === null) return '';

    const delta = targetPrice - currentPlanInfo.price;
    return delta > 0 ? `+${formatCurrency(delta, 'USD')}` : formatCurrency(delta, 'USD');
  };

  // Get current plan info
  const getCurrentPlanInfo = (): Plan | null => {
    if (!subscriptionData?.subscription) return null;

    const currentPlanName = subscriptionData.subscription.planName;
    return allPlans.find(p => p.name === currentPlanName) || null;
  };

  if (loading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          </div>
        </div>
      </>
    );
  }

  if (error || !instance || !subscriptionData) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-red-900 mb-2">Error</h2>
            <p className="text-red-700">{error || 'Failed to load subscription data'}</p>
            <Link
              to="/instances"
              className="mt-4 inline-block bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
            >
              Back to Instances
            </Link>
          </div>
        </div>
      </>
    );
  }

  // Check if subscription is active
  if (subscriptionData.subscription.state !== 'ACTIVE') {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-yellow-900 mb-2">Subscription Not Active</h2>
            <p className="text-yellow-700 mb-4">
              You can only upgrade active subscriptions. Current status: {subscriptionData.subscription.state}
            </p>
            <Link
              to={`/billing/instance/${instanceId}`}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
            >
              Back to Billing Management
            </Link>
          </div>
        </div>
      </>
    );
  }

  // Check if there are upgradable plans
  if (upgradablePlans.length === 0) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="max-w-7xl mx-auto px-4 py-8">
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <h2 className="text-xl font-semibold text-blue-900 mb-2">No Upgrades Available</h2>
            <p className="text-blue-700 mb-4">
              You're already on the highest tier available. There are no plans to upgrade to.
            </p>
            <Link
              to={`/billing/instance/${instanceId}`}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
            >
              Back to Billing Management
            </Link>
          </div>
        </div>
      </>
    );
  }

  const currentPlan = getCurrentPlanInfo();

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="mb-6 text-sm text-gray-600">
          <Link to="/billing" className="hover:text-blue-600">Billing</Link>
          {' → '}
          <Link to={`/billing/instance/${instanceId}`} className="hover:text-blue-600">Instance Billing</Link>
          {' → '}
          <span className="text-gray-900">Upgrade Subscription</span>
        </div>

        {/* Page Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Upgrade Your Subscription</h1>
          <p className="text-gray-600">
            Instance: <span className="font-medium text-gray-900">{instance.name}</span>
          </p>
        </div>

        {/* Current Plan Card */}
        <div className="mb-8 p-6 bg-gradient-to-r from-blue-50 to-gray-50 border border-blue-200 rounded-lg">
          <h2 className="text-sm font-medium text-gray-600 mb-3">Current Plan</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <div className="text-sm text-gray-600">Plan</div>
              <div className="text-lg font-semibold text-gray-900">{subscriptionData.subscription.plan_name}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Billing Period</div>
              <div className="text-lg font-semibold text-gray-900">{subscriptionData.billing_period || 'Monthly'}</div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Resources</div>
              <div className="text-sm font-medium text-gray-900">
                {currentPlan?.cpu_limit || 'N/A'} CPU, {currentPlan?.memory_limit || 'N/A'} RAM, {currentPlan?.storage_limit || 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-sm text-gray-600">Next Billing</div>
              <div className="text-sm font-medium text-gray-900">
                {subscriptionData.next_billing_date ? formatDate(subscriptionData.next_billing_date) : 'N/A'}
              </div>
            </div>
          </div>
        </div>

        {!showConfirmation ? (
          <>
            {/* Available Upgrades */}
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-gray-900 mb-4">Available Upgrades</h2>
              <p className="text-gray-600 mb-6">Select a plan to upgrade to:</p>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {upgradablePlans.map((plan) => (
                  <div
                    key={plan.name}
                    onClick={() => setSelectedPlan(plan)}
                    className={`p-6 border-2 rounded-lg cursor-pointer transition-all ${
                      selectedPlan?.name === plan.name
                        ? 'border-blue-600 bg-blue-50 shadow-md'
                        : 'border-gray-300 hover:border-blue-400 hover:shadow-sm'
                    }`}
                  >
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center">
                        <input
                          type="radio"
                          checked={selectedPlan?.name === plan.name}
                          onChange={() => setSelectedPlan(plan)}
                          className="mr-3"
                        />
                        <h3 className="text-lg font-semibold text-gray-900">{plan.product} - {plan.name}</h3>
                      </div>
                    </div>

                    <div className="mb-4">
                      <div className="text-2xl font-bold text-gray-900">{formatCurrency(plan.price, plan.currency)}</div>
                      <div className="text-sm text-green-600 font-medium">{getPriceDelta(plan.price)}/month</div>
                    </div>

                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-gray-600">CPU:</span>
                        <span className="font-medium text-gray-900">{plan.cpu_limit} cores</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Memory:</span>
                        <span className="font-medium text-gray-900">{plan.memory_limit}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Storage:</span>
                        <span className="font-medium text-gray-900">{plan.storage_limit}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Comparison Table */}
            {selectedPlan && currentPlan && (
              <div className="mb-8 p-6 bg-white border border-gray-200 rounded-lg">
                <h2 className="text-xl font-bold text-gray-900 mb-4">Plan Comparison</h2>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b-2 border-gray-300">
                        <th className="text-left py-3 px-4 text-gray-600">Feature</th>
                        <th className="text-left py-3 px-4 text-gray-600">Current Plan</th>
                        <th className="text-left py-3 px-4 text-blue-600">After Upgrade</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-gray-200">
                        <td className="py-3 px-4 font-medium text-gray-700">Plan</td>
                        <td className="py-3 px-4">{currentPlan.name}</td>
                        <td className="py-3 px-4 text-blue-600 font-semibold">{selectedPlan.name}</td>
                      </tr>
                      <tr className="border-b border-gray-200">
                        <td className="py-3 px-4 font-medium text-gray-700">CPU</td>
                        <td className="py-3 px-4">{currentPlan.cpu_limit} cores</td>
                        <td className="py-3 px-4 text-blue-600 font-semibold">
                          {selectedPlan.cpu_limit} cores
                          {selectedPlan.cpu_limit && currentPlan.cpu_limit && selectedPlan.cpu_limit > currentPlan.cpu_limit && ' ⬆'}
                        </td>
                      </tr>
                      <tr className="border-b border-gray-200">
                        <td className="py-3 px-4 font-medium text-gray-700">Memory</td>
                        <td className="py-3 px-4">{currentPlan.memory_limit}</td>
                        <td className="py-3 px-4 text-blue-600 font-semibold">{selectedPlan.memory_limit} ⬆</td>
                      </tr>
                      <tr className="border-b border-gray-200">
                        <td className="py-3 px-4 font-medium text-gray-700">Storage</td>
                        <td className="py-3 px-4">{currentPlan.storage_limit}</td>
                        <td className="py-3 px-4 text-blue-600 font-semibold">{selectedPlan.storage_limit} ⬆</td>
                      </tr>
                      <tr>
                        <td className="py-3 px-4 font-medium text-gray-700">Price/month</td>
                        <td className="py-3 px-4">{formatCurrency(currentPlan.price, currentPlan.currency)}</td>
                        <td className="py-3 px-4 text-blue-600 font-semibold">{formatCurrency(selectedPlan.price, selectedPlan.currency)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* How Upgrade Works */}
            <div className="mb-8 p-6 bg-blue-50 rounded-lg border border-blue-200">
              <h3 className="font-semibold text-blue-900 mb-3">How the upgrade works:</h3>
              <ol className="list-decimal list-inside space-y-2 text-sm text-blue-800">
                <li>A prorated invoice will be created for the remaining billing period</li>
                <li>You'll be redirected to pay the prorated amount</li>
                <li>Once payment is received, your instance resources will be upgraded automatically</li>
                <li>If your instance is running, resources apply immediately</li>
                <li>If stopped, new resources will apply when you next start it</li>
              </ol>
            </div>

            {/* Important Notes */}
            <div className="mb-8 p-6 bg-yellow-50 rounded-lg border border-yellow-200">
              <h3 className="font-semibold text-yellow-900 mb-3">⚠️ Important Notes:</h3>
              <ul className="list-disc list-inside space-y-2 text-sm text-yellow-800">
                <li>Downgrades are not supported - upgrades only</li>
                <li>Your next billing date remains unchanged</li>
                <li>You'll only pay the prorated difference for this period</li>
                <li>Future invoices will reflect the new plan price</li>
              </ul>
            </div>

            {/* Action Buttons */}
            <div className="flex gap-4 sticky bottom-0 bg-white py-4 border-t border-gray-200">
              <Link
                to={`/billing/instance/${instanceId}`}
                className="flex-1 px-6 py-3 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 text-center font-medium"
              >
                Cancel
              </Link>
              <button
                onClick={() => setShowConfirmation(true)}
                disabled={!selectedPlan}
                className="flex-1 bg-blue-600 text-white px-6 py-3 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                Review Upgrade
              </button>
            </div>
          </>
        ) : (
          /* Confirmation Step */
          <div className="mb-8">
            <div className="bg-white border-2 border-blue-600 rounded-lg p-8 shadow-lg">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">Confirm Your Upgrade</h2>

              {/* Summary */}
              <div className="mb-6 p-6 bg-gray-50 rounded-lg">
                <h3 className="font-semibold text-gray-900 mb-4">Upgrade Summary</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Current Plan:</span>
                    <span className="font-medium text-gray-900">{subscriptionData.subscription.plan_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">New Plan:</span>
                    <span className="font-medium text-blue-600">{selectedPlan?.product} - {selectedPlan?.name}</span>
                  </div>
                  <div className="flex justify-between border-t border-gray-200 pt-3">
                    <span className="text-gray-600">Price Change:</span>
                    <span className="font-semibold text-green-600">{getPriceDelta(selectedPlan?.price || null)}/month</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">New Monthly Price:</span>
                    <span className="font-semibold text-gray-900">{formatCurrency(selectedPlan?.price || null, selectedPlan?.currency)}</span>
                  </div>
                </div>
              </div>

              {/* Confirmation Checkbox */}
              <div className="mb-6">
                <label className="flex items-start cursor-pointer">
                  <input
                    type="checkbox"
                    checked={confirmationChecked}
                    onChange={(e) => setConfirmationChecked(e.target.checked)}
                    className="mt-1 mr-3"
                  />
                  <span className="text-sm text-gray-700">
                    I understand this upgrade is immediate and will generate a prorated invoice that must be paid to apply the new resources.
                  </span>
                </label>
              </div>

              {/* Action Buttons */}
              <div className="flex gap-4">
                <button
                  onClick={() => {
                    setShowConfirmation(false);
                    setConfirmationChecked(false);
                  }}
                  disabled={upgrading}
                  className="flex-1 px-6 py-3 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-50 font-medium"
                >
                  Go Back
                </button>
                <button
                  onClick={handleConfirmUpgrade}
                  disabled={!confirmationChecked || upgrading}
                  className="flex-1 bg-blue-600 text-white px-6 py-3 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                >
                  {upgrading ? (
                    <span className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                      Processing...
                    </span>
                  ) : (
                    'Confirm Upgrade'
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Payment Modal */}
      {paymentModalOpen && pendingInvoice && profile && (
        <PaymentModal
          invoice={pendingInvoice}
          customerEmail={profile.email}
          onClose={() => setPaymentModalOpen(false)}
          onSuccess={handlePaymentSuccess}
        />
      )}
    </>
  );
};

export default SubscriptionUpgrade;
