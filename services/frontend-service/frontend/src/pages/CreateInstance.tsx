import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { instanceAPI, authAPI, billingAPI, CreateInstanceRequest, CreateInstanceWithSubscriptionRequest, UserProfile } from '../utils/api';
import Navigation from '../components/Navigation';

const CreateInstance: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [formData, setFormData] = useState<CreateInstanceRequest>({
    customer_id: '',
    name: '',
    description: '',
    odoo_version: '17.0',
    instance_type: 'development',
    cpu_limit: 1.0,
    memory_limit: '2G',
    storage_limit: '10G',
    admin_email: '',
    admin_password: '',
    database_name: '',
    subdomain: '',
    demo_data: true,
    custom_addons: [],
  });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState('');
  const [instanceFlow, setInstanceFlow] = useState<'trial' | 'paid'>('trial');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        const profileResponse = await authAPI.getProfile();

        setProfile(profileResponse.data);
        setFormData(prev => ({
          ...prev,
          customer_id: profileResponse.data.id,
          admin_email: profileResponse.data.email
        }));
      } catch (err) {
        setError('Failed to load form data');
      } finally {
        setInitialLoading(false);
      }
    };

    fetchInitialData();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      if (instanceFlow === 'trial') {
        // Trial flow: Create instance directly (existing flow)
        const submitData = {
          ...formData,
          subdomain: formData.subdomain?.trim() || null,
          description: formData.description || null,
        };
        await instanceAPI.create(submitData);
        navigate('/instances');
      } else {
        // Paid flow: Create subscription with instance configuration
        const subscriptionData: CreateInstanceWithSubscriptionRequest = {
          customer_id: formData.customer_id,
          plan_name: 'basic-immediate',
          name: formData.name,
          description: formData.description || null,
          admin_email: formData.admin_email,
          admin_password: formData.admin_password,
          subdomain: formData.subdomain?.trim() || null,
          database_name: formData.database_name,
          odoo_version: formData.odoo_version,
          instance_type: formData.instance_type,
          demo_data: formData.demo_data,
          cpu_limit: formData.cpu_limit,
          memory_limit: formData.memory_limit,
          storage_limit: formData.storage_limit,
          custom_addons: formData.custom_addons,
        };
        
        const response = await billingAPI.createInstanceWithSubscription(subscriptionData);
        
        // Show success message with payment instructions
        alert(`Subscription created! Please pay the invoice to activate your instance. Invoice amount: $${response.data.invoice?.amount || '5.00'}`);
        navigate('/billing');
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

  const generateInstanceName = (subdomain: string) => {
    return subdomain
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const generateDatabaseName = (subdomain: string) => {
    return subdomain
      .toLowerCase()
      .replace(/[^a-z0-9]/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .substring(0, 30);
  };

  const handleSubdomainChange = (subdomain: string) => {
    handleInputChange('subdomain', subdomain);
    
    // Auto-generate instance name and database name from subdomain
    if (subdomain) {
      const instanceName = generateInstanceName(subdomain);
      const dbName = generateDatabaseName(subdomain);
      
      handleInputChange('name', instanceName);
      handleInputChange('database_name', dbName);
    }
  };


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


  return (
    <>
      <Navigation userProfile={profile || undefined} />
      
      <main className="max-w-3xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          {/* Header */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-gray-900">Create New Odoo Instance</h1>
            <p className="mt-1 text-sm text-gray-600">
              Set up a new Odoo instance
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

              {/* Instance Flow Selection */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Instance Type</h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div 
                    className={`relative rounded-lg border p-4 cursor-pointer hover:bg-gray-50 ${
                      instanceFlow === 'trial' ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
                    }`}
                    onClick={() => setInstanceFlow('trial')}
                  >
                    <div className="flex items-center">
                      <input
                        type="radio"
                        name="instanceFlow"
                        value="trial"
                        checked={instanceFlow === 'trial'}
                        onChange={() => setInstanceFlow('trial')}
                        className="h-4 w-4 text-blue-600"
                      />
                      <div className="ml-3">
                        <label className="block text-sm font-medium text-gray-900">
                          Free Trial (14 days)
                        </label>
                        <p className="text-sm text-gray-500">
                          Start immediately with a 14-day free trial
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <div 
                    className={`relative rounded-lg border p-4 cursor-pointer hover:bg-gray-50 ${
                      instanceFlow === 'paid' ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
                    }`}
                    onClick={() => setInstanceFlow('paid')}
                  >
                    <div className="flex items-center">
                      <input
                        type="radio"
                        name="instanceFlow"
                        value="paid"
                        checked={instanceFlow === 'paid'}
                        onChange={() => setInstanceFlow('paid')}
                        className="h-4 w-4 text-blue-600"
                      />
                      <div className="ml-3">
                        <label className="block text-sm font-medium text-gray-900">
                          Paid Instance ($5/month)
                        </label>
                        <p className="text-sm text-gray-500">
                          Pay now and activate immediately
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Basic Information */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Instance Information</h3>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Subdomain *
                    </label>
                    <div className="flex">
                      <input
                        type="text"
                        required
                        value={formData.subdomain || ''}
                        onChange={(e) => handleSubdomainChange(e.target.value)}
                        className="input-field rounded-r-none"
                        placeholder="crm"
                        pattern="[a-z0-9-]+"
                        title="Only lowercase letters, numbers, and hyphens allowed"
                        maxLength={30}
                      />
                      <span className="inline-flex items-center px-3 rounded-r-md border border-l-0 border-gray-300 bg-gray-50 text-gray-500 text-sm">
                        .saasodoo.local
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-gray-500">
                      This will be your Odoo URL: {formData.subdomain || 'subdomain'}.saasodoo.local
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Instance Name *
                    </label>
                    <input
                      type="text"
                      required
                      value={formData.name}
                      onChange={(e) => handleInputChange('name', e.target.value)}
                      className="input-field"
                      placeholder="Auto-generated from subdomain"
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      Display name for this instance in your dashboard
                    </p>
                  </div>
                </div>

                <div className="mt-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formData.description || ''}
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

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                  <div>
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

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Admin Password *
                    </label>
                    <input
                      type="password"
                      required
                      value={formData.admin_password || ''}
                      onChange={(e) => handleInputChange('admin_password', e.target.value)}
                      className="input-field"
                      placeholder="Enter secure password for Odoo admin"
                      minLength={8}
                      pattern="^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$"
                      title="Password must contain at least 8 characters with uppercase, lowercase, and number"
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      Must be at least 8 characters with uppercase, lowercase, and number
                    </p>
                  </div>
                </div>

                <div className="mt-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Database Name
                    </label>
                    <input
                      type="text"
                      value={formData.database_name}
                      className="input-field bg-gray-50"
                      placeholder="Auto-generated from subdomain"
                      readOnly
                      disabled
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      Automatically generated from subdomain (read-only)
                    </p>
                  </div>
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
                        {instanceFlow === 'trial' ? 'Creating Trial Instance...' : 'Creating Subscription...'}
                      </span>
                    ) : (
                      instanceFlow === 'trial' ? 'Create Trial Instance' : 'Create Paid Subscription'
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