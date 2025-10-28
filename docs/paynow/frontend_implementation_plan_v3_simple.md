# Paynow Frontend Integration - Simple Implementation Plan

**Version:** 3.0 (Simplified)
**Date:** 2025-10-28
**Focus:** Just make payments work - no over-engineering

---

## Current State

### Where Pay Buttons Exist:

**1. BillingInvoices page** (`/billing/invoices`)
- ✅ Has a table showing all invoices
- ✅ Each unpaid invoice has a "💳 Pay Now" button (line 266-273)
- ✅ Button opens a modal showing invoice details
- ❌ Modal currently just calls generic `makePayment()` API (doesn't work with Paynow)

**2. Billing Dashboard** (`/billing`)
- ✅ Has "Outstanding Invoices" section (line 273-316)
- ✅ Shows invoices that need payment
- ❌ **NO Pay button** - just shows text "Payment processing not yet implemented" (line 315)
- ❌ User has to navigate to `/billing/invoices` to pay

---

## What Needs to Change

### Part 1: Add Pay Buttons to Billing Dashboard

**File:** `services/frontend-service/frontend/src/pages/Billing.tsx`

**Where:** Line 300-316 (the outstanding invoices table)

**What to add:**
- Add a new column header "Actions" in the table header
- In each invoice row, add a "Pay Now" button (same as BillingInvoices page has)
- When clicked, open the payment modal (need to add modal code to this page too)

**Why:** Users should be able to pay directly from the dashboard without navigating away

---

### Part 2: Create Shared Payment Modal Component

**Current problem:**
- BillingInvoices has a modal (lines 365-425)
- Billing dashboard needs the same modal
- Don't want to duplicate code



**Option  (Better):** Create a shared component now
- Create `src/components/PaymentModal.tsx`
- Use it in both BillingInvoices and Billing
- Only maintain code in one place

---

### Part 3: Update Payment Modal for Paynow

**Current modal** (BillingInvoices.tsx lines 365-425):
```
Shows:
- Invoice number
- Amount due
- "Pay Now" button that calls generic makePayment()
- Cancel button
```

**New Paynow modal needs 3 states:**

#### State 1: Payment Method Selection

**When:** User first opens modal

**Show:**
- Invoice summary (amount, due date) ← Already exists
- **NEW: Payment method selector**
  - Radio buttons:
    - 📱 EcoCash (mobile money)
    - 📱 OneMoney (mobile money)
    - 💳 Card Payment (Visa/Mastercard)
- **NEW: Phone number input** (only show if EcoCash or OneMoney selected)
  - Text input with format: `077 123 4567`
  - Validation: Must be 10 digits starting with 07
  - Error message if invalid
- **Pay button** - Click initiates payment
- **Cancel button** - Close modal

#### State 2: Waiting for Payment

**When:** Payment initiated (mobile money only)

**Show:**
- Title: "Waiting for Payment Approval"
- Spinner animation
- Instructions: "Check your phone (***567) and approve the payment request"
- Countdown timer: "1:45 remaining"
- Current status from backend
- **Cancel button** - Stop waiting

**What happens behind the scenes:**
- Call backend API: `POST /api/billing/payments/paynow/initiate`
- Backend sends USSD to customer's phone
- Frontend polls status every 3 seconds: `GET /api/billing/payments/paynow/status/{payment_id}`
- When status changes to 'paid' or 'failed', stop polling

#### State 3: Payment Success/Failure

**When:** Payment completed

**Show (if success):**
- ✅ Big green checkmark
- "Payment Successful!"
- Payment details (amount, method, reference)
- Auto-close after 2 seconds

**Show (if failed):**
- ❌ Red X
- "Payment Failed"
- Error message (e.g., "Insufficient balance", "User cancelled")
- **Retry button** - Go back to State 1
- **Cancel button** - Close modal

---

### Part 4: The Three Payment Flows

#### Flow A: Mobile Money (EcoCash / OneMoney)

```
User clicks Pay Now
  ↓
Modal opens → User selects EcoCash
  ↓
User enters phone: 0771234567
  ↓
User clicks Pay
  ↓
Call API: initiatePaynowPayment({
  invoice_id,
  payment_method: 'ecocash',
  phone: '0771234567'
})
  ↓
Backend responds: {payment_id, status: 'pending', poll_url}
  ↓
Modal switches to "Waiting" state
  ↓
Start polling: Every 3 seconds, call getPaynowPaymentStatus(payment_id)
  ↓
Backend checks with Paynow for status
  ↓
When status = 'paid' → Show success, refresh invoices
When status = 'failed' → Show error
When 2 minutes pass → Show timeout error
```

#### Flow B: Card Payment

```
User clicks Pay Now
  ↓
Modal opens → User selects Card
  ↓
User clicks Pay (no phone needed)
  ↓
Call API: initiatePaynowPayment({
  invoice_id,
  payment_method: 'card',
  return_url: window.location.origin + '/billing/invoices?payment_return=true'
})
  ↓
Backend responds: {payment_id, redirect_url: 'https://paynow.co.zw/...'}
  ↓
Browser redirects to Paynow website
  ↓
User enters card details on Paynow
  ↓
User completes payment
  ↓
Paynow redirects back to: /billing/invoices?payment_return=true
  ↓
Frontend detects payment_return=true in URL
  ↓
Refresh invoices to show updated balance
  ↓
Show success message
```

#### Flow C: Error Handling

```
If API call fails:
- Show error message in modal
- Let user retry or cancel

If polling times out (2 minutes):
- Show "Payment timeout" message
- Explain: "Your payment may still be processing. Check back later."
- Close modal

If user cancels during waiting:
- Stop polling
- Close modal
- Note: Backend payment may still complete (that's okay)
```

---

## Implementation Steps

### Step 1: Update Types

**File:** `src/types/billing.ts`

Add new interfaces for Paynow:

```typescript
// Request sent to backend to initiate payment
interface PaynowPaymentRequest {
  invoice_id: string;
  payment_method: 'ecocash' | 'onemoney' | 'card';
  phone?: string;  // Required for mobile money
  return_url?: string;  // Required for cards
  customer_email: string;
}

// Response from backend after initiating payment
interface PaynowPaymentResponse {
  payment_id: string;
  reference: string;
  payment_type: 'mobile' | 'redirect';
  status: 'pending' | 'paid' | 'failed';
  poll_url: string;
  redirect_url?: string;  // Only for cards
  message: string;
}

// Status returned when polling
interface PaynowPaymentStatus {
  payment_id: string;
  reference: string;
  status: 'pending' | 'paid' | 'failed' | 'cancelled';
  paynow_status: string;  // Raw status from Paynow
  amount: number;
  payment_method: string;
  phone?: string;
  created_at: string;
  webhook_received: boolean;
}
```

---

### Step 2: Update API Functions

**File:** `src/utils/api.ts`

Add Paynow endpoints to billingAPI object:

```typescript
export const billingAPI = {
  // ... existing methods ...

  // NEW: Initiate Paynow payment
  initiatePaynowPayment: (request: PaynowPaymentRequest) =>
    axios.post(`${BILLING_API_URL}/payments/paynow/initiate`, request),

  // NEW: Check Paynow payment status
  getPaynowPaymentStatus: (paymentId: string) =>
    axios.get(`${BILLING_API_URL}/payments/paynow/status/${paymentId}`),
}
```

---

### Step 3: Create Polling Hook

**File:** `src/hooks/usePaymentPolling.ts` (NEW FILE)

**Purpose:** Poll payment status every 3 seconds until payment completes or times out

**What it does:**
- Takes: paymentId, enabled flag, callbacks
- Returns: status, loading, error, timeRemaining, stopPolling function
- Polls backend every 3 seconds
- Stops when status = 'paid' or 'failed'
- Times out after 2 minutes
- Calls callback functions on success/failure/timeout

**Key features:**
- Countdown timer for UX
- Proper cleanup on unmount
- Prevents memory leaks
- Prevents race conditions

**The 3 critical bug fixes go here:**

1. **No sensitive data in logs**
   - Don't log full phone numbers
   - Don't log payment details to console
   - Only log payment_id (sanitized)

2. **Fix race condition**
   - Use callback refs instead of putting callbacks in useEffect dependencies
   - Prevents multiple polling instances running at once

3. **Fix memory leak**
   - Use a `mounted` ref to track if component is still mounted
   - Check `mounted` before calling setState
   - Clear all timers in cleanup function

---

### Step 4: Update BillingInvoices Modal

**File:** `src/pages/BillingInvoices.tsx`

**What to change:**

**4.1: Add state variables:**
```typescript
const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('ecocash');
const [phoneNumber, setPhoneNumber] = useState('');
const [phoneError, setPhoneError] = useState('');
const [paymentId, setPaymentId] = useState(null);
const [pollingEnabled, setPollingEnabled] = useState(false);
const [paymentCompleted, setPaymentCompleted] = useState(false);
```

**4.2: Add polling hook:**
```typescript
const { status, loading, error, timeRemaining, stopPolling } = usePaymentPolling({
  paymentId,
  enabled: pollingEnabled,
  onSuccess: (status) => {
    setPaymentCompleted(true);
    setTimeout(() => {
      setShowPaymentModal(false);
      fetchInvoices();  // Refresh to show updated balance
    }, 2000);
  },
  onFailure: (status) => {
    setPaymentError(status.paynow_status);
  },
  onTimeout: () => {
    setPaymentError('Payment timeout');
  }
});
```

**4.3: Update processPayment function:**
```typescript
const processPayment = async () => {
  if (!selectedInvoice || !profile) return;

  // Validate phone for mobile money
  if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
    if (!phoneNumber || phoneNumber.replace(/\D/g, '').length !== 10) {
      setPhoneError('Invalid phone number');
      return;
    }
  }

  setProcessingPayment(true);

  try {
    const request = {
      invoice_id: selectedInvoice.id,
      payment_method: selectedPaymentMethod,
      customer_email: profile.email,
    };

    // Add phone for mobile money
    if (['ecocash', 'onemoney'].includes(selectedPaymentMethod)) {
      request.phone = phoneNumber.replace(/\D/g, '');  // Remove spaces
    }

    // Add return URL for cards
    if (selectedPaymentMethod === 'card') {
      request.return_url = window.location.origin + '/billing/invoices?payment_return=true';
    }

    const response = await billingAPI.initiatePaynowPayment(request);
    const paymentData = response.data;

    setPaymentId(paymentData.payment_id);

    if (paymentData.payment_type === 'mobile') {
      // Start polling
      setPollingEnabled(true);
    } else if (paymentData.payment_type === 'redirect') {
      // Redirect to Paynow
      window.location.href = paymentData.redirect_url;
    }
  } catch (err) {
    setPaymentError(err.response?.data?.message || 'Payment failed');
  } finally {
    setProcessingPayment(false);
  }
};
```

**4.4: Update modal JSX (lines 365-425):**

Replace the simple modal with the 3-state modal described in Part 3 above.

---

### Step 5: Add Pay Buttons to Billing Dashboard

**File:** `src/pages/Billing.tsx`

**5.1: Add state variables** (same as BillingInvoices):
```typescript
const [selectedInvoice, setSelectedInvoice] = useState(null);
const [showPaymentModal, setShowPaymentModal] = useState(false);
// ... all the payment state variables ...
```

**5.2: Add the handlePayInvoice function:**
```typescript
const handlePayInvoice = (invoice) => {
  setSelectedInvoice(invoice);
  setShowPaymentModal(true);
};
```

**5.3: Update outstanding invoices table (line 300-316):**

Add "Actions" column header:
```typescript
<th>Actions</th>
```

In each row, replace line 315 with:
```typescript
<button
  onClick={() => handlePayInvoice(invoice)}
  className="text-green-600 hover:text-green-900"
>
  💳 Pay Now
</button>
```

**5.4: Copy the entire payment modal from BillingInvoices:**

Add the modal JSX at the end of the component (before the closing div).

---

### Step 6: Handle Card Payment Returns

**File:** `src/pages/BillingInvoices.tsx`

**Add useEffect to detect return from Paynow:**

```typescript
useEffect(() => {
  const urlParams = new URLSearchParams(window.location.search);
  const isPaymentReturn = urlParams.get('payment_return');

  if (isPaymentReturn === 'true') {
    // User came back from Paynow card payment
    alert('Payment completed. Checking status...');

    if (customerId) {
      fetchInvoices();  // Refresh to see updated invoice
    }

    // Clean URL (remove query parameter)
    window.history.replaceState({}, '', '/billing/invoices');
  }
}, [customerId]);
```

---

## Testing Checklist

### Manual Testing with Paynow Test Numbers

**Test Numbers:**
- `0771111111` - Success (payment completes)
- `0773333333` - User cancelled
- `0774444444` - Insufficient balance

### Test Cases:

**1. EcoCash Payment - Success**
- Go to /billing/invoices
- Click "Pay Now" on an unpaid invoice
- Select EcoCash
- Enter: 0771111111
- Click Pay
- **Expect:** Waiting screen appears
- **Expect:** After ~5 seconds, status updates to "Paid"
- **Expect:** Success screen shows
- **Expect:** Modal auto-closes after 2 seconds
- **Expect:** Invoice balance updates to $0

**2. OneMoney Payment - Success**
- Same as above but select OneMoney

**3. EcoCash Payment - User Cancelled**
- Click Pay Now
- Select EcoCash
- Enter: 0773333333
- Click Pay
- **Expect:** After ~30 seconds, error message shows "User cancelled"

**4. Card Payment**
- Click Pay Now
- Select Card
- Click Pay
- **Expect:** Redirects to Paynow website (test page in staging)
- Complete payment on Paynow
- **Expect:** Redirects back to /billing/invoices
- **Expect:** Alert shows "Payment completed"
- **Expect:** Invoice refreshes

**5. Phone Validation**
- Click Pay Now
- Select EcoCash
- Try invalid phones:
  - Empty → "Phone number is required"
  - "123" → "Invalid phone number"
  - "0881234567" → "Invalid phone number" (wrong prefix)
- Enter valid: "0771234567" → Should accept

**6. Payment from Dashboard**
- Go to /billing (dashboard)
- Find outstanding invoice
- Click "Pay Now"
- **Expect:** Same modal opens
- **Expect:** Payment works same as /billing/invoices

**7. Timeout Scenario**
- Initiate EcoCash payment
- Wait 2 minutes without approving on phone
- **Expect:** Countdown reaches 0:00
- **Expect:** Error: "Payment timeout"
- **Expect:** Polling stops

**8. Cancel During Waiting**
- Initiate payment
- Click Cancel while in waiting screen
- **Expect:** Modal closes
- **Expect:** Polling stops (check no console errors)

---

## Summary of Changes

### Files to Create:
1. `src/hooks/usePaymentPolling.ts` - Polling hook with bug fixes

### Files to Modify:
1. `src/types/billing.ts` - Add Paynow types
2. `src/utils/api.ts` - Add Paynow API functions
3. `src/pages/BillingInvoices.tsx` - Update modal, add polling
4. `src/pages/Billing.tsx` - Add Pay buttons and modal

### What Gets Fixed:
1. ✅ No phone numbers in console logs
2. ✅ No race conditions in polling
3. ✅ No memory leaks
4. ✅ Users can pay from dashboard
5. ✅ Users can pay from invoices page
6. ✅ Mobile money works (EcoCash, OneMoney)
7. ✅ Card payments work (redirect flow)

---

## Environment Variables Needed

Add to `.env`:

```bash
# Optional - defaults to window.location.origin if not set
REACT_APP_PAYMENT_RETURN_URL=https://yourdomain.com/billing/invoices
```

---

## That's It!

This plan focuses on just making payments work. No over-engineering, no unnecessary complexity.

**The core loop:**
1. User clicks "Pay Now" button
2. Modal opens with payment method selector
3. User picks method and enters phone (if mobile money)
4. Click Pay → Backend sends USSD or returns redirect URL
5. Frontend polls status (mobile) or redirects (card)
6. Show success/failure
7. Done!

Keep it simple. Make it work. Improve later if needed.
