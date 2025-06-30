import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI } from '../utils/api';
import { PaymentMethod, CreatePaymentMethodRequest } from '../types/billing';

const BillingPayment: React.FC = () => {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [billingAccountId, setBillingAccountId] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [formData, setFormData] = useState({
    type: 'CREDIT_CARD' as 'CREDIT_CARD' | 'PAYPAL' | 'BANK_TRANSFER',
    card_number: '',
    exp_month: '',
    exp_year: '',
    cvv: '',
    card_holder_name: '',
    email: '',
    account_name: '',
    routing_number: '',
    account_number: '',
    is_default: false
  });

  useEffect(() => {
    fetchUserProfile();
  }, []);

  useEffect(() => {
    if (customerId) {
      Promise.all([
        fetchPaymentMethods(),
        fetchBillingAccount()
      ]);
    }
  }, [customerId]);

  const fetchUserProfile = async () => {
    try {
      const response = await authAPI.getProfile();
      setCustomerId(response.data.id);
    } catch (err) {
      setError('Failed to load user profile');
      setLoading(false);
    }
  };

  const fetchBillingAccount = async () => {
    if (!customerId) return;
    
    try {
      const response = await billingAPI.getAccount(customerId);
      setBillingAccountId(response.data.account.id);
    } catch (err: any) {
      setError('Failed to load billing account');
    }
  };

  const fetchPaymentMethods = async () => {
    if (!customerId) return;
    
    try {
      setLoading(true);
      const response = await billingAPI.getPaymentMethods(customerId);
      setPaymentMethods(response.data.payment_methods);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to load payment methods');
    } finally {
      setLoading(false);
    }
  };

  const handleAddPaymentMethod = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!billingAccountId) {
      setError('Billing account not found');
      return;
    }

    setProcessing(true);
    
    try {
      const requestData: CreatePaymentMethodRequest = {
        account_id: billingAccountId,
        plugin_name: formData.type === 'CREDIT_CARD' ? 'credit-card' : 
                     formData.type === 'PAYPAL' ? 'paypal' : 'bank-transfer',
        plugin_info: {
          type: formData.type,
          ...(formData.type === 'CREDIT_CARD' && {
            card_number: formData.card_number.replace(/\s/g, ''),
            exp_month: parseInt(formData.exp_month),
            exp_year: parseInt(formData.exp_year),
            cvv: formData.cvv,
            card_holder_name: formData.card_holder_name
          }),
          ...(formData.type === 'PAYPAL' && {
            email: formData.email
          }),
          ...(formData.type === 'BANK_TRANSFER' && {
            account_name: formData.account_name,
            routing_number: formData.routing_number,
            account_number: formData.account_number
          })
        },
        is_default: formData.is_default
      };

      await billingAPI.addPaymentMethod(requestData);
      await fetchPaymentMethods();
      setShowAddForm(false);
      resetForm();
      alert('Payment method added successfully!');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to add payment method');
    } finally {
      setProcessing(false);
    }
  };

  const handleDeletePaymentMethod = async (paymentMethodId: string) => {
    if (!window.confirm('Are you sure you want to delete this payment method?')) {
      return;
    }

    try {
      await billingAPI.deletePaymentMethod(paymentMethodId);
      await fetchPaymentMethods();
      alert('Payment method deleted successfully');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to delete payment method');
    }
  };

  const handleSetDefault = async (paymentMethodId: string) => {
    try {
      await billingAPI.setDefaultPaymentMethod(paymentMethodId);
      await fetchPaymentMethods();
      alert('Default payment method updated');
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to set default payment method');
    }
  };

  const resetForm = () => {
    setFormData({
      type: 'CREDIT_CARD',
      card_number: '',
      exp_month: '',
      exp_year: '',
      cvv: '',
      card_holder_name: '',
      email: '',
      account_name: '',
      routing_number: '',
      account_number: '',
      is_default: false
    });
  };

  const formatCardNumber = (value: string) => {
    const v = value.replace(/\s+/g, '').replace(/[^0-9]/gi, '');
    const matches = v.match(/\d{4,16}/g);
    const match = matches && matches[0] || '';
    const parts = [];

    for (let i = 0, len = match.length; i < len; i += 4) {
      parts.push(match.substring(i, i + 4));
    }

    if (parts.length) {
      return parts.join(' ');
    } else {
      return v;
    }
  };

  const getPaymentMethodIcon = (type: string) => {
    switch (type) {
      case 'CREDIT_CARD':
        return '💳';
      case 'PAYPAL':
        return '🅿️';
      case 'BANK_TRANSFER':
        return '🏦';
      default:
        return '💳';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded max-w-md">
          <strong className="font-bold">Error: </strong>
          <span>{error}</span>
          <button 
            onClick={() => window.location.reload()} 
            className="ml-4 text-sm underline"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Payment Methods</h1>
        <p className="mt-2 text-gray-600">Manage your payment methods for billing</p>
      </div>

      {/* Add Payment Method Button */}
      <div className="mb-8">
        <button
          onClick={() => setShowAddForm(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
        >
          + Add Payment Method
        </button>
      </div>

      {/* Payment Methods List */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Your Payment Methods</h2>
        </div>
        
        {paymentMethods.length > 0 ? (
          <div className="divide-y divide-gray-200">
            {paymentMethods.map((method) => (
              <div key={method.id} className="p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-4">
                    <div className="text-3xl">
                      {getPaymentMethodIcon(method.plugin_info.type)}
                    </div>
                    <div>
                      <h3 className="font-medium text-gray-900">
                        {method.plugin_info.type.replace('_', ' ')}
                      </h3>
                      {method.plugin_info.last_4 && (
                        <p className="text-sm text-gray-600">•••• •••• •••• {method.plugin_info.last_4}</p>
                      )}
                      {method.plugin_info.exp_month && method.plugin_info.exp_year && (
                        <p className="text-sm text-gray-600">
                          Expires {method.plugin_info.exp_month.toString().padStart(2, '0')}/{method.plugin_info.exp_year}
                        </p>
                      )}
                      {method.plugin_info.email && (
                        <p className="text-sm text-gray-600">{method.plugin_info.email}</p>
                      )}
                      {method.plugin_info.account_name && (
                        <p className="text-sm text-gray-600">{method.plugin_info.account_name}</p>
                      )}
                      {method.is_default && (
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 mt-1">
                          Default
                        </span>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex space-x-2">
                    {!method.is_default && (
                      <button
                        onClick={() => handleSetDefault(method.id)}
                        className="text-sm text-blue-600 hover:text-blue-800"
                      >
                        Set as Default
                      </button>
                    )}
                    <button
                      onClick={() => handleDeletePaymentMethod(method.id)}
                      className="text-sm text-red-600 hover:text-red-800"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <div className="text-6xl mb-4">💳</div>
            <h3 className="text-lg font-medium text-gray-900 mb-2">No payment methods</h3>
            <p className="text-gray-600 mb-4">Add a payment method to enable automatic billing.</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
            >
              Add Payment Method
            </button>
          </div>
        )}
      </div>

      {/* Add Payment Method Modal */}
      {showAddForm && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Add Payment Method</h3>
              
              <form onSubmit={handleAddPaymentMethod}>
                {/* Payment Type */}
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Payment Type
                  </label>
                  <select
                    value={formData.type}
                    onChange={(e) => setFormData({...formData, type: e.target.value as any})}
                    className="w-full border border-gray-300 rounded-md px-3 py-2"
                  >
                    <option value="CREDIT_CARD">Credit Card</option>
                    <option value="PAYPAL">PayPal</option>
                    <option value="BANK_TRANSFER">Bank Transfer</option>
                  </select>
                </div>

                {/* Credit Card Fields */}
                {formData.type === 'CREDIT_CARD' && (
                  <>
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Card Holder Name
                      </label>
                      <input
                        type="text"
                        value={formData.card_holder_name}
                        onChange={(e) => setFormData({...formData, card_holder_name: e.target.value})}
                        className="w-full border border-gray-300 rounded-md px-3 py-2"
                        required
                      />
                    </div>
                    
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Card Number
                      </label>
                      <input
                        type="text"
                        value={formData.card_number}
                        onChange={(e) => setFormData({...formData, card_number: formatCardNumber(e.target.value)})}
                        placeholder="1234 5678 9012 3456"
                        maxLength={19}
                        className="w-full border border-gray-300 rounded-md px-3 py-2"
                        required
                      />
                    </div>
                    
                    <div className="grid grid-cols-3 gap-4 mb-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Month
                        </label>
                        <select
                          value={formData.exp_month}
                          onChange={(e) => setFormData({...formData, exp_month: e.target.value})}
                          className="w-full border border-gray-300 rounded-md px-3 py-2"
                          required
                        >
                          <option value="">MM</option>
                          {Array.from({ length: 12 }, (_, i) => (
                            <option key={i + 1} value={i + 1}>
                              {(i + 1).toString().padStart(2, '0')}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          Year
                        </label>
                        <select
                          value={formData.exp_year}
                          onChange={(e) => setFormData({...formData, exp_year: e.target.value})}
                          className="w-full border border-gray-300 rounded-md px-3 py-2"
                          required
                        >
                          <option value="">YYYY</option>
                          {Array.from({ length: 10 }, (_, i) => (
                            <option key={i} value={new Date().getFullYear() + i}>
                              {new Date().getFullYear() + i}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                          CVV
                        </label>
                        <input
                          type="text"
                          value={formData.cvv}
                          onChange={(e) => setFormData({...formData, cvv: e.target.value.replace(/\D/g, '')})}
                          maxLength={4}
                          className="w-full border border-gray-300 rounded-md px-3 py-2"
                          required
                        />
                      </div>
                    </div>
                  </>
                )}

                {/* PayPal Fields */}
                {formData.type === 'PAYPAL' && (
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      PayPal Email
                    </label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => setFormData({...formData, email: e.target.value})}
                      className="w-full border border-gray-300 rounded-md px-3 py-2"
                      required
                    />
                  </div>
                )}

                {/* Bank Transfer Fields */}
                {formData.type === 'BANK_TRANSFER' && (
                  <>
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Account Name
                      </label>
                      <input
                        type="text"
                        value={formData.account_name}
                        onChange={(e) => setFormData({...formData, account_name: e.target.value})}
                        className="w-full border border-gray-300 rounded-md px-3 py-2"
                        required
                      />
                    </div>
                    
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Routing Number
                      </label>
                      <input
                        type="text"
                        value={formData.routing_number}
                        onChange={(e) => setFormData({...formData, routing_number: e.target.value.replace(/\D/g, '')})}
                        className="w-full border border-gray-300 rounded-md px-3 py-2"
                        required
                      />
                    </div>
                    
                    <div className="mb-4">
                      <label className="block text-sm font-medium text-gray-700 mb-2">
                        Account Number
                      </label>
                      <input
                        type="text"
                        value={formData.account_number}
                        onChange={(e) => setFormData({...formData, account_number: e.target.value.replace(/\D/g, '')})}
                        className="w-full border border-gray-300 rounded-md px-3 py-2"
                        required
                      />
                    </div>
                  </>
                )}

                {/* Default Payment Method */}
                <div className="mb-6">
                  <label className="flex items-center">
                    <input
                      type="checkbox"
                      checked={formData.is_default}
                      onChange={(e) => setFormData({...formData, is_default: e.target.checked})}
                      className="mr-2"
                    />
                    <span className="text-sm text-gray-700">Set as default payment method</span>
                  </label>
                </div>

                <div className="flex space-x-3">
                  <button
                    type="submit"
                    disabled={processing}
                    className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {processing ? (
                      <span className="flex items-center justify-center">
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                        Adding...
                      </span>
                    ) : (
                      'Add Payment Method'
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddForm(false);
                      resetForm();
                    }}
                    disabled={processing}
                    className="flex-1 bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400 disabled:opacity-50"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Back to Billing */}
      <div className="mt-8 text-center">
        <a
          href="/billing"
          className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
        >
          ← Back to Billing Dashboard
        </a>
      </div>
    </div>
  );
};

export default BillingPayment;