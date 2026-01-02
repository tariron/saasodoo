import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { authAPI, instanceAPI, billingAPI, UserProfile, Instance } from '../utils/api';
import { BillingOverview } from '../types/billing';
import Navigation from '../components/Navigation';

const Dashboard: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [instances, setInstances] = useState<Instance[]>([]);
  const [billingData, setBillingData] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [billingLoading, setBillingLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchBillingData = async (customerId: string) => {
    try {
      setBillingLoading(true);
      const billingResponse = await billingAPI.getBillingOverview(customerId);
      setBillingData(billingResponse.data.data);
    } catch (billingErr) {
      console.warn('Failed to fetch billing data:', billingErr);
      setBillingData(null);
    } finally {
      setBillingLoading(false);
    }
  };

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);

        // Fetch user profile
        console.log('Fetching user profile...');
        const profileResponse = await authAPI.getProfile();
        console.log('User profile:', profileResponse.data);
        setProfile(profileResponse.data);

        // Fetch instances for this customer
        try {
          console.log('Fetching instances for customer:', profileResponse.data.id);
          const instancesResponse = await instanceAPI.list(profileResponse.data.id);
          console.log('Instances response:', instancesResponse.data);
          setInstances(instancesResponse.data.instances || []);
        } catch (instanceErr) {
          console.warn('Failed to fetch instances:', instanceErr);
          setInstances([]);
        }

        // Fetch billing data
        await fetchBillingData(profileResponse.data.id);
      } catch (err: any) {
        console.error('Dashboard error:', err);
        setError(`Failed to load dashboard data: ${err.response?.data?.detail || err.message}`);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const getStatusBadge = (status: string) => {
    const badges: Record<string, { class: string; icon: JSX.Element }> = {
      running: {
        class: 'badge-success',
        icon: <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full mr-1.5 animate-pulse"></span>
      },
      stopped: {
        class: 'badge-neutral',
        icon: <span className="w-1.5 h-1.5 bg-warm-400 rounded-full mr-1.5"></span>
      },
      creating: {
        class: 'badge-info',
        icon: <svg className="w-3 h-3 mr-1.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>
      },
      error: {
        class: 'badge-error',
        icon: <span className="w-1.5 h-1.5 bg-rose-500 rounded-full mr-1.5"></span>
      },
      paused: {
        class: 'badge-warning',
        icon: <span className="w-1.5 h-1.5 bg-amber-500 rounded-full mr-1.5"></span>
      }
    };
    return badges[status] || badges.stopped;
  };

  const getBillingBadge = (status: string) => {
    const badges: Record<string, string> = {
      paid: 'badge-success',
      trial: 'badge-warning',
      payment_required: 'badge-error'
    };
    return badges[status] || 'badge-neutral';
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const getSubscriptionInfo = () => {
    const paidInstances = instances.filter(instance =>
      instance.billing_status === 'paid'
    );

    if (paidInstances.length > 0) {
      return {
        plan: `${paidInstances.length} Active`,
        status: 'active',
        isActive: true
      };
    }
    return {
      plan: 'No Active',
      status: 'inactive',
      isActive: false
    };
  };

  const getTrialInfo = () => {
    if (billingData?.trial_info?.is_trial) {
      return {
        isInTrial: true,
        daysRemaining: billingData.trial_info.days_remaining || 0,
        trialEndDate: billingData.trial_info.trial_end_date
      };
    }
    return { isInTrial: false, daysRemaining: 0, trialEndDate: null };
  };

  // Calculate stats
  const totalInstances = instances.length;
  const runningInstances = instances.filter(i => i.status === 'running').length;
  const stoppedInstances = instances.filter(i => i.status === 'stopped').length;
  const subscriptionInfo = getSubscriptionInfo();
  const trialInfo = getTrialInfo();

  if (loading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center bg-warm-50">
          <div className="flex flex-col items-center animate-fade-in">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-primary-200 rounded-full"></div>
              <div className="w-16 h-16 border-4 border-primary-600 rounded-full animate-spin absolute top-0 left-0 border-t-transparent"></div>
            </div>
            <p className="mt-4 text-warm-600 font-medium">Loading your dashboard...</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />

      <main className="min-h-screen bg-warm-50 bg-mesh">
        <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
          {/* Welcome section */}
          <div className="mb-10 animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-warm-900">
                  Welcome back, <span className="text-gradient">{profile?.first_name}</span>
                </h1>
                <p className="mt-2 text-warm-500">
                  Here's what's happening with your Odoo instances today
                </p>
              </div>
              <Link
                to="/instances/create"
                className="btn-primary hidden sm:inline-flex"
              >
                <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                New Instance
              </Link>
            </div>
          </div>

          {error && (
            <div className="mb-8 animate-fade-in-down bg-rose-50 border border-rose-200 text-rose-700 px-5 py-4 rounded-xl flex items-start">
              <svg className="w-5 h-5 mr-3 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Stats cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-10">
            {/* Total Instances */}
            <div className="stat-card animate-fade-in-up">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-primary-500 to-primary-600 rounded-xl flex items-center justify-center shadow-glow">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                </div>
                <span className="badge badge-info">Total</span>
              </div>
              <div className="text-3xl font-bold text-warm-900 mb-1">{totalInstances}</div>
              <div className="text-sm text-warm-500">
                {totalInstances === 1 ? 'Instance' : 'Instances'}
              </div>
            </div>

            {/* Running Instances */}
            <div className="stat-card animate-fade-in-up animation-delay-100">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <span className="badge badge-success">Active</span>
              </div>
              <div className="text-3xl font-bold text-warm-900 mb-1">{runningInstances}</div>
              <div className="text-sm text-warm-500">Running</div>
            </div>

            {/* Stopped Instances */}
            <div className="stat-card animate-fade-in-up animation-delay-200">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-warm-400 to-warm-500 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                  </svg>
                </div>
                <span className="badge badge-neutral">Idle</span>
              </div>
              <div className="text-3xl font-bold text-warm-900 mb-1">{stoppedInstances}</div>
              <div className="text-sm text-warm-500">Stopped</div>
            </div>

            {/* Subscription Status */}
            <div className="stat-card animate-fade-in-up animation-delay-300">
              <div className="flex items-center justify-between mb-4">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  billingLoading ? 'bg-warm-200' :
                  subscriptionInfo.isActive ? 'bg-gradient-to-br from-accent-500 to-accent-600' :
                  trialInfo.isInTrial ? 'bg-gradient-to-br from-amber-500 to-amber-600' :
                  'bg-warm-400'
                }`}>
                  {billingLoading ? (
                    <svg className="w-5 h-5 text-warm-500 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                    </svg>
                  ) : (
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                    </svg>
                  )}
                </div>
                <span className={`badge ${trialInfo.isInTrial ? 'badge-warning' : subscriptionInfo.isActive ? 'badge-success' : 'badge-neutral'}`}>
                  {trialInfo.isInTrial ? 'Trial' : 'Billing'}
                </span>
              </div>
              <div className="text-3xl font-bold text-warm-900 mb-1">
                {billingLoading ? '...' :
                 trialInfo.isInTrial ? `${trialInfo.daysRemaining}d` :
                 subscriptionInfo.plan}
              </div>
              <div className="text-sm text-warm-500">
                {trialInfo.isInTrial ? 'Remaining' : 'Subscriptions'}
              </div>
            </div>
          </div>

          {/* Trial notification */}
          {trialInfo.isInTrial && (
            <div className="mb-8 animate-fade-in-up animation-delay-400">
              <div className="relative overflow-hidden bg-gradient-to-r from-amber-50 via-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-6">
                <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-amber-400/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/2"></div>
                <div className="relative flex items-center">
                  <div className="w-14 h-14 bg-gradient-to-br from-amber-400 to-amber-500 rounded-xl flex items-center justify-center mr-5 shadow-lg">
                    <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-amber-900">
                      Trial Period Active
                    </h3>
                    <p className="text-amber-700">
                      You have <strong>{trialInfo.daysRemaining} days</strong> remaining in your trial.
                      <Link to="/billing" className="ml-2 text-amber-800 underline underline-offset-2 hover:text-amber-900 font-medium">
                        View billing options →
                      </Link>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Payment Required Alert */}
          {billingData && (billingData.pending_subscriptions.length > 0 || billingData.outstanding_invoices.length > 0 || billingData.total_outstanding > 0) && (
            <div className="mb-8 animate-fade-in-up animation-delay-400">
              <div className="relative overflow-hidden bg-gradient-to-r from-rose-50 via-rose-50 to-red-50 border border-rose-200 rounded-2xl p-6">
                <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-rose-400/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/2"></div>
                <div className="relative flex items-start">
                  <div className="w-14 h-14 bg-gradient-to-br from-rose-500 to-rose-600 rounded-xl flex items-center justify-center mr-5 shadow-lg flex-shrink-0">
                    <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="text-lg font-semibold text-rose-900 mb-2">
                      Payment Required
                    </h3>
                    <div className="text-rose-700 space-y-1">
                      {billingData.total_outstanding > 0 && (
                        <p className="font-semibold text-lg">
                          Outstanding balance: {formatCurrency(billingData.total_outstanding)}
                        </p>
                      )}
                      {billingData.pending_subscriptions.length > 0 && (
                        <p>
                          {billingData.pending_subscriptions.length} subscription{billingData.pending_subscriptions.length > 1 ? 's' : ''} awaiting payment
                        </p>
                      )}
                      {billingData.provisioning_blocked_instances.length > 0 && (
                        <p className="font-medium flex items-center">
                          <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                          {billingData.provisioning_blocked_instances.length} instance{billingData.provisioning_blocked_instances.length > 1 ? 's' : ''} waiting to be provisioned
                        </p>
                      )}
                    </div>
                    <Link
                      to="/billing"
                      className="inline-flex items-center mt-4 text-rose-800 font-semibold hover:text-rose-900 transition-colors"
                    >
                      View Details & Pay
                      <svg className="w-4 h-4 ml-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                      </svg>
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Recent Instances */}
          <div className="animate-fade-in-up animation-delay-500">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-warm-900">
                Your Instances
              </h2>
              <Link
                to="/instances"
                className="text-sm font-medium text-primary-600 hover:text-primary-500 transition-colors flex items-center"
              >
                View all
                <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </Link>
            </div>

            {instances.length === 0 ? (
              <div className="card p-12 text-center">
                <div className="w-20 h-20 bg-gradient-to-br from-primary-100 to-primary-200 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <svg className="w-10 h-10 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold text-warm-900 mb-2">
                  No instances yet
                </h3>
                <p className="text-warm-500 mb-8 max-w-md mx-auto">
                  Deploy your first Odoo instance in minutes. Choose from multiple versions and configurations.
                </p>
                <Link
                  to="/instances/create"
                  className="btn-primary"
                >
                  <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Create Your First Instance
                </Link>
              </div>
            ) : (
              <div className="card overflow-hidden">
                <div className="divide-y divide-warm-100">
                  {instances.slice(0, 5).map((instance, index) => {
                    const statusBadge = getStatusBadge(instance.status);
                    return (
                      <div
                        key={instance.id}
                        className="p-4 sm:p-5 hover:bg-warm-50/50 transition-colors"
                        style={{ animationDelay: `${(index + 6) * 50}ms` }}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                          {/* Instance info */}
                          <div className="flex items-center min-w-0">
                            <div className="w-10 h-10 sm:w-12 sm:h-12 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center mr-3 sm:mr-4 flex-shrink-0">
                              <span className="text-primary-700 font-bold text-base sm:text-lg">
                                {instance.name[0].toUpperCase()}
                              </span>
                            </div>
                            <div className="min-w-0 flex-1">
                              <h4 className="text-sm sm:text-base font-semibold text-warm-900 truncate">
                                {instance.name}
                              </h4>
                              <div className="flex items-center text-xs sm:text-sm text-warm-500 mt-0.5">
                                <span className="capitalize">{instance.instance_type}</span>
                                <span className="mx-1.5 sm:mx-2">•</span>
                                <span>Odoo {instance.odoo_version}</span>
                              </div>
                            </div>
                          </div>

                          {/* Badges and actions */}
                          <div className="flex items-center justify-between sm:justify-end gap-2 sm:gap-3 ml-13 sm:ml-0">
                            <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                              <span className={`badge text-xs ${statusBadge.class} flex items-center`}>
                                {statusBadge.icon}
                                <span className="capitalize">{instance.status}</span>
                              </span>
                              <span className={`badge text-xs ${getBillingBadge(instance.billing_status)}`}>
                                {instance.billing_status === 'paid' ? 'Paid' :
                                 instance.billing_status === 'payment_required' ? 'Due' :
                                 'Trial'}
                              </span>
                            </div>

                            {instance.external_url && (
                              <a
                                href={instance.external_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn-secondary py-1.5 px-3 text-xs flex-shrink-0"
                              >
                                Open
                                <svg className="w-3.5 h-3.5 ml-1 hidden sm:inline" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                </svg>
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })}

                  {instances.length > 5 && (
                    <div className="p-4 bg-warm-50/50 text-center">
                      <Link
                        to="/instances"
                        className="text-sm font-medium text-primary-600 hover:text-primary-500 transition-colors"
                      >
                        View {instances.length - 5} more instance{instances.length - 5 > 1 ? 's' : ''} →
                      </Link>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Mobile FAB */}
          <Link
            to="/instances/create"
            className="sm:hidden fixed bottom-6 right-6 w-14 h-14 bg-gradient-to-br from-primary-600 to-primary-500 rounded-full shadow-soft-lg flex items-center justify-center text-white hover:shadow-glow transition-all duration-300 hover:scale-105 z-50"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </Link>
        </div>
      </main>
    </>
  );
};

export default Dashboard;
