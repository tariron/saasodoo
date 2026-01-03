import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import Login from './pages/Login';
import Register from './pages/Register';
import VerifyEmail from './pages/VerifyEmail';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Dashboard from './pages/Dashboard';
import Instances from './pages/Instances';
import CreateInstance from './pages/CreateInstance';
import Profile from './pages/Profile';
import Billing from './pages/Billing';
import BillingInvoices from './pages/BillingInvoices';
import BillingPayment from './pages/BillingPayment';
import BillingPaymentStatus from './pages/BillingPaymentStatus';
import BillingInstanceManage from './pages/BillingInstanceManage';
import SubscriptionUpgrade from './pages/SubscriptionUpgrade';
import LandingPage from './pages/LandingPage';
import PricingPage from './pages/PricingPage';
import AuthenticatedLayout from './components/AuthenticatedLayout';
import MarketingLayout from './components/MarketingLayout';
import { TokenManager, initializeAPI } from './utils/api';

/**
 * Detect if we're on a marketing domain (www.*) or app domain (app.*)
 * Marketing domain shows landing page and pricing
 * App domain shows dashboard and authenticated routes
 */
const isMarketingDomain = (): boolean => {
  const hostname = window.location.hostname;
  // Marketing domain: www.* or root domain without subdomain
  // App domain: app.* or any other subdomain
  return hostname.startsWith('www.') ||
         // For local development, treat localhost as app domain
         (!hostname.startsWith('app.') && !hostname.includes('localhost') && !hostname.match(/^\d+\.\d+\.\d+\.\d+/));
};

/**
 * Get the app domain URL for redirects after login
 */
const getAppDomainUrl = (path: string = '/dashboard'): string => {
  const hostname = window.location.hostname;
  const protocol = window.location.protocol;
  const port = window.location.port;

  // If already on app subdomain, just return the path
  if (hostname.startsWith('app.')) {
    return path;
  }

  // If on www, redirect to app subdomain
  if (hostname.startsWith('www.')) {
    const baseDomain = hostname.replace('www.', '');
    const portSuffix = port ? `:${port}` : '';
    return `${protocol}//app.${baseDomain}${portSuffix}${path}`;
  }

  // Local development or IP-based - just return path
  return path;
};

function App() {
  const [isConfigLoading, setIsConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const isMarketing = isMarketingDomain();

  useEffect(() => {
    // Initialize API configuration before rendering app
    const init = async () => {
      try {
        await initializeAPI();
      } catch (error) {
        console.error('Failed to initialize API:', error);
        setConfigError('Failed to load application configuration');
      } finally {
        setIsConfigLoading(false);
      }
    };
    init();
  }, []);

  // Show loading state while config loads
  if (isConfigLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-warm-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
          <p className="mt-4 text-warm-600">Loading...</p>
        </div>
      </div>
    );
  }

  // Show error state if config failed to load
  if (configError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-warm-50">
        <div className="text-center">
          <div className="text-rose-600 text-xl mb-4">⚠️</div>
          <p className="text-warm-900 font-semibold">{configError}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Marketing site routes (www.* domain)
  if (isMarketing) {
    return (
      <Router>
        <MarketingLayout>
          <Routes>
            {/* Landing page */}
            <Route path="/" element={<LandingPage />} />

            {/* Pricing page */}
            <Route path="/pricing" element={<PricingPage />} />

            {/* Auth routes - work on marketing domain too */}
            <Route
              path="/login"
              element={
                TokenManager.isAuthenticated() ? (
                  // Redirect to app domain after login
                  <RedirectToApp />
                ) : (
                  <Login />
                )
              }
            />

            <Route
              path="/register"
              element={
                TokenManager.isAuthenticated() ? (
                  <RedirectToApp />
                ) : (
                  <Register />
                )
              }
            />

            <Route path="/verify-email" element={<VerifyEmail />} />

            <Route
              path="/forgot-password"
              element={
                TokenManager.isAuthenticated() ?
                  <RedirectToApp /> :
                  <ForgotPassword />
              }
            />

            <Route
              path="/reset-password/:token"
              element={
                TokenManager.isAuthenticated() ?
                  <RedirectToApp /> :
                  <ResetPassword />
              }
            />

            <Route
              path="/reset-password"
              element={
                TokenManager.isAuthenticated() ?
                  <RedirectToApp /> :
                  <ResetPassword />
              }
            />

            {/* Redirect any app routes to app domain */}
            <Route path="/dashboard" element={<RedirectToApp path="/dashboard" />} />
            <Route path="/instances/*" element={<RedirectToApp path="/instances" />} />
            <Route path="/billing/*" element={<RedirectToApp path="/billing" />} />
            <Route path="/profile" element={<RedirectToApp path="/profile" />} />

            {/* 404 fallback */}
            <Route
              path="*"
              element={
                <div className="min-h-screen flex items-center justify-center">
                  <div className="text-center">
                    <h1 className="text-4xl font-bold text-warm-900">404</h1>
                    <p className="mt-2 text-warm-600">Page not found</p>
                    <Link to="/" className="mt-4 inline-block btn-primary">
                      Go Home
                    </Link>
                  </div>
                </div>
              }
            />
          </Routes>
        </MarketingLayout>
      </Router>
    );
  }

  // App routes (app.* domain or localhost)
  return (
    <Router>
      <div className="min-h-screen bg-warm-50">
        <Routes>
          {/* Public routes */}
          <Route
            path="/login"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <Login />
            }
          />

          <Route
            path="/register"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <Register />
            }
          />

          <Route
            path="/verify-email"
            element={<VerifyEmail />}
          />

          <Route
            path="/forgot-password"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <ForgotPassword />
            }
          />

          <Route
            path="/reset-password/:token"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <ResetPassword />
            }
          />

          <Route
            path="/reset-password"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <ResetPassword />
            }
          />

          {/* Protected routes */}
          <Route
            path="/dashboard"
            element={
              <AuthenticatedLayout>
                <Dashboard />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/instances"
            element={
              <AuthenticatedLayout>
                <Instances />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/instances/create"
            element={
              <AuthenticatedLayout>
                <CreateInstance />
              </AuthenticatedLayout>
            }
          />

          {/* Billing routes */}
          <Route
            path="/billing"
            element={
              <AuthenticatedLayout>
                <Billing />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/billing/invoices"
            element={
              <AuthenticatedLayout>
                <BillingInvoices />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/billing/payment"
            element={
              <AuthenticatedLayout>
                <BillingPayment />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/billing/payment-status"
            element={
              <AuthenticatedLayout>
                <BillingPaymentStatus />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/billing/instance/:instanceId"
            element={
              <AuthenticatedLayout>
                <BillingInstanceManage />
              </AuthenticatedLayout>
            }
          />

          <Route
            path="/billing/instance/:instanceId/upgrade"
            element={
              <AuthenticatedLayout>
                <SubscriptionUpgrade />
              </AuthenticatedLayout>
            }
          />

          {/* User Management routes */}
          <Route
            path="/profile"
            element={
              <AuthenticatedLayout>
                <Profile />
              </AuthenticatedLayout>
            }
          />

          {/* Pricing page - also available on app domain */}
          <Route path="/pricing" element={
            <MarketingLayout>
              <PricingPage />
            </MarketingLayout>
          } />

          {/* Default redirect */}
          <Route
            path="/"
            element={
              TokenManager.isAuthenticated() ?
                <Navigate to="/dashboard" replace /> :
                <Navigate to="/login" replace />
            }
          />

          {/* 404 fallback */}
          <Route
            path="*"
            element={
              <div className="min-h-screen flex items-center justify-center bg-warm-50">
                <div className="text-center">
                  <h1 className="text-4xl font-bold text-warm-900">404</h1>
                  <p className="mt-2 text-warm-600">Page not found</p>
                  <Link to="/dashboard" className="mt-4 inline-block btn-primary">
                    Go to Dashboard
                  </Link>
                </div>
              </div>
            }
          />
        </Routes>
      </div>
    </Router>
  );
}

/**
 * Component to redirect to app domain
 */
const RedirectToApp: React.FC<{ path?: string }> = ({ path = '/dashboard' }) => {
  useEffect(() => {
    const appUrl = getAppDomainUrl(path);
    if (appUrl.startsWith('http')) {
      window.location.href = appUrl;
    } else {
      window.location.pathname = appUrl;
    }
  }, [path]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-warm-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto"></div>
        <p className="mt-4 text-warm-600">Redirecting to app...</p>
      </div>
    </div>
  );
};

export default App;
