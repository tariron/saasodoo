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
import AuthGuard from './components/AuthGuard';
import { TokenManager, initializeAPI } from './utils/api';

function App() {
  const [isConfigLoading, setIsConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);

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
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading application...</p>
        </div>
      </div>
    );
  }

  // Show error state if config failed to load
  if (configError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="text-red-600 text-xl mb-4">⚠️</div>
          <p className="text-gray-900 font-semibold">{configError}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
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
              <AuthGuard>
                <Dashboard />
              </AuthGuard>
            } 
          />
          
          <Route 
            path="/instances" 
            element={
              <AuthGuard>
                <Instances />
              </AuthGuard>
            } 
          />
          
          <Route 
            path="/instances/create" 
            element={
              <AuthGuard>
                <CreateInstance />
              </AuthGuard>
            } 
          />
          
          {/* Billing routes */}
          <Route 
            path="/billing" 
            element={
              <AuthGuard>
                <Billing />
              </AuthGuard>
            } 
          />
          
          
          <Route 
            path="/billing/invoices" 
            element={
              <AuthGuard>
                <BillingInvoices />
              </AuthGuard>
            } 
          />
          
          <Route
            path="/billing/payment"
            element={
              <AuthGuard>
                <BillingPayment />
              </AuthGuard>
            }
          />

          <Route
            path="/billing/payment-status"
            element={
              <AuthGuard>
                <BillingPaymentStatus />
              </AuthGuard>
            }
          />

          <Route
            path="/billing/instance/:instanceId"
            element={
              <AuthGuard>
                <BillingInstanceManage />
              </AuthGuard>
            }
          />

          <Route
            path="/billing/instance/:instanceId/upgrade"
            element={
              <AuthGuard>
                <SubscriptionUpgrade />
              </AuthGuard>
            }
          />

          {/* User Management routes */}
          <Route 
            path="/profile" 
            element={
              <AuthGuard>
                <Profile />
              </AuthGuard>
            } 
          />
          
          {/* Default redirect */}
          <Route 
            path="/" 
            element={<Navigate to="/dashboard" replace />} 
          />
          
          {/* 404 fallback */}
          <Route 
            path="*" 
            element={
              <div className="min-h-screen flex items-center justify-center bg-gray-50">
                <div className="text-center">
                  <h1 className="text-4xl font-bold text-gray-900">404</h1>
                  <p className="mt-2 text-gray-600">Page not found</p>
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

export default App;