TRIAL LOGIC OVERHAUL - CHANGE PLAN
EXECUTIVE SUMMARY
Transform the trial system from "trial as a plan feature" to "trial as a user entitlement" by implementing trial invisibility - users who are ineligible for trials never see any trial-related UI or messaging.

CORE PROBLEM STATEMENT
Current State:

Trial information is tied to plan definitions (static)
Every user sees "14 day trial" regardless of eligibility
Frontend does client-side eligibility checking with different logic than backend
Users who already used trials see confusing "trial not available" warnings
Trial eligibility validation has a critical bug that allows multiple trials
Desired State:

Trial visibility is tied to user eligibility (dynamic)
Only eligible users see any trial information
Single source of truth for eligibility (backend API)
Ineligible users never see the word "trial" anywhere
Robust validation prevents multiple trials per customer
PHASE 1: BACKEND CHANGES
Change 1.1: Fix Trial Eligibility Validation Bug
Location: Billing service subscription creation endpoint

Current Logic Problem: The validation checks if the last subscription in the loop is a trial AND if the trial count is greater than zero. This condition can never properly validate because it checks the individual subscription's phase type after the loop has counted trials.

Required Change: Separate the counting logic from the validation logic. First, iterate through all subscriptions and count how many are trials. Then, after the loop completes, check if that count exceeds the allowed limit.

Impact: This prevents users from creating multiple trial subscriptions, enforcing the "one trial per customer" business rule.

Change 1.2: Create Trial Eligibility API Endpoint
Location: New endpoint in billing service

Purpose: Create a single source of truth for trial eligibility that both frontend and backend use.

Endpoint Behavior: When called with a customer ID, this endpoint should:

Query KillBill to get all subscriptions for the customer
Check subscription history to see if customer ever had a trial (historical check)
Check current subscriptions to see if customer has an active trial (current check)
Check if customer has any active subscriptions at all
Apply business rules to determine eligibility
Return detailed response including eligibility status and a flag specifically for UI rendering
Response Structure: The response needs to include:

Boolean indicating if customer is eligible for a trial
Boolean flag specifically telling the UI whether to show trial information
Number of trial days available (14 if eligible, 0 if not)
Whether customer has any active subscriptions
Count of total subscriptions (for analytics)
Reason code for the eligibility decision (for logging, not shown to user)
Business Rules to Implement:

Customer is ineligible if they have ever had a trial subscription in the past (lifetime limit)
Customer is ineligible if they currently have an active trial
These rules apply across all plans - one trial per customer account, period
Error Handling: If the eligibility check fails due to system errors, default to allowing the trial (fail open) to avoid blocking legitimate new customers. Log the error for investigation.

Change 1.3: Update Subscription Creation Validation
Location: Billing service subscription creation endpoint

Required Change: Before creating a subscription where the phase type is "TRIAL", call the new trial eligibility API endpoint. If the endpoint returns ineligible, reject the subscription creation with a clear error response.

Error Response Structure: Return an error that includes:

Error code identifying this as a trial eligibility issue
Generic message suitable for display
Reason code for debugging (not shown to user)
Impact: This creates a second layer of validation at the point of subscription creation, preventing trial creation even if frontend validation is bypassed.

Change 1.4: Create Shared Type Definitions
Location: Shared schemas directory

Purpose: Define the data structures for trial eligibility responses so backend and frontend use consistent types.

Required Definitions:

Trial eligibility response structure with all fields
Enumeration of possible eligibility reason codes
Ensure these types are available to both backend and frontend
PHASE 2: FRONTEND CHANGES
Change 2.1: Add Trial Eligibility API Client
Location: Frontend API client module

Required Change: Add a method that calls the new backend trial eligibility endpoint and returns the typed response.

Location: Frontend type definitions

Required Change: Import or define the trial eligibility response types to ensure type safety.

Change 2.2: Replace Client-Side Eligibility Logic
Location: CreateInstance page component

Current Logic: The page currently fetches all subscriptions and checks if any subscription event has a phase that includes "trial". This is an incomplete check that doesn't match backend logic.

Required Change: Replace this entire eligibility checking logic with a single call to the new trial eligibility API endpoint. Store the full response object in component state instead of just a boolean.

State Management Change: Instead of storing a simple boolean for "trialEligible", store the entire eligibility response object. This provides access to all the eligibility information including the critical "can_show_trial_info" flag.

Change 2.3: Implement Plan Data Transformation
Location: CreateInstance page component

Purpose: Transform plan data before rendering based on user eligibility, removing all trial information for ineligible users.

Required Logic: Create a function that takes a plan object and the eligibility response, and returns a modified plan object. The logic should:

Check the "can_show_trial_info" flag from the eligibility response
If false, zero out all trial-related fields (trial_length, trial_time_unit)
Add a "display_trial" flag to the plan object indicating whether trial UI should render
Return the transformed plan
Why This Matters: This single transformation ensures that all downstream rendering logic has the correct data. Plans for ineligible users will have no trial information.

Change 2.4: Update Plan Card Rendering
Location: CreateInstance page plan card display

Current Behavior: Plan cards show trial badges and trial pricing based on the plan definition, resulting in all users seeing trial information.

Required Changes:

Trial Badge: Only render the trial badge if the transformed plan has "display_trial" set to true. The badge should never appear for ineligible users.

Pricing Display: Implement conditional pricing display:

If display_trial is true: Show "$0 for X days, then $Y/month"
If display_trial is false: Show only "$Y/month"
Plan Description: No mention of trials in the description for ineligible users. Keep descriptions generic and focused on features.

Change 2.5: Update Trial Choice Section
Location: CreateInstance page trial/paid selection area

Current Behavior: After selecting a plan, users see a choice between starting with trial or starting with paid subscription. If ineligible, a warning message appears but the choice section still shows.

Required Changes:

Conditional Rendering: Only render the entire "How would you like to start?" section if the selected plan has "display_trial" set to true.

For Eligible Users: Show two radio button options:

Start with free trial (with clear explanation of $0 now, then price after trial)
Skip trial and start paid (with clear explanation of immediate billing)
For Ineligible Users: Don't render the choice section at all. Include a hidden form field that automatically sets the phase type to "EVERGREEN" (paid). The user moves directly from plan selection to instance configuration.

Remove Warning Message: Delete the entire warning block that says "Trial not available - You have already used your free trial". This message should never appear because ineligible users won't see trial information at all.

Change 2.6: Update Form Submission Logic
Location: CreateInstance page form submission handler

Required Change: Update the logic that determines which phase type to send to the backend:

If the plan has "display_trial" true, use whatever the user selected (TRIAL or EVERGREEN)
If the plan has "display_trial" false, always use EVERGREEN
Never send undefined or null for phase type
Response Handling: After submission:

If trial was selected and started: Show success message mentioning trial, redirect to instances
If paid was selected: Show payment modal immediately
If backend returns trial eligibility error: Show generic error message (shouldn't happen if frontend logic is correct)
Change 2.7: Update Billing Dashboard Trial Display
Location: Billing dashboard page

Current Behavior: Shows trial information banner based on trial_info data structure.

Required Change: Only render the trial banner if the user currently has an active trial subscription. Don't show trial information for:

Users who completed trials in the past
Users who never had trials
Users with only paid subscriptions
Banner Content: When shown, the banner should display:

Clear indication that a trial is active
Trial end date
Days remaining
For trials ending in 3 days or less: Additional warning and prompt to add payment method
Change 2.8: Add Trial Countdown to Instance Cards
Location: Instance list/cards component

Required Change: When rendering an instance with billing_status of "trial", add additional UI elements:

Badge showing "Trial" status
Countdown showing days remaining
Trial end date
For trials with less than 3 days remaining: Visual emphasis (color change, icon)
For Non-Trial Instances: Continue showing existing billing status badges (Paid, Payment Required) without any trial information.

Change 2.9: Update Styling
Location: CSS files for CreateInstance and related components

Required Changes:

Style for trial badge (green, prominent, only shown when applicable)
Style for trial choice radio buttons (clear visual distinction)
Style for trial countdown in instance cards (warning colors for expiring trials)
Ensure plans without trial information look clean and complete (not like something is missing)
Remove any styling related to trial warning messages
PHASE 3: NOTIFICATIONS & MONITORING
Change 3.1: Trial Expiration Email Notifications
Location: Notification service

Required Changes: Create a new notification type for trial expiration warnings with an email template that includes:

Days remaining until trial ends
Trial end date
What happens after trial ends (billing starts)
Call to action to add payment method
Pricing information for the subscription
Link to billing page
Add an endpoint that accepts trial expiration notification data and sends the email.

Change 3.2: Trial Monitoring Background Job
Location: Instance service Celery tasks

Required Changes: Create a new Celery task that runs on a daily schedule and:

Queries all instances with billing_status of "trial"
For each trial instance, gets the trial end date from the billing service
Calculates days remaining until trial expiration
At specific thresholds (7 days, 3 days, 1 day), triggers notification emails
Logs all notification attempts for audit purposes
Celery Beat Configuration: Schedule this task to run once daily at a consistent time (e.g., 9 AM).

Change 3.3: Trial Expiration Warning Banner
Location: Instance list page

Required Change: Add a prominent banner at the top of the instances page that appears when:

User has at least one instance with trial status
That trial has 3 or fewer days remaining
The trial has not yet expired
Banner Content:

Clear warning that trial is ending soon
Days remaining
Explanation of what happens if no payment method is added
Call to action button/link to billing page
When Not to Show: Don't show this banner for users with no active trials or trials with more than 3 days remaining.

CONFIGURATION & SHARED CONSTANTS
Change: Create Trial Constants
Location: Shared constants or configuration file

Purpose: Centralize trial-related constants to avoid hardcoding values throughout the application.

Required Constants:

Phase type values (TRIAL, EVERGREEN)
Trial eligibility reason codes
Trial duration default (14 days)
Trial notification thresholds (7, 3, 1 days)
Any other trial-related configuration values
Import and Use: Update both backend and frontend to import and use these constants instead of hardcoded strings.

DOCUMENTATION UPDATES
Change: Update Project Documentation
Location: CLAUDE.md

Add Section: Document the trial logic implementation including:

Eligibility rules (one trial per customer, lifetime)
Trial duration and pricing
How trial eligibility is determined
Frontend behavior for eligible vs ineligible users
Trial invisibility principle
Location: API documentation

Add Endpoint Documentation: Document the new trial eligibility endpoint with:

Endpoint URL and method
Request parameters
Response structure with examples
Eligibility rules explanation
Usage notes for frontend developers
DATA FLOW SUMMARY
Trial Eligibility Check Flow
User navigates to CreateInstance page
Frontend loads user profile to get customer ID
Frontend calls trial eligibility API endpoint with customer ID
Backend queries KillBill for customer's account and all subscriptions
Backend checks historical subscription events for any past trials
Backend checks current subscriptions for active trials
Backend applies business rules and determines eligibility
Backend returns eligibility response with "can_show_trial_info" flag
Frontend stores eligibility response in state
Frontend transforms plan data based on eligibility
Frontend renders plans with or without trial information accordingly
Trial Subscription Creation Flow (Eligible User)
User selects plan and chooses "Start with trial"
Frontend submits form with phase_type = "TRIAL"
Backend receives subscription creation request
Backend calls trial eligibility API to validate
If eligible, backend creates subscription in KillBill with TRIAL phase
KillBill fires SUBSCRIPTION_CREATION webhook
Webhook handler detects phase type is TRIAL
Webhook handler creates instance with billing_status = "trial"
Instance provisioning begins via Celery
Frontend shows success message and redirects to instances
Instance appears with "Trial" badge and countdown
Trial Subscription Creation Flow (Ineligible User)
User navigates to CreateInstance page
Frontend checks trial eligibility - receives ineligible response
Frontend transforms plans to remove all trial information
User sees plans with only paid pricing, no trial badges
User selects plan and moves directly to instance configuration (no trial choice)
Frontend auto-sets phase_type to "EVERGREEN"
Frontend submits form
Backend creates subscription with paid phase
KillBill creates subscription in EVERGREEN phase (no trial)
Instance creation proceeds with billing_status = "payment_required"
Frontend shows payment modal immediately
User completes payment to activate instance
Trial Expiration Flow
Trial period elapses (14 days by default)
Background monitoring job detects trial ending soon (7 days out)
Notification email sent to user
Repeat at 3 days and 1 day remaining
Frontend shows warning banner when < 3 days remaining
Trial end date arrives
KillBill transitions subscription from TRIAL to EVERGREEN phase
KillBill fires SUBSCRIPTION_PHASE webhook
Webhook handler updates instance billing_status from "trial" to "payment_required"
KillBill generates first invoice
Frontend shows "Payment Required" badge on instance
User pays invoice
KillBill fires INVOICE_PAYMENT_SUCCESS webhook
Webhook handler updates billing_status to "paid"
Instance continues running normally
BEHAVIORAL CHANGES SUMMARY
For New Users (Trial Eligible)
Before:

Saw "14 day trial" on plans
Could start trial
Client-side eligibility check (unreliable)
After:

See "✓ 14-day trial" badge on all plans
See "$0 for 14 days, then $X/month" pricing
Choose between trial or paid subscription
Backend validates eligibility before allowing trial
Trial instance provisions automatically
See trial countdown on instance card
Receive email warnings before expiration
Smooth transition to paid or payment required status
For Users Who Used Trial
Before:

Still saw "14 day trial" on plans (confusing)
Saw "Trial not available" warning
Had to read and understand why trial wasn't available
Could potentially create multiple trials (bug)
After:

See NO trial badges anywhere
See only "$X/month" pricing
No trial choice section appears
No warning messages about trial
Never see the word "trial" in any UI
Go straight from plan selection to payment
Clean, simple experience as if trial never existed
For Users with Active Trials
Before:

Could potentially create second trial (bug)
No trial countdown visible
No proactive expiration warnings
After:

Cannot create second trial (backend prevents it)
See trial countdown on instance card
Receive email warnings at 7, 3, and 1 day marks
See warning banner when < 3 days remaining
Prompted to add payment method before expiration
Clear visibility into trial status at all times
For Users with Active Paid Subscriptions
Before:

Saw trial information despite already being paying customers
Confusing messaging about trials they can't use
After:

See no trial information (policy decision - can be adjusted)
Clean pricing without trial confusion
Focused on their current subscription status
BUSINESS RULES CODIFIED
Trial Eligibility Rules
One Trial Per Customer (Lifetime)

Once a customer has had any trial subscription, they are permanently ineligible for future trials
This applies across all plans and products
No exceptions without manual admin intervention
No Multiple Active Trials

A customer cannot have more than one active trial at the same time
Must complete or cancel existing trial before starting another
Trial Duration

14 days for production plans
1 day for test plans
Configured in KillBill catalog, not in application code
Trial Pricing

$0 during trial period
Automatic transition to regular pricing after trial ends
Instance Provisioning

Trial subscriptions provision instances automatically
Paid subscriptions require payment before provisioning
UI Display Rules
Trial Visibility

Show trial information ONLY if user is eligible
If ineligible, hide ALL trial-related content
No Negative Messaging

Never show "you can't have a trial" messages
Never explain why trial isn't available
Just don't show trial information at all
Pricing Transparency

Eligible users see trial pricing and post-trial pricing
Ineligible users see only regular pricing
All pricing is clear and upfront
Status Visibility

Users in trial see countdown and expiration date
Users not in trial see appropriate billing status
Clear distinction between trial, paid, and payment required
EDGE CASES HANDLED
System Error During Eligibility Check
Scenario: API call to KillBill fails or returns unexpected data

Behavior: Fail open - assume user is eligible to avoid blocking legitimate new customers. Log error for investigation.

User Has Cancelled Trial
Scenario: User started trial, then cancelled before it ended

Behavior: User is still ineligible for future trials (one trial per lifetime applies to attempts, not completions).

User Has Multiple Subscriptions on Different Plans
Scenario: User has Basic plan subscription and tries to create Standard plan subscription

Behavior: Check looks across ALL subscriptions, not per-plan. If any subscription ever had a trial, user is ineligible.

Network Timeout During Eligibility Check
Scenario: Frontend can't reach backend eligibility endpoint

Behavior: Frontend shows error message and prevents form submission. Don't default to eligible or ineligible - require explicit check.

User Refreshes Page During Instance Creation
Scenario: User submits trial subscription form, then refreshes before redirect

Behavior: Eligibility check runs again. If trial was already created, backend rejects duplicate attempt.

Trial Ends But User Doesn't Pay
Scenario: Trial expires, invoice generated, user ignores payment

Behavior: Instance status changes to "payment_required". Instance behavior depends on policy (keep running, stop, grace period). KillBill handles subscription lifecycle.

VALIDATION & TESTING REQUIREMENTS
Backend Validation Points
Trial eligibility endpoint returns correct status for:

Brand new customer (no KillBill account)
Customer with KillBill account but no subscriptions
Customer with past trial subscription
Customer with active trial subscription
Customer with multiple paid subscriptions
Subscription creation properly validates trial eligibility before allowing trial

Multiple rapid trial creation attempts are all rejected (race condition handling)

Trial counting bug is fixed and multiple trials cannot be created

Frontend Validation Points
Trial-eligible user sees trial badges and trial pricing on all eligible plans

Trial-ineligible user sees NO trial information anywhere (badges, pricing, choice section)

Word "trial" does not appear in UI for ineligible users

Plan selection works identically for both eligible and ineligible users

Form submission sends correct phase_type based on eligibility and user choice

Payment modal appears immediately for ineligible users (no trial choice shown)

Integration Validation Points
Trial creation flow completes end-to-end for eligible user

Trial rejection works for ineligible user attempting to create trial

Instance provisioning works correctly for trial subscriptions

Trial expiration flow works (transition from trial to payment_required to paid)

Email notifications are sent at correct intervals (7, 3, 1 day)

Warning banner appears at correct time (< 3 days remaining)

SUCCESS CRITERIA
The trial logic overhaul is considered successful when:

✅ No Confusion: Users never see trial information they can't use
✅ No Bugs: Multiple trials per customer are impossible
✅ Consistent Logic: Frontend and backend always agree on eligibility
✅ Clean UX: Ineligible users have simple, clear experience without trial clutter
✅ Proactive Communication: Users know when trial is ending and what to do
✅ Single Source of Truth: Backend API controls all eligibility decisions
✅ Type Safety: Frontend and backend use shared type definitions
✅ Clear Visibility: Users in trial always see countdown and expiration info
RISKS & MITIGATIONS
Risk: Breaking Existing Trial Users
Mitigation: Changes only affect new trial creation and UI display. Existing active trials continue working normally through standard webhook flows.

Risk: Frontend/Backend Sync Issues
Mitigation: Frontend always calls backend API for eligibility. No client-side logic that could drift from backend rules.

Risk: Performance Impact of Eligibility Checks
Mitigation: Eligibility endpoint is called once per CreateInstance page load. Cache result in frontend state. KillBill query is fast (indexed by external key).

Risk: Users Upset About Not Seeing Trial Option
Mitigation: This is intentional. Users who aren't eligible don't need to know trial exists. Cleaner UX than showing unavailable features.

Risk: Support Tickets About "Where's My Trial?"
Mitigation: Only users who already used their trial would ask this. Documentation can clarify "one trial per customer" policy if needed.

IMPLEMENTATION SEQUENCE
Why This Order Matters:

Backend First: Fix the critical bug and create the API endpoint before frontend depends on it
Frontend Second: Update UI once backend is proven to work correctly
Notifications Last: Polish feature that enhances but doesn't block core functionality
Dependencies:

Frontend changes depend on backend API being available
Trial monitoring job depends on trial end date being properly stored
Email notifications depend on notification service endpoint existing
Can Be Done in Parallel:

Backend bug fix and API creation (same service, different files)
Frontend plan transformation and styling updates
Documentation updates (can happen anytime)