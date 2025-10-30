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
  // Payment method selection
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState<'ecocash' | 'onemoney' | 'card'>('ecocash');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [phoneError, setPhoneError] = useState('');

  // Payment processing
  const [initiatingPayment, setInitiatingPayment] = useState(false);
  const [paymentId, setPaymentId] = useState<string | null>(null);
  const [pollingEnabled, setPollingEnabled] = useState(false);
  const [paymentCompleted, setPaymentCompleted] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);

  // Payment polling hook
  const { status: paymentStatus, error: pollingError, timeRemaining, stopPolling } = usePaymentPolling({
    paymentId,
    enabled: pollingEnabled,
    onSuccess: (status) => {
      setPaymentCompleted(true);
      setPollingEnabled(false);
      // Redirect after 2 seconds to show success message
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
    // Validate phone for mobile money
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

      // Add phone for mobile money
      if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
        request.phone = phoneNumber.replace(/\D/g, '');
      }

      // Add return URL for cards - we'll use a temporary placeholder that backend will replace
      if (selectedPaymentMethod === 'card') {
        request.return_url = window.location.origin + '/billing/payment-status?payment_id=PLACEHOLDER';
      }

      const response = await billingAPI.initiatePaynowPayment(request);
      const paymentData = response.data;

      setPaymentId(paymentData.payment_id);

      if (paymentData.payment_type === 'mobile') {
        // Start polling
        setPollingEnabled(true);
      } else if (paymentData.payment_type === 'redirect' && paymentData.redirect_url) {
        // Redirect to Paynow
        // Paynow will redirect user back to our return_url (with payment_id) after payment
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
    <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
      <div className="relative top-20 mx-auto p-5 border w-full max-w-md shadow-lg rounded-md bg-white">
        <div className="mt-3">
          {/* State 1: Payment Method Selection */}
          {!pollingEnabled && !paymentCompleted && (
            <>
              <h3 className="text-lg font-medium text-gray-900 mb-4">
                Pay Invoice #{invoice.invoice_number}
              </h3>

              {/* Invoice Summary */}
              <div className="mb-4 p-4 bg-gray-50 rounded-lg">
                <div className="flex justify-between mb-2">
                  <span className="text-sm text-gray-600">Balance Due:</span>
                  <span className="font-medium text-red-600">
                    {formatCurrency(invoice.balance, invoice.currency)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-sm text-gray-600">Due Date:</span>
                  <span className="text-sm">{formatDate(invoice.target_date)}</span>
                </div>
              </div>

              {/* Payment Method Selector */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Select Payment Method
                </label>

                {/* EcoCash */}
                <label
                  className="flex items-center p-4 border-2 rounded-lg mb-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: selectedPaymentMethod === 'ecocash' ? '#3B82F6' : '#D1D5DB' }}
                >
                  <input
                    type="radio"
                    name="payment_method"
                    value="ecocash"
                    checked={selectedPaymentMethod === 'ecocash'}
                    onChange={(e) => setSelectedPaymentMethod(e.target.value as 'ecocash')}
                    className="mr-3"
                  />
                  <div>
                    <div className="flex items-center">
                      <span className="text-2xl mr-2">📱</span>
                      <span className="font-medium text-gray-900">EcoCash</span>
                    </div>
                    <span className="text-sm text-gray-600">Pay with mobile money</span>
                  </div>
                </label>

                {/* OneMoney */}
                <label
                  className="flex items-center p-4 border-2 rounded-lg mb-3 cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: selectedPaymentMethod === 'onemoney' ? '#3B82F6' : '#D1D5DB' }}
                >
                  <input
                    type="radio"
                    name="payment_method"
                    value="onemoney"
                    checked={selectedPaymentMethod === 'onemoney'}
                    onChange={(e) => setSelectedPaymentMethod(e.target.value as 'onemoney')}
                    className="mr-3"
                  />
                  <div>
                    <div className="flex items-center">
                      <span className="text-2xl mr-2">📱</span>
                      <span className="font-medium text-gray-900">OneMoney</span>
                    </div>
                    <span className="text-sm text-gray-600">Pay with mobile money</span>
                  </div>
                </label>

                {/* Card */}
                <label
                  className="flex items-center p-4 border-2 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors"
                  style={{ borderColor: selectedPaymentMethod === 'card' ? '#3B82F6' : '#D1D5DB' }}
                >
                  <input
                    type="radio"
                    name="payment_method"
                    value="card"
                    checked={selectedPaymentMethod === 'card'}
                    onChange={(e) => setSelectedPaymentMethod(e.target.value as 'card')}
                    className="mr-3"
                  />
                  <div>
                    <div className="flex items-center">
                      <span className="text-2xl mr-2">💳</span>
                      <span className="font-medium text-gray-900">Card Payment</span>
                    </div>
                    <span className="text-sm text-gray-600">Visa, Mastercard via Paynow</span>
                  </div>
                </label>
              </div>

              {/* Phone Number Input (for mobile money only) */}
              {['ecocash', 'onemoney'].includes(selectedPaymentMethod) && (
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Phone Number *
                  </label>
                  <input
                    type="tel"
                    value={phoneNumber}
                    onChange={(e) => {
                      const formatted = formatPhoneNumber(e.target.value);
                      setPhoneNumber(formatted);
                      setPhoneError('');
                    }}
                    placeholder="077 123 4567"
                    className={`w-full border rounded-md px-3 py-2 ${
                      phoneError ? 'border-red-500' : 'border-gray-300'
                    }`}
                  />
                  {phoneError && (
                    <p className="text-sm text-red-600 mt-1">{phoneError}</p>
                  )}
                  <p className="text-xs text-gray-500 mt-1">
                    A payment request will be sent to your phone
                  </p>
                </div>
              )}

              {/* Card Payment Info */}
              {selectedPaymentMethod === 'card' && (
                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
                  <p className="text-sm text-blue-800">
                    You will be redirected to Paynow's secure payment page to complete your card payment.
                  </p>
                </div>
              )}

              {/* Error Message */}
              {paymentError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
                  <p className="text-sm text-red-800">{paymentError}</p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex space-x-3">
                <button
                  onClick={initiatePayment}
                  disabled={initiatingPayment}
                  className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {initiatingPayment ? (
                    <span className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Initiating...
                    </span>
                  ) : (
                    `Pay ${formatCurrency(invoice.balance, invoice.currency)}`
                  )}
                </button>
                <button
                  onClick={handleCancel}
                  disabled={initiatingPayment}
                  className="flex-1 bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400 disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            </>
          )}

          {/* State 2: Waiting for Payment */}
          {pollingEnabled && !paymentCompleted && (
            <div className="text-center">
              <h3 className="text-lg font-medium text-gray-900 mb-6">
                Waiting for Payment Approval
              </h3>

              {/* Spinner */}
              <div className="mb-6">
                <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto"></div>
              </div>

              {/* Instructions */}
              <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                <p className="text-sm text-gray-800 mb-2">
                  Check your phone ({maskPhoneNumber(phoneNumber)})
                </p>
                <p className="text-sm text-gray-800">
                  and approve the payment request
                </p>
              </div>

              {/* Countdown Timer */}
              <div className="mb-6">
                <div className="text-3xl font-bold text-gray-900 mb-2">
                  {Math.floor(timeRemaining / 60)}:{(timeRemaining % 60).toString().padStart(2, '0')}
                </div>
                <p className="text-sm text-gray-600">Time remaining</p>
              </div>

              {/* Current Status */}
              {paymentStatus && (
                <div className="mb-4 p-3 bg-gray-50 rounded-md">
                  <p className="text-sm text-gray-700">
                    Status: <span className="font-medium">{paymentStatus.paynow_status}</span>
                  </p>
                </div>
              )}

              {/* Polling Error */}
              {pollingError && (
                <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
                  <p className="text-sm text-red-800">{pollingError}</p>
                </div>
              )}

              {/* Cancel Button */}
              <button
                onClick={handleCancel}
                className="w-full bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400"
              >
                Cancel
              </button>

              <p className="text-xs text-gray-500 mt-3">
                Note: Canceling will stop checking status. Your payment may still be processing.
              </p>
            </div>
          )}

          {/* State 3: Payment Successful */}
          {paymentCompleted && (
            <div className="text-center">
              <div className="mb-4">
                <div className="text-6xl mb-4">✅</div>
                <h3 className="text-xl font-medium text-green-600 mb-2">
                  Payment Successful!
                </h3>
                <p className="text-sm text-gray-600">
                  Your payment has been processed successfully.
                </p>
              </div>

              {/* Payment Details */}
              {paymentStatus && (
                <div className="mb-4 p-4 bg-gray-50 rounded-lg text-left">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm text-gray-600">Amount Paid:</span>
                    <span className="font-medium">
                      {formatCurrency(paymentStatus.amount, invoice.currency)}
                    </span>
                  </div>
                  <div className="flex justify-between mb-2">
                    <span className="text-sm text-gray-600">Payment Method:</span>
                    <span className="font-medium capitalize">{paymentStatus.payment_method}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-sm text-gray-600">Reference:</span>
                    <span className="text-sm font-mono text-gray-800">
                      {paymentStatus.reference.substring(0, 20)}...
                    </span>
                  </div>
                </div>
              )}

              <p className="text-xs text-gray-500">
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
