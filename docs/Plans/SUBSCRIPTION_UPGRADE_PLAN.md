# Implementation Plan: Subscription Upgrade Feature

## Overview
Implement tier-based subscription upgrades with immediate effect, prorated charges, live resource updates, and upgrade-only validation (no downgrades allowed).

## User Requirements
1. **Plan Hierarchy**: Explicit tier ranking (Basic=1, Standard=2, Premium=3)
2. **Effective Date**: Immediate upgrades with prorated charges
3. **Downgrade Policy**: Only allow upgrades (no downgrades)
4. **Resource Updates**: Apply immediately to running instances

## Current System Strengths
- ✅ KillBill already handles SUBSCRIPTION_CHANGE webhooks
- ✅ Webhook handler updates instance resources and applies live changes
- ✅ `apply_resource_upgrade()` function updates running Docker containers
- ✅ Frontend has BillingInstanceManage page with subscription UI
- ✅ KillBill natively handles proration calculations

## Implementation Phases

### Phase 1: Database Schema - Add Tier Ranking

**File**: `infrastructure/postgres/init-scripts/05-plan-entitlements.sql`

Add tier_rank column and populate values:

```sql
-- Add tier_rank column
ALTER TABLE plan_entitlements ADD COLUMN tier_rank INTEGER;

-- Set tier ranks
UPDATE plan_entitlements SET tier_rank = 1
WHERE plan_name IN ('basic-monthly', 'basic-immediate', 'basic-test-trial');

UPDATE plan_entitlements SET tier_rank = 2
WHERE plan_name = 'standard-monthly';

UPDATE plan_entitlements SET tier_rank = 3
WHERE plan_name = 'premium-monthly';

-- Make required and add index
ALTER TABLE plan_entitlements ALTER COLUMN tier_rank SET NOT NULL;
CREATE INDEX idx_plan_entitlements_tier_rank ON plan_entitlements(tier_rank);
```

**Migration Script**: Create new file `infrastructure/postgres/migrations/006-add-tier-ranks.sql`

---

### Phase 2: KillBill Catalog - Enable Immediate Changes

**File**: `services/billing-service/killbill_catalog.xml`
**Line**: 23-27

**Change from**:
```xml
<changePolicy>
    <changePolicyCase>
        <policy>END_OF_TERM</policy>
    </changePolicyCase>
</changePolicy>
```

**Change to**:
```xml
<changePolicy>
    <changePolicyCase>
        <policy>IMMEDIATE</policy>
    </changePolicyCase>
</changePolicy>
```

**Impact**: Enables instant plan changes with automatic KillBill proration

---

### Phase 3: Backend Validation Logic

**File**: `services/billing-service/app/utils/database.py`
**Location**: Add after line 124

**Add two functions**:

```python
async def get_plan_tier_rank(plan_name: str) -> Optional[int]:
    """Get tier rank for a plan to determine upgrade/downgrade eligibility"""
    pool = get_pool()
    query = """
        SELECT tier_rank FROM plan_entitlements
        WHERE plan_name = $1
        ORDER BY effective_date DESC LIMIT 1
    """
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query, plan_name)
        return result['tier_rank'] if result else None


async def validate_plan_upgrade(current_plan: str, target_plan: str) -> dict:
    """
    Validate if plan change is an upgrade (not downgrade or same tier)
    Returns dict with 'valid' boolean and descriptive 'message'
    """
    current_tier = await get_plan_tier_rank(current_plan)
    target_tier = await get_plan_tier_rank(target_plan)

    if not current_tier or not target_tier:
        return {
            'valid': False,
            'message': 'Plan not found'
        }

    if target_tier < current_tier:
        return {
            'valid': False,
            'is_downgrade': True,
            'message': f'Downgrades not allowed (tier {current_tier} → {target_tier})'
        }

    if target_tier == current_tier:
        return {
            'valid': False,
            'is_same_tier': True,
            'message': 'Already on this tier'
        }

    return {
        'valid': True,
        'is_upgrade': True,
        'current_tier': current_tier,
        'target_tier': target_tier,
        'message': f'Upgrade allowed: tier {current_tier} → {target_tier}'
    }
```

---

### Phase 4: KillBill Client Integration

**File**: `services/billing-service/app/utils/killbill_client.py`
**Location**: Add after `cancel_subscription()` method (after line 271)

**Add method**:

```python
async def change_subscription_plan(
    self,
    subscription_id: str,
    new_plan_name: str,
    billing_policy: str = "IMMEDIATE",
    reason: str = "Plan upgrade"
) -> Dict[str, Any]:
    """
    Change subscription to new plan

    Args:
        subscription_id: KillBill subscription ID
        new_plan_name: Target plan name (e.g., 'premium-monthly')
        billing_policy: IMMEDIATE (with proration) or END_OF_TERM
        reason: Reason for change (audit trail)

    Returns:
        Updated subscription details
    """
    endpoint = f"/1.0/kb/subscriptions/{subscription_id}"
    payload = {"planName": new_plan_name}
    params = {
        "billingPolicy": billing_policy,
        "callCompletion": "true",
        "pluginProperty": f"reason={reason}"
    }

    logger.info(
        "Changing subscription plan",
        subscription_id=subscription_id,
        new_plan=new_plan_name,
        policy=billing_policy
    )

    response = await self._make_request(
        "PUT",
        endpoint,
        data=payload,
        params=params
    )

    return response or {"status": "plan_changed"}
```

---

### Phase 5: Upgrade API Endpoint

**File**: `services/billing-service/app/routes/subscriptions.py`

**Step 1**: Add Pydantic model (after line 27)

```python
class UpgradeSubscriptionRequest(BaseModel):
    target_plan_name: str
    reason: Optional[str] = "Customer requested upgrade"
```

**Step 2**: Add endpoint (after `get_subscription_invoices()`, around line 286)

```python
@router.post("/subscription/{subscription_id}/upgrade")
async def upgrade_subscription(
    subscription_id: str,
    upgrade_data: UpgradeSubscriptionRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """
    Upgrade subscription with tier validation and immediate effect

    - Validates upgrade (prevents downgrades)
    - Applies IMMEDIATE billing policy with proration
    - Returns new resource allocations
    - Webhook handles actual resource updates
    """
    try:
        from ..utils.database import validate_plan_upgrade, get_plan_entitlements

        # Get current subscription
        subscription = await killbill.get_subscription_by_id(subscription_id)
        if not subscription:
            raise HTTPException(
                status_code=404,
                detail="Subscription not found"
            )

        current_plan = subscription.get('planName')

        # Validate upgrade (prevents downgrades)
        validation = await validate_plan_upgrade(
            current_plan,
            upgrade_data.target_plan_name
        )

        if not validation['valid']:
            raise HTTPException(
                status_code=400,
                detail=validation['message']
            )

        # Perform upgrade via KillBill
        await killbill.change_subscription_plan(
            subscription_id=subscription_id,
            new_plan_name=upgrade_data.target_plan_name,
            billing_policy="IMMEDIATE",
            reason=upgrade_data.reason
        )

        # Get new resource entitlements
        new_entitlements = await get_plan_entitlements(
            upgrade_data.target_plan_name
        )

        return {
            "success": True,
            "message": f"Upgraded from {current_plan} to {upgrade_data.target_plan_name}",
            "subscription_id": subscription_id,
            "new_resources": {
                "cpu_limit": float(new_entitlements['cpu_limit']),
                "memory_limit": new_entitlements['memory_limit'],
                "storage_limit": new_entitlements['storage_limit']
            },
            "tier_change": f"{validation['current_tier']} → {validation['target_tier']}",
            "note": "Resources applied automatically with zero downtime. Prorated charge on next invoice."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Upgrade failed", error=str(e), subscription_id=subscription_id)
        raise HTTPException(
            status_code=500,
            detail=f"Upgrade failed: {str(e)}"
        )
```

---

### Phase 6: Webhook Handler Enhancement (Optional)

**File**: `services/billing-service/app/routes/webhooks.py`
**Location**: Line 583 (inside `handle_subscription_change`)

**Optional Enhancement**: Add tier rank logging for visibility

```python
# After fetching entitlements, add:
new_tier = entitlements.get('tier_rank')
logger.info(
    "Plan change detected",
    instance_id=instance_id,
    new_plan=new_plan_name,
    new_tier=new_tier
)
```

**Note**: Existing webhook handler already:
- ✅ Handles SUBSCRIPTION_CHANGE events
- ✅ Updates instance database records
- ✅ Applies live resource updates via `apply_resource_upgrade()`
- ✅ Sends email notifications

---

### Phase 7: Shared Schema Updates

**File**: `shared/schemas/billing.py`

Add response schema (around line 50):

```python
class UpgradeSubscriptionResponse(BaseModel):
    success: bool
    message: str
    subscription_id: str
    new_resources: dict
    tier_change: str
    note: str
```

---

### Phase 8: Frontend Types

**File**: `frontend/src/types/billing.ts`

Add interfaces:

```typescript
export interface UpgradeSubscriptionRequest {
  target_plan_name: string;
  reason?: string;
}

export interface UpgradeSubscriptionResponse {
  success: boolean;
  message: string;
  subscription_id: string;
  new_resources: {
    cpu_limit: number;
    memory_limit: string;
    storage_limit: string;
  };
  tier_change: string;
  note: string;
}

// Add to Plan interface
export interface Plan {
  name: string;
  product: string;
  description: string;
  billing_period: string;
  price: number | null;
  cpu_limit?: number;
  memory_limit?: string;
  storage_limit?: string;
  tier_rank?: number;  // NEW - for upgrade validation
}
```

---

### Phase 9: Frontend API Client

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

### Phase 10: Frontend UI - Upgrade Modal

**File**: `frontend/src/pages/BillingInstanceManage.tsx`

**Step 1**: Add state variables (after line 28)

```typescript
const [upgradeModalOpen, setUpgradeModalOpen] = useState(false);
const [selectedUpgradePlan, setSelectedUpgradePlan] = useState<string>('');
const [upgradeLoading, setUpgradeLoading] = useState(false);
const [upgradablePlans, setUpgradablePlans] = useState<Plan[]>([]);
```

**Step 2**: Add function to fetch upgradable plans

```typescript
const fetchUpgradablePlans = async (currentPlanName: string) => {
  try {
    const response = await billingAPI.getPlans();
    if (response.data.success) {
      const currentPlan = response.data.plans.find(
        (p: Plan) => p.name === currentPlanName
      );

      if (!currentPlan?.tier_rank) {
        console.warn('Current plan has no tier rank');
        return;
      }

      // Filter plans with higher tier rank
      const upgrades = response.data.plans.filter(
        (p: Plan) => p.tier_rank && p.tier_rank > currentPlan.tier_rank
      );

      setUpgradablePlans(upgrades);
    }
  } catch (error) {
    console.error('Failed to fetch upgradable plans:', error);
  }
};
```

**Step 3**: Call fetchUpgradablePlans when subscription loads

```typescript
useEffect(() => {
  if (instance?.subscription?.plan_name) {
    fetchUpgradablePlans(instance.subscription.plan_name);
  }
}, [instance?.subscription?.plan_name]);
```

**Step 4**: Add upgrade handler

```typescript
const handleUpgradeSubscription = async () => {
  if (!instance?.subscription_id || !selectedUpgradePlan) {
    alert('Missing subscription or plan selection');
    return;
  }

  const confirmed = window.confirm(
    `Upgrade to ${selectedUpgradePlan}?\n\n` +
    `• Changes apply immediately\n` +
    `• Resources updated with zero downtime\n` +
    `• Prorated charge on next invoice`
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
      `Tier change: ${response.data.tier_change}\n` +
      `${response.data.note}`
    );

    setUpgradeModalOpen(false);
    await fetchInstanceBillingData();

  } catch (err: any) {
    const errorMsg = err.response?.data?.detail || err.message;
    alert(`❌ Upgrade failed: ${errorMsg}`);
  } finally {
    setUpgradeLoading(false);
  }
};
```

**Step 5**: Add "Upgrade Plan" button in Subscription Management section (around line 640)

```tsx
{instance.subscription?.state === 'ACTIVE' && (
  <button
    onClick={() => setUpgradeModalOpen(true)}
    disabled={upgradablePlans.length === 0}
    className="bg-green-600 text-white px-6 py-2 rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
  >
    {upgradablePlans.length > 0 ? 'Upgrade Plan' : 'No Upgrades Available'}
  </button>
)}
```

**Step 6**: Add modal component (before return statement, around line 336)

```tsx
{/* Upgrade Modal */}
{upgradeModalOpen && (
  <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div className="bg-white rounded-lg p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <h2 className="text-2xl font-bold mb-4">Upgrade Subscription</h2>

      <div className="mb-6">
        <p className="text-gray-600 mb-2">Current Plan:</p>
        <p className="font-semibold text-lg">{instance.subscription?.plan_name}</p>
      </div>

      <div className="mb-6">
        <label className="block text-gray-700 font-medium mb-2">
          Select Upgrade Plan:
        </label>
        <select
          value={selectedUpgradePlan}
          onChange={(e) => setSelectedUpgradePlan(e.target.value)}
          className="w-full p-2 border rounded-md"
        >
          <option value="">-- Choose Plan --</option>
          {upgradablePlans.map((plan) => (
            <option key={plan.name} value={plan.name}>
              {plan.product} - {plan.billing_period} - ${plan.price}/mo
              (Tier {plan.tier_rank}: {plan.cpu_limit} CPU, {plan.memory_limit} RAM, {plan.storage_limit} Storage)
            </option>
          ))}
        </select>
      </div>

      <div className="bg-blue-50 border border-blue-200 rounded-md p-4 mb-6">
        <h3 className="font-semibold mb-2">Upgrade Details:</h3>
        <ul className="text-sm space-y-1">
          <li>✓ Changes apply immediately</li>
          <li>✓ Zero downtime - resources updated live</li>
          <li>✓ Prorated charge based on remaining billing period</li>
          <li>✓ No downgrades allowed</li>
        </ul>
      </div>

      <div className="flex justify-end space-x-4">
        <button
          onClick={() => {
            setUpgradeModalOpen(false);
            setSelectedUpgradePlan('');
          }}
          disabled={upgradeLoading}
          className="px-6 py-2 border rounded-md hover:bg-gray-100"
        >
          Cancel
        </button>
        <button
          onClick={handleUpgradeSubscription}
          disabled={!selectedUpgradePlan || upgradeLoading}
          className="px-6 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400"
        >
          {upgradeLoading ? 'Processing...' : 'Confirm Upgrade'}
        </button>
      </div>
    </div>
  </div>
)}
```

---

## Critical Files Summary

### Backend Changes
1. `infrastructure/postgres/init-scripts/05-plan-entitlements.sql` - Add tier_rank column
2. `services/billing-service/app/utils/database.py` - Validation functions
3. `services/billing-service/app/utils/killbill_client.py` - Change plan method
4. `services/billing-service/app/routes/subscriptions.py` - Upgrade endpoint
5. `services/billing-service/killbill_catalog.xml` - Change policy to IMMEDIATE
6. `shared/schemas/billing.py` - Response schema

### Frontend Changes
7. `frontend/src/types/billing.ts` - Type definitions
8. `frontend/src/utils/api.ts` - API client method
9. `frontend/src/pages/BillingInstanceManage.tsx` - UI implementation

### Already Working
10. `services/billing-service/app/routes/webhooks.py` - SUBSCRIPTION_CHANGE handler ✅

---

## Testing Strategy

### Unit Tests
- [ ] Test `validate_plan_upgrade()` with various tier combinations
- [ ] Test upgrade endpoint with valid/invalid plans
- [ ] Test downgrade rejection logic
- [ ] Test same-tier prevention

### Integration Tests
- [ ] Complete upgrade flow: Basic → Standard
- [ ] Complete upgrade flow: Standard → Premium
- [ ] Verify proration calculation in KillBill invoice
- [ ] Verify live resource updates to running container
- [ ] Test upgrade during active instance (no downtime)
- [ ] Test upgrade when instance is stopped

### Edge Cases
- [ ] Attempt downgrade (should fail with 400)
- [ ] Attempt upgrade to same tier (should fail)
- [ ] Attempt upgrade with invalid plan name
- [ ] Concurrent upgrade requests (race condition)
- [ ] Upgrade during trial period
- [ ] Upgrade with missing payment method

### UI Testing
- [ ] Upgrade button only shows for ACTIVE subscriptions
- [ ] Modal shows only higher-tier plans
- [ ] Confirmation dialog displays correctly
- [ ] Success message shows tier change
- [ ] Error handling displays user-friendly messages
- [ ] Subscription data refreshes after upgrade

---

## Deployment Checklist

### Pre-Deployment
1. [ ] Backup production database
2. [ ] Test on staging environment
3. [ ] Verify KillBill catalog change won't affect existing subscriptions

### Deployment Steps
1. [ ] Apply database migration (add tier_rank column)
2. [ ] Update KillBill catalog XML
3. [ ] Deploy backend services (billing-service)
4. [ ] Deploy frontend service
5. [ ] Smoke test upgrade flow
6. [ ] Monitor logs for errors

### Post-Deployment
1. [ ] Monitor first production upgrade
2. [ ] Verify proration invoice generated correctly
3. [ ] Confirm resource updates applied successfully
4. [ ] Check email notifications sent

---

## Success Metrics

- Upgrades complete within 5 seconds
- Resource updates apply with zero downtime
- Prorated charges calculated correctly by KillBill
- Zero downgrade requests succeed (100% blocked)
- User sees updated resources immediately in dashboard

---

## Rollback Plan

If critical issues arise:
1. Revert KillBill catalog to END_OF_TERM policy
2. Remove upgrade button from frontend
3. Existing subscriptions remain unaffected
4. Database tier_rank column can remain (no harm)

---

**Estimated Implementation Time**: 12-16 hours
**Complexity**: Medium (leverages existing infrastructure)
**Risk Level**: Low (no changes to core instance lifecycle)
