import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { instanceAPI, tenantAPI, authAPI, CreateInstanceRequest, Tenant, UserProfile } from '../utils/api';
import Navigation from '../components/Navigation';

const CreateInstance: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [formData, setFormData] = useState<CreateInstanceRequest>({
    tenant_id: '',
    name: '',
    description: '',
    odoo_version: '17.0',
    instance_type: 'development',
    cpu_limit: 1.0,
    memory_limit: '2G',
    storage_limit: '10G',
    admin_email: '',
    demo_data: true,
    database_name: '',
    custom_addons: [],
    accept_terms: false,
  });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const [profileResponse, tenantsResponse] = await Promise.all([
          authAPI.getProfile(),
          authAPI.getProfile().then(profile => tenantAPI.list(profile.data.id))
        ]);

        setProfile(profileResponse.data);
        setTenants(tenantsResponse.data.tenants || []);

        // Check for tenant pre-selection from URL
        const tenantParam = searchParams.get('tenant');
        const selectedTenant = tenantParam && tenantsResponse.data.tenants?.find(t => t.id === tenantParam);

        setFormData(prev => ({
          ...prev,
          tenant_id: selectedTenant ? selectedTenant.id : (tenantsResponse.data.tenants?.[0]?.id || ''),
          admin_email: profileResponse.data.email
        }));
      } catch (err) {
        setError('Failed to load form data');
      } finally {
        setInitialLoading(false);
      }
    };

    fetchInitialData();
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await instanceAPI.create(formData);
      
      // Redirect back to instances page or dashboard
      const tenantParam = searchParams.get('tenant');
      if (tenantParam) {
        navigate(`/instances?tenant=${tenantParam}`);
      } else {
        navigate('/instances');
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 
                          (err.response?.data?.errors ? 
                            Object.values(err.response.data.errors).flat().join(', ') : 
                            'Failed to create instance'
                          );
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: keyof CreateInstanceRequest, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const generateDatabaseName = (instanceName: string) => {
    return instanceName
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .substring(0, 30);
  };

  const handleNameChange = (name: string) => {
    handleInputChange('name', name);
    
    // Auto-generate database name if not manually set
    if (name && (!formData.database_name || formData.database_name === generateDatabaseName(formData.name))) {
      const dbName = generateDatabaseName(name);
      handleInputChange('database_name', dbName);
    }
  };

  const selectedTenantName = tenants.find(t => t.id === formData.tenant_id)?.name;

  if (initialLoading) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center">
          <div className="flex flex-col items-center">
            <svg className="animate-spin h-8 w-8 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p className="mt-2 text-sm text-gray-600">Loading form...</p>
          </div>
        </div>
      </>
    );
  }

  if (tenants.length === 0) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <main className="max-w-3xl mx-auto py-6 sm:px-6 lg:px-8">
          <div className="px-4 py-6 sm:px-0">
            <div className="text-center py-12 bg-white rounded-lg shadow">
              <div className="text-gray-400 text-6xl mb-4">🏢</div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No workspaces found</h3>
              <p className="text-gray-600 mb-6">
                You need to create a workspace before you can create instances
              </p>
              <div className="space-x-4">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="btn-secondary"
                >
                  Back to Dashboard
                </button>
                <button
                  onClick={() => navigate('/tenants/create')}
                  className="btn-primary"
                >
                  Create Workspace
                </button>
              </div>
            </div>
          </div>
        </main>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      
      <main className="max-w-3xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Create New Odoo Instance</h1>
            <p className="mt-1 text-sm text-gray-600">
              Set up a new Odoo instance {selectedTenantName && `in ${selectedTenantName} workspace`}
            </p>
          </div>

          {/* Form */}
          <div className="bg-white shadow rounded-lg">
            <form onSubmit={handleSubmit} className="space-y-6 p-6">
              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-md text-sm">
                  {error}
                </div>
              )}

              {/* Workspace Selection */}
              {tenants.length > 1 && (
                <div>
                  <h3 className="text-lg font-medium text-gray-900 mb-4">Workspace</h3>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Select Workspace *
                    </label>
                    <select
                      required
                      value={formData.tenant_id}
                      onChange={(e) => handleInputChange('tenant_id', e.target.value)}
                      className="input-field"
                    >
                      {tenants.map((tenant) => (
                        <option key={tenant.id} value={tenant.id}>
                          {tenant.name}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-xs text-gray-500">
                      The workspace where this instance will be created
                    </p>
                  </div>
                </div>
              )}

              {/* Basic Information */}
              <div className={tenants.length > 1 ? "border-t border-gray-200 pt-6" : ""}>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Instance Information</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Instance Name *
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.name}
                      onChange={(e) => handleNameChange(e.target.value)}
                      className="input-field"
                      placeholder="My Production Instance"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Database Name *
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.database_name}
                      onChange={(e) => handleInputChange('database_name', e.target.value)}
                      className="input-field"
                      placeholder="my_production_db"
                      pattern="[a-z0-9_]+"
                      title="Only lowercase letters, numbers, and underscores allowed"
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      Only lowercase letters, numbers, and underscores
                    </p>
                  </div>
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => handleInputChange('description', e.target.value)}
                    rows={3}
                    className="input-field"
                    placeholder="Brief description of this instance..."
                  />
                </div>
              </div>

              {/* Configuration */}
              <div className="border-t border-gray-200 pt-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Configuration</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Odoo Version
                    </label>
                    <select
                      value={formData.odoo_version}
                      onChange={(e) => handleInputChange('odoo_version', e.target.value)}
                      className="input-field"
                    >
                      <option value="17.0">Odoo 17.0 (Latest)</option>
                      <option value="16.0">Odoo 16.0</option>
                      <option value="15.0">Odoo 15.0</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Instance Type
                    </label>
                    <select
                      value={formData.instance_type}
                      onChange={(e) => handleInputChange('instance_type', e.target.value as any)}
                      className="input-field"
                    >
                      <option value="development">Development</option>
                      <option value="staging">Staging</option>
                      <option value="production">Production</option>
                    </select>
                  </div>
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Admin Email *
                  </label>
                  <input
                    type="email"
                    required
                    value={formData.admin_email}
                    onChange={(e) => handleInputChange('admin_email', e.target.value)}
                    className="input-field"
                    placeholder="admin@company.com"
                  />
                </div>
              </div>

              {/* Resource Allocation */}
              <div className="border-t border-gray-200 pt-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Resource Allocation</h3>
                
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      CPU Cores
                    </label>
                    <select
                      value={formData.cpu_limit}
                      onChange={(e) => handleInputChange('cpu_limit', parseFloat(e.target.value))}
                      className="input-field"
                    >
                      <option value={0.5}>0.5 cores</option>
                      <option value={1.0}>1 core</option>
                      <option value={2.0}>2 cores</option>
                      <option value={4.0}>4 cores</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Memory (RAM)
                    </label>
                    <select
                      value={formData.memory_limit}
                      onChange={(e) => handleInputChange('memory_limit', e.target.value)}
                      className="input-field"
                    >
                      <option value="1G">1 GB</option>
                      <option value="2G">2 GB</option>
                      <option value="4G">4 GB</option>
                      <option value="8G">8 GB</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Storage
                    </label>
                    <select
                      value={formData.storage_limit}
                      onChange={(e) => handleInputChange('storage_limit', e.target.value)}
                      className="input-field"
                    >
                      <option value="10G">10 GB</option>
                      <option value="20G">20 GB</option>
                      <option value="50G">50 GB</option>
                      <option value="100G">100 GB</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Options */}
              <div className="border-t border-gray-200 pt-6">
                <h3 className="text-lg font-medium text-gray-900 mb-4">Options</h3>
                
                <div className="space-y-4">
                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="demo_data"
                      checked={formData.demo_data}
                      onChange={(e) => handleInputChange('demo_data', e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label htmlFor="demo_data" className="ml-2 text-sm text-gray-900">
                      Install demo data (recommended for development/testing)
                    </label>
                  </div>

                  <div className="flex items-center">
                    <input
                      type="checkbox"
                      id="accept_terms"
                      required
                      checked={formData.accept_terms}
                      onChange={(e) => handleInputChange('accept_terms', e.target.checked)}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                    />
                    <label htmlFor="accept_terms" className="ml-2 text-sm text-gray-900">
                      I accept the{' '}
                      <a href="#" className="text-primary-600 hover:text-primary-500">
                        terms and conditions
                      </a>{' '}
                      *
                    </label>
                  </div>
                </div>
              </div>

              {/* Submit buttons */}
              <div className="border-t border-gray-200 pt-6">
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => navigate('/instances')}
                    className="px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="btn-primary"
                  >
                    {loading ? (
                      <span className="flex items-center">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Creating Instance...
                      </span>
                    ) : (
                      'Create Instance'
                    )}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      </main>
    </>
  );
};

export default CreateInstance;