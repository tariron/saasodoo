import { useEffect, useRef, useCallback } from 'react';

/**
 * Custom hook that provides an AbortController for cancelling async operations.
 * Automatically aborts on component unmount to prevent memory leaks.
 *
 * Usage:
 * const { getSignal, isAborted } = useAbortController();
 *
 * useEffect(() => {
 *   const fetchData = async () => {
 *     try {
 *       const response = await api.get('/data', { signal: getSignal() });
 *       if (!isAborted()) setData(response.data);
 *     } catch (err) {
 *       if (!isAborted()) setError(err);
 *     }
 *   };
 *   fetchData();
 * }, [getSignal, isAborted]);
 */
export const useAbortController = () => {
  const abortControllerRef = useRef<AbortController | null>(null);
  const isMountedRef = useRef(true);

  // Create a new AbortController and return its signal
  const getSignal = useCallback(() => {
    // Abort any previous controller
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    // Create new controller
    abortControllerRef.current = new AbortController();
    return abortControllerRef.current.signal;
  }, []);

  // Check if the component is still mounted
  const isAborted = useCallback(() => {
    return !isMountedRef.current;
  }, []);

  // Manually abort current request
  const abort = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return { getSignal, isAborted, abort };
};

/**
 * Check if an error is an abort error (request was cancelled)
 */
export const isAbortError = (error: unknown): boolean => {
  if (error instanceof Error) {
    return error.name === 'AbortError' || error.name === 'CanceledError';
  }
  return false;
};
