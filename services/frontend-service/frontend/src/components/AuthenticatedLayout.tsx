import React from 'react';
import AuthGuard from './AuthGuard';
import { UserProvider } from '../contexts/UserContext';

interface AuthenticatedLayoutProps {
  children: React.ReactNode;
}

/**
 * AuthenticatedLayout - Wraps protected routes with authentication and user context.
 *
 * This component ensures:
 * 1. User is authenticated (via AuthGuard)
 * 2. User profile is loaded once and shared across all child components
 * 3. No redundant profile API calls across protected pages
 *
 * Usage:
 * <Route path="/dashboard" element={<AuthenticatedLayout><Dashboard /></AuthenticatedLayout>} />
 */
const AuthenticatedLayout: React.FC<AuthenticatedLayoutProps> = ({ children }) => {
  return (
    <AuthGuard>
      <UserProvider>
        {children}
      </UserProvider>
    </AuthGuard>
  );
};

export default AuthenticatedLayout;
