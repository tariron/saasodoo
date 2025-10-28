import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { usePaymentPolling } from '../hooks/usePaymentPolling';
import Navigation from '../components/Navigation';
import { authAPI } from '../utils/api';

const BillingPaymentStatus: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [profile, setProfile] = React.useState<any>(null);

  const paymentId = searchParams.get('payment_id');
  const [redirectCountdown, setRedirectCountdown] = React.useState(5);
  const [paymentCompleted, setPaymentCompleted] = React.useState(false);
  const [paymentFailed, setPaymentFailed] = React.useState(false);

  // Fetch user profile
  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const response = await authAPI.getProfile();
        setProfile(response.data);
      } catch (err) {
        console.error('Failed to load profile:', err);
      }
    };
    fetchProfile();
  }, []);

  // Payment polling hook (reused from mobile money)
  const { status: paymentStatus, error: pollingError, timeRemaining, stopPolling } = usePaymentPolling({
    paymentId,
    enabled: !!paymentId,
    onSuccess: (status) => {
      setPaymentCompleted(true);
      setPaymentFailed(false);
      stopPolling();

      // Start countdown for redirect
      let countdown = 5;
      setRedirectCountdown(countdown);
      const countdownInterval = setInterval(() => {
        countdown--;
        setRedirectCountdown(countdown);
        if (countdown <= 0) {
          clearInterval(countdownInterval);
          navigate('/billing/invoices');
        }
      }, 1000);
    },
    onFailure: (status) => {
      setPaymentFailed(true);
      setPaymentCompleted(false);
      stopPolling();
    },
    onTimeout: () => {
      setPaymentFailed(true);
      stopPolling();
    }
  });

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  // Handle missing payment ID
  if (!paymentId) {
    return (
      <>
        <Navigation userProfile={profile || undefined} />
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-8">
            <div className="text-center">
              <div className="text-6xl mb-4">⚠️</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-4">Invalid Payment Link</h2>
              <p className="text-gray-600 mb-6">
                No payment ID found in the URL. This link may be invalid or expired.
              </p>
              <button
                onClick={() => navigate('/billing/invoices')}
                className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700"
              >
                Go to Invoices
              </button>
            </div>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Navigation userProfile={profile || undefined} />
      <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full bg-white shadow-lg rounded-lg p-8">

          {/* Processing State */}
          {!paymentCompleted && !paymentFailed && (
            <div className="text-center">
              <h2 className="text-2xl font-bold text-gray-900 mb-6">
                Processing Your Payment
              </h2>

              {/* Spinner */}
              <div className="mb-6">
                <div className="animate-spin rounded-full h-20 w-20 border-b-4 border-blue-600 mx-auto"></div>
              </div>

              {/* Instructions */}
              <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                <p className="text-sm text-gray-800 mb-2">
                  Verifying your payment with Paynow...
                </p>
                <p className="text-sm text-gray-600">
                  This usually takes a few seconds
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
                    Status: <span className="font-medium capitalize">{paymentStatus.paynow_status || paymentStatus.status}</span>
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Payment ID: {paymentId.substring(0, 8)}...
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
                onClick={() => navigate('/billing/invoices')}
                className="w-full bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400 mt-4"
              >
                Return to Invoices
              </button>

              <p className="text-xs text-gray-500 mt-3">
                Note: Your payment may still be processing even if you leave this page.
              </p>
            </div>
          )}

          {/* Success State */}
          {paymentCompleted && (
            <div className="text-center">
              <div className="mb-4">
                <div className="text-6xl mb-4">✅</div>
                <h2 className="text-2xl font-bold text-green-600 mb-2">
                  Payment Successful!
                </h2>
                <p className="text-sm text-gray-600 mb-4">
                  Your payment has been processed successfully.
                </p>
              </div>

              {/* Payment Details */}
              {paymentStatus && (
                <div className="mb-6 p-4 bg-gray-50 rounded-lg text-left">
                  <div className="flex justify-between mb-2">
                    <span className="text-sm text-gray-600">Amount Paid:</span>
                    <span className="font-medium">
                      {formatCurrency(paymentStatus.amount)}
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

              {/* Next Steps */}
              <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
                <p className="text-sm text-green-800 font-medium mb-2">
                  What happens next?
                </p>
                <ul className="text-sm text-green-700 text-left space-y-1">
                  <li>✅ Invoice will be marked as paid</li>
                  <li>✅ Your Odoo instance will be provisioned</li>
                  <li>✅ You'll receive an email when ready</li>
                </ul>
              </div>

              {/* Redirect Notice */}
              <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
                <p className="text-sm text-blue-800">
                  Redirecting to invoices in <span className="font-bold">{redirectCountdown}</span> seconds...
                </p>
              </div>

              {/* Manual Navigation */}
              <div className="flex space-x-3">
                <button
                  onClick={() => navigate('/billing/invoices')}
                  className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
                >
                  View Invoices
                </button>
                <button
                  onClick={() => navigate('/instances')}
                  className="flex-1 bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700"
                >
                  View Instances
                </button>
              </div>
            </div>
          )}

          {/* Failure State */}
          {paymentFailed && (
            <div className="text-center">
              <div className="mb-4">
                <div className="text-6xl mb-4">❌</div>
                <h2 className="text-2xl font-bold text-red-600 mb-2">
                  Payment Failed
                </h2>
                <p className="text-sm text-gray-600 mb-4">
                  {pollingError || 'We could not verify your payment. This could be due to:'}
                </p>
              </div>

              {/* Possible Reasons */}
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-left">
                <ul className="text-sm text-red-700 space-y-2">
                  <li>• Payment was cancelled</li>
                  <li>• Insufficient funds</li>
                  <li>• Payment timeout</li>
                  <li>• Network issues</li>
                </ul>
              </div>

              {/* Payment Status Info */}
              {paymentStatus && (
                <div className="mb-4 p-3 bg-gray-50 rounded-md text-left">
                  <p className="text-sm text-gray-700 mb-1">
                    Status: <span className="font-medium text-red-600 capitalize">
                      {paymentStatus.paynow_status || paymentStatus.status}
                    </span>
                  </p>
                  <p className="text-xs text-gray-500">
                    Payment ID: {paymentId}
                  </p>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-col space-y-3">
                <button
                  onClick={() => navigate('/billing/invoices')}
                  className="w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
                >
                  Try Again
                </button>
                <button
                  onClick={() => navigate('/billing')}
                  className="w-full bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400"
                >
                  Back to Billing
                </button>
              </div>

              {/* Help Text */}
              <p className="text-xs text-gray-500 mt-4">
                If you believe this is an error, please contact support with your payment ID.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default BillingPaymentStatus;
