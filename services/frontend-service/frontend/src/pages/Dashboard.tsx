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

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running': return 'text-green-600 bg-green-100';
      case 'stopped': return 'text-gray-600 bg-gray-100';
      case 'creating': return 'text-blue-600 bg-blue-100';
      case 'error': return 'text-red-600 bg-red-100';
      default: return 'text-yellow-600 bg-yellow-100';
    }
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const getSubscriptionInfo = () => {
    // Count instances with paid billing status (active subscriptions)
    const paidInstances = instances.filter(instance => 
      instance.billing_status === 'paid'
    );
    
    if (paidInstances.length > 0) {
      return {
        plan: `${paidInstances.length} Instance${paidInstances.length > 1 ? 's' : ''}`,
        status: 'active',
        isActive: true
      };
    }
    return {
      plan: 'No Active Instances',
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
  const subscriptionInfo = getSubscriptionInfo();
  const trialInfo = getTrialInfo();

  if (loading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="flex flex-col items-center">
            <svg className="animate-spin h-8 w-8 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p className="mt-2 text-sm text-gray-600">Loading dashboard...</p>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Welcome section */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">
              Welcome back, {profile?.first_name}! 👋
            </h1>
            <p className="mt-1 text-sm text-gray-600">
              Here's what's happening with your Odoo instances
            </p>
          </div>

          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md">
              {error}
            </div>
          )}

          {/* Stats cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-indigo-500 rounded-full flex items-center justify-center">
                      <span className="text-white font-bold text-sm">{totalInstances}</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Total Instances
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {totalInstances} {totalInstances === 1 ? 'instance' : 'instances'}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-blue-500 rounded-full flex items-center justify-center">
                      <span className="text-white font-bold text-sm">{runningInstances}</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Running Instances
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {runningInstances} active
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
                      <span className="text-white font-bold text-sm">{instances.filter(i => i.status === 'stopped').length}</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Stopped Instances
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {instances.filter(i => i.status === 'stopped').length} stopped
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white overflow-hidden shadow rounded-lg">
              <div className="p-5">
                <div className="flex items-center">
                  <div className="flex-shrink-0">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      billingLoading ? 'bg-gray-300' : 
                      subscriptionInfo.isActive ? 'bg-green-500' : 
                      trialInfo.isInTrial ? 'bg-yellow-500' : 'bg-gray-500'
                    }`}>
                      <span className="text-white text-xs">
                        {billingLoading ? '...' : 
                         subscriptionInfo.isActive ? '✓' : 
                         trialInfo.isInTrial ? '⏰' : '○'}
                      </span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        {trialInfo.isInTrial ? 'Trial' : 'Subscription'}
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {billingLoading ? 'Loading...' : 
                         trialInfo.isInTrial ? `${trialInfo.daysRemaining} days left` :
                         subscriptionInfo.plan}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Trial notification */}
          {trialInfo.isInTrial && (
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
                    You have {trialInfo.daysRemaining} days remaining in your trial period.
                  </p>
                  <div className="mt-2">
                    <Link
                      to="/billing/subscription"
                      className="text-sm font-medium text-yellow-600 hover:text-yellow-500"
                    >
                      Choose a subscription plan →
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Billing overview */}
          {billingData && !billingLoading && (
            <div className="bg-white shadow rounded-lg mb-8">
              <div className="px-4 py-5 sm:p-6">
                <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                  Instance Billing Overview
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div className="text-center p-4 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">
                      {formatCurrency(billingData.account_balance)}
                    </div>
                    <div className="text-sm text-gray-600">Account Balance</div>
                  </div>
                  <div className="text-center p-4 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-600">
                      {instances.filter(instance => instance.billing_status === 'paid').length}
                    </div>
                    <div className="text-sm text-gray-600">Billed Instances</div>
                  </div>
                  <div className="text-center p-4 bg-purple-50 rounded-lg">
                    <div className="text-2xl font-bold text-purple-600">
                      {instances.filter(instance => instance.billing_status === 'trial').length}
                    </div>
                    <div className="text-sm text-gray-600">Trial Instances</div>
                  </div>
                </div>
                <div className="mt-4 text-center">
                  <Link
                    to="/billing"
                    className="text-sm font-medium text-blue-600 hover:text-blue-500"
                  >
                    Manage instance billing →
                  </Link>
                </div>
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className="bg-white shadow rounded-lg mb-8">
            <div className="px-4 py-5 sm:p-6">
              <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                Quick Actions
              </h3>
              <div className="flex flex-wrap gap-4">
                <Link
                  to="/instances/create"
                  className="btn-primary inline-flex items-center"
                >
                  <span className="mr-2">➕</span>
                  Create Instance
                </Link>
                <Link
                  to="/instances"
                  className="btn-secondary inline-flex items-center"
                >
                  <span className="mr-2">🖥️</span>
                  Manage Instances
                </Link>
                <Link
                  to="/billing"
                  className="btn-secondary inline-flex items-center"
                >
                  <span className="mr-2">💳</span>
                  View Billing
                </Link>
                {trialInfo.isInTrial && (
                  <Link
                    to="/billing/subscription"
                    className="btn-primary inline-flex items-center bg-yellow-600 hover:bg-yellow-700"
                  >
                    <span className="mr-2">⭐</span>
                    Upgrade Plan
                  </Link>
                )}
                <button className="btn-secondary inline-flex items-center">
                  <span className="mr-2">📊</span>
                  View Analytics
                </button>
              </div>
            </div>
          </div>

          {/* Recent Instances */}
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Your Instances
              </h3>
              <Link
                to="/instances"
                className="text-sm text-primary-600 hover:text-primary-500"
              >
                View all instances →
              </Link>
            </div>

            {instances.length === 0 ? (
              <div className="bg-white shadow rounded-lg">
                <div className="text-center py-12">
                  <div className="text-gray-400 text-6xl mb-4">🖥️</div>
                  <h4 className="text-lg font-medium text-gray-900 mb-2">
                    No instances yet
                  </h4>
                  <p className="text-gray-600 mb-6">
                    Create your first Odoo instance to get started
                  </p>
                  <Link
                    to="/instances/create"
                    className="btn-primary inline-flex items-center"
                  >
                    <span className="mr-2">➕</span>
                    Create Your First Instance
                  </Link>
                </div>
              </div>
            ) : (
              <div className="bg-white shadow rounded-lg">
                <div className="px-4 py-5 sm:p-6">
                  <div className="space-y-3">
                    {instances.slice(0, 5).map((instance) => (
                      <div
                        key={instance.id}
                        className="flex items-center justify-between p-3 border border-gray-200 rounded hover:bg-gray-50"
                      >
                        <div className="flex items-center">
                          <div className="w-8 h-8 bg-primary-100 rounded flex items-center justify-center mr-3">
                            <span className="text-primary-600 font-medium text-xs">
                              {instance.name[0].toUpperCase()}
                            </span>
                          </div>
                          <div>
                            <div className="text-sm font-medium text-gray-900">
                              {instance.name}
                            </div>
                            <div className="text-xs text-gray-500">
                              {instance.instance_type} • {instance.odoo_version}
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${getStatusColor(instance.status)}`}>
                            {instance.status}
                          </span>
                          {/* Instance billing status badge */}
                          {instance.billing_status === 'paid' ? (
                            <span className="px-2 py-1 text-xs font-medium rounded-full text-green-600 bg-green-100">
                              Paid
                            </span>
                          ) : (
                            <span className="px-2 py-1 text-xs font-medium rounded-full text-yellow-600 bg-yellow-100">
                              Trial
                            </span>
                          )}
                          {instance.external_url && (
                            <a
                              href={instance.external_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-primary-600 hover:text-primary-500"
                            >
                              Open
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                    
                    {instances.length > 5 && (
                      <div className="text-center pt-2 border-t border-gray-100">
                        <Link
                          to="/instances"
                          className="text-xs text-primary-600 hover:text-primary-500"
                        >
                          View {instances.length - 5} more instances →
                        </Link>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
};

export default Dashboard;