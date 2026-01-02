import React, { useState } from 'react';
import { Invoice, PaynowPaymentRequest } from '../types/billing';
import { billingAPI } from '../utils/api';
import { usePaymentPolling } from '../hooks/usePaymentPolling';

interface PaymentModalProps {
  invoice: Invoice;
  customerEmail: string;
  onClose: () => void;
  onSuccess: () => void;
}

const PaymentModal: React.FC<PaymentModalProps> = ({
  invoice,
  customerEmail,
  onClose,
  onSuccess
}) => {
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<'ecocash' | 'onemoney' | 'card'>('ecocash');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [phoneError, setPhoneError] = useState('');

  const [initiatingPayment, setInitiatingPayment] = useState(false);
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [paymentCompleted, setPaymentCompleted] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  const { status: paymentStatus, error: pollingError, timeRemaining, stopPolling } = usePaymentPolling({
    paymentId,
    enabled: pollingEnabled,
    onSuccess: (status) => {
      setPaymentCompleted(true);
      setPollingEnabled(false);
      setTimeout(() => {
        onSuccess();
      }, 2000);
    },
    onFailure: (status) => {
      setPaymentError(`Payment ${status.status}: ${status.paynow_status}`);
      setPollingEnabled(false);
    },
    onTimeout: () => {
      setPaymentError('Payment timeout - please check your payment status later');
      setPollingEnabled(false);
    }
  });

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatPhoneNumber = (value: string): string => {
    const digits = value.replace(/\D/g, '');
    const limited = digits.slice(0, 10);

    if (limited.length <= 3) {
      return limited;
    } else if (limited.length <= 6) {
      return `${limited.slice(0, 3)} ${limited.slice(3)}`;
    } else {
      return `${limited.slice(0, 3)} ${limited.slice(3, 6)} ${limited.slice(6)}`;
    }
  };

  const maskPhoneNumber = (phone: string): string => {
    const digits = phone.replace(/\D/g, '');
    return digits.length >= 3 ? `***${digits.slice(-3)}` : '***';
  };

  const initiatePayment = async () => {
    if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
      const cleanPhone = phoneNumber.replace(/\D/g, '');
      if (!cleanPhone || cleanPhone.length !== 10) {
        setPhoneError('Invalid phone number. Must be 10 digits.');
        return;
      }
      if (!cleanPhone.startsWith('07')) {
        setPhoneError('Phone must start with 07');
        return;
      }
    }

    setInitiatingPayment(true);
    setPaymentError(null);

    try {
      const request: PaynowPaymentRequest = {
        invoice_id: invoice.id,
        payment_method: selectedPaymentMethod,
        customer_email: customerEmail,
      };

      if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
        request.phone = phoneNumber.replace(/\D/g, '');
      }

      if (selectedPaymentMethod === 'card') {
        request.return_url = window.location.origin + '/billing/payment-status?payment_id=PLACEHOLDER';
      }

      const response = await billingAPI.initiatePaynowPayment(request);
      const paymentData = response.data;

      setPaymentId(paymentData.payment_id);

      if (paymentData.payment_type === 'mobile') {
        setPollingEnabled(true);
      } else if (paymentData.payment_type === 'redirect' && paymentData.redirect_url) {
        window.location.href = paymentData.redirect_url;
      } else {
        setPaymentError('Invalid payment response from server');
      }
    } catch (err: any) {
      setPaymentError(err.response?.data?.message || 'Payment failed. Please try again.');
    } finally {
      setInitiatingPayment(false);
    }
  };

  const handleCancel = () => {
    if (pollingEnabled) {
      stopPolling();
    }
    onClose();
  };

  return (
    <div className="fixed inset-0 bg-warm-900/60 backdrop-blur-sm overflow-y-auto h-full w-full z-50 flex items-start justify-center pt-16 px-4">
      <div className="relative w-full max-w-md card p-0 animate-fade-in-up shadow-2xl">
        <div className="p-6">
          {/* State 1: Payment Method Selection */}
          {!pollingEnabled && !paymentCompleted && (
            <>
              {/* Header */}
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-3">
                  <div className="w-10 h-10 bg-primary-100 rounded-xl flex items-center justify-center">
                    <svg className="w-5 h-5 text-primary-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-warm-900">
                      Pay Invoice
                    </h3>
                    <p className="text-sm text-warm-500">#{invoice.invoice_number}</p>
                  </div>
                </div>
                <button
                  onClick={handleCancel}
                  className="p-2 text-warm-400 hover:text-warm-600 hover:bg-warm-100 rounded-lg transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Invoice Summary */}
              <div className="mb-5 p-4 bg-warm-50 rounded-xl border border-warm-200">
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-warm-600">Balance Due</span>
                  <span className="font-semibold text-rose-600 text-lg">
                    {formatCurrency(invoice.balance, invoice.currency)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-warm-500">Due Date</span>
                  <span className="text-sm text-warm-700">{formatDate(invoice.target_date)}</span>
                </div>
              </div>

              {/* Payment Method Selector */}
              <div className="mb-5">
                <label className="block text-sm font-medium text-warm-700 mb-3">
                  Select Payment Method
                </label>

                <div className="space-y-2">
                  {/* EcoCash */}
                  <label
                    className={`flex items-center p-4 border-2 rounded-xl cursor-pointer transition-all ${
                      selectedPaymentMethod === 'ecocash'
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-warm-200 hover:border-warm-300 hover:bg-warm-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="payment_method"
                      value="ecocash"
                      checked={selectedPaymentMethod === 'ecocash'}
                      onChange={(e) => setSelectedPaymentMethod(e.target.value as 'ecocash')}
                      className="sr-only"
                    />
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center mr-3">
                      <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-warm-900">EcoCash</span>
                      <p className="text-sm text-warm-500">Pay with mobile money</p>
                    </div>
                    {selectedPaymentMethod === 'ecocash' && (
                      <svg className="w-5 h-5 text-primary-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    )}
                  </label>

                  {/* OneMoney */}
                  <label
                    className={`flex items-center p-4 border-2 rounded-xl cursor-pointer transition-all ${
                      selectedPaymentMethod === 'onemoney'
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-warm-200 hover:border-warm-300 hover:bg-warm-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="payment_method"
                      value="onemoney"
                      checked={selectedPaymentMethod === 'onemoney'}
                      onChange={(e) => setSelectedPaymentMethod(e.target.value as 'onemoney')}
                      className="sr-only"
                    />
                    <div className="w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center mr-3">
                      <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-warm-900">OneMoney</span>
                      <p className="text-sm text-warm-500">Pay with mobile money</p>
                    </div>
                    {selectedPaymentMethod === 'onemoney' && (
                      <svg className="w-5 h-5 text-primary-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    )}
                  </label>

                  {/* Card */}
                  <label
                    className={`flex items-center p-4 border-2 rounded-xl cursor-pointer transition-all ${
                      selectedPaymentMethod === 'card'
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-warm-200 hover:border-warm-300 hover:bg-warm-50'
                    }`}
                  >
                    <input
                      type="radio"
                      name="payment_method"
                      value="card"
                      checked={selectedPaymentMethod === 'card'}
                      onChange={(e) => setSelectedPaymentMethod(e.target.value as 'card')}
                      className="sr-only"
                    />
                    <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center mr-3">
                      <svg className="w-5 h-5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-warm-900">Card Payment</span>
                      <p className="text-sm text-warm-500">Visa, Mastercard via Paynow</p>
                    </div>
                    {selectedPaymentMethod === 'card' && (
                      <svg className="w-5 h-5 text-primary-600" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                    )}
                  </label>
                </div>
              </div>

              {/* Phone Number Input (for mobile money only) */}
              {['ecocash', 'onemoney'].includes(selectedPaymentMethod) && (
                <div className="mb-5">
                  <label className="block text-sm font-medium text-warm-700 mb-2">
                    Phone Number
                  </label>
                  <div className="relative">
                    <div className="input-icon">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                      </svg>
                    </div>
                    <input
                      type="tel"
                      value={phoneNumber}
                      onChange={(e) => {
                        const formatted = formatPhoneNumber(e.target.value);
                        setPhoneNumber(formatted);
                        setPhoneError('');
                      }}
                      placeholder="077 123 4567"
                      className={`input-field input-with-icon ${phoneError ? 'border-rose-300 focus:border-rose-500 focus:ring-rose-500' : ''}`}
                    />
                  </div>
                  {phoneError && (
                    <p className="text-sm text-rose-600 mt-1.5 flex items-center">
                      <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      {phoneError}
                    </p>
                  )}
                  <p className="text-xs text-warm-500 mt-1.5">
                    A payment request will be sent to your phone
                  </p>
                </div>
              )}

              {/* Card Payment Info */}
              {selectedPaymentMethod === 'card' && (
                <div className="mb-5 p-3 bg-blue-50 border border-blue-200 rounded-xl">
                  <p className="text-sm text-blue-800 flex items-center">
                    <svg className="w-4 h-4 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    You will be redirected to Paynow's secure payment page to complete your card payment.
                  </p>
                </div>
              )}

              {/* Error Message */}
              {paymentError && (
                <div className="mb-5 p-3 bg-rose-50 border border-rose-200 rounded-xl">
                  <p className="text-sm text-rose-800 flex items-center">
                    <svg className="w-4 h-4 mr-2 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    {paymentError}
                  </p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex gap-3">
                <button
                  onClick={initiatePayment}
                  disabled={initiatingPayment}
                  className="flex-1 btn-primary py-3"
                >
                  {initiatingPayment ? (
                    <span className="flex items-center justify-center">
                      <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Initiating...
                    </span>
                  ) : (
                    `Pay ${formatCurrency(invoice.balance, invoice.currency)}`
                  )}
                </button>
                <button
                  onClick={handleCancel}
                  disabled={initiatingPayment}
                  className="btn-secondary py-3"
                >
                  Cancel
                </button>
              </div>
            </>
          )}

          {/* State 2: Waiting for Payment */}
          {pollingEnabled && !paymentCompleted && (
            <div className="text-center py-4">
              <div className="w-16 h-16 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-6">
                <svg className="animate-spin h-8 w-8 text-primary-600" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
              </div>

              <h3 className="text-lg font-semibold text-warm-900 mb-2">
                Waiting for Payment Approval
              </h3>

              {/* Instructions */}
              <div className="mb-6 p-4 bg-primary-50 border border-primary-200 rounded-xl">
                <p className="text-sm text-primary-800">
                  Check your phone <span className="font-semibold">({maskPhoneNumber(phoneNumber)})</span> and approve the payment request
                </p>
              </div>

              {/* Countdown Timer */}
              <div className="mb-6">
                <div className="text-4xl font-bold text-warm-900 mb-1">
                  {Math.floor(timeRemaining / 60)}:{(timeRemaining % 60).toString().padStart(2, '0')}
                </div>
                <p className="text-sm text-warm-500">Time remaining</p>
              </div>

              {/* Current Status */}
              {paymentStatus && (
                <div className="mb-4 p-3 bg-warm-50 border border-warm-200 rounded-xl">
                  <p className="text-sm text-warm-700">
                    Status: <span className="font-medium">{paymentStatus.paynow_status}</span>
                  </p>
                </div>
              )}

              {/* Polling Error */}
              {pollingError && (
                <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-xl">
                  <p className="text-sm text-rose-800">{pollingError}</p>
                </div>
              )}

              {/* Cancel Button */}
              <button onClick={handleCancel} className="btn-secondary w-full py-3">
                Cancel
              </button>

              <p className="text-xs text-warm-500 mt-3">
                Note: Canceling will stop checking status. Your payment may still be processing.
              </p>
            </div>
          )}

          {/* State 3: Payment Successful */}
          {paymentCompleted && (
            <div className="text-center py-4">
              <div className="w-20 h-20 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-6 animate-fade-in">
                <svg className="w-10 h-10 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>

              <h3 className="text-xl font-semibold text-emerald-600 mb-2">
                Payment Successful!
              </h3>
              <p className="text-sm text-warm-500 mb-6">
                Your payment has been processed successfully.
              </p>

              {/* Payment Details */}
              {paymentStatus && (
                <div className="p-4 bg-warm-50 border border-warm-200 rounded-xl text-left mb-4">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm text-warm-500">Amount Paid</span>
                    <span className="font-semibold text-warm-900">
                      {formatCurrency(paymentStatus.amount, invoice.currency)}
                    </span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm text-warm-500">Payment Method</span>
                    <span className="font-medium text-warm-900 capitalize">{paymentStatus.payment_method}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-warm-500">Reference</span>
                    <span className="text-sm font-mono text-warm-700">
                      {paymentStatus.reference.substring(0, 20)}...
                    </span>
                  </div>
                </div>
              )}

              <p className="text-xs text-warm-400">
                Closing automatically...
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PaymentModal;
