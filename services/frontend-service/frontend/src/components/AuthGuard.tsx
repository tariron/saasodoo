import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { authAPI, TokenManager } from '../utils/api';
import { useAbortController, isAbortError } from '../hooks/useAbortController';

interface AuthGuardProps {
  children: React.ReactNode;
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const location = useLocation();
  const { getSignal, isAborted } = useAbortController();

  useEffect(() => {
    const checkAuth = async () => {
      // First check if we have a token
      if (!TokenManager.isAuthenticated()) {
        if (!isAborted()) {
          setIsAuthenticated(false);
          setIsLoading(false);
        }
        return;
      }

      try {
        // Verify token with server
        await authAPI.getProfile(getSignal());
        if (!isAborted()) {
          setIsAuthenticated(true);
        }
      } catch (error) {
        // Ignore abort errors
        if (isAbortError(error)) return;
        // Token is invalid
        TokenManager.clearTokens();
        if (!isAborted()) {
          setIsAuthenticated(false);
        }
      } finally {
        if (!isAborted()) {
          setIsLoading(false);
        }
      }
    };

    checkAuth();
  }, [getSignal, isAborted]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center">
          <svg className="animate-spin h-8 w-8 text-primary-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <p className="mt-2 text-sm text-gray-600">Verifying authentication...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Redirect to login with return URL
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
};

export default AuthGuard;