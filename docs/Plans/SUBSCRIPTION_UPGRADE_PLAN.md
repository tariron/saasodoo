# Implementation Plan: Payment-Based Subscription Upgrades

## Overview
Implement subscription upgrades that only apply resource changes **after payment is received**, using price-based tier comparison (no database migrations required).

## User Requirements (Confirmed)
1. **Payment-Based**: Resource changes applied ONLY when payment received via `INVOICE_PAYMENT_SUCCESS` webhook
2. **Price-Based Tiers**: Use existing plan prices to determine upgrade eligibility (higher price = upgrade)
3. **No Downgrades**: Block all downgrades and same-tier changes
4. **Frontend**: Add upgrade button in BillingInstanceManage page with plan selection UI
5. **No Database Changes**: Use existing price field from KillBill catalog, no migrations needed

## Current Pricing Structure
- **Basic**: $5.00/month (1 CPU, 2G RAM, 10G storage)
- **Standard**: $8.00/month (2 CPU, 4G RAM, 20G storage)
- **Premium**: $10.00/month (4 CPU, 8G RAM, 50G storage)

Prices defined in: `services/billing-service/killbill_catalog.xml`

## Critical Insight: Payment Flow Difference

### Current `SUBSCRIPTION_CHANGE` Flow (Immediate)
```
User changes plan → KillBill SUBSCRIPTION_CHANGE webhook fires →
Resources updated immediately → Invoice created later
```

### Required `INVOICE_PAYMENT_SUCCESS` Flow (After Payment)
```
User requests upgrade → Subscription changed in KillBill → Invoice created →
User pays invoice → INVOICE_PAYMENT_SUCCESS webhook fires →
Check if upgrade → Apply resources with apply_resource_upgrade()
```

## Key Changes Required

### ✅ Already Working (Don't Modify)
1. `apply_resource_upgrade()` function (handles CPU, memory, CephFS quota) - instances.py:1285
2. `INVOICE_PAYMENT_SUCCESS` webhook handler - webhooks.py:657
3. Plan fetching API (`GET /api/billing/plans/`) - plans.py
4. Frontend plan display - CreateInstance.tsx

### 🔧 Must Add/Modify
1. Upgrade detection logic in `INVOICE_PAYMENT_SUCCESS` webhook
2. Price-based tier validation (helper function)
3. Upgrade API endpoint in billing-service
4. Frontend upgrade button and modal in BillingInstanceManage.tsx
5. TypeScript types for upgrade request/response

---

## Implementation Phases

### Phase 1: Backend - Price Comparison Helper

**File**: `services/billing-service/app/utils/pricing.py` (NEW FILE)

Create utility functions for price-based tier comparison:

```python
"""Pricing utilities for tier-based upgrades"""
from typing import Optional, Dict, Any
from app.utils.killbill_client import KillBillClient
import logging

logger = logging.getLogger(__name__)

async def get_plan_price(plan_name: str, killbill: KillBillClient) -> Optional[float]:
    """Get recurring price for a plan from KillBill catalog"""
    try:
        plans = await killbill.get_catalog_plans()
        for plan in plans:
            if plan['name'] == plan_name:
                return plan.get('price')
        logger.warning(f"Plan not found: {plan_name}")
        return None
    except Exception as e:
        logger.error(f"Failed to get plan price: {e}")
        return None

async def validate_upgrade(
    current_plan: str,
    target_plan: str,
    killbill: KillBillClient
) -> Dict[str, Any]:
    """
    Validate if plan change is an upgrade based on price comparison

    Returns:
        dict with 'valid' bool, 'message' str, and pricing info
    """
    current_price = await get_plan_price(current_plan, killbill)
    target_price = await get_plan_price(target_plan, killbill)

    if current_price is None or target_price is None:
        return {
            'valid': False,
            'message': 'Plan pricing not found',
            'error': 'missing_pricing'
        }

    if target_price < current_price:
        return {
            'valid': False,
            'is_downgrade': True,
            'message': f'Downgrades not allowed (${current_price} → ${target_price})',
            'current_price': current_price,
            'target_price': target_price
        }

    if target_price == current_price:
        return {
            'valid': False,
            'is_same_tier': True,
            'message': f'Already on this pricing tier (${current_price})',
            'current_price': current_price,
            'target_price': target_price
        }

    return {
        'valid': True,
        'is_upgrade': True,
        'message': f'Upgrade allowed: ${current_price} → ${target_price}',
        'current_price': current_price,
        'target_price': target_price
    }
```

---

### Phase 2: Backend - Upgrade Endpoint

**File**: `services/billing-service/app/routes/subscriptions.py`

**Add imports** (top of file):
```python
from app.utils.pricing import validate_upgrade
from pydantic import BaseModel
```

**Add request model** (after existing models):
```python
class UpgradeSubscriptionRequest(BaseModel):
    target_plan_name: str
    reason: Optional[str] = "Customer requested upgrade"
```

**Add endpoint** (after existing subscription endpoints):
```python
@router.post("/subscription/{subscription_id}/upgrade")
async def upgrade_subscription(
    subscription_id: str,
    upgrade_data: UpgradeSubscriptionRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """
    Initiate subscription upgrade with validation

    Flow:
    1. Validate upgrade (price-based, no downgrades)
    2. Change subscription in KillBill (creates invoice)
    3. User receives invoice and pays
    4. INVOICE_PAYMENT_SUCCESS webhook applies resources

    Returns upgrade preview (actual changes happen after payment)
    """
    try:
        # Get current subscription
        subscription = await killbill.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        current_plan = subscription.get('planName')

        # Validate upgrade using price comparison
        validation = await validate_upgrade(current_plan, upgrade_data.target_plan_name, killbill)

        if not validation['valid']:
            raise HTTPException(status_code=400, detail=validation['message'])

        # Change subscription in KillBill (IMMEDIATE policy creates prorated invoice)
        await killbill.change_subscription_plan(
            subscription_id=subscription_id,
            new_plan_name=upgrade_data.target_plan_name,
            billing_policy="IMMEDIATE",
            reason=upgrade_data.reason
        )

        # Get new plan entitlements (preview only - applied after payment)
        from app.utils.database import get_plan_entitlements
        new_entitlements = await get_plan_entitlements(upgrade_data.target_plan_name)

        logger.info(
            f"Upgrade initiated: {current_plan} → {upgrade_data.target_plan_name}",
            subscription_id=subscription_id,
            price_change=f"${validation['current_price']} → ${validation['target_price']}"
        )

        return {
            "success": True,
            "message": f"Upgrade from {current_plan} to {upgrade_data.target_plan_name} initiated",
            "subscription_id": subscription_id,
            "current_plan": current_plan,
            "target_plan": upgrade_data.target_plan_name,
            "price_change": f"${validation['current_price']}/mo → ${validation['target_price']}/mo",
            "new_resources": {
                "cpu_limit": float(new_entitlements['cpu_limit']),
                "memory_limit": new_entitlements['memory_limit'],
                "storage_limit": new_entitlements['storage_limit']
            },
            "note": "Invoice created. Resources will be upgraded automatically when payment is received."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upgrade failed: {e}", subscription_id=subscription_id)
        raise HTTPException(status_code=500, detail=f"Upgrade failed: {str(e)}")
```

**Ensure KillBill client has change_subscription_plan method** (add if missing):
In `services/billing-service/app/utils/killbill_client.py`, add after `cancel_subscription()`:

```python
async def change_subscription_plan(
    self,
    subscription_id: str,
    new_plan_name: str,
    billing_policy: str = "IMMEDIATE",
    reason: str = "Plan upgrade"
) -> Dict[str, Any]:
    """Change subscription to new plan"""
    endpoint = f"/1.0/kb/subscriptions/{subscription_id}"
    payload = {"planName": new_plan_name}
    params = {
        "billingPolicy": billing_policy,
        "callCompletion": "true"
    }

    logger.info(f"Changing subscription {subscription_id} to {new_plan_name}")

    response = await self._make_request("PUT", endpoint, data=payload, params=params)
    return response or {"status": "plan_changed"}
```

---

### Phase 3: Backend - Enhance INVOICE_PAYMENT_SUCCESS Webhook

**File**: `services/billing-service/app/routes/webhooks.py`

**Location**: Inside `handle_invoice_payment_success()` function (around line 777, after reactivation handling)

**Add upgrade detection logic** (insert after line 816, before creating new instances):

```python
# Check if payment is for an upgraded subscription (instance exists + running)
existing_instance = await instance_client.get_instance_by_subscription_id(subscription_id)

if existing_instance:
    instance_id = existing_instance['id']
    instance_status = existing_instance.get('status')
    current_cpu = existing_instance.get('cpu_limit')
    current_memory = existing_instance.get('memory_limit')
    current_storage = existing_instance.get('storage_limit')

    logger.info(f"Instance {instance_id} already exists for subscription {subscription_id} - checking for upgrade")

    # Get plan entitlements to check if resources changed (upgrade scenario)
    from ..utils.database import get_plan_entitlements
    new_entitlements = await get_plan_entitlements(plan_name)

    new_cpu = float(new_entitlements['cpu_limit'])
    new_memory = new_entitlements['memory_limit']
    new_storage = new_entitlements['storage_limit']

    # Detect upgrade: higher resources than current
    is_upgrade = (
        new_cpu > current_cpu or
        new_memory != current_memory or  # Memory/storage comparison needs parsing, simplified here
        new_storage != current_storage
    )

    if is_upgrade:
        logger.info(
            f"UPGRADE DETECTED for instance {instance_id}",
            old_resources=f"{current_cpu} CPU, {current_memory} RAM, {current_storage} storage",
            new_resources=f"{new_cpu} CPU, {new_memory} RAM, {new_storage} storage"
        )

        # Update instance database record with new resource limits
        await instance_client.update_instance_resources(instance_id, new_cpu, new_memory, new_storage)
        logger.info(f"Updated instance {instance_id} database record with new resource limits")

        # Apply live resource updates if instance is running
        if instance_status == 'running':
            try:
                await instance_client.apply_resource_upgrade(instance_id)
                logger.info(f"✅ Applied live resource upgrade to running instance {instance_id}")
            except Exception as upgrade_error:
                logger.error(f"Failed to apply live upgrade to {instance_id}: {upgrade_error}")
        else:
            logger.info(f"Instance {instance_id} not running (status: {instance_status}), resources updated in DB only")

        # Send upgrade completion email
        try:
            from ..utils.notification_client import get_notification_client
            customer_info = await _get_customer_info_by_external_key(customer_external_key)

            if customer_info:
                client = get_notification_client()
                await client.send_template_email(
                    to_emails=[customer_info.get('email', '')],
                    template_name="subscription_upgraded",
                    template_variables={
                        "first_name": customer_info.get('first_name', ''),
                        "new_plan": plan_name,
                        "cpu_limit": str(new_cpu),
                        "memory_limit": new_memory,
                        "storage_limit": new_storage,
                        "old_cpu": str(current_cpu),
                        "old_memory": current_memory,
                        "old_storage": current_storage
                    },
                    tags=["billing", "subscription", "upgrade", "payment_received"]
                )
                logger.info(f"✅ Sent upgrade completion email to {customer_info.get('email')}")
        except Exception as email_error:
            logger.error(f"Failed to send upgrade email: {email_error}")

        # Continue to next subscription - upgrade handled
        continue
    else:
        # Regular payment for existing instance (not an upgrade)
        logger.info(f"Regular payment for existing instance {instance_id} (not an upgrade)")

        # Update billing status to paid
        try:
            await instance_client.provision_instance(
                instance_id=instance_id,
                subscription_id=subscription_id,
                billing_status="paid",
                provisioning_trigger="invoice_payment_success_billing_update"
            )
            logger.info(f"Updated billing status to 'paid' for instance {instance_id}")

            # Start instance if stopped
            if instance_status in ['stopped', 'suspended']:
                await instance_client.start_instance(instance_id, "Payment successful")
                logger.info(f"Started instance {instance_id} after payment")
        except Exception as e:
            logger.error(f"Failed to update instance {instance_id}: {e}")

        continue
```

**Note**: This logic goes **before** the existing duplicate prevention check, replacing the current handling for existing instances.

---

### Phase 4: Frontend - TypeScript Types

**File**: `frontend/src/types/billing.ts`

Add new interfaces:

```typescript
export interface UpgradeSubscriptionRequest {
  target_plan_name: string;
  reason?: string;
}

export interface UpgradeSubscriptionResponse {
  success: boolean;
  message: string;
  subscription_id: string;
  current_plan: string;
  target_plan: string;
  price_change: string;
  new_resources: {
    cpu_limit: number;
    memory_limit: string;
    storage_limit: string;
  };
  note: string;
}
```

---

### Phase 5: Frontend - API Client

**File**: `frontend/src/utils/api.ts`

Add to `billingAPI` object:

```typescript
upgradeSubscription: async (
  subscriptionId: string,
  upgradeData: UpgradeSubscriptionRequest
): Promise<AxiosResponse<UpgradeSubscriptionResponse>> => {
  const config = await ConfigManager.getConfig();
  return axios.post(
    `${config.API_BASE_URL}/api/billing/subscriptions/subscription/${subscriptionId}/upgrade`,
    upgradeData
  );
},
```

---

### Phase 6: Frontend - Upgrade Button & Modal

**File**: `frontend/src/pages/BillingInstanceManage.tsx`

**Step 1**: Add imports (top of file):
```typescript
import { UpgradeSubscriptionRequest, UpgradeSubscriptionResponse } from '../types/billing';
```

**Step 2**: Add state variables (after existing useState declarations):
```typescript
const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
const [selectedUpgradePlan, setSelectedUpgradePlan] = useState<string>('');
const [upgradeLoading, setUpgradeLoading] = useState(false);
const [availablePlans, setAvailablePlans] = useState<Plan[]>([]);
const [currentPlanPrice, setCurrentPlanPrice] = useState<number | null>(null);
```

**Step 3**: Add function to fetch upgradable plans:
```typescript
const fetchUpgradablePlans = async () => {
  if (!instance?.subscription?.plan_name) return;

  try {
    const response = await billingAPI.getPlans();
    if (response.data.success) {
      const allPlans = response.data.plans;

      // Find current plan price
      const currentPlan = allPlans.find((p: Plan) => p.name === instance.subscription.plan_name);
      const currentPrice = currentPlan?.price ?? 0;
      setCurrentPlanPrice(currentPrice);

      // Filter plans with higher price (upgrades only)
      const upgrades = allPlans.filter((p: Plan) =>
        p.price !== null && p.price > currentPrice
      );

      setAvailablePlans(upgrades);
      console.log(`Found ${upgrades.length} upgrade options from $${currentPrice}`);
    }
  } catch (error) {
    console.error('Failed to fetch upgradable plans:', error);
  }
};
```

**Step 4**: Call fetchUpgradablePlans when subscription loads:
```typescript
useEffect(() => {
  if (instance?.subscription?.plan_name) {
    fetchUpgradablePlans();
  }
}, [instance?.subscription?.plan_name]);
```

**Step 5**: Add upgrade handler:
```typescript
const handleUpgradeSubscription = async () => {
  if (!instance?.subscription_id || !selectedUpgradePlan) {
    alert('Missing subscription or plan selection');
    return;
  }

  const selectedPlan = availablePlans.find(p => p.name === selectedUpgradePlan);
  if (!selectedPlan) {
    alert('Selected plan not found');
    return;
  }

  const confirmed = window.confirm(
    `Upgrade to ${selectedPlan.product} - ${selectedPlan.billing_period}?\n\n` +
    `Price: $${currentPlanPrice}/mo → $${selectedPlan.price}/mo\n` +
    `Resources: ${selectedPlan.cpu_limit} CPU, ${selectedPlan.memory_limit} RAM, ${selectedPlan.storage_limit} storage\n\n` +
    `• Invoice will be created immediately\n` +
    `• Resources upgrade after payment is received\n` +
    `• Prorated charge based on remaining billing period`
  );

  if (!confirmed) return;

  try {
    setUpgradeLoading(true);

    const response = await billingAPI.upgradeSubscription(
      instance.subscription_id,
      {
        target_plan_name: selectedUpgradePlan,
        reason: "User requested upgrade via dashboard"
      }
    );

    alert(
      `✅ ${response.data.message}\n\n` +
      `Price change: ${response.data.price_change}\n\n` +
      `${response.data.note}\n\n` +
      `Please check your email for the invoice.`
    );

    setUpgradeModalOpen(false);
    setSelectedUpgradePlan('');
    await fetchInstanceBillingData();

  } catch (err: any) {
    const errorMsg = err.response?.data?.detail || err.message;
    alert(`❌ Upgrade failed: ${errorMsg}`);
  } finally {
    setUpgradeLoading(false);
  }
};
```

**Step 6**: Add "Upgrade Plan" button in Subscription Management section:

Find the section with cancel subscription button (around line 640), add before it:

```tsx
{/* Upgrade Plan Button */}
{instance.subscription?.state === 'ACTIVE' && (
  <button
    onClick={() => setUpgradeModalOpen(true)}
    disabled={availablePlans.length === 0}
    className="bg-green-600 text-white px-6 py-2 rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
  >
    {availablePlans.length > 0
      ? `Upgrade Plan (${availablePlans.length} options)`
      : 'No Upgrades Available'}
  </button>
)}
```

**Step 7**: Add upgrade modal (add before the final return statement):

```tsx
{/* Upgrade Modal */}
{upgradeModalOpen && (
  <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div className="bg-white rounded-lg p-8 max-w-3xl w-full max-h-[90vh] overflow-y-auto">
      <h2 className="text-2xl font-bold mb-4">Upgrade Subscription</h2>

      <div className="mb-6 bg-gray-50 p-4 rounded-md">
        <p className="text-sm text-gray-600 mb-1">Current Plan:</p>
        <p className="font-semibold text-lg">{instance.subscription?.plan_name}</p>
        {currentPlanPrice !== null && (
          <p className="text-gray-700">${currentPlanPrice}/month</p>
        )}
      </div>

      <div className="mb-6">
        <label className="block text-gray-700 font-medium mb-2">
          Select Upgrade Plan:
        </label>
        <select
          value={selectedUpgradePlan}
          onChange={(e) => setSelectedUpgradePlan(e.target.value)}
          className="w-full p-3 border rounded-md"
          disabled={upgradeLoading}
        >
          <option value="">-- Choose a plan --</option>
          {availablePlans.map((plan) => (
            <option key={plan.name} value={plan.name}>
              {plan.product} - {plan.billing_period} - ${plan.price}/mo
              ({plan.cpu_limit} CPU, {plan.memory_limit} RAM, {plan.storage_limit} storage)
            </option>
          ))}
        </select>
      </div>

      {selectedUpgradePlan && (
        <div className="mb-6 bg-blue-50 border border-blue-200 rounded-md p-4">
          <h3 className="font-semibold mb-2">What happens next:</h3>
          <ol className="text-sm space-y-2 list-decimal list-inside">
            <li>Prorated invoice created immediately</li>
            <li>You'll receive invoice via email</li>
            <li>After payment is received, resources upgrade automatically</li>
            <li>Zero downtime - running instances updated live</li>
          </ol>
        </div>
      )}

      <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4 mb-6">
        <p className="text-sm font-medium">⚠️ Important Notes:</p>
        <ul className="text-sm space-y-1 mt-2">
          <li>• Downgrades are not allowed</li>
          <li>• Resource changes apply only after invoice payment</li>
          <li>• Proration based on remaining billing period</li>
        </ul>
      </div>

      <div className="flex justify-end space-x-4">
        <button
          onClick={() => {
            setUpgradeModalOpen(false);
            setSelectedUpgradePlan('');
          }}
          disabled={upgradeLoading}
          className="px-6 py-2 border rounded-md hover:bg-gray-100 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          onClick={handleUpgradeSubscription}
          disabled={!selectedUpgradePlan || upgradeLoading}
          className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {upgradeLoading ? 'Processing...' : 'Create Upgrade Invoice'}
        </button>
      </div>
    </div>
  </div>
)}
```

---

### Phase 7: KillBill Catalog Policy (Optional - Already Set)

**File**: `services/billing-service/killbill_catalog.xml`

**Verify** that changePolicy is set to IMMEDIATE (line 23-27):

```xml
<changePolicy>
    <changePolicyCase>
        <policy>IMMEDIATE</policy>
    </changePolicyCase>
</changePolicy>
```

**Note**: If currently END_OF_TERM, change to IMMEDIATE to enable instant plan changes with proration.

---

## Critical Files Summary

### Backend Changes (5 files)
1. `services/billing-service/app/utils/pricing.py` - NEW: Price comparison utilities
2. `services/billing-service/app/routes/subscriptions.py` - ADD: Upgrade endpoint
3. `services/billing-service/app/utils/killbill_client.py` - ADD: change_subscription_plan method (if missing)
4. `services/billing-service/app/routes/webhooks.py` - MODIFY: INVOICE_PAYMENT_SUCCESS handler (add upgrade detection)
5. `services/billing-service/killbill_catalog.xml` - VERIFY: IMMEDIATE policy

### Frontend Changes (3 files)
6. `frontend/src/types/billing.ts` - ADD: Upgrade types
7. `frontend/src/utils/api.ts` - ADD: upgradeSubscription API method
8. `frontend/src/pages/BillingInstanceManage.tsx` - ADD: Upgrade button and modal UI

### Already Working (No Changes Needed)
- `services/instance-service/app/routes/instances.py:1285` - apply_resource_upgrade() ✅
- `services/billing-service/app/routes/plans.py` - getPlans() endpoint ✅
- `services/billing-service/app/utils/database.py` - get_plan_entitlements() ✅

---

## Flow Diagram

```
[User clicks "Upgrade Plan" button]
         ↓
[Frontend shows available higher-priced plans]
         ↓
[User selects plan, clicks "Create Upgrade Invoice"]
         ↓
[POST /api/billing/subscriptions/{id}/upgrade]
         ↓
[Backend validates: target_price > current_price]
         ↓
[KillBill subscription changed via PUT /subscriptions/{id}]
         ↓
[KillBill creates prorated invoice]
         ↓
[User receives invoice email]
         ↓
[User pays invoice (external payment gateway)]
         ↓
[INVOICE_PAYMENT_SUCCESS webhook fires]
         ↓
[Webhook detects: instance exists + resources changed]
         ↓
[update_instance_resources() - DB updated]
         ↓
[apply_resource_upgrade() - Live container update]
         ↓
[Email sent: "Upgrade complete"]
         ↓
[Frontend refreshes: shows new resources]
```

---

## Testing Strategy

### Unit Tests
- [ ] Price comparison logic (upgrade/downgrade/same tier)
- [ ] validate_upgrade() with various price combinations
- [ ] Upgrade endpoint validation (400 on downgrade, 404 on invalid subscription)

### Integration Tests
- [ ] Full upgrade flow: Basic ($5) → Standard ($8)
- [ ] Full upgrade flow: Standard ($8) → Premium ($10)
- [ ] Downgrade rejection: Premium → Basic (should fail)
- [ ] Same-tier rejection: Basic → Basic (should fail)
- [ ] Resource update verification after payment
- [ ] CephFS quota update confirmation

### Edge Cases
- [ ] Upgrade during trial period
- [ ] Upgrade for stopped instance (resources update DB only)
- [ ] Concurrent upgrade requests (race condition)
- [ ] Payment failure after upgrade initiated
- [ ] Upgrade with missing plan pricing data

### UI Testing
- [ ] Upgrade button only shows for ACTIVE subscriptions
- [ ] Modal filters to higher-priced plans only
- [ ] Confirmation dialog shows price change
- [ ] Success message displays correctly
- [ ] Error handling for failed upgrades
- [ ] Subscription data refreshes after upgrade

---

## Deployment Checklist

### Pre-Deployment
1. [ ] Test on staging environment
2. [ ] Backup production database
3. [ ] Verify KillBill catalog has IMMEDIATE policy

### Deployment Steps
1. [ ] Deploy backend: billing-service, instance-service (if apply_resource_upgrade modified)
2. [ ] Deploy frontend service
3. [ ] Smoke test: Initiate upgrade, verify invoice created
4. [ ] Smoke test: Pay invoice, verify resources upgraded

### Post-Deployment
1. [ ] Monitor first production upgrade
2. [ ] Verify INVOICE_PAYMENT_SUCCESS webhook detects upgrades
3. [ ] Confirm live resource updates with zero downtime
4. [ ] Check email notifications sent correctly

---

## Success Metrics

- Upgrade request completes in < 2 seconds (invoice created)
- Resource updates apply within 10 seconds of payment
- Zero downtime during live resource upgrades
- 100% downgrade blocking (all rejected with 400 error)
- Upgrade emails delivered within 1 minute

---

## Rollback Plan

If critical issues arise:
1. Disable upgrade button in frontend (remove or hide)
2. Existing subscriptions remain unaffected
3. Revert webhook changes (remove upgrade detection logic)
4. Manual resource upgrades via admin interface if needed

---

**Estimated Implementation Time**: 8-12 hours
**Complexity**: Medium (leverages existing infrastructure)
**Risk Level**: Low (payment-gated, no automatic changes)
