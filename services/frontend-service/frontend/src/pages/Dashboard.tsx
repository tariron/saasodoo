import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { authAPI, instanceAPI, tenantAPI, UserProfile, Instance, Tenant, TenantWithInstances } from '../utils/api';
import Navigation from '../components/Navigation';

const Dashboard: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [tenantsWithInstances, setTenantsWithInstances] = useState<TenantWithInstances[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        
        // Fetch user profile
        console.log('Fetching user profile...');
        const profileResponse = await authAPI.getProfile();
        console.log('User profile:', profileResponse.data);
        setProfile(profileResponse.data);

        // Fetch tenants and their instances
        try {
          console.log('Fetching tenants for customer:', profileResponse.data.id);
          const tenantsResponse = await tenantAPI.list(profileResponse.data.id);
          console.log('Tenants response:', tenantsResponse.data);
          const tenants = tenantsResponse.data.tenants || [];

          // Fetch instances for each tenant
          const tenantsWithInstancesData: TenantWithInstances[] = [];
          for (const tenant of tenants) {
            try {
              console.log('Fetching instances for tenant:', tenant.id);
              const instancesResponse = await instanceAPI.list(tenant.id);
              console.log(`Instances for tenant ${tenant.name}:`, instancesResponse.data);
              tenantsWithInstancesData.push({
                ...tenant,
                instances: instancesResponse.data.instances || []
              });
            } catch (instanceErr) {
              console.warn(`Failed to fetch instances for tenant ${tenant.id}:`, instanceErr);
              // Add tenant with empty instances array if fetch fails
              tenantsWithInstancesData.push({
                ...tenant,
                instances: []
              });
            }
          }
          setTenantsWithInstances(tenantsWithInstancesData);
        } catch (tenantErr) {
          console.warn('Failed to fetch tenants:', tenantErr);
          setTenantsWithInstances([]);
        }
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

  // Calculate aggregate stats across all tenants
  const allInstances = tenantsWithInstances.flatMap(t => t.instances);
  const totalInstances = allInstances.length;
  const runningInstances = allInstances.filter(i => i.status === 'running').length;
  const totalTenants = tenantsWithInstances.length;

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
                      <span className="text-white font-bold text-sm">{totalTenants}</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Workspaces
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {totalTenants} {totalTenants === 1 ? 'workspace' : 'workspaces'}
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
                    <div className="w-8 h-8 bg-green-500 rounded-full flex items-center justify-center">
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
                    <div className="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center">
                      <span className="text-white text-xs">✓</span>
                    </div>
                  </div>
                  <div className="ml-5 w-0 flex-1">
                    <dl>
                      <dt className="text-sm font-medium text-gray-500 truncate">
                        Subscription
                      </dt>
                      <dd className="text-lg font-medium text-gray-900">
                        {profile?.subscription_plan || 'Basic'}
                      </dd>
                    </dl>
                  </div>
                </div>
              </div>
            </div>
          </div>

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
                  to="/tenants/create"
                  className="btn-secondary inline-flex items-center"
                >
                  <span className="mr-2">🏢</span>
                  Create Workspace
                </Link>
                <button className="btn-secondary inline-flex items-center">
                  <span className="mr-2">📊</span>
                  View Analytics
                </button>
              </div>
            </div>
          </div>

          {/* Workspaces and their instances */}
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-lg leading-6 font-medium text-gray-900">
                Your Workspaces
              </h3>
              <Link
                to="/instances"
                className="text-sm text-primary-600 hover:text-primary-500"
              >
                View all instances →
              </Link>
            </div>

            {tenantsWithInstances.length === 0 ? (
              <div className="bg-white shadow rounded-lg">
                <div className="text-center py-12">
                  <div className="text-gray-400 text-6xl mb-4">🏢</div>
                  <h4 className="text-lg font-medium text-gray-900 mb-2">
                    No workspaces yet
                  </h4>
                  <p className="text-gray-600 mb-6">
                    Create your first workspace to start managing Odoo instances
                  </p>
                  <Link
                    to="/tenants/create"
                    className="btn-primary inline-flex items-center"
                  >
                    <span className="mr-2">🏢</span>
                    Create Your First Workspace
                  </Link>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {tenantsWithInstances.map((tenant) => (
                  <div key={tenant.id} className="bg-white shadow rounded-lg">
                    <div className="px-4 py-5 sm:p-6">
                      {/* Tenant header */}
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h4 className="text-lg font-medium text-gray-900">
                            {tenant.name}
                          </h4>
                          <p className="text-sm text-gray-600">
                            {tenant.description || 'No description'}
                          </p>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-medium text-gray-900">
                            {tenant.instances.length} {tenant.instances.length === 1 ? 'instance' : 'instances'}
                          </div>
                          <div className="text-xs text-gray-500">
                            {tenant.instances.filter(i => i.status === 'running').length} running
                          </div>
                        </div>
                      </div>

                      {/* Instances in this tenant */}
                      {tenant.instances.length === 0 ? (
                        <div className="text-center py-6 border border-gray-200 rounded-lg bg-gray-50">
                          <div className="text-gray-400 text-2xl mb-2">🖥️</div>
                          <p className="text-sm text-gray-600 mb-3">
                            No instances in this workspace
                          </p>
                          <Link
                            to={`/instances/create?tenant=${tenant.id}`}
                            className="text-xs bg-primary-600 text-white px-3 py-1 rounded hover:bg-primary-700"
                          >
                            Create Instance
                          </Link>
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {tenant.instances.slice(0, 3).map((instance) => (
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
                          
                          {tenant.instances.length > 3 && (
                            <div className="text-center pt-2">
                              <Link
                                to="/instances"
                                className="text-xs text-primary-600 hover:text-primary-500"
                              >
                                View {tenant.instances.length - 3} more instances →
                              </Link>
                            </div>
                          )}
                          
                          <div className="text-center pt-2 border-t border-gray-100">
                            <Link
                              to={`/instances/create?tenant=${tenant.id}`}
                              className="text-xs text-primary-600 hover:text-primary-500"
                            >
                              + Add instance to this workspace
                            </Link>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>
    </>
  );
};

export default Dashboard;