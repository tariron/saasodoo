import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { billingAPI, authAPI } from '../utils/api';
import { Invoice } from '../types/billing';
import Navigation from '../components/Navigation';
import PaymentModal from '../components/PaymentModal';

const BillingInvoices: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalInvoices, setTotalInvoices] = useState(0);
  const [downloadingInvoice, setDownloadingInvoice] = useState<string | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [showPaymentModal, setShowPaymentModal] = useState(false);

  const itemsPerPage = 10;

  useEffect(() => {
    fetchUserProfile();
  }, []);

  useEffect(() => {
    if (customerId) {
      fetchInvoices();
    }
  }, [customerId, currentPage]);

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

  const fetchInvoices = async () => {
    if (!customerId) return;

    try {
      setLoading(true);
      const response = await billingAPI.getInvoices(customerId, currentPage, itemsPerPage);
      setInvoices(response.data.invoices);
      setTotalInvoices(response.data.total);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to load invoices');
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadInvoice = async (invoiceId: string) => {
    setDownloadingInvoice(invoiceId);

    try {
      const response = await billingAPI.downloadInvoice(invoiceId);

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `invoice-${invoiceId}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert('Failed to download invoice. Please try again.');
    } finally {
      setDownloadingInvoice(null);
    }
  };

  const handlePayInvoice = async (invoice: Invoice) => {
    setSelectedInvoice(invoice);
    setShowPaymentModal(true);
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusConfig = (status: string) => {
    switch (status.toLowerCase()) {
      case 'paid':
        return {
          bg: 'bg-emerald-50',
          text: 'text-emerald-700',
          border: 'border-emerald-200',
          dot: 'bg-emerald-500'
        };
      case 'committed':
        return {
          bg: 'bg-amber-50',
          text: 'text-amber-700',
          border: 'border-amber-200',
          dot: 'bg-amber-500'
        };
      case 'draft':
        return {
          bg: 'bg-warm-100',
          text: 'text-warm-600',
          border: 'border-warm-200',
          dot: 'bg-warm-400'
        };
      case 'void':
        return {
          bg: 'bg-rose-50',
          text: 'text-rose-700',
          border: 'border-rose-200',
          dot: 'bg-rose-500'
        };
      case 'written_off':
        return {
          bg: 'bg-purple-50',
          text: 'text-purple-700',
          border: 'border-purple-200',
          dot: 'bg-purple-500'
        };
      default:
        return {
          bg: 'bg-warm-100',
          text: 'text-warm-600',
          border: 'border-warm-200',
          dot: 'bg-warm-400'
        };
    }
  };

  const totalPages = Math.ceil(totalInvoices / itemsPerPage);

  // Loading State
  if (loading && currentPage === 1) {
    return (
      <div className="min-h-screen bg-warm-50 bg-mesh">
        <Navigation userProfile={undefined} />
        <div className="flex flex-col items-center justify-center min-h-[60vh]">
          <div className="relative">
            <div className="w-16 h-16 border-4 border-warm-200 rounded-full"></div>
            <div className="w-16 h-16 border-4 border-primary-500 rounded-full border-t-transparent animate-spin absolute inset-0"></div>
          </div>
          <p className="mt-4 text-warm-600 font-medium">Loading invoices...</p>
        </div>
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div className="min-h-screen bg-warm-50 bg-mesh">
        <Navigation userProfile={profile || undefined} />
        <div className="max-w-lg mx-auto px-4 py-16">
          <div className="card p-8 text-center">
            <div className="w-16 h-16 bg-rose-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-rose-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-warm-900 mb-2">Unable to Load Invoices</h3>
            <p className="text-warm-600 mb-6">{error}</p>
            <button
              onClick={() => window.location.reload()}
              className="btn-primary"
            >
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Try Again
            </button>
          </div>
        </div>
      </div>
    );
  }

  const paidCount = invoices.filter(inv => inv.status === 'PAID').length;
  const outstandingCount = invoices.filter(inv => inv.status === 'COMMITTED').length;
  const totalBalance = invoices.reduce((sum, inv) => sum + inv.balance, 0);

  return (
    <div className="min-h-screen bg-warm-50 bg-mesh">
      <Navigation userProfile={profile || undefined} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="mb-8 animate-fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold text-warm-900">Invoices</h1>
              <p className="mt-1 text-warm-600">View and manage your billing history</p>
            </div>
            <Link
              to="/billing"
              className="btn-secondary inline-flex items-center self-start"
            >
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
              </svg>
              Back to Billing
            </Link>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8 animate-fade-in-up" style={{ animationDelay: '50ms' }}>
          {/* Total Invoices */}
          <div className="card p-5 group hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-warm-500 mb-1">Total Invoices</p>
                <p className="text-2xl font-bold text-warm-900">{totalInvoices}</p>
              </div>
              <div className="w-12 h-12 bg-primary-100 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
            </div>
          </div>

          {/* Paid */}
          <div className="card p-5 group hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-warm-500 mb-1">Paid</p>
                <p className="text-2xl font-bold text-emerald-600">{paidCount}</p>
              </div>
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          {/* Outstanding */}
          <div className="card p-5 group hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-warm-500 mb-1">Outstanding</p>
                <p className="text-2xl font-bold text-amber-600">{outstandingCount}</p>
              </div>
              <div className="w-12 h-12 bg-amber-100 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          {/* Total Balance */}
          <div className="card p-5 group hover:shadow-lg transition-shadow">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-warm-500 mb-1">Balance Due</p>
                <p className="text-2xl font-bold text-purple-600">{formatCurrency(totalBalance)}</p>
              </div>
              <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        {/* Invoice Table Card */}
        <div className="card overflow-hidden animate-fade-in-up" style={{ animationDelay: '100ms' }}>
          {/* Table Header */}
          <div className="px-6 py-4 border-b border-warm-100 bg-warm-50/50">
            <div className="flex items-center space-x-3">
              <div className="w-8 h-8 bg-primary-100 rounded-lg flex items-center justify-center">
                <svg className="w-4 h-4 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
              </div>
              <h2 className="text-lg font-semibold text-warm-900">Invoice History</h2>
            </div>
          </div>

          {invoices.length > 0 ? (
            <>
              {/* Desktop Table */}
              <div className="hidden md:block overflow-x-auto">
                <table className="min-w-full">
                  <thead>
                    <tr className="bg-warm-50/80">
                      <th className="px-6 py-3 text-left text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Invoice
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Date
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Amount
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Balance
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-warm-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-warm-100">
                    {invoices.map((invoice, index) => {
                      const statusConfig = getStatusConfig(invoice.status);
                      return (
                        <tr
                          key={invoice.id}
                          className="hover:bg-warm-50/50 transition-colors animate-fade-in"
                          style={{ animationDelay: `${index * 30}ms` }}
                        >
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="flex items-center">
                              <div className="w-8 h-8 bg-warm-100 rounded-lg flex items-center justify-center mr-3">
                                <svg className="w-4 h-4 text-warm-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                </svg>
                              </div>
                              <span className="text-sm font-medium text-warm-900">#{invoice.invoice_number}</span>
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-warm-600">
                            {formatDate(invoice.invoice_date)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-warm-900">
                            {formatCurrency(invoice.amount, invoice.currency)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-warm-600">
                            {invoice.balance > 0 ? (
                              <span className="font-medium text-amber-600">
                                {formatCurrency(invoice.balance, invoice.currency)}
                              </span>
                            ) : (
                              <span className="text-warm-400">—</span>
                            )}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${statusConfig.bg} ${statusConfig.text} border ${statusConfig.border}`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${statusConfig.dot} mr-1.5`}></span>
                              {invoice.status}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right">
                            <div className="flex items-center justify-end space-x-2">
                              <button
                                onClick={() => handleDownloadInvoice(invoice.id)}
                                disabled={downloadingInvoice === invoice.id}
                                className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-warm-600 hover:text-warm-900 hover:bg-warm-100 rounded-lg transition-colors disabled:opacity-50"
                              >
                                {downloadingInvoice === invoice.id ? (
                                  <svg className="animate-spin w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24">
                                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                  </svg>
                                ) : (
                                  <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                  </svg>
                                )}
                                PDF
                              </button>

                              {invoice.status === 'COMMITTED' && invoice.balance > 0 && (
                                <button
                                  onClick={() => handlePayInvoice(invoice)}
                                  className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
                                >
                                  <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                                  </svg>
                                  Pay
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile Cards */}
              <div className="md:hidden divide-y divide-warm-100">
                {invoices.map((invoice, index) => {
                  const statusConfig = getStatusConfig(invoice.status);
                  return (
                    <div
                      key={invoice.id}
                      className="p-4 animate-fade-in"
                      style={{ animationDelay: `${index * 30}ms` }}
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div className="flex items-center">
                          <div className="w-10 h-10 bg-warm-100 rounded-lg flex items-center justify-center mr-3">
                            <svg className="w-5 h-5 text-warm-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                            </svg>
                          </div>
                          <div>
                            <p className="font-medium text-warm-900">#{invoice.invoice_number}</p>
                            <p className="text-sm text-warm-500">{formatDate(invoice.invoice_date)}</p>
                          </div>
                        </div>
                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${statusConfig.bg} ${statusConfig.text}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${statusConfig.dot} mr-1`}></span>
                          {invoice.status}
                        </span>
                      </div>

                      <div className="flex items-center justify-between mb-3">
                        <div>
                          <p className="text-xs text-warm-500 uppercase">Amount</p>
                          <p className="font-semibold text-warm-900">{formatCurrency(invoice.amount, invoice.currency)}</p>
                        </div>
                        {invoice.balance > 0 && (
                          <div className="text-right">
                            <p className="text-xs text-warm-500 uppercase">Balance</p>
                            <p className="font-semibold text-amber-600">{formatCurrency(invoice.balance, invoice.currency)}</p>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleDownloadInvoice(invoice.id)}
                          disabled={downloadingInvoice === invoice.id}
                          className="flex-1 btn-secondary py-2 text-sm"
                        >
                          {downloadingInvoice === invoice.id ? (
                            <span className="flex items-center justify-center">
                              <svg className="animate-spin w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                              </svg>
                              Downloading...
                            </span>
                          ) : (
                            <span className="flex items-center justify-center">
                              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                              </svg>
                              Download PDF
                            </span>
                          )}
                        </button>

                        {invoice.status === 'COMMITTED' && invoice.balance > 0 && (
                          <button
                            onClick={() => handlePayInvoice(invoice)}
                            className="flex-1 btn-primary py-2 text-sm"
                          >
                            <span className="flex items-center justify-center">
                              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                              </svg>
                              Pay Now
                            </span>
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="px-6 py-4 bg-warm-50/50 border-t border-warm-100">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                    <p className="text-sm text-warm-600">
                      Showing <span className="font-medium text-warm-900">{(currentPage - 1) * itemsPerPage + 1}</span> to{' '}
                      <span className="font-medium text-warm-900">{Math.min(currentPage * itemsPerPage, totalInvoices)}</span> of{' '}
                      <span className="font-medium text-warm-900">{totalInvoices}</span> invoices
                    </p>

                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                        disabled={currentPage === 1 || loading}
                        className="p-2 rounded-lg border border-warm-200 text-warm-600 hover:bg-warm-100 hover:text-warm-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                        </svg>
                      </button>

                      <div className="hidden sm:flex items-center space-x-1">
                        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                          const pageNum = Math.max(1, Math.min(totalPages - 4, currentPage - 2)) + i;
                          if (pageNum <= totalPages) {
                            return (
                              <button
                                key={pageNum}
                                onClick={() => setCurrentPage(pageNum)}
                                className={`w-10 h-10 rounded-lg text-sm font-medium transition-colors ${
                                  pageNum === currentPage
                                    ? 'bg-primary-600 text-white'
                                    : 'text-warm-600 hover:bg-warm-100 hover:text-warm-900'
                                }`}
                              >
                                {pageNum}
                              </button>
                            );
                          }
                          return null;
                        })}
                      </div>

                      <span className="sm:hidden text-sm text-warm-600">
                        Page {currentPage} of {totalPages}
                      </span>

                      <button
                        onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                        disabled={currentPage === totalPages || loading}
                        className="p-2 rounded-lg border border-warm-200 text-warm-600 hover:bg-warm-100 hover:text-warm-900 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            /* Empty State */
            <div className="text-center py-16 px-6">
              <div className="w-20 h-20 bg-warm-100 rounded-2xl flex items-center justify-center mx-auto mb-6">
                <svg className="w-10 h-10 text-warm-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-warm-900 mb-2">No invoices yet</h3>
              <p className="text-warm-600 max-w-sm mx-auto mb-6">
                Your invoices will appear here once you have active subscriptions.
              </p>
              <Link to="/instances" className="btn-primary inline-flex items-center">
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Create an Instance
              </Link>
            </div>
          )}
        </div>
      </div>

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
            fetchInvoices();
          }}
        />
      )}
    </div>
  );
};

export default BillingInvoices;
