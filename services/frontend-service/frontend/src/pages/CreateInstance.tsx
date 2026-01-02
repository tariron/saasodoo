import React, { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { instanceAPI, authAPI, billingAPI, CreateInstanceRequest, CreateInstanceWithSubscriptionRequest, UserProfile } from '../utils/api';
import { Plan, Invoice, TrialEligibilityResponse } from '../types/billing';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';
import { useConfig } from '../hooks/useConfig';

/**
 * Transform plan data for display based on trial eligibility
 * Implements "trial invisibility" - users who can't access trials never see trial info
 */
const transformPlanForDisplay = (plan: Plan, eligibility: TrialEligibilityResponse | null): Plan & { display_trial: boolean } => {
  if (!eligibility) {
    return { ...plan, display_trial: plan.trial_length > 0 };
  }

  if (!eligibility.can_show_trial_info) {
    return {
      ...plan,
      trial_length: 0,
      trial_time_unit: '',
      display_trial: false
    };
  }

  return {
    ...plan,
    display_trial: plan.trial_length > 0
  };
};

const CreateInstance: React.FC = () => {
  const { config } = useConfig();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [phaseType, setPhaseType] = useState<string>('TRIAL');
  const [trialEligibility, setTrialEligibility] = useState<TrialEligibilityResponse | null>(null);
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
    database_name: '',
    subdomain: '',
    demo_data: true,
    custom_addons: [],
  });
  const [loading, setLoading] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState('');
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

  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  useEffect(() => {
    const fetchInitialData = async () => {
      try {
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

        try {
          const eligibilityResponse = await billingAPI.getTrialEligibility(profileResponse.data.id);
          setTrialEligibility(eligibilityResponse.data);
        } catch (eligibilityError) {
          console.error('Failed to check trial eligibility:', eligibilityError);
          setTrialEligibility({
            eligible: false,
            can_show_trial_info: false,
            trial_days: 0,
            has_active_subscriptions: false,
            subscription_count: 0,
            reason: 'system_error'
          });
        }

        if (plansResponse.data.success) {
          setPlans(plansResponse.data.plans);
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

  useEffect(() => {
    if (trialEligibility && !trialEligibility.can_show_trial_info && selectedPlan && selectedPlan.trial_length > 0) {
      setPhaseType('EVERGREEN');
    }
  }, [trialEligibility, selectedPlan]);

  useEffect(() => {
    if (selectedPlan) {
      setFormData(prev => ({
        ...prev,
        cpu_limit: selectedPlan.cpu_limit || 1.0,
        memory_limit: selectedPlan.memory_limit || '2G',
        storage_limit: selectedPlan.storage_limit || '10G'
      }));
    }
  }, [selectedPlan]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (!selectedPlan) {
      setError('Please select a plan');
      setLoading(false);
      return;
    }

    if (subdomainStatus.available === false) {
      setError('Please choose an available subdomain');
      setLoading(false);
      return;
    }

    if (subdomainStatus.checking) {
      setError('Please wait for subdomain availability check to complete');
      setLoading(false);
      return;
    }

    try {
      const subscriptionData: CreateInstanceWithSubscriptionRequest = {
          customer_id: formData.customer_id,
          plan_name: selectedPlan.name,
          name: formData.name,
          description: formData.description || null,
          admin_email: formData.admin_email,
          subdomain: formData.subdomain?.trim() || null,
          database_name: formData.database_name,
          odoo_version: formData.odoo_version,
          instance_type: formData.instance_type,
          demo_data: formData.demo_data,
          cpu_limit: formData.cpu_limit,
          memory_limit: formData.memory_limit,
          storage_limit: formData.storage_limit,
          custom_addons: formData.custom_addons,
          phase_type: (trialEligibility?.can_show_trial_info && selectedPlan.trial_length > 0 && phaseType === 'TRIAL') ? 'TRIAL' : 'EVERGREEN',
        };

        const response = await billingAPI.createInstanceWithSubscription(subscriptionData);

        const isTrialStarted = selectedPlan.trial_length > 0 && phaseType === 'TRIAL';

        if (isTrialStarted) {
          const message = `Trial subscription created! Your ${selectedPlan.trial_length}-day trial will start immediately.`;
          alert(message);
          navigate('/instances');
        } else {
          if (response.data.invoice) {
            setSelectedInvoice(response.data.invoice);
            setShowPaymentModal(true);
          } else {
            alert(`Subscription created! Invoice amount: $${selectedPlan.price || '5.00'}`);
            navigate('/billing');
          }
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
    }, 500);

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

    if (subdomain) {
      const instanceName = generateInstanceName(subdomain);
      const dbName = generateDatabaseName(subdomain);

      handleInputChange('name', instanceName);
      handleInputChange('database_name', dbName);
    }
  };

  if (initialLoading) {
    return (
      <div className="min-h-screen bg-warm-50 bg-mesh">
        <Navigation userProfile={profile || undefined} />
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <svg className="animate-spin h-12 w-12 text-primary-600 mx-auto mb-4" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <p className="text-warm-600">Loading plans...</p>
          </div>
        </div>
      </div>
    );
  }


  return (
    <div className="min-h-screen bg-warm-50 bg-mesh">
      <Navigation userProfile={profile || undefined} />

      <main className="max-w-4xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-2">
            <div className="w-10 h-10 bg-primary-100 rounded-xl flex items-center justify-center">
              <svg className="w-5 h-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-warm-900">Create New Instance</h1>
          </div>
          <p className="text-warm-500 ml-13">
            Set up a new Odoo ERP instance for your business
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div className="animate-fade-in-down bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl text-sm flex items-start">
              <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          {/* Plan Selection */}
          <div className="card p-6">
            <div className="flex items-center space-x-3 mb-5">
              <div className="w-8 h-8 bg-amber-100 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-warm-900">Select Plan</h3>
            </div>

            {plans.length === 0 ? (
              <div className="text-center py-8">
                <svg className="animate-spin h-8 w-8 text-primary-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <p className="text-warm-500">Loading available plans...</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {plans.map((plan) => {
                  const displayPlan = transformPlanForDisplay(plan, trialEligibility);
                  const isSelected = selectedPlan?.name === plan.name;
                  return (
                    <div
                      key={plan.name}
                      className={`relative rounded-xl border-2 p-4 cursor-pointer transition-all ${
                        isSelected
                          ? 'border-primary-500 bg-primary-50 shadow-md'
                          : 'border-warm-200 hover:border-warm-300 hover:bg-warm-50'
                      }`}
                      onClick={() => setSelectedPlan(plan)}
                    >
                      {/* Selected indicator */}
                      {isSelected && (
                        <div className="absolute top-3 right-3 w-6 h-6 bg-primary-500 rounded-full flex items-center justify-center">
                          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      )}

                      <div className="pr-8">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="font-semibold text-warm-900">{displayPlan.product}</h4>
                          {displayPlan.display_trial && (
                            <span className="badge badge-success text-xs">
                              {displayPlan.trial_length}-day trial
                            </span>
                          )}
                        </div>

                        <p className="text-sm text-warm-500 mb-3 line-clamp-2">
                          {plan.description}
                        </p>

                        {/* Resources */}
                        {plan.cpu_limit && (
                          <div className="space-y-1.5 mb-3">
                            <div className="text-xs text-warm-600 flex items-center">
                              <svg className="w-3.5 h-3.5 mr-1.5 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                              </svg>
                              {plan.cpu_limit} CPU • {plan.memory_limit} RAM • {plan.storage_limit}
                            </div>
                          </div>
                        )}

                        {/* Pricing */}
                        <div className="pt-2 border-t border-warm-200">
                          {displayPlan.display_trial && displayPlan.price === 0 ? (
                            <span className="text-lg font-bold text-emerald-600">Free Trial</span>
                          ) : displayPlan.display_trial ? (
                            <div>
                              <span className="text-sm text-emerald-600 font-medium">$0 for {displayPlan.trial_length} days</span>
                              <span className="block text-lg font-bold text-warm-900">
                                then ${plan.price}/{plan.billing_period.toLowerCase()}
                              </span>
                            </div>
                          ) : (
                            <span className="text-lg font-bold text-warm-900">
                              ${plan.price}<span className="text-sm font-normal text-warm-500">/{plan.billing_period.toLowerCase()}</span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Trial/Payment Choice */}
            {selectedPlan && trialEligibility?.can_show_trial_info && selectedPlan.trial_length > 0 && (
              <div className="mt-5 p-4 bg-warm-50 rounded-xl border border-warm-200">
                <h4 className="text-sm font-semibold text-warm-900 mb-3">Billing Options</h4>
                <div className="space-y-3">
                  <label className={`flex items-start p-3 rounded-lg border-2 cursor-pointer transition-all ${
                    phaseType === 'TRIAL' ? 'border-primary-500 bg-primary-50' : 'border-warm-200 hover:border-warm-300'
                  }`}>
                    <input
                      type="radio"
                      name="phaseOption"
                      checked={phaseType === 'TRIAL'}
                      onChange={() => setPhaseType('TRIAL')}
                      className="mt-0.5 h-4 w-4 text-primary-600 focus:ring-primary-500 border-warm-300"
                    />
                    <div className="ml-3">
                      <span className="block text-sm font-medium text-warm-900">
                        Start with {selectedPlan.trial_length}-day free trial
                      </span>
                      <span className="block text-xs text-warm-500 mt-0.5">
                        No payment required now. You'll be charged ${selectedPlan.price} after the trial ends.
                      </span>
                    </div>
                  </label>

                  <label className={`flex items-start p-3 rounded-lg border-2 cursor-pointer transition-all ${
                    phaseType === 'EVERGREEN' ? 'border-primary-500 bg-primary-50' : 'border-warm-200 hover:border-warm-300'
                  }`}>
                    <input
                      type="radio"
                      name="phaseOption"
                      checked={phaseType === 'EVERGREEN'}
                      onChange={() => setPhaseType('EVERGREEN')}
                      className="mt-0.5 h-4 w-4 text-primary-600 focus:ring-primary-500 border-warm-300"
                    />
                    <div className="ml-3">
                      <span className="block text-sm font-medium text-warm-900">
                        Skip trial, start paid subscription immediately
                      </span>
                      <span className="block text-xs text-warm-500 mt-0.5">
                        You'll be charged ${selectedPlan.price} immediately to activate your instance.
                      </span>
                    </div>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* Instance Information */}
          <div className="card p-6">
            <div className="flex items-center space-x-3 mb-5">
              <div className="w-8 h-8 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-warm-900">Instance Information</h3>
            </div>

            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-warm-700 mb-2">
                  Subdomain *
                </label>
                <div className="flex">
                  <div className="relative flex-1">
                    <div className="input-icon">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <input
                      type="text"
                      required
                      value={formData.subdomain || ''}
                      onChange={(e) => handleSubdomainChange(e.target.value)}
                      className={`input-field input-with-icon rounded-r-none ${
                        subdomainStatus.available === false ? 'border-rose-300 focus:border-rose-500 focus:ring-rose-500' :
                        subdomainStatus.available === true ? 'border-emerald-300 focus:border-emerald-500 focus:ring-emerald-500' : ''
                      }`}
                      placeholder="my-company"
                      pattern="[a-z0-9-]+"
                      title="Only lowercase letters, numbers, and hyphens allowed"
                      maxLength={30}
                    />
                  </div>
                  <span className="inline-flex items-center px-4 rounded-r-xl border border-l-0 border-warm-300 bg-warm-100 text-warm-600 text-sm font-medium">
                    .{config?.BASE_DOMAIN || 'saasodoo.local'}
                  </span>
                </div>

                {/* Subdomain availability status */}
                {formData.subdomain && formData.subdomain.length >= 3 && (
                  <div className="mt-2 flex items-center space-x-1.5">
                    {subdomainStatus.checking ? (
                      <>
                        <svg className="animate-spin h-4 w-4 text-warm-400" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span className="text-sm text-warm-500">Checking availability...</span>
                      </>
                    ) : subdomainStatus.available === true ? (
                      <>
                        <svg className="h-4 w-4 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        <span className="text-sm text-emerald-600 font-medium">Available</span>
                      </>
                    ) : subdomainStatus.available === false ? (
                      <>
                        <svg className="h-4 w-4 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                        <span className="text-sm text-rose-600 font-medium">{subdomainStatus.message}</span>
                      </>
                    ) : null}
                  </div>
                )}

                <p className="mt-1.5 text-xs text-warm-500">
                  Your Odoo URL: <span className="font-medium text-warm-700">{formData.subdomain || 'subdomain'}.{config?.BASE_DOMAIN || 'saasodoo.local'}</span>
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-warm-700 mb-2">
                  Description <span className="text-warm-400 font-normal">(Optional)</span>
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
          </div>

          {/* Configuration */}
          <div className="card p-6">
            <div className="flex items-center space-x-3 mb-5">
              <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-warm-900">Configuration</h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm font-medium text-warm-700 mb-2">
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
                <label className="block text-sm font-medium text-warm-700 mb-2">
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

              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-warm-700 mb-2">
                  Admin Email *
                </label>
                <div className="relative">
                  <div className="input-icon">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                    </svg>
                  </div>
                  <input
                    type="email"
                    required
                    value={formData.admin_email}
                    onChange={(e) => handleInputChange('admin_email', e.target.value)}
                    className="input-field input-with-icon"
                    placeholder="admin@company.com"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Resource Allocation - Included with Plan */}
          {selectedPlan && (
            <div className="card p-6">
              <div className="flex items-center space-x-3 mb-5">
                <div className="w-8 h-8 bg-emerald-100 rounded-lg flex items-center justify-center">
                  <svg className="w-4 h-4 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-warm-900">Included Resources</h3>
              </div>

              <div className="bg-gradient-to-br from-primary-50 to-primary-100 rounded-xl p-5 border border-primary-200">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="bg-white/60 backdrop-blur-sm rounded-xl p-4">
                    <div className="text-xs font-medium text-warm-500 uppercase tracking-wide mb-1">
                      CPU Cores
                    </div>
                    <div className="text-2xl font-bold text-primary-700">
                      {formData.cpu_limit}
                    </div>
                  </div>
                  <div className="bg-white/60 backdrop-blur-sm rounded-xl p-4">
                    <div className="text-xs font-medium text-warm-500 uppercase tracking-wide mb-1">
                      Memory
                    </div>
                    <div className="text-2xl font-bold text-primary-700">
                      {formData.memory_limit}
                    </div>
                  </div>
                  <div className="bg-white/60 backdrop-blur-sm rounded-xl p-4">
                    <div className="text-xs font-medium text-warm-500 uppercase tracking-wide mb-1">
                      Storage
                    </div>
                    <div className="text-2xl font-bold text-primary-700">
                      {formData.storage_limit}
                    </div>
                  </div>
                </div>
                <p className="text-xs text-center text-primary-700 mt-4">
                  Included with your <span className="font-semibold">{selectedPlan.product}</span> plan
                </p>
              </div>
            </div>
          )}

          {/* Options */}
          <div className="card p-6">
            <div className="flex items-center space-x-3 mb-5">
              <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-warm-900">Options</h3>
            </div>

            <label className="flex items-center p-3 bg-warm-50 rounded-xl cursor-pointer hover:bg-warm-100 transition-colors">
              <input
                type="checkbox"
                checked={formData.demo_data}
                onChange={(e) => handleInputChange('demo_data', e.target.checked)}
                className="w-4 h-4 text-primary-600 bg-white border-warm-300 rounded focus:ring-primary-500"
              />
              <div className="ml-3">
                <span className="text-sm font-medium text-warm-900">Install demo data</span>
                <span className="block text-xs text-warm-500">Recommended for development and testing</span>
              </div>
            </label>
          </div>

          {/* Submit buttons */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={() => navigate('/instances')}
              className="btn-secondary"
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
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  {selectedPlan && trialEligibility?.can_show_trial_info && selectedPlan.trial_length > 0 && phaseType === 'TRIAL' ? 'Creating Trial...' : 'Creating Subscription...'}
                </span>
              ) : (
                <span className="flex items-center">
                  {selectedPlan
                    ? trialEligibility?.can_show_trial_info && selectedPlan.trial_length > 0 && phaseType === 'TRIAL'
                      ? `Start ${selectedPlan.trial_length}-Day Trial`
                      : `Create Instance - $${selectedPlan.price}/${selectedPlan.billing_period.toLowerCase()}`
                    : 'Select a Plan'}
                  <svg className="w-4 h-4 ml-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </span>
              )}
            </button>
          </div>
        </form>
      </main>

      {/* Payment Modal */}
      {showPaymentModal && selectedInvoice && profile && (
        <PaymentModal
          invoice={selectedInvoice}
          customerEmail={profile.email}
          onClose={() => {
            setShowPaymentModal(false);
            setSelectedInvoice(null);
            navigate('/billing');
          }}
          onSuccess={() => {
            setShowPaymentModal(false);
            setSelectedInvoice(null);
            navigate('/instances');
          }}
        />
      )}
    </div>
  );
};

export default CreateInstance;
