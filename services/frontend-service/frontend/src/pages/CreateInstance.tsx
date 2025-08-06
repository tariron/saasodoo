import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { instanceAPI, authAPI, billingAPI, CreateInstanceRequest, CreateInstanceWithSubscriptionRequest, UserProfile } from '../utils/api';
import { Plan } from '../types/billing';
import Navigation from '../components/Navigation';

const CreateInstance: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [phaseType, setPhaseType] = useState<string>('TRIAL');
  const [formData, setFormData] = useState<CreateInstanceRequest>({
    customer_id: '',
    name: '',
    description: '',
    odoo_version: '17',
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
  const [adminPasswordStrength, setAdminPasswordStrength] = useState(0);
  const [subdomainStatus, setSubdomainStatus] = useState<{
    checking: boolean;
    available: boolean | null;
    message: string;
  }>({
    checking: false,
    available: null,
    message: ''
  });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
        // Fetch user profile and available plans in parallel
        const [profileResponse, plansResponse] = await Promise.all([
          authAPI.getProfile(),
          billingAPI.getPlans()
        ]);

        setProfile(profileResponse.data);
        setFormData(prev => ({
          ...prev,
          customer_id: profileResponse.data.id,
          admin_email: profileResponse.data.email
        }));

        if (plansResponse.data.success) {
          setPlans(plansResponse.data.plans);
          // Auto-select first trial plan if available
          const trialPlan = plansResponse.data.plans.find(plan => plan.trial_length > 0);
          if (trialPlan) {
            setSelectedPlan(trialPlan);
          } else if (plansResponse.data.plans.length > 0) {
            setSelectedPlan(plansResponse.data.plans[0]);
          }
        }
      } catch (err) {
        setError('Failed to load form data and plans');
        console.error('Failed to fetch initial data:', err);
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

    if (!selectedPlan) {
      setError('Please select a plan');
      setLoading(false);
      return;
    }

    // Check if subdomain is available
    if (subdomainStatus.available === false) {
      setError('Please choose an available subdomain');
      setLoading(false);
      return;
    }

    // Check if subdomain check is still in progress
    if (subdomainStatus.checking) {
      setError('Please wait for subdomain availability check to complete');
      setLoading(false);
      return;
    }

    try {
      // All plans now go through billing service for proper subscription management and trial eligibility checking
      // Create subscription with instance configuration through billing service
      const subscriptionData: CreateInstanceWithSubscriptionRequest = {
          customer_id: formData.customer_id,
          plan_name: selectedPlan.name,
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
          phase_type: selectedPlan.trial_length > 0 ? phaseType : undefined,
        };
        
        const response = await billingAPI.createInstanceWithSubscription(subscriptionData);
        
        // Show success message with payment instructions
        const isTrialStarted = selectedPlan.trial_length > 0 && phaseType === 'TRIAL';
        const message = isTrialStarted
          ? `Trial subscription created! Your ${selectedPlan.trial_length}-day trial will start immediately.`
          : `Subscription created! Please pay the invoice to activate your instance. Invoice amount: $${response.data.invoice?.amount || selectedPlan.price || '5.00'}`;
        
        alert(message);
        navigate(isTrialStarted ? '/instances' : '/billing');
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

  // Debounced subdomain availability check
  useEffect(() => {
    const checkSubdomainAvailability = async (subdomain: string) => {
      if (!subdomain || subdomain.length < 3) {
        setSubdomainStatus({ checking: false, available: null, message: '' });
        return;
      }

      setSubdomainStatus({ checking: true, available: null, message: 'Checking...' });

      try {
        const response = await instanceAPI.checkSubdomain(subdomain);
        setSubdomainStatus({
          checking: false,
          available: response.data.available,
          message: response.data.message
        });
      } catch (error: any) {
        setSubdomainStatus({
          checking: false,
          available: false,
          message: error.response?.data?.detail || 'Error checking subdomain'
        });
      }
    };

    const timeoutId = setTimeout(() => {
      if (formData.subdomain) {
        checkSubdomainAvailability(formData.subdomain);
      }
    }, 500); // 500ms debounce

    return () => clearTimeout(timeoutId);
  }, [formData.subdomain]);

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

  const checkAdminPasswordStrength = (password: string) => {
    let strength = 0;
    const checks = {
      length: password.length >= 8,
      lowercase: /[a-z]/.test(password),
      uppercase: /[A-Z]/.test(password),
      digit: /[0-9]/.test(password),
      special: /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password)
    };
    if (checks.length) strength++;
    if (checks.lowercase) strength++;
    if (checks.uppercase) strength++;
    if (checks.digit) strength++;
    if (checks.special) strength++;
    return { strength, checks };
  };

  const isAdminPasswordValid = () => {
    const result = checkAdminPasswordStrength(formData.admin_password);
    const { checks } = result;
    return checks.length && checks.lowercase && checks.uppercase && checks.digit && checks.special;
  };

  const getAdminPasswordStrengthText = () => {
    const result = checkAdminPasswordStrength(formData.admin_password);
    const { checks } = result;
    
    if (isAdminPasswordValid()) {
      return 'Strong - All requirements met';
    }
    
    const missing = [];
    if (!checks.length) missing.push('8+ characters');
    if (!checks.uppercase) missing.push('uppercase letter');
    if (!checks.lowercase) missing.push('lowercase letter');  
    if (!checks.digit) missing.push('number');
    if (!checks.special) missing.push('special character');
    
    return `Missing: ${missing.join(', ')}`;
  };

  const getAdminPasswordStrengthColor = () => {
    if (isAdminPasswordValid()) {
      return 'bg-green-500';
    } else if (adminPasswordStrength >= 3) {
      return 'bg-yellow-500';
    } else {
      return 'bg-red-500';
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

              {/* Plan Selection */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Select Plan</h3>
                {plans.length === 0 ? (
                  <div className="text-center py-4">
                    <p className="text-gray-500">Loading available plans...</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {plans.map((plan) => (
                      <div 
                        key={plan.name}
                        className={`relative rounded-lg border p-4 cursor-pointer hover:bg-gray-50 ${
                          selectedPlan?.name === plan.name ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
                        }`}
                        onClick={() => setSelectedPlan(plan)}
                      >
                        <div className="flex items-start">
                          <input
                            type="radio"
                            name="planSelection"
                            value={plan.name}
                            checked={selectedPlan?.name === plan.name}
                            onChange={() => setSelectedPlan(plan)}
                            className="h-4 w-4 text-blue-600 mt-1"
                          />
                          <div className="ml-3 flex-1">
                            <label className="block text-sm font-medium text-gray-900">
                              {plan.product} 
                              {plan.trial_length > 0 && (
                                <span className="ml-1 text-green-600">
                                  ({plan.trial_length} day trial)
                                </span>
                              )}
                            </label>
                            <p className="text-sm text-gray-500 mt-1">
                              {plan.description}
                            </p>
                            <div className="mt-2">
                              {plan.trial_length > 0 && plan.price === 0 ? (
                                <span className="text-lg font-semibold text-green-600">Free Trial</span>
                              ) : plan.trial_length > 0 ? (
                                <div>
                                  <span className="text-sm text-green-600">
                                    {plan.trial_length} days free
                                  </span>
                                  <span className="block text-lg font-semibold text-gray-900">
                                    ${plan.price}/{plan.billing_period.toLowerCase()}
                                  </span>
                                </div>
                              ) : (
                                <span className="text-lg font-semibold text-gray-900">
                                  ${plan.price}/{plan.billing_period.toLowerCase()}
                                </span>
                              )}
                            </div>
                            {plan.fallback && (
                              <span className="inline-block mt-1 px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                                Default
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                
                {/* Trial/Payment Choice */}
                {selectedPlan && selectedPlan.trial_length > 0 && (
                  <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-900 mb-2">Billing Options</h4>
                    <div className="space-y-2">
                      <div className="flex items-center">
                        <input
                          type="radio"
                          id="start-trial"
                          name="phaseOption"
                          checked={phaseType === 'TRIAL'}
                          onChange={() => setPhaseType('TRIAL')}
                          className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                        />
                        <label htmlFor="start-trial" className="ml-2 text-sm text-gray-900">
                          Start with {selectedPlan.trial_length}-day free trial
                          <span className="block text-xs text-gray-500">
                            No payment required now. You'll be charged ${selectedPlan.price} after the trial ends.
                          </span>
                        </label>
                      </div>
                      <div className="flex items-center">
                        <input
                          type="radio"
                          id="skip-trial"
                          name="phaseOption"
                          checked={phaseType === 'EVERGREEN'}
                          onChange={() => setPhaseType('EVERGREEN')}
                          className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                        />
                        <label htmlFor="skip-trial" className="ml-2 text-sm text-gray-900">
                          Skip trial, start paid subscription immediately
                          <span className="block text-xs text-gray-500">
                            You'll be charged ${selectedPlan.price} immediately to activate your instance.
                          </span>
                        </label>
                      </div>
                    </div>
                  </div>
                )}
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
                        className={`input-field rounded-r-none ${
                          subdomainStatus.available === false ? 'border-red-300 focus:border-red-500' :
                          subdomainStatus.available === true ? 'border-green-300 focus:border-green-500' :
                          'border-gray-300'
                        }`}
                        placeholder="crm"
                        pattern="[a-z0-9-]+"
                        title="Only lowercase letters, numbers, and hyphens allowed"
                        maxLength={30}
                      />
                      <span className="inline-flex items-center px-3 rounded-r-md border border-l-0 border-gray-300 bg-gray-50 text-gray-500 text-sm">
                        .saasodoo.local
                      </span>
                    </div>
                    
                    {/* Subdomain availability status */}
                    {formData.subdomain && formData.subdomain.length >= 3 && (
                      <div className="mt-2 flex items-center space-x-1">
                        {subdomainStatus.checking ? (
                          <>
                            <svg className="animate-spin h-4 w-4 text-gray-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                            <span className="text-sm text-gray-500">Checking availability...</span>
                          </>
                        ) : subdomainStatus.available === true ? (
                          <>
                            <svg className="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path>
                            </svg>
                            <span className="text-sm text-green-600 font-medium">Available</span>
                          </>
                        ) : subdomainStatus.available === false ? (
                          <>
                            <svg className="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                            <span className="text-sm text-red-600 font-medium">Already taken</span>
                          </>
                        ) : null}
                      </div>
                    )}
                    
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
                      <option value="18">Odoo 18 (Latest)</option>
                      <option value="17">Odoo 17</option>
                      <option value="16">Odoo 16</option>
                      <option value="15">Odoo 15</option>
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
                      onChange={(e) => {
                        const password = e.target.value;
                        setFormData({ ...formData, admin_password: password });
                        const result = checkAdminPasswordStrength(password);
                        setAdminPasswordStrength(result.strength);
                        // Optionally clear error on change
                        if (error) setError('');
                      }}
                      className="input-field"
                      placeholder="Enter secure password for Odoo admin"
                      minLength={8}
                      pattern="^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]).{8,}$"
                      title="Password must contain at least 8 characters with uppercase, lowercase, number, and special character"
                    />
                    
                    {formData.admin_password && (
                      <div className="mt-2">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-gray-600">Password Strength:</span>
                          <span className={`font-medium ${
                            isAdminPasswordValid() ? 'text-green-600' : 'text-red-600'
                          }`}>
                            {getAdminPasswordStrengthText()}
                          </span>
                        </div>
                        <div className="mt-1 w-full bg-gray-200 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full transition-all duration-300 ${getAdminPasswordStrengthColor()}`}
                            style={{ width: `${(adminPasswordStrength / 5) * 100}%` }}
                          ></div>
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          Required: 8+ characters, uppercase, lowercase, number & special character
                        </div>
                      </div>
                    )}
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
                    disabled={loading || !selectedPlan || subdomainStatus.available === false || subdomainStatus.checking}
                    className="btn-primary"
                  >
                    {loading ? (
                      <span className="flex items-center">
                        <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        {selectedPlan && selectedPlan.trial_length > 0 && phaseType === 'TRIAL' ? 'Creating Trial...' : 'Creating Subscription...'}
                      </span>
                    ) : (
                      selectedPlan
                        ? selectedPlan.trial_length > 0 && phaseType === 'TRIAL'
                          ? `Start ${selectedPlan.trial_length}-Day Trial`
                          : `Create Instance - $${selectedPlan.price}/${selectedPlan.billing_period.toLowerCase()}`
                        : 'Select a Plan'
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