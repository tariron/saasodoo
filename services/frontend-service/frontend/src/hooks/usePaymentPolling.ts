import { useState, useEffect, useRef, useCallback } from 'react';
import { billingAPI } from '../utils/api';
import { PaynowPaymentStatus } from '../types/billing';

interface UsePaymentPollingOptions {
  paymentId: string | null;
  enabled: boolean;
  interval?: number;
  timeout?: number;
  onSuccess?: (status: PaynowPaymentStatus) => void;
  onFailure?: (status: PaynowPaymentStatus) => void;
  onTimeout?: () => void;
}

interface UsePaymentPollingResult {
  status: PaynowPaymentStatus | null;
  loading: boolean;
  error: string | null;
  timeRemaining: number;
  stopPolling: () => void;
}

/**
 * Custom hook to poll Paynow payment status
 *
 * Features:
 * - Polls every 3 seconds by default
 * - 2-minute timeout by default
 * - Countdown timer for UX
 * - Proper cleanup on unmount
 *
 * Bug Fixes:
 * 1. No sensitive data logged to console
 * 2. Race condition prevented with callback refs
 * 3. Memory leak prevented with mounted ref
 */
export const usePaymentPolling = ({
  paymentId,
  enabled,
  interval = 3000,
  timeout = 120000,
  onSuccess,
  onFailure,
  onTimeout
}: UsePaymentPollingOptions): UsePaymentPollingResult => {
  // State
  const [status, setStatus] = useState<PaynowPaymentStatus | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<number>(timeout / 1000);

  // Refs for timers
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(Date.now());

  // BUG FIX #3: Prevent memory leaks - track if component is mounted
  const mountedRef = useRef<boolean>(true);

  // BUG FIX #2: Prevent race conditions - use callback refs
  const onSuccessRef = useRef(onSuccess);
  const onFailureRef = useRef(onFailure);
  const onTimeoutRef = useRef(onTimeout);

  // Update callback refs when callbacks change
  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onFailureRef.current = onFailure;
    onTimeoutRef.current = onTimeout;
  }, [onSuccess, onFailure, onTimeout]);

  // Track mounted state
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /**
   * Stop all polling and cleanup timers
   */
  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    // BUG FIX #3: Only update state if still mounted
    if (mountedRef.current) {
      setLoading(false);
    }
  }, []);

  /**
   * Poll payment status from backend
   */
  const pollStatus = useCallback(async () => {
    // BUG FIX #3: Check if still mounted before proceeding
    if (!paymentId || !mountedRef.current) return;

    try {
      const response = await billingAPI.getPaynowPaymentStatus(paymentId);

      // BUG FIX #3: Check if still mounted before setting state
      if (!mountedRef.current) return;

      const newStatus = response.data;
      setStatus(newStatus);

      // Check if payment completed (success)
      if (newStatus.status === 'paid') {
        // BUG FIX #1: Don't log sensitive data - only log payment_id
        if (process.env.NODE_ENV === 'development') {
          console.log('[Payment] Payment completed:', paymentId);
        }
        stopPolling();
        onSuccessRef.current?.(newStatus);
      }
      // Check if payment failed or cancelled
      else if (['failed', 'cancelled'].includes(newStatus.status)) {
        if (process.env.NODE_ENV === 'development') {
          console.log('[Payment] Payment failed/cancelled:', paymentId);
        }
        stopPolling();
        onFailureRef.current?.(newStatus);
      }
      // Still pending, continue polling
      else {
        if (process.env.NODE_ENV === 'development') {
          console.log('[Payment] Payment pending:', paymentId);
        }
      }
    } catch (err: any) {
      console.error('[Payment] Error polling payment status:', err.message);

      // BUG FIX #3: Check if still mounted before setting state
      if (!mountedRef.current) return;

      setError(err.response?.data?.message || 'Failed to check payment status');
      stopPolling();
    }
  }, [paymentId, stopPolling]);

  /**
   * Main effect - starts/stops polling based on enabled flag
   */
  useEffect(() => {
    // Don't poll if disabled or no payment ID
    if (!enabled || !paymentId) {
      stopPolling();
      return;
    }

    if (process.env.NODE_ENV === 'development') {
      console.log('[Payment] Starting payment polling:', paymentId);
    }

    setLoading(true);
    setError(null);
    startTimeRef.current = Date.now();
    setTimeRemaining(timeout / 1000);

    // Start countdown timer (updates every second for UX)
    countdownRef.current = setInterval(() => {
      // BUG FIX #3: Check if still mounted
      if (!mountedRef.current) return;

      const elapsed = Date.now() - startTimeRef.current;
      const remaining = Math.max(0, Math.ceil((timeout - elapsed) / 1000));
      setTimeRemaining(remaining);
    }, 1000);

    // Poll immediately on start
    pollStatus();

    // Set up polling interval
    intervalRef.current = setInterval(pollStatus, interval);

    // Set up timeout
    timeoutRef.current = setTimeout(() => {
      if (process.env.NODE_ENV === 'development') {
        console.log('[Payment] Payment polling timeout:', paymentId);
      }
      stopPolling();

      // BUG FIX #3: Check if still mounted before setting state
      if (mountedRef.current) {
        setError('Payment timeout - please check status later');
      }

      onTimeoutRef.current?.();
    }, timeout);

    // Cleanup on unmount or when dependencies change
    return () => {
      if (process.env.NODE_ENV === 'development') {
        console.log('[Payment] Cleaning up payment polling:', paymentId);
      }
      stopPolling();
    };
    // BUG FIX #2: Remove callback dependencies to prevent race conditions
  }, [enabled, paymentId, interval, timeout, pollStatus, stopPolling]);

  return {
    status,
    loading,
    error,
    timeRemaining,
    stopPolling
  };
};
