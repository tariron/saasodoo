import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { instanceAPI, billingAPI, CreateInstanceRequest, CreateInstanceWithSubscriptionRequest, getErrorMessage } from '../utils/api';
import { Plan, Invoice, TrialEligibilityResponse, BillingPeriod, BILLING_PERIOD_LABELS, BILLING_PERIOD_MONTHS, BILLING_PERIOD_SHORT } from '../types/billing';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';
import { useConfig } from '../hooks/useConfig';
import { useUser } from '../contexts/UserContext';
import { useAbortController, isAbortError } from '../hooks/useAbortController';

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

/**
 * Calculate monthly equivalent price for a plan
 */
const getMonthlyEquivalent = (plan: Plan): number => {
  const months = BILLING_PERIOD_MONTHS[plan.billing_period as BillingPeriod] || 1;
  return plan.price ? plan.price / months : 0;
};

/**
 * Calculate savings percentage compared to monthly
 */
const getSavingsPercent = (plan: Plan, monthlyPrice: number): number => {
  if (!monthlyPrice || !plan.price) return 0;
  const monthlyEquiv = getMonthlyEquivalent(plan);
  const savings = Math.round((1 - monthlyEquiv / monthlyPrice) * 100);
  return savings > 0 ? savings : 0;
};

/**
 * Get the base monthly price for a product
 */
const getBaseMonthlyPrice = (plans: Plan[], productName: string): number => {
  const monthlyPlan = plans.find(p => p.product === productName && p.billing_period === 'MONTHLY');
  return monthlyPlan?.price || 0;
};

const CreateInstance: React.FC = () => {
  const { config } = useConfig();
  const { profile, loading: profileLoading } = useUser();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [selectedBillingPeriod, setSelectedBillingPeriod] = useState<BillingPeriod>('MONTHLY');
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
  const { getSignal, isAborted } = useAbortController();

  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  // Filter plans by selected billing period
  const filteredPlans = useMemo(() => {
    return plans.filter(plan => plan.billing_period === selectedBillingPeriod);
  }, [plans, selectedBillingPeriod]);

  // Get unique products for display
  const uniqueProducts = useMemo(() => {
    const products = new Set(plans.map(p => p.product));
    return Array.from(products);
  }, [plans]);

  // Update form data when profile is loaded from context
  useEffect(() => {
    if (profile) {
      setFormData(prev => ({
        ...prev,
        customer_id: profile.id,
        admin_email: profile.email
      }));
    }
  }, [profile]);

  // Fetch plans and trial eligibility when profile is available
  useEffect(() => {
    const fetchInitialData = async () => {
      if (!profile?.id) return;

      try {
        const plansResponse = await billingAPI.getPlans();

        if (isAborted()) return;

        if (plansResponse.data.success) {
          setPlans(plansResponse.data.plans);
          // Select the first monthly plan (Basic with trial)
          const basicMonthly = plansResponse.data.plans.find(
            plan => plan.product === 'Basic' && plan.billing_period === 'MONTHLY'
          );
          if (basicMonthly) {
            setSelectedPlan(basicMonthly);
          } else if (plansResponse.data.plans.length > 0) {
            setSelectedPlan(plansResponse.data.plans[0]);
          }
        }

        // Fetch trial eligibility
        try {
          const eligibilityResponse = await billingAPI.getTrialEligibility(profile.id);
          if (!isAborted()) {
            setTrialEligibility(eligibilityResponse.data);
          }
        } catch (eligibilityError: unknown) {
          if (isAbortError(eligibilityError)) return;
          // Fail closed - deny trials on error
          if (!isAborted()) {
            setTrialEligibility({
              eligible: false,
              can_show_trial_info: false,
              trial_days: 0,
              has_active_subscriptions: false,
              subscription_count: 0,
              reason: 'system_error'
            });
          }
        }
      } catch (err: unknown) {
        if (isAbortError(err)) return;
        if (!isAborted()) {
          setError(getErrorMessage(err, 'Failed to load plans'));
        }
      } finally {
        if (!isAborted()) {
          setInitialLoading(false);
        }
      }
    };

    if (profile?.id) {
      fetchInitialData();
    }
  }, [profile?.id, getSignal, isAborted]);

  // Update selected plan when billing period changes
  useEffect(() => {
    if (selectedPlan && plans.length > 0) {
      // Find the same product with the new billing period
      const newPlan = plans.find(
        p => p.product === selectedPlan.product && p.billing_period === selectedBillingPeriod
      );
      if (newPlan) {
        setSelectedPlan(newPlan);
      }
    }
  }, [selectedBillingPeriod, plans]);

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
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to create instance'));
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (field: keyof CreateInstanceRequest, value: CreateInstanceRequest[keyof CreateInstanceRequest]) => {
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
      } catch (error: unknown) {
        setSubdomainStatus({
          checking: false,
          available: false,
          message: getErrorMessage(error, 'Error checking subdomain')
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

  // Show loading while profile is loading or plans are being fetched
  const isLoading = profileLoading || (profile && initialLoading);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-warm-50 bg-mesh">
        <Navigation userProfile={profile ?? undefined} />
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
      <Navigation userProfile={profile ?? undefined} />

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

            {/* Billing Period Toggle */}
            <div className="mb-6">
              <div className="flex justify-center">
                <div className="inline-flex p-1 bg-warm-100 rounded-xl">
                  {(['MONTHLY', 'QUARTERLY', 'BIANNUAL', 'ANNUAL'] as BillingPeriod[]).map((period, index) => {
                    const isSelected = selectedBillingPeriod === period;
                    const isAnnual = period === 'ANNUAL';
                    return (
                      <button
                        key={period}
                        type="button"
                        onClick={() => setSelectedBillingPeriod(period)}
                        className={`
                          relative px-4 py-2.5 text-sm font-medium rounded-lg transition-all duration-200
                          ${isSelected
                            ? 'bg-white text-primary-700 shadow-md'
                            : 'text-warm-600 hover:text-warm-900 hover:bg-warm-50'
                          }
                          ${index === 0 ? 'rounded-l-lg' : ''}
                          ${index === 3 ? 'rounded-r-lg' : ''}
                        `}
                        style={{ animationDelay: `${index * 50}ms` }}
                      >
                        <span className="relative z-10">{BILLING_PERIOD_LABELS[period]}</span>
                        {isAnnual && (
                          <span className={`
                            ml-1.5 px-1.5 py-0.5 text-[10px] font-bold rounded-md
                            ${isSelected
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-emerald-50 text-emerald-600'
                            }
                          `}>
                            SAVE 20%
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Period description */}
              <p className="text-center text-xs text-warm-500 mt-3">
                {selectedBillingPeriod === 'MONTHLY' && 'Pay monthly with maximum flexibility'}
                {selectedBillingPeriod === 'QUARTERLY' && 'Pay every 3 months and save ~10%'}
                {selectedBillingPeriod === 'BIANNUAL' && 'Pay every 6 months and save ~15%'}
                {selectedBillingPeriod === 'ANNUAL' && 'Pay yearly for the best value — save up to 20%'}
              </p>
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
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {filteredPlans.map((plan, index) => {
                  const displayPlan = transformPlanForDisplay(plan, trialEligibility);
                  const isSelected = selectedPlan?.name === plan.name;
                  const baseMonthlyPrice = getBaseMonthlyPrice(plans, plan.product);
                  const savings = getSavingsPercent(plan, baseMonthlyPrice);
                  const monthlyEquiv = getMonthlyEquivalent(plan);
                  const hasTrial = displayPlan.display_trial && displayPlan.trial_length > 0;

                  // Determine tier styling
                  const isBasic = plan.product === 'Basic';
                  const isStandard = plan.product === 'Standard';
                  const isPremium = plan.product === 'Premium';

                  return (
                    <div
                      key={plan.name}
                      className={`
                        relative rounded-2xl border-2 p-5 cursor-pointer transition-all duration-300
                        ${isSelected
                          ? 'border-primary-500 bg-gradient-to-b from-primary-50 to-white shadow-lg scale-[1.02]'
                          : 'border-warm-200 hover:border-primary-300 hover:bg-warm-50/50 hover:shadow-md'
                        }
                        ${isPremium && !isSelected ? 'bg-gradient-to-b from-amber-50/30 to-white' : ''}
                      `}
                      onClick={() => setSelectedPlan(plan)}
                      style={{ animationDelay: `${index * 100}ms` }}
                    >
                      {/* Savings badge */}
                      {savings > 0 && (
                        <div className="absolute -top-2.5 -right-2 z-10">
                          <div className="bg-gradient-to-r from-emerald-500 to-emerald-400 text-white text-[10px] font-bold px-2.5 py-1 rounded-full shadow-md">
                            SAVE {savings}%
                          </div>
                        </div>
                      )}

                      {/* Trial badge - only for Basic Monthly */}
                      {hasTrial && (
                        <div className="absolute -top-2.5 left-3 z-10">
                          <div className="bg-gradient-to-r from-primary-500 to-primary-400 text-white text-[10px] font-bold px-2.5 py-1 rounded-full shadow-md flex items-center">
                            <svg className="w-3 h-3 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {displayPlan.trial_length}-DAY TRIAL
                          </div>
                        </div>
                      )}

                      {/* Selected indicator */}
                      {isSelected && (
                        <div className="absolute top-3 right-3 w-6 h-6 bg-primary-500 rounded-full flex items-center justify-center shadow-md">
                          <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                          </svg>
                        </div>
                      )}

                      <div className={`${hasTrial || savings > 0 ? 'pt-3' : ''}`}>
                        {/* Plan name with tier indicator */}
                        <div className="flex items-center gap-2 mb-2">
                          <div className={`
                            w-8 h-8 rounded-lg flex items-center justify-center
                            ${isBasic ? 'bg-warm-100' : ''}
                            ${isStandard ? 'bg-primary-100' : ''}
                            ${isPremium ? 'bg-amber-100' : ''}
                          `}>
                            {isBasic && (
                              <svg className="w-4 h-4 text-warm-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                              </svg>
                            )}
                            {isStandard && (
                              <svg className="w-4 h-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                              </svg>
                            )}
                            {isPremium && (
                              <svg className="w-4 h-4 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 3l3.5 6L12 3l3.5 6L19 3v12a2 2 0 01-2 2H7a2 2 0 01-2-2V3z" />
                              </svg>
                            )}
                          </div>
                          <h4 className="font-bold text-warm-900 text-lg">{plan.product}</h4>
                        </div>

                        <p className="text-sm text-warm-500 mb-4 line-clamp-2 min-h-[40px]">
                          {plan.description || `${plan.product} tier with dedicated resources`}
                        </p>

                        {/* Resources */}
                        {plan.cpu_limit && (
                          <div className="space-y-2 mb-4 p-3 bg-warm-50 rounded-xl">
                            <div className="flex items-center text-xs text-warm-600">
                              <svg className="w-3.5 h-3.5 mr-2 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
                              </svg>
                              <span className="font-medium">{plan.cpu_limit} CPU</span>
                            </div>
                            <div className="flex items-center text-xs text-warm-600">
                              <svg className="w-3.5 h-3.5 mr-2 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                              </svg>
                              <span className="font-medium">{plan.memory_limit} RAM</span>
                            </div>
                            <div className="flex items-center text-xs text-warm-600">
                              <svg className="w-3.5 h-3.5 mr-2 text-primary-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                              </svg>
                              <span className="font-medium">{plan.storage_limit} Storage</span>
                            </div>
                          </div>
                        )}

                        {/* Pricing */}
                        <div className="pt-3 border-t border-warm-200">
                          {hasTrial && trialEligibility?.can_show_trial_info ? (
                            <div>
                              <div className="flex items-baseline gap-1">
                                <span className="text-2xl font-bold text-emerald-600">$0</span>
                                <span className="text-sm text-warm-500">for {displayPlan.trial_length} days</span>
                              </div>
                              <div className="text-sm text-warm-600 mt-1">
                                then <span className="font-semibold text-warm-900">${plan.price}</span>
                                <span className="text-warm-500">{BILLING_PERIOD_SHORT[selectedBillingPeriod]}</span>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div className="flex items-baseline gap-1">
                                <span className="text-2xl font-bold text-warm-900">${plan.price}</span>
                                <span className="text-sm text-warm-500">{BILLING_PERIOD_SHORT[selectedBillingPeriod]}</span>
                              </div>
                              {selectedBillingPeriod !== 'MONTHLY' && (
                                <div className="text-xs text-warm-500 mt-1">
                                  ${monthlyEquiv.toFixed(2)}/mo equivalent
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Trial/Payment Choice - Only show for plans with trial */}
            {selectedPlan && trialEligibility?.can_show_trial_info && selectedPlan.trial_length > 0 && (
              <div className="mt-6 p-4 bg-gradient-to-br from-primary-50 to-warm-50 rounded-xl border border-primary-100">
                <h4 className="text-sm font-semibold text-warm-900 mb-3 flex items-center">
                  <svg className="w-4 h-4 mr-2 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  How would you like to start?
                </h4>
                <div className="space-y-3">
                  <label className={`flex items-start p-3 rounded-xl border-2 cursor-pointer transition-all ${
                    phaseType === 'TRIAL' ? 'border-primary-500 bg-white shadow-sm' : 'border-warm-200 hover:border-warm-300 bg-white/50'
                  }`}>
                    <input
                      type="radio"
                      name="phaseOption"
                      checked={phaseType === 'TRIAL'}
                      onChange={() => setPhaseType('TRIAL')}
                      className="mt-0.5 h-4 w-4 text-primary-600 focus:ring-primary-500 border-warm-300"
                    />
                    <div className="ml-3">
                      <span className="block text-sm font-semibold text-warm-900">
                        Start with {selectedPlan.trial_length}-day free trial
                      </span>
                      <span className="block text-xs text-warm-500 mt-0.5">
                        No payment required now. You'll be charged ${selectedPlan.price} after the trial ends.
                      </span>
                    </div>
                  </label>

                  <label className={`flex items-start p-3 rounded-xl border-2 cursor-pointer transition-all ${
                    phaseType === 'EVERGREEN' ? 'border-primary-500 bg-white shadow-sm' : 'border-warm-200 hover:border-warm-300 bg-white/50'
                  }`}>
                    <input
                      type="radio"
                      name="phaseOption"
                      checked={phaseType === 'EVERGREEN'}
                      onChange={() => setPhaseType('EVERGREEN')}
                      className="mt-0.5 h-4 w-4 text-primary-600 focus:ring-primary-500 border-warm-300"
                    />
                    <div className="ml-3">
                      <span className="block text-sm font-semibold text-warm-900">
                        Skip trial, start paid subscription
                      </span>
                      <span className="block text-xs text-warm-500 mt-0.5">
                        Pay ${selectedPlan.price} now to activate your instance immediately.
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
                  onChange={(e) => handleInputChange('instance_type', e.target.value as 'development' | 'staging' | 'production')}
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
                      : `Create Instance — $${selectedPlan.price}${BILLING_PERIOD_SHORT[selectedBillingPeriod]}`
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
            navigate('/instances', { state: { fromPayment: true } });
          }}
        />
      )}
    </div>
  );
};

export default CreateInstance;
