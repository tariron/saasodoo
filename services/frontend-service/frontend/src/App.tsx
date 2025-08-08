import React from 'react';
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
import BillingInstanceManage from './pages/BillingInstanceManage';
import AuthGuard from './components/AuthGuard';
import { TokenManager } from './utils/api';

function App() {
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
            path="/billing/instance/:instanceId" 
            element={
              <AuthGuard>
                <BillingInstanceManage />
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