# Issue: KillBill Webhook Duplicate Registration

**Date Reported:** 2025-12-24
**Status:** Workaround Applied (scaled to 1 replica)
**Severity:** High
**Component:** billing-service

---

## Summary

The billing-service registers duplicate webhook URLs with KillBill when running with multiple replicas, causing KillBill to fail when sending webhook notifications with error: `TenantKVCacheLoader expecting no more than one value for key PUSH_NOTIFICATION_CB::1`.

This prevents instance provisioning after successful payment because KillBill cannot deliver the `INVOICE_PAYMENT_SUCCESS` webhook to trigger the provisioning workflow.

---

## Symptoms

1. **Payment succeeds** but instance provisioning does not start
2. **KillBill logs show webhook error:**
   ```
   TenantKVCacheLoader expecting no more than one value for key PUSH_NOTIFICATION_CB::1
   ```
3. **Database query shows duplicate webhook registrations:**
   ```sql
   SELECT record_id, tenant_key, tenant_value
   FROM tenant_kvs
   WHERE tenant_key LIKE 'PUSH_NOTIFICATION_CB%';

   -- Result: Multiple rows with same tenant_key
   record_id  tenant_key             tenant_value
   25         PUSH_NOTIFICATION_CB   http://billing-service:8004/api/billing/webhooks/killbill
   26         PUSH_NOTIFICATION_CB   http://billing-service:8004/api/billing/webhooks/killbill
   ```

---

## Root Cause Analysis

### Problem Flow

1. **billing-service deployment has multiple replicas** (was set to `replicas: 2`)
2. **Each pod registers webhook on startup** via lifespan function in `main.py`:
   ```python
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # Startup
       logger.info("Starting Billing Service...")
       await init_db()

       # Register webhook with KillBill
       try:
           webhook_url = os.getenv("KILLBILL_NOTIFICATION_URL",
                                   "http://billing-service:8004/api/billing/webhooks/killbill")
           await app.state.killbill.register_webhook(webhook_url)  # ❌ No idempotency check
           logger.info(f"Successfully registered webhook: {webhook_url}")
       except Exception as e:
           logger.warning(f"Failed to register webhook during startup: {e}")
   ```

3. **register_webhook() does NOT check if webhook already exists** in `utils/killbill_client.py`:
   ```python
   async def register_webhook(self, webhook_url: str) -> Dict[str, Any]:
       """Register webhook URL with KillBill using proper notification callback API"""
       try:
           headers = self.headers.copy()
           headers["X-Killbill-ApiKey"] = self.api_key
           headers["X-Killbill-ApiSecret"] = self.api_secret
           headers["X-Killbill-CreatedBy"] = "billing-service"

           url = f"{self.base_url}/1.0/kb/tenants/registerNotificationCallback"
           params = {"cb": webhook_url}

           async with httpx.AsyncClient() as client:
               response = await client.post(
                   url=url,
                   headers=headers,
                   params=params,
                   auth=(self.username, self.password),
                   timeout=30.0
               )
               # ❌ Just posts directly - no check if already exists
   ```

4. **Result:** With N replicas, N duplicate webhook registrations are created

---

## Current State

### Temporary Workaround Applied

**File:** `infrastructure/orchestration/kubernetes/services/billing-service/01-deployment.yaml`

```yaml
spec:
  replicas: 1  # ✅ Changed from 2 to prevent duplicates
```

**Database State:**
```
record_id: 25
tenant_key: PUSH_NOTIFICATION_CB
tenant_value: http://billing-service:8004/api/billing/webhooks/killbill
```

Currently running with 1 webhook registration (as expected).

### Limitations of Current Workaround

1. **No high availability** - Single point of failure
2. **No load distribution** - All webhook traffic to one pod
3. **Restart risk** - Any restart will create another duplicate (code still not idempotent)
4. **Scaling restricted** - Cannot scale up without creating duplicates

---

## Impact

### Business Impact
- **Critical:** Blocks instance provisioning after payment
- **Revenue impact:** Customers pay but don't receive their instances
- **Support burden:** Manual intervention required to provision instances

### Technical Impact
- **Scalability:** Cannot run multiple replicas for HA/load balancing
- **Reliability:** Single pod = single point of failure
- **Operational:** Manual cleanup required after each restart

---

## Recommended Solutions

### Solution 1: Idempotent Webhook Registration (Recommended)

**Approach:** Check if webhook exists before registering.

**Implementation:**

#### Step 1: Add method to get existing webhooks

Add to `services/billing-service/app/utils/killbill_client.py`:

```python
async def get_tenant_config(self) -> Dict[str, Any]:
    """Get all tenant configuration including registered webhooks"""
    try:
        headers = self.headers.copy()
        headers["X-Killbill-ApiKey"] = self.api_key
        headers["X-Killbill-ApiSecret"] = self.api_secret

        url = f"{self.base_url}/1.0/kb/tenants/userKeyValue"

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url=url,
                headers=headers,
                auth=(self.username, self.password),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Failed to get tenant config: {e}")
        return {}
```

#### Step 2: Make register_webhook() idempotent

Replace the `register_webhook()` method:

```python
async def register_webhook(self, webhook_url: str) -> Dict[str, Any]:
    """Register webhook URL with KillBill (idempotent - checks if already registered)"""
    try:
        # ✅ Step 1: Check if webhook already registered
        tenant_config = await self.get_tenant_config()

        # Check if this webhook URL is already registered
        for key, value in tenant_config.items():
            if key.startswith("PUSH_NOTIFICATION_CB") and value == webhook_url:
                logger.info(f"Webhook already registered: {webhook_url}")
                return {"status": "already_registered", "webhook_url": webhook_url}

        # ✅ Step 2: Only register if not found
        logger.info(f"Registering new webhook: {webhook_url}")

        headers = self.headers.copy()
        headers["X-Killbill-ApiKey"] = self.api_key
        headers["X-Killbill-ApiSecret"] = self.api_secret
        headers["X-Killbill-CreatedBy"] = "billing-service"

        url = f"{self.base_url}/1.0/kb/tenants/registerNotificationCallback"
        params = {"cb": webhook_url}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=url,
                headers=headers,
                params=params,
                auth=(self.username, self.password),
                timeout=30.0
            )
            response.raise_for_status()

            logger.info(f"Successfully registered webhook: {webhook_url}")
            return {
                "status": "registered",
                "webhook_url": webhook_url,
                "status_code": response.status_code
            }
    except Exception as e:
        logger.error(f"Failed to register webhook: {e}")
        raise
```

#### Step 3: Scale back to multiple replicas

After implementing the fix, update deployment:

```yaml
# infrastructure/orchestration/kubernetes/services/billing-service/01-deployment.yaml
spec:
  replicas: 2  # Safe to scale now with idempotent registration
```

**Benefits:**
- ✅ No duplicates regardless of replica count
- ✅ Safe to restart/scale anytime
- ✅ Enables high availability
- ✅ Self-healing - if webhook deleted, next pod restart will re-register

**Testing:**
```bash
# 1. Apply code changes
# 2. Restart billing-service
kubectl rollout restart deployment/billing-service -n saasodoo

# 3. Verify only one webhook registered
kubectl exec -n saasodoo killbill-db-0 -- mysql -uroot -pkillbill_root_secure_change_me -Dkillbill -e \
  "SELECT record_id, tenant_key FROM tenant_kvs WHERE tenant_key LIKE 'PUSH_NOTIFICATION_CB%';"

# Should show only ONE record

# 4. Scale to 2 replicas
kubectl scale deployment/billing-service -n saasodoo --replicas=2

# 5. Verify still only one webhook (idempotency working)
# Run same query again - should still show only ONE record
```

---

### Solution 2: Leader Election (Alternative - More Complex)

**Approach:** Use Kubernetes leader election to ensure only one pod registers webhook.

**Implementation:**
- Add leader election using `coordination.k8s.io/v1` Lease API
- Only the leader pod registers the webhook
- If leader dies, new leader is elected and checks/registers webhook

**Pros:**
- Guaranteed single registration
- Standard Kubernetes pattern

**Cons:**
- More complex implementation
- Requires additional RBAC permissions (leases)
- Overkill for this simple use case

**Recommendation:** Use Solution 1 (idempotent registration) instead.

---

### Solution 3: External Job/Operator (Alternative)

**Approach:** Move webhook registration out of application lifecycle.

**Implementation:**
- Create Kubernetes Job or Init Container that runs once
- Registers webhook before billing-service starts
- Uses same idempotent logic from Solution 1

**Pros:**
- Webhook registration decoupled from app lifecycle
- Runs only once on deployment

**Cons:**
- Additional resource to manage
- Doesn't handle webhook deletion/re-registration
- More moving parts

**Recommendation:** Use Solution 1 (idempotent registration) instead.

---

## Migration Plan

### Phase 1: Implement Idempotent Registration
1. Add `get_tenant_config()` method to `killbill_client.py`
2. Update `register_webhook()` to check before registering
3. Add unit tests for idempotency
4. Test in development environment

### Phase 2: Clean Up and Deploy
1. Clean up any duplicate webhooks in KillBill database:
   ```sql
   -- Keep only the first webhook registration
   DELETE FROM tenant_kvs
   WHERE tenant_key LIKE 'PUSH_NOTIFICATION_CB%'
   AND record_id > (
       SELECT MIN(record_id)
       FROM tenant_kvs
       WHERE tenant_key LIKE 'PUSH_NOTIFICATION_CB%'
   );
   ```
2. Deploy updated code
3. Restart billing-service to verify idempotency

### Phase 3: Scale Up
1. Update deployment to `replicas: 2`
2. Verify only one webhook remains registered
3. Monitor for any duplicate registrations

### Phase 4: Documentation
1. Update `CLAUDE.md` with webhook registration pattern
2. Add operational runbook for webhook verification
3. Document cleanup procedure for future reference

---

## Prevention

### Code Review Checklist
- [ ] All external API registrations must be idempotent
- [ ] Check for existing resources before creating
- [ ] Log when skipping duplicate creation
- [ ] Add integration tests for multi-replica scenarios

### Deployment Checklist
- [ ] Verify single webhook registration after deployment
- [ ] Test instance provisioning end-to-end
- [ ] Monitor KillBill logs for webhook errors
- [ ] Validate webhook delivery on test payment

---

## Related Files

### Code Files
- `services/billing-service/app/main.py` (lifespan function)
- `services/billing-service/app/utils/killbill_client.py` (register_webhook)

### Configuration Files
- `infrastructure/orchestration/kubernetes/services/billing-service/01-deployment.yaml` (replicas)

### Database
- Table: `killbill.tenant_kvs`
- Key pattern: `PUSH_NOTIFICATION_CB%`

---

## References

- KillBill API Documentation: https://docs.killbill.io/latest/tenant_configuration.html
- KillBill Webhook Registration: https://docs.killbill.io/latest/push_notifications.html
- Original issue discussion: 2025-12-24 Kubernetes migration session

---

## Appendix: Useful Commands

### Check webhook registrations
```bash
kubectl exec -n saasodoo killbill-db-0 -- mysql -uroot -pkillbill_root_secure_change_me -Dkillbill -e \
  "SELECT record_id, tenant_record_id, tenant_key, tenant_value FROM tenant_kvs WHERE tenant_key LIKE 'PUSH_NOTIFICATION_CB%' ORDER BY record_id;"
```

### Delete duplicate webhooks (keep first)
```bash
kubectl exec -n saasodoo killbill-db-0 -- mysql -uroot -pkillbill_root_secure_change_me -Dkillbill -e \
  "DELETE FROM tenant_kvs WHERE tenant_key = 'PUSH_NOTIFICATION_CB' AND record_id > (SELECT MIN(record_id) FROM (SELECT record_id FROM tenant_kvs WHERE tenant_key = 'PUSH_NOTIFICATION_CB') AS t);"
```

### Check billing-service replicas
```bash
kubectl get deployment billing-service -n saasodoo
```

### Check billing-service logs for webhook registration
```bash
kubectl logs -n saasodoo -l app.kubernetes.io/name=billing-service --tail=100 | grep webhook
```

### Test KillBill webhook endpoint
```bash
kubectl exec -n saasodoo deployment/killbill -- curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://billing-service:8004/api/billing/webhooks/killbill/healthcheck"
```
