import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { billingAPI, authAPI, UserProfile } from '../utils/api';
import { BillingOverview, Subscription, Invoice, OutstandingInvoice } from '../types/billing';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';

const Billing: React.FC = () => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [billingData, setBillingData] = useState<BillingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);

  useEffect(() => {
    fetchUserProfile();
  }, []);

  useEffect(() => {
    if (customerId) {
      fetchBillingData();
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

  const fetchBillingData = async () => {
    if (!customerId) return;
    try {
      setLoading(true);
      const response = await billingAPI.getBillingOverview(customerId);
      setBillingData(response.data.data);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to load billing information');
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const handlePayInvoice = (invoice: OutstandingInvoice) => {
    const fullInvoice: Invoice = {
      id: invoice.id,
      invoice_number: invoice.invoice_number,
      invoice_date: invoice.invoice_date,
      amount: invoice.amount,
      balance: invoice.balance,
      currency: invoice.currency,
      status: invoice.status as 'DRAFT' | 'COMMITTED' | 'PAID' | 'VOID' | 'WRITTEN_OFF',
      account_id: '',
      target_date: invoice.invoice_date,
      credit_adj: 0,
      refund_adj: 0,
      created_at: invoice.invoice_date,
      updated_at: invoice.invoice_date,
    };
    setSelectedInvoice(fullInvoice);
    setShowPaymentModal(true);
  };

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
            <p className="mt-4 text-warm-600 font-medium">Loading billing data...</p>
          </div>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center bg-warm-50">
          <div className="card p-8 max-w-md text-center animate-fade-in">
            <div className="w-16 h-16 bg-rose-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-warm-900 mb-2">Error Loading Data</h2>
            <p className="text-warm-500">{error}</p>
          </div>
        </div>
      </>
    );
  }

  if (!billingData) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center bg-warm-50">
          <div className="card p-12 text-center animate-fade-in">
            <div className="w-20 h-20 bg-warm-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-warm-900 mb-2">No Billing Data</h2>
            <p className="text-warm-500">No billing information found for your account.</p>
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
          {/* Header */}
          <div className="mb-8 animate-fade-in">
            <h1 className="text-3xl font-bold text-warm-900">Billing & Subscriptions</h1>
            <p className="mt-2 text-warm-500">Manage your billing information and subscriptions</p>
          </div>

          {/* Account Overview Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 animate-fade-in-up">
            <div className="stat-card">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-primary-500 to-primary-600 rounded-xl flex items-center justify-center shadow-glow">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <span className="badge badge-info">Balance</span>
              </div>
              <div className="text-3xl font-bold text-warm-900">{formatCurrency(billingData.account_balance)}</div>
              <div className="text-sm text-warm-500">Account Balance</div>
            </div>

            <div className="stat-card animation-delay-100">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z" />
                  </svg>
                </div>
                <span className="badge badge-success">Active</span>
              </div>
              <div className="text-3xl font-bold text-warm-900">{billingData.active_subscriptions.length}</div>
              <div className="text-sm text-warm-500">Active Subscriptions</div>
            </div>

            <div className="stat-card animation-delay-200">
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 bg-gradient-to-br from-accent-500 to-accent-600 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                </div>
                <span className="badge badge-warning">Next</span>
              </div>
              <div className="text-3xl font-bold text-warm-900">
                {billingData.next_billing_amount ? formatCurrency(billingData.next_billing_amount) : 'N/A'}
              </div>
              <div className="text-sm text-warm-500">Next Billing</div>
            </div>
          </div>

          {/* Trial Information */}
          {billingData.trial_info?.is_trial && (
            <div className="mb-8 animate-fade-in-up animation-delay-300">
              <div className="relative overflow-hidden bg-gradient-to-r from-amber-50 via-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-6">
                <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-amber-400/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/2"></div>
                <div className="relative flex items-center">
                  <div className="w-14 h-14 bg-gradient-to-br from-amber-400 to-amber-500 rounded-xl flex items-center justify-center mr-5 shadow-lg">
                    <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-amber-900">Trial Period Active</h3>
                    <p className="text-amber-700">
                      Your trial ends on <strong>{formatDate(billingData.trial_info.trial_end_date!)}</strong> ({billingData.trial_info.days_remaining} days remaining)
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Payment Required Section */}
          {(billingData.pending_subscriptions.length > 0 || billingData.outstanding_invoices.length > 0 || billingData.total_outstanding > 0) && (
            <div className="mb-8 animate-fade-in-up animation-delay-300">
              <div className="relative overflow-hidden bg-gradient-to-r from-rose-50 via-rose-50 to-red-50 border border-rose-200 rounded-2xl p-6">
                <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-rose-400/10 to-transparent rounded-full -translate-y-1/2 translate-x-1/2"></div>
                <div className="relative">
                  <div className="flex items-center mb-6">
                    <div className="w-14 h-14 bg-gradient-to-br from-rose-500 to-rose-600 rounded-xl flex items-center justify-center mr-5 shadow-lg">
                      <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-lg font-semibold text-rose-900">Payment Required</h3>
                      <p className="text-rose-700">You have pending subscriptions or outstanding invoices.</p>
                    </div>
                  </div>

                  {/* Outstanding Balance */}
                  {billingData.total_outstanding > 0 && (
                    <div className="bg-white/80 backdrop-blur rounded-xl p-4 mb-4">
                      <div className="text-sm font-medium text-warm-600">Total Outstanding Balance</div>
                      <div className="text-2xl font-bold text-rose-600">{formatCurrency(billingData.total_outstanding)}</div>
                    </div>
                  )}

                  {/* Outstanding Invoices */}
                  {billingData.outstanding_invoices.length > 0 && (
                    <div className="bg-white rounded-xl overflow-hidden">
                      <div className="px-4 py-3 bg-warm-50 border-b border-warm-100">
                        <h4 className="font-semibold text-warm-900">Outstanding Invoices ({billingData.outstanding_invoices.length})</h4>
                      </div>
                      <div className="divide-y divide-warm-100">
                        {billingData.outstanding_invoices.map((invoice) => (
                          <div key={invoice.id} className="p-4 hover:bg-warm-50/50 transition-colors">
                            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                              <div className="flex-1">
                                <div className="font-medium text-warm-900 text-sm sm:text-base">{invoice.invoice_number}</div>
                                <div className="text-xs sm:text-sm text-warm-500">{formatDate(invoice.invoice_date)}</div>
                              </div>
                              <div className="flex items-center justify-between sm:justify-end gap-3 sm:gap-4">
                                <div className="sm:text-right">
                                  <div className="text-xs sm:text-sm text-warm-500">Balance Due</div>
                                  <div className="font-semibold text-rose-600">{formatCurrency(invoice.balance)}</div>
                                </div>
                                <button
                                  onClick={() => handlePayInvoice(invoice)}
                                  className="btn-primary py-1.5 px-4 text-sm flex-shrink-0"
                                >
                                  Pay Now
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Blocked Instances */}
                  {billingData.provisioning_blocked_instances.length > 0 && (
                    <div className="mt-4 bg-rose-100/50 rounded-xl p-4">
                      <div className="flex items-start">
                        <svg className="w-5 h-5 text-rose-600 mr-2 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <div>
                          <h4 className="font-medium text-rose-900">{billingData.provisioning_blocked_instances.length} Instance(s) Waiting</h4>
                          <p className="text-sm text-rose-700">Complete payment to provision your instances.</p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Instance Billing Overview */}
          <div className="card mb-8 animate-fade-in-up animation-delay-400">
            <div className="p-6 border-b border-warm-100">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-warm-900">Instance Billing</h2>
                <Link to="/instances/create" className="link text-sm flex items-center">
                  Create Instance
                  <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </Link>
              </div>
            </div>

            {billingData.customer_instances && billingData.customer_instances.length > 0 ? (
              <div className="divide-y divide-warm-100">
                {billingData.customer_instances.map((instance: any) => {
                  const linkedSubscription = billingData.active_subscriptions.find(
                    (sub: any) => sub.instance_id === instance.id || sub.id === instance.subscription_id
                  );

                  return (
                    <div key={instance.id} className="p-4 sm:p-6 hover:bg-warm-50/50 transition-colors">
                      <div className="flex flex-col gap-4">
                        {/* Instance Info */}
                        <div className="flex items-start space-x-3 sm:space-x-4">
                          <div className="w-12 h-12 sm:w-14 sm:h-14 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center flex-shrink-0">
                            <span className="text-primary-700 font-bold text-lg sm:text-xl">{instance.name[0].toUpperCase()}</span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 mb-1">
                              <h3 className="font-semibold text-warm-900 text-sm sm:text-base truncate">{instance.name}</h3>
                              <span className={`badge text-xs w-fit ${
                                instance.status === 'running' ? 'badge-success' :
                                instance.status === 'paused' ? 'badge-warning' : 'badge-neutral'
                              }`}>
                                {instance.status}
                              </span>
                            </div>
                            <p className="text-xs sm:text-sm text-warm-500 line-clamp-1">{instance.description || 'No description'}</p>
                          </div>
                        </div>

                        {/* Subscription Info */}
                        <div className="flex items-center justify-between gap-3 border-t border-warm-100 pt-3 -mx-4 px-4 sm:mx-0 sm:px-0 sm:border-0 sm:pt-0">
                          {linkedSubscription ? (
                            <div className="flex-1">
                              <div className="font-medium text-warm-900 text-sm">{linkedSubscription.plan_name}</div>
                              <div className="text-xs text-warm-500">{linkedSubscription.billing_period} billing</div>
                              <div className="flex items-center gap-2 mt-1">
                                <span className={`badge text-xs ${
                                  instance.billing_status === 'paid' ? 'badge-success' :
                                  instance.billing_status === 'payment_required' ? 'badge-error' : 'badge-warning'
                                }`}>
                                  {instance.billing_status === 'paid' ? 'Paid' :
                                   instance.billing_status === 'payment_required' ? 'Due' : 'Trial'}
                                </span>
                              </div>
                            </div>
                          ) : (
                            <div className="text-xs sm:text-sm text-warm-500">No subscription</div>
                          )}
                          <Link
                            to={`/billing/instance/${instance.id}`}
                            className="btn-primary py-1.5 sm:py-2 px-3 sm:px-4 text-xs sm:text-sm flex-shrink-0"
                          >
                            Manage
                          </Link>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-12 text-center">
                <div className="w-20 h-20 bg-gradient-to-br from-primary-100 to-primary-200 rounded-2xl flex items-center justify-center mx-auto mb-6">
                  <svg className="w-10 h-10 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                  </svg>
                </div>
                <h3 className="text-xl font-semibold text-warm-900 mb-2">No instances found</h3>
                <p className="text-warm-500 mb-6">Create your first Odoo instance to start billing</p>
                <Link to="/instances/create" className="btn-primary">Create Instance</Link>
              </div>
            )}
          </div>

          {/* Payment Methods */}
          <div className="card mb-8 animate-fade-in-up animation-delay-500">
            <div className="p-6 border-b border-warm-100">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-warm-900">Payment Methods</h2>
                <Link to="/billing/payment" className="link text-sm flex items-center">
                  Manage
                  <svg className="w-4 h-4 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </Link>
              </div>
            </div>

            {billingData.payment_methods.length > 0 ? (
              <div className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {billingData.payment_methods.map((method) => (
                  <div key={method.id} className="border border-warm-200 rounded-xl p-4 hover:border-warm-300 transition-colors">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-warm-100 rounded-lg flex items-center justify-center">
                          <svg className="w-5 h-5 text-warm-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                          </svg>
                        </div>
                        <span className="font-medium text-warm-900">
                          {method.plugin_info.type.replace('_', ' ')}
                        </span>
                      </div>
                      {method.is_default && (
                        <span className="badge badge-info">Default</span>
                      )}
                    </div>
                    {method.plugin_info.last_4 && (
                      <p className="text-sm text-warm-600">•••• {method.plugin_info.last_4}</p>
                    )}
                    {method.plugin_info.exp_month && method.plugin_info.exp_year && (
                      <p className="text-xs text-warm-500 mt-1">
                        Expires {method.plugin_info.exp_month}/{method.plugin_info.exp_year}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-8 text-center">
                <p className="text-warm-500 mb-4">No payment methods on file</p>
                <Link to="/billing/payment" className="btn-secondary">Add Payment Method</Link>
              </div>
            )}
          </div>

          {/* Quick Actions */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 animate-fade-in-up animation-delay-500">
            <Link to="/billing/invoices" className="card p-6 card-hover text-center group">
              <div className="w-14 h-14 bg-gradient-to-br from-primary-100 to-primary-200 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <svg className="w-7 h-7 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="font-semibold text-warm-900 mb-1">View Invoices</h3>
              <p className="text-sm text-warm-500">See all your invoices</p>
            </Link>

            <Link to="/billing/payment" className="card p-6 card-hover text-center group">
              <div className="w-14 h-14 bg-gradient-to-br from-emerald-100 to-emerald-200 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <svg className="w-7 h-7 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                </svg>
              </div>
              <h3 className="font-semibold text-warm-900 mb-1">Payment Methods</h3>
              <p className="text-sm text-warm-500">Manage your cards</p>
            </Link>

            <button className="card p-6 card-hover text-center group">
              <div className="w-14 h-14 bg-gradient-to-br from-accent-100 to-accent-200 rounded-xl flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
                <svg className="w-7 h-7 text-accent-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z" />
                </svg>
              </div>
              <h3 className="font-semibold text-warm-900 mb-1">Contact Support</h3>
              <p className="text-sm text-warm-500">Get help with billing</p>
            </button>
          </div>
        </div>
      </main>

      {/* Payment Modal */}
      {showPaymentModal && selectedInvoice && profile && (
        <PaymentModal
          invoice={selectedInvoice}
          customerEmail={profile.email}
          onClose={() => {
            setShowPaymentModal(false);
            setSelectedInvoice(null);
          }}
          onSuccess={() => {
            window.location.href = '/instances';
          }}
        />
      )}
    </>
  );
};

export default Billing;
