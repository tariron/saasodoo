# Frontend Paynow Payment Integration - Complete Implementation Plan

## Table of Contents
1. [Overview](#overview)
2. [Backend API Status](#backend-api-status)
3. [Implementation Strategy](#implementation-strategy)
4. [Detailed Implementation Steps](#detailed-implementation-steps)
5. [Testing Checklist](#testing-checklist)
6. [Success Criteria](#success-criteria)

---

## Overview

### Objective
Implement Paynow payment integration in the React frontend to allow customers to pay invoices using:
- 📱 **EcoCash** (mobile money - USSD push to phone)
- 📱 **OneMoney** (mobile money - USSD push to phone)
- 💳 **Card** (Visa/Mastercard via Paynow redirect)

### Why Remove Existing Payment Method Code?
The existing `BillingPayment.tsx` assumes **KillBill-managed payment methods** (credit cards stored in KillBill database). Paynow works differently:
- ✅ **Instant/External:** Customers pay on-demand, no stored payment methods
- ✅ **Mobile Money:** Customer enters phone number when paying, USSD prompt sent immediately
- ✅ **Card:** Customer redirected to Paynow's secure page, no card details stored locally

**Conclusion:** Old payment method management is not needed for Paynow integration.

---

## Backend API Status

### ✅ Already Implemented (Confirmed Working)

**Payment Initiation Endpoint:**
```
POST /api/billing/payments/paynow/initiate
```
- **For Mobile Money:** Correctly uses Paynow's `/interface/remotetransaction` endpoint
- **For Cards:** Correctly uses Paynow's `/interface/initiatetransaction` endpoint
- **Request:**
  ```json
  {
    "invoice_id": "uuid",
    "payment_method": "ecocash" | "onemoney" | "card",
    "phone": "0771234567",  // Required for mobile money
    "return_url": "https://...",  // Required for cards
    "customer_email": "user@example.com"
  }
  ```
- **Response:**
  ```json
  {
    "payment_id": "uuid",
    "reference": "INV_...",
    "payment_type": "mobile" | "redirect",
    "status": "pending",
    "poll_url": "/api/billing/payments/paynow/status/xxx",
    "redirect_url": "https://paynow.co.zw/...",  // Only for cards
    "message": "Payment request sent..."
  }
  ```

**Payment Status Polling:**
```
GET /api/billing/payments/paynow/status/{payment_id}
```
- Polls every 3 seconds from frontend
- Returns current payment status
- After 30 seconds of pending, backend polls Paynow directly
- **Response:**
  ```json
  {
    "payment_id": "uuid",
    "reference": "INV_...",
    "status": "pending" | "paid" | "failed" | "cancelled",
    "paynow_status": "Paid" | "Created" | "Failed",
    "amount": 5.00,
    "payment_method": "ecocash",
    "phone": "0771234567",
    "created_at": "2025-10-27T...",
    "webhook_received": true
  }
  ```

**Webhook Handler:**
```
POST /api/billing/webhooks/paynow
```
- Receives status updates from Paynow
- Validates hash signature
- Updates payment record
- Updates KillBill invoice balance
- Triggers instance provisioning if needed

### Key Implementation Details

**Paynow Client Methods:**
1. `initiate_mobile_transaction()` - EcoCash/OneMoney
   - Uses `/interface/remotetransaction`
   - Sends USSD push to phone immediately
   - No browser interaction needed

2. `initiate_transaction()` - Card payments
   - Uses `/interface/initiatetransaction`
   - Returns `browserurl` for redirect
   - Customer completes payment on Paynow page

---

## Implementation Strategy

### Phase 1: Cleanup Old Code
Remove KillBill payment method management since Paynow doesn't use stored payment methods.

### Phase 2: Add Paynow Types & API
Define TypeScript types and API functions for Paynow integration.

### Phase 3: Create Polling Hook
Custom React hook to poll payment status until completion.

### Phase 4: Update Invoice Payment UI
Replace generic payment modal with Paynow-specific UI.

### Phase 5: Testing
End-to-end testing with Paynow test phone numbers.

---

## Detailed Implementation Steps

### STEP 1: Update TypeScript Types

**File:** `services/frontend-service/frontend/src/types/billing.ts`

#### Remove Old Types:
```typescript
// DELETE THESE INTERFACES:
export interface PaymentMethod { ... }  // Lines 136-152
export interface CreatePaymentMethodRequest { ... }  // Lines 178-194
export interface PaymentMethodsResponse { ... }  // Lines 264-268
```

#### Add New Paynow Types:
```typescript
// ADD AFTER Invoice INTERFACE (around line 106):

/**
 * Paynow Payment Request
 * Sent to backend to initiate payment
 */
export interface PaynowPaymentRequest {
  invoice_id: string;
  payment_method: 'ecocash' | 'onemoney' | 'card';
  phone?: string; // Required for ecocash/onemoney
  return_url?: string; // Required for card
  customer_email: string; // Required for all methods
}

/**
 * Paynow Payment Response
 * Returned from backend after initiating payment
 */
export interface PaynowPaymentResponse {
  payment_id: string;           // UUID of payment record
  reference: string;             // Merchant reference (INV_xxx_xxx)
  payment_type: 'mobile' | 'redirect';  // Flow type
  status: 'pending' | 'paid' | 'failed';
  poll_url: string;             // URL to poll for status updates
  redirect_url?: string;        // Only for card payments
  message: string;              // User-friendly message
}

/**
 * Paynow Payment Status
 * Returned when polling payment status
 */
export interface PaynowPaymentStatus {
  payment_id: string;
  reference: string;
  status: 'pending' | 'paid' | 'failed' | 'cancelled';
  paynow_status: string;        // Raw Paynow status (Paid, Created, Failed, etc.)
  amount: number;
  payment_method: string;       // ecocash, onemoney, card
  phone?: string;               // For mobile money payments
  created_at: string;           // ISO timestamp
  webhook_received: boolean;    // True if webhook processed
}
```

#### Update Existing Payment Interface:
```typescript
// FIND Payment INTERFACE (around line 121) and UPDATE:
export interface Payment {
  id: string;
  account_id: string;
  invoice_id?: string;
  amount: number;
  currency: string;
  status: 'SUCCESS' | 'PENDING' | 'FAILED' | 'CANCELLED';

  // ADD THESE PAYNOW-SPECIFIC FIELDS:
  payment_method?: 'ecocash' | 'onemoney' | 'card';
  phone?: string;                    // Mobile money phone number
  paynow_reference?: string;         // Paynow's internal reference
  paynow_status?: string;            // Paynow's status string
  webhook_received_at?: string;      // When webhook was received

  gateway_error_code?: string;
  gateway_error_msg?: string;
  created_at: string;
  updated_at: string;
}
```

---

### STEP 2: Update API Functions

**File:** `services/frontend-service/frontend/src/utils/api.ts`

#### Remove Old Payment Method APIs:

**Find and DELETE these functions from `billingAPI` object:**
```typescript
// DELETE THESE:
addPaymentMethod: (request: CreatePaymentMethodRequest) => { ... },
getPaymentMethods: (customerId: string) => { ... },
deletePaymentMethod: (paymentMethodId: string) => { ... },
setDefaultPaymentMethod: (paymentMethodId: string) => { ... },
makePayment: (invoiceId: string) => { ... },  // Generic payment - replace
```

#### Add Paynow API Functions:

**Add to `billingAPI` object (after `getInvoices`):**
```typescript
export const billingAPI = {
  // ... existing methods (getAccount, createAccount, getInvoices, etc.) ...

  // ==================== PAYNOW PAYMENT METHODS ====================

  /**
   * Initiate Paynow payment for an invoice
   * Supports mobile money (EcoCash/OneMoney) and card payments
   *
   * Mobile Money Flow:
   * - Backend sends USSD push to customer's phone
   * - Customer approves on phone
   * - Frontend polls status endpoint
   *
   * Card Flow:
   * - Backend returns redirect URL
   * - Frontend redirects to Paynow payment page
   * - Customer completes payment
   * - Paynow redirects back to return_url
   */
  initiatePaynowPayment: (request: PaynowPaymentRequest): Promise<AxiosResponse<PaynowPaymentResponse>> =>
    axios.post(`${BILLING_API_URL}/payments/paynow/initiate`, request),

  /**
   * Poll Paynow payment status
   * Called repeatedly (every 3 seconds) until payment completes
   *
   * Returns:
   * - Current payment status
   * - Paynow's raw status
   * - Whether webhook has been received
   */
  getPaynowPaymentStatus: (paymentId: string): Promise<AxiosResponse<PaynowPaymentStatus>> =>
    axios.get(`${BILLING_API_URL}/payments/paynow/status/${paymentId}`),
};
```

**Full Context Example:**
```typescript
// Around line 150-200 in api.ts

export const billingAPI = {
  // Account Management
  getAccount: (customerId: string): Promise<AxiosResponse<BillingAccountResponse>> =>
    axios.get(`${BILLING_API_URL}/account/${customerId}`),

  createAccount: (customerId: string): Promise<AxiosResponse<BillingAccountResponse>> =>
    axios.post(`${BILLING_API_URL}/account`, { customer_id: customerId }),

  // Subscription Management
  getSubscriptions: (customerId: string): Promise<AxiosResponse<SubscriptionsResponse>> =>
    axios.get(`${BILLING_API_URL}/subscriptions/${customerId}`),

  createSubscription: (request: CreateSubscriptionRequest): Promise<AxiosResponse<CreateSubscriptionResponse>> =>
    axios.post(`${BILLING_API_URL}/subscriptions`, request),

  cancelSubscription: (subscriptionId: string, reason?: string): Promise<AxiosResponse<any>> =>
    axios.delete(`${BILLING_API_URL}/subscriptions/${subscriptionId}`, {
      params: { reason }
    }),

  // Invoice Management
  getInvoices: (customerId: string, page: number = 1, limit: number = 10): Promise<AxiosResponse<InvoicesResponse>> =>
    axios.get(`${BILLING_API_URL}/invoices/${customerId}`, {
      params: { page, limit }
    }),

  downloadInvoice: (invoiceId: string): Promise<AxiosResponse<Blob>> =>
    axios.get(`${BILLING_API_URL}/invoices/${invoiceId}/download`, {
      responseType: 'blob'
    }),

  // ==================== PAYNOW PAYMENT METHODS ====================

  initiatePaynowPayment: (request: PaynowPaymentRequest): Promise<AxiosResponse<PaynowPaymentResponse>> =>
    axios.post(`${BILLING_API_URL}/payments/paynow/initiate`, request),

  getPaynowPaymentStatus: (paymentId: string): Promise<AxiosResponse<PaynowPaymentStatus>> =>
    axios.get(`${BILLING_API_URL}/payments/paynow/status/${paymentId}`),

  // Plans
  getPlans: (): Promise<AxiosResponse<PlansResponse>> =>
    axios.get(`${BILLING_API_URL}/plans`),
};
```

---

### STEP 3: Remove BillingPayment Page

**File:** `services/frontend-service/frontend/src/pages/BillingPayment.tsx`

**Action:** **DELETE THIS ENTIRE FILE**

**Reason:** This page manages KillBill payment methods (credit cards, PayPal, bank accounts). Paynow doesn't use stored payment methods - customers pay on-demand.

**Alternative:** In future, could repurpose this page as "Payment History" to show past Paynow transactions.

---

### STEP 4: Update App Routes

**File:** `services/frontend-service/frontend/src/App.tsx` (or your routing file)

**Find and REMOVE this route:**
```typescript
// DELETE THIS LINE:
<Route path="/billing/payment" element={<BillingPayment />} />
```

**Full Context Example:**
```typescript
// Around line 20-50 in App.tsx

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />

        {/* Protected Routes */}
        <Route element={<AuthGuard />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/instances" element={<Instances />} />
          <Route path="/instances/create" element={<CreateInstance />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/billing" element={<Billing />} />
          <Route path="/billing/invoices" element={<BillingInvoices />} />

          {/* DELETE THIS LINE: */}
          {/* <Route path="/billing/payment" element={<BillingPayment />} /> */}

          <Route path="/billing/instances/:instanceId" element={<BillingInstanceManage />} />
        </Route>
      </Routes>
    </Router>
  );
}
```

---

### STEP 5: Create Payment Polling Hook

**New File:** `services/frontend-service/frontend/src/hooks/usePaymentPolling.ts`

**Purpose:** Custom React hook to poll payment status every 3 seconds until payment completes (success/failure) or times out (2 minutes).

**Complete Implementation:**
```typescript
import { useState, useEffect, useRef, useCallback } from 'react';
import { billingAPI } from '../utils/api';
import { PaynowPaymentStatus } from '../types/billing';

/**
 * Configuration options for payment polling hook
 */
interface UsePaymentPollingOptions {
  /** Payment ID to poll (null to disable polling) */
  paymentId: string | null;

  /** Whether polling is enabled */
  enabled: boolean;

  /** Polling interval in milliseconds (default: 3000 = 3 seconds) */
  interval?: number;

  /** Timeout in milliseconds (default: 120000 = 2 minutes) */
  timeout?: number;

  /** Callback when payment succeeds */
  onSuccess?: (status: PaynowPaymentStatus) => void;

  /** Callback when payment fails or is cancelled */
  onFailure?: (status: PaynowPaymentStatus) => void;

  /** Callback when polling times out */
  onTimeout?: () => void;
}

/**
 * Return value from payment polling hook
 */
interface UsePaymentPollingResult {
  /** Current payment status (null if not yet fetched) */
  status: PaynowPaymentStatus | null;

  /** Whether polling is active */
  loading: boolean;

  /** Error message if polling failed */
  error: string | null;

  /** Time remaining until timeout (in seconds) */
  timeRemaining: number;

  /** Function to manually stop polling */
  stopPolling: () => void;
}

/**
 * Custom hook to poll Paynow payment status
 *
 * Features:
 * - Polls every 3 seconds by default
 * - 2-minute timeout by default
 * - Countdown timer for UX
 * - Auto-cleanup on unmount
 * - Callbacks for success/failure/timeout
 *
 * Example Usage:
 * ```tsx
 * const { status, loading, timeRemaining, stopPolling } = usePaymentPolling({
 *   paymentId: paymentId,
 *   enabled: isWaiting,
 *   onSuccess: (status) => {
 *     alert('Payment successful!');
 *     refreshInvoices();
 *   },
 *   onFailure: (status) => {
 *     alert(`Payment failed: ${status.paynow_status}`);
 *   }
 * });
 * ```
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

  // Refs for timers (to enable cleanup)
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const countdownRef = useRef<NodeJS.Timeout | null>(null);
  const startTimeRef = useRef<number>(Date.now());

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
    setLoading(false);
  }, []);

  /**
   * Poll payment status from backend
   */
  const pollStatus = useCallback(async () => {
    if (!paymentId) return;

    try {
      const response = await billingAPI.getPaynowPaymentStatus(paymentId);
      const newStatus = response.data;
      setStatus(newStatus);

      // Check if payment completed (success)
      if (newStatus.status === 'paid') {
        console.log('✅ Payment successful:', newStatus);
        stopPolling();
        onSuccess?.(newStatus);
      }
      // Check if payment failed or cancelled
      else if (['failed', 'cancelled'].includes(newStatus.status)) {
        console.log('❌ Payment failed:', newStatus);
        stopPolling();
        onFailure?.(newStatus);
      }
      // Still pending, continue polling
      else {
        console.log('⏳ Payment pending:', newStatus);
      }
    } catch (err: any) {
      console.error('Error polling payment status:', err);
      setError(err.response?.data?.message || 'Failed to check payment status');
      stopPolling();
    }
  }, [paymentId, stopPolling, onSuccess, onFailure]);

  /**
   * Main effect - starts/stops polling based on enabled flag
   */
  useEffect(() => {
    // Don't poll if disabled or no payment ID
    if (!enabled || !paymentId) {
      stopPolling();
      return;
    }

    console.log('🚀 Starting payment polling:', paymentId);
    setLoading(true);
    setError(null);
    startTimeRef.current = Date.now();
    setTimeRemaining(timeout / 1000);

    // Start countdown timer (updates every second for UX)
    countdownRef.current = setInterval(() => {
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
      console.log('⏰ Payment polling timeout');
      stopPolling();
      setError('Payment timeout - please check status later');
      onTimeout?.();
    }, timeout);

    // Cleanup on unmount or when dependencies change
    return () => {
      console.log('🛑 Cleaning up payment polling');
      stopPolling();
    };
  }, [enabled, paymentId, interval, timeout, pollStatus, stopPolling, onTimeout]);

  return {
    status,
    loading,
    error,
    timeRemaining,
    stopPolling
  };
};
```

**Key Features:**
1. ✅ **Auto-polling:** Polls every 3 seconds
2. ✅ **Timeout:** Stops after 2 minutes
3. ✅ **Countdown:** Updates remaining time every second
4. ✅ **Callbacks:** Success/failure/timeout events
5. ✅ **Cleanup:** Proper cleanup on unmount
6. ✅ **Error Handling:** Catches API errors
7. ✅ **Manual Control:** `stopPolling()` function

---

### STEP 6: Update BillingInvoices.tsx - Part 1 (State & Imports)

**File:** `services/frontend-service/frontend/src/pages/BillingInvoices.tsx`

#### 6.1 Update Imports

**Add after existing imports (around line 5):**
```typescript
import React, { useState, useEffect } from 'react';
import { billingAPI, authAPI } from '../utils/api';
import { Invoice, Payment, PaynowPaymentRequest, PaynowPaymentStatus } from '../types/billing';  // UPDATE THIS LINE
import Navigation from '../components/Navigation';
import { usePaymentPolling } from '../hooks/usePaymentPolling';  // ADD THIS LINE
```

#### 6.2 Replace Payment Modal State Variables

**Find and REPLACE these state variables (around line 14-17):**

**OLD:**
```typescript
const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
const [showPaymentModal, setShowPaymentModal] = useState(false);
const [processingPayment, setProcessingPayment] = useState(false);
```

**NEW:**
```typescript
// Payment modal state
const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
const [showPaymentModal, setShowPaymentModal] = useState(false);

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
```

#### 6.3 Add Payment Polling Hook

**Add AFTER state variables (around line 30):**
```typescript
// Use payment polling hook for mobile money payments
const {
  status: paymentStatus,
  loading: polling,
  error: pollingError,
  timeRemaining,
  stopPolling
} = usePaymentPolling({
  paymentId,
  enabled: pollingEnabled,
  interval: 3000,  // Poll every 3 seconds
  timeout: 120000, // 2 minute timeout
  onSuccess: (status) => {
    console.log('Payment successful:', status);
    setPaymentCompleted(true);
    setPollingEnabled(false);
    // Close modal after 2 seconds to show success message
    setTimeout(() => {
      closePaymentModal();
      fetchInvoices(); // Refresh invoice list
    }, 2000);
  },
  onFailure: (status) => {
    console.log('Payment failed:', status);
    setPaymentError(`Payment ${status.status}: ${status.paynow_status}`);
    setPollingEnabled(false);
  },
  onTimeout: () => {
    console.log('Payment timeout');
    setPaymentError('Payment timeout - please check your payment status later');
    setPollingEnabled(false);
  }
});
```

---

### STEP 7: Update BillingInvoices.tsx - Part 2 (Payment Functions)

**File:** `services/frontend-service/frontend/src/pages/BillingInvoices.tsx`

#### 7.1 Replace Payment Functions

**Find and DELETE the old `processPayment` function (around line 84-100)**

**Add these NEW functions (around line 100):**

```typescript
/**
 * Initiate Paynow payment
 * Validates input, calls backend API, starts polling for mobile money
 */
const initiatePayment = async () => {
  if (!selectedInvoice || !profile) return;

  // Validate phone number for mobile money methods
  if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
    if (!phoneNumber) {
      setPhoneError('Phone number is required');
      return;
    }

    // Zimbabwe phone number validation: 07X XXX XXXX
    const phoneRegex = /^07[0-9]{8}$/;
    const cleanPhone = phoneNumber.replace(/\s/g, '');

    if (!phoneRegex.test(cleanPhone)) {
      setPhoneError('Invalid phone number. Format: 0771234567');
      return;
    }
  }

  setInitiatingPayment(true);
  setPaymentError(null);

  try {
    // Build request payload
    const request: PaynowPaymentRequest = {
      invoice_id: selectedInvoice.id,
      payment_method: selectedPaymentMethod,
      customer_email: profile.email,
    };

    // Add phone for mobile money
    if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
      request.phone = phoneNumber.replace(/\s/g, '');
    }

    // Add return URL for card payments
    if (selectedPaymentMethod === 'card') {
      request.return_url = `${window.location.origin}/billing/invoices?payment_return=true`;
    }

    console.log('Initiating payment:', request);

    // Call backend API
    const response = await billingAPI.initiatePaynowPayment(request);
    const paymentData = response.data;

    console.log('Payment initiated:', paymentData);

    // Store payment ID
    setPaymentId(paymentData.payment_id);

    // Handle based on payment type
    if (paymentData.payment_type === 'mobile') {
      // Mobile money: Start polling
      setPollingEnabled(true);
    } else if (paymentData.payment_type === 'redirect' && paymentData.redirect_url) {
      // Card: Redirect to Paynow
      console.log('Redirecting to Paynow:', paymentData.redirect_url);
      window.location.href = paymentData.redirect_url;
    } else {
      setPaymentError('Invalid payment response from server');
    }
  } catch (err: any) {
    console.error('Payment initiation error:', err);
    const errorMessage = err.response?.data?.detail ||
                        err.response?.data?.message ||
                        'Failed to initiate payment. Please try again.';
    setPaymentError(errorMessage);
  } finally {
    setInitiatingPayment(false);
  }
};

/**
 * Close payment modal and reset all state
 */
const closePaymentModal = () => {
  setShowPaymentModal(false);
  setSelectedInvoice(null);
  setSelectedPaymentMethod('ecocash');
  setPhoneNumber('');
  setPhoneError('');
  setPaymentId(null);
  setPollingEnabled(false);
  setPaymentCompleted(false);
  setPaymentError(null);
  stopPolling();
};

/**
 * Open payment modal for an invoice
 */
const handlePayInvoice = async (invoice: Invoice) => {
  console.log('Opening payment modal for invoice:', invoice.id);
  setSelectedInvoice(invoice);
  setShowPaymentModal(true);

  // Reset all payment state
  setSelectedPaymentMethod('ecocash');
  setPhoneNumber('');
  setPhoneError('');
  setPaymentId(null);
  setPollingEnabled(false);
  setPaymentCompleted(false);
  setPaymentError(null);
};

/**
 * Format phone number as user types
 * Formats: 0771234567 → 077 123 4567
 */
const formatPhoneNumber = (value: string): string => {
  // Remove all non-digits
  const digits = value.replace(/\D/g, '');

  // Limit to 10 digits (Zimbabwe phone number length)
  const limited = digits.slice(0, 10);

  // Format as 077 123 4567
  if (limited.length <= 3) {
    return limited;
  } else if (limited.length <= 6) {
    return `${limited.slice(0, 3)} ${limited.slice(3)}`;
  } else {
    return `${limited.slice(0, 3)} ${limited.slice(3, 6)} ${limited.slice(6)}`;
  }
};
```

#### 7.2 Add Card Payment Return Handler

**Add AFTER existing useEffect hooks (around line 55):**

```typescript
/**
 * Handle return from Paynow card payment redirect
 * Checks URL for payment_return parameter
 */
useEffect(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const isPaymentReturn = urlParams.get('payment_return');

  if (isPaymentReturn === 'true') {
    console.log('Returned from Paynow card payment');

    // Show notification
    alert('Payment completed. Checking status...');

    // Refresh invoices to see updated balance
    if (customerId) {
      fetchInvoices();
    }

    // Clean URL (remove query parameter)
    window.history.replaceState({}, '', '/billing/invoices');
  }
}, [customerId]);
```

---

### STEP 8: Update BillingInvoices.tsx - Part 3 (Payment Modal JSX)

**File:** `services/frontend-service/frontend/src/pages/BillingInvoices.tsx`

**Find the Payment Modal section (around line 364-425)**

**REPLACE THE ENTIRE MODAL with this new implementation:**

```typescript
{/* Paynow Payment Modal */}
{showPaymentModal && selectedInvoice && (
  <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
    <div className="relative top-20 mx-auto p-5 border w-full max-w-md shadow-lg rounded-md bg-white">
      <div className="mt-3">
        {/* STEP 1: Payment Method Selection */}
        {!pollingEnabled && !paymentCompleted ? (
          <>
            <h3 className="text-lg font-medium text-gray-900 mb-4">
              Pay Invoice #{selectedInvoice.invoice_number}
            </h3>

            {/* Invoice Summary */}
            <div className="mb-4 p-4 bg-gray-50 rounded-lg">
              <div className="flex justify-between mb-2">
                <span className="text-sm text-gray-600">Amount Due:</span>
                <span className="font-medium text-red-600">
                  {formatCurrency(selectedInvoice.balance, selectedInvoice.currency)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">Due Date:</span>
                <span className="text-sm">{formatDate(selectedInvoice.target_date)}</span>
              </div>
            </div>

            {/* Payment Method Selector */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-3">
                Select Payment Method
              </label>

              {/* EcoCash Option */}
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

              {/* OneMoney Option */}
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

              {/* Card Option */}
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
                  ℹ️ A payment request will be sent to your phone
                </p>
              </div>
            )}

            {/* Card Payment Info */}
            {selectedPaymentMethod === 'card' && (
              <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md">
                <p className="text-sm text-blue-800">
                  ℹ️ You will be redirected to Paynow's secure payment page to complete your card payment.
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
                  `Pay ${formatCurrency(selectedInvoice.balance, selectedInvoice.currency)}`
                )}
              </button>
              <button
                onClick={closePaymentModal}
                disabled={initiatingPayment}
                className="flex-1 bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </>
        )

        {/* STEP 2: Waiting for Payment Approval */}
        : pollingEnabled && !paymentCompleted ? (
          <div className="text-center">
            <h3 className="text-lg font-medium text-gray-900 mb-6">
              ⏳ Waiting for Payment Approval
            </h3>

            {/* Spinner Animation */}
            <div className="mb-6">
              <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-600 mx-auto"></div>
            </div>

            {/* Instructions */}
            <div className="mb-6 p-4 bg-blue-50 rounded-lg">
              <p className="text-sm text-gray-800 mb-2">
                Check your phone ({phoneNumber.replace(/(\d{3})(\d{3})(\d{4})/, '$1****$3')})
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
              onClick={() => {
                stopPolling();
                closePaymentModal();
              }}
              className="w-full bg-gray-300 text-gray-700 px-4 py-2 rounded-md hover:bg-gray-400"
            >
              Cancel
            </button>

            <p className="text-xs text-gray-500 mt-3">
              Note: Canceling will stop checking status. Your payment may still be processing.
            </p>
          </div>
        )

        {/* STEP 3: Payment Successful */}
        : paymentCompleted ? (
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
                    {formatCurrency(paymentStatus.amount, selectedInvoice.currency)}
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
        ) : null}
      </div>
    </div>
  </div>
)}
```

---

### STEP 9: Testing Checklist

#### Manual Testing Steps

**Prerequisites:**
- ✅ Paynow integration must be in **test mode**
- ✅ Use merchant email registered with Paynow
- ✅ Have unpaid invoice in system

#### Test Case 1: EcoCash Payment - Success

**Steps:**
1. Navigate to `/billing/invoices`
2. Find invoice with balance > 0
3. Click "Pay Now" button
4. Select "EcoCash" payment method
5. Enter phone: `0771111111` (Paynow test success number)
6. Click "Pay $X.XX"

**Expected Results:**
- ✅ Modal switches to "Waiting" state
- ✅ Countdown timer appears (2:00)
- ✅ Spinner animation shows
- ✅ After ~5 seconds, status changes to "Paid"
- ✅ Success screen appears with green checkmark
- ✅ Modal auto-closes after 2 seconds
- ✅ Invoice list refreshes
- ✅ Invoice balance shows $0.00
- ✅ Invoice status changes to "PAID" or similar

**Console Logs to Check:**
```
🚀 Starting payment polling: {payment_id}
⏳ Payment pending: {status}
✅ Payment successful: {status}
```

#### Test Case 2: OneMoney Payment - Success

**Steps:**
1. Same as Test Case 1, but select "OneMoney"
2. Use phone: `0771111111`

**Expected Results:**
- Same as Test Case 1

#### Test Case 3: EcoCash Payment - User Declined

**Steps:**
1. Click "Pay Now"
2. Select "EcoCash"
3. Enter phone: `0773333333` (Paynow test declined number)
4. Click "Pay"

**Expected Results:**
- ✅ Waiting screen appears
- ✅ After ~30 seconds, error message shows
- ✅ Message: "Payment failed: User Cancelled" or similar
- ✅ Poll stops automatically
- ✅ User can close modal

#### Test Case 4: EcoCash Payment - Insufficient Balance

**Steps:**
1. Click "Pay Now"
2. Select "EcoCash"
3. Enter phone: `0774444444` (Paynow test insufficient balance)
4. Click "Pay"

**Expected Results:**
- ✅ Error shown immediately or within 5 seconds
- ✅ Message about insufficient balance
- ✅ User can retry with different method

#### Test Case 5: Card Payment (Redirect)

**Steps:**
1. Click "Pay Now"
2. Select "Card Payment"
3. Click "Pay"

**Expected Results:**
- ✅ Page redirects to Paynow payment page
- ✅ In test mode, shows Paynow test page
- ✅ Complete payment on Paynow page
- ✅ Redirects back to `/billing/invoices?payment_return=true`
- ✅ Alert shows "Payment completed. Checking status..."
- ✅ Invoice list refreshes
- ✅ URL cleaned (no query parameter)

#### Test Case 6: Phone Number Validation

**Steps:**
1. Click "Pay Now"
2. Select "EcoCash"
3. Try invalid phone numbers:
   - Empty → Should show "Phone number is required"
   - `123` → Should show "Invalid phone number"
   - `08712345678` → Should show "Invalid phone number" (not 07X)
   - `0771234` → Should show "Invalid phone number" (too short)
4. Enter valid: `0771234567` → Should accept

**Expected Results:**
- ✅ All validations work correctly
- ✅ Error messages clear when user types
- ✅ Auto-formatting applies (077 123 4567)

#### Test Case 7: Payment Timeout

**Steps:**
1. Click "Pay Now"
2. Select "EcoCash"
3. Enter valid phone
4. Click "Pay"
5. Wait 2 minutes without approving on phone

**Expected Results:**
- ✅ Countdown reaches 0:00
- ✅ Error message: "Payment timeout - please check status later"
- ✅ Polling stops
- ✅ User can close modal

#### Test Case 8: Cancel During Waiting

**Steps:**
1. Initiate EcoCash payment
2. While waiting screen is showing, click "Cancel"

**Expected Results:**
- ✅ Modal closes immediately
- ✅ Polling stops (check console for cleanup log)
- ✅ Invoice list remains unchanged
- ✅ No memory leaks (timers cleared)

#### Test Case 9: Multiple Payments

**Steps:**
1. Pay invoice A with EcoCash → Success
2. Immediately pay invoice B with OneMoney → Success
3. Pay invoice C with Card → Success

**Expected Results:**
- ✅ Each payment processes independently
- ✅ No state conflicts between payments
- ✅ All invoices update correctly

#### Test Case 10: Network Error

**Steps:**
1. Open DevTools → Network tab
2. Set throttling to "Offline"
3. Try to initiate payment

**Expected Results:**
- ✅ Error message shows
- ✅ User can retry when back online
- ✅ No crash or infinite loading

---

### STEP 10: Browser Console Debugging

**Expected Console Logs (Successful Payment):**

```
Opening payment modal for invoice: 4fdf2d3e-1c74-467c-ba21-7e8de76a73d2
Initiating payment: {invoice_id: "...", payment_method: "ecocash", phone: "0771111111", ...}
Payment initiated: {payment_id: "...", payment_type: "mobile", status: "pending", ...}
🚀 Starting payment polling: 3509772a-2176-46d8-82f8-90c92bc92bed
⏳ Payment pending: {status: "pending", paynow_status: "Created", ...}
⏳ Payment pending: {status: "pending", paynow_status: "Sent", ...}
✅ Payment successful: {status: "paid", paynow_status: "Paid", ...}
🛑 Cleaning up payment polling
```

**Error Indicators:**
- `❌ Payment failed:` - Payment was declined/cancelled
- `⏰ Payment polling timeout` - 2 minute timeout reached
- `Error polling payment status:` - Network/API error

---

## Success Criteria

### Functional Requirements
- ✅ User can pay invoice with EcoCash (mobile money)
- ✅ User can pay invoice with OneMoney (mobile money)
- ✅ User can pay invoice with Card (Paynow redirect)
- ✅ Mobile money shows waiting screen with countdown
- ✅ Polling updates status every 3 seconds
- ✅ Payment success updates invoice balance to $0
- ✅ Payment success triggers KillBill update (via webhook)
- ✅ Card payment redirects to Paynow and back
- ✅ Proper validation on phone numbers
- ✅ Error messages are user-friendly

### Technical Requirements
- ✅ No memory leaks (timers cleaned up on unmount)
- ✅ Proper TypeScript types throughout
- ✅ Console logs for debugging
- ✅ No old payment method code remains
- ✅ Responsive design (mobile-friendly)
- ✅ Works in Chrome, Firefox, Safari
- ✅ Proper error handling (network, API, validation)

### User Experience
- ✅ Clear instructions at each step
- ✅ Visual feedback (spinners, countdowns)
- ✅ Success/failure states clearly shown
- ✅ Can cancel during waiting
- ✅ Auto-refresh after success
- ✅ Loading states prevent double-clicks

---

## File Change Summary

### Files to DELETE:
1. ✅ `services/frontend-service/frontend/src/pages/BillingPayment.tsx`

### Files to CREATE:
1. ✅ `services/frontend-service/frontend/src/hooks/usePaymentPolling.ts`
2. ✅ `docs/paynow/frontend_implementation_plan.md` (this file)

### Files to MODIFY:
1. ✅ `services/frontend-service/frontend/src/types/billing.ts`
   - Remove: PaymentMethod, CreatePaymentMethodRequest, PaymentMethodsResponse
   - Add: PaynowPaymentRequest, PaynowPaymentResponse, PaynowPaymentStatus
   - Update: Payment interface (add paynow fields)

2. ✅ `services/frontend-service/frontend/src/utils/api.ts`
   - Remove: addPaymentMethod, getPaymentMethods, deletePaymentMethod, setDefaultPaymentMethod, makePayment
   - Add: initiatePaynowPayment, getPaynowPaymentStatus

3. ✅ `services/frontend-service/frontend/src/pages/BillingInvoices.tsx`
   - Update imports (add usePaymentPolling)
   - Replace payment modal state
   - Add payment polling hook
   - Replace processPayment → initiatePayment
   - Add closePaymentModal, formatPhoneNumber
   - Replace entire payment modal JSX
   - Add card payment return handler

4. ✅ `services/frontend-service/frontend/src/App.tsx`
   - Remove: `/billing/payment` route

---

## Implementation Timeline

**Phase 1: Foundation (1-2 hours)**
1. ✅ Update types (billing.ts) - 15 min
2. ✅ Update API (api.ts) - 15 min
3. ✅ Create polling hook (usePaymentPolling.ts) - 30 min
4. ✅ Delete BillingPayment.tsx and route - 5 min

**Phase 2: UI Implementation (3-4 hours)**
1. ✅ Update BillingInvoices state - 30 min
2. ✅ Add payment functions - 45 min
3. ✅ Implement payment modal UI - 2 hours
4. ✅ Add phone formatting & validation - 30 min

**Phase 3: Testing & Polish (1-2 hours)**
1. ✅ Test all payment methods - 45 min
2. ✅ Test error scenarios - 30 min
3. ✅ Mobile responsive check - 15 min
4. ✅ Fix bugs - 30 min

**Total Estimated Time: 5-8 hours**

---

## Support & Troubleshooting

### Common Issues

**1. Payment stays pending forever**
- **Cause:** Webhook not received (local dev - Paynow can't reach localhost)
- **Solution:** After 30 seconds, backend polls Paynow directly. Status should update.

**2. "Invalid hash" error**
- **Cause:** PAYNOW_INTEGRATION_KEY doesn't match
- **Solution:** Check `.env` file, restart billing-service

**3. Phone number validation fails**
- **Cause:** Phone format not matching regex
- **Solution:** Use `07XXXXXXXX` format (10 digits starting with 07)

**4. Card redirect doesn't return**
- **Cause:** Return URL not accessible
- **Solution:** Ensure return URL matches your actual domain

### Debug Commands

**Check payment in database:**
```bash
docker exec saasodoo-postgres psql -U billing_service -d billing \
  -c "SELECT id, payment_method, payment_status, paynow_status, phone FROM payments WHERE id = 'PAYMENT_ID';"
```

**Check invoice balance:**
```bash
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/invoices/INVOICE_ID" | jq '.balance'
```

**Check billing-service logs:**
```bash
docker logs saasodoo-billing-service | grep -i paynow
```

---

## Next Steps (Future Enhancements)

**Not in Initial Implementation:**

1. **Payment History Page**
   - Repurpose BillingPayment.tsx as payment history
   - Show all past Paynow transactions
   - Filter by status, date, method

2. **Save Payment Preferences**
   - Remember last-used payment method
   - Save phone numbers (encrypted)
   - Quick pay with saved info

3. **Payment Receipts**
   - Generate PDF receipt after success
   - Email confirmation
   - Download from UI

4. **Better Error Messages**
   - Map Paynow error codes to user-friendly messages
   - Suggest solutions (e.g., "Check your balance")
   - Retry button for transient errors

5. **Analytics**
   - Track payment success rates
   - Monitor failure reasons
   - A/B test payment UI

6. **Bulk Payments**
   - Pay multiple invoices at once
   - Combined total

---

**End of Implementation Plan**
