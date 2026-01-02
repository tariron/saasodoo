import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { authAPI, UserProfile, getErrorMessage } from '../utils/api';
import { useAbortController, isAbortError } from '../hooks/useAbortController';

interface UserContextType {
  profile: UserProfile | null;
  loading: boolean;
  error: string | null;
  refreshProfile: () => Promise<void>;
  clearProfile: () => void;
}

const UserContext = createContext<UserContextType | null>(null);

interface UserProviderProps {
  children: ReactNode;
}

/**
 * UserProvider - Provides user profile data to all child components.
 *
 * Benefits:
 * - Single source of truth for user data
 * - Eliminates redundant API calls across pages
 * - Profile refreshes automatically on mount
 * - Manual refresh available via refreshProfile()
 */
export const UserProvider: React.FC<UserProviderProps> = ({ children }) => {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { getSignal, isAborted } = useAbortController();

  const fetchProfile = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoading(true);
      setError(null);
      const response = await authAPI.getProfile(signal);
      if (!isAborted()) {
        setProfile(response.data);
      }
    } catch (err: unknown) {
      if (isAbortError(err)) return;
      if (!isAborted()) {
        setError(getErrorMessage(err, 'Failed to load user profile'));
        setProfile(null);
      }
    } finally {
      if (!isAborted()) {
        setLoading(false);
      }
    }
  }, [isAborted]);

  const refreshProfile = useCallback(async () => {
    await fetchProfile(getSignal());
  }, [fetchProfile, getSignal]);

  const clearProfile = useCallback(() => {
    setProfile(null);
    setError(null);
  }, []);

  // Initial fetch on mount
  useEffect(() => {
    fetchProfile(getSignal());
  }, [fetchProfile, getSignal]);

  return (
    <UserContext.Provider value={{ profile, loading, error, refreshProfile, clearProfile }}>
      {children}
    </UserContext.Provider>
  );
};

/**
 * useUser - Hook to access user profile from any component.
 *
 * Usage:
 * const { profile, loading, error, refreshProfile } = useUser();
 *
 * @throws Error if used outside of UserProvider
 */
export const useUser = (): UserContextType => {
  const context = useContext(UserContext);
  if (!context) {
    throw new Error('useUser must be used within a UserProvider');
  }
  return context;
};

export default UserContext;
