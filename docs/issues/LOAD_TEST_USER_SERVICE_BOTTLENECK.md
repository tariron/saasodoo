# Load Testing Analysis: User Service Bottleneck

**Date:** 2025-12-30
**Status:** Partially Resolved
**Severity:** High
**Affected Services:** user-service, billing-service, KillBill

---

## Executive Summary

During load testing of the SaaSOdoo platform, we identified significant performance bottlenecks in the user registration flow. Initial testing showed the system could handle ~210 users/min at 50 concurrent connections. After optimization attempts, performance degraded to ~70 users/min with 69% success rate.

Root cause analysis revealed that "optimization" changes to user-service (connection pooling, async password hashing) actually **degraded** performance. Reverting user-service to the simpler implementation restored performance to **500+ users/min at 150 concurrent with 100% success rate**.

The system has a hard limit at ~150-175 concurrent connections, beyond which user-service becomes unresponsive and requires a restart.

---

## Problem Description

### Symptoms Observed

1. **Timeouts under load**: At 50+ concurrent requests, registration requests started timing out (30s timeout)
2. **Degraded throughput**: Performance dropped from 210 users/min to 70 users/min after "optimizations"
3. **Service unresponsiveness**: At 200 concurrent, user-service becomes completely stuck and doesn't recover
4. **Cascading failures**: Once stuck, even single requests timeout until service restart

### Test Configuration

- **Test Tool**: Custom Python capacity_test.py using ThreadPoolExecutor
- **Endpoint**: `POST /user/auth/register`
- **Timeout**: 30 seconds per request
- **Test Sizes**: 50-300 users, 25-200 concurrent

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌──────────┐
│   Client    │────▶│  user-service   │────▶│ billing-service  │────▶│ KillBill │
│ (Load Test) │     │  (2 replicas)   │     │   (2 replicas)   │     │(1 replica)│
└─────────────┘     └────────┬────────┘     └──────────────────┘     └─────┬────┘
                             │                                              │
                             ▼                                              ▼
                    ┌────────────────┐                             ┌────────────────┐
                    │   PostgreSQL   │                             │    MariaDB     │
                    │  (auth db)     │                             │ (KillBill db)  │
                    └────────────────┘                             └────────────────┘
```

### Registration Flow

1. Client → user-service: `POST /auth/register`
2. user-service: Hash password (bcrypt)
3. user-service: Create user in PostgreSQL
4. user-service → billing-service: Create billing account
5. billing-service → KillBill: Create account (POST)
6. billing-service → KillBill: Set AUTO_PAY_OFF tag (POST)
7. Response returns to client

---

## Investigation Process

### Phase 1: Initial Baseline (Commit c262e24)

**Results:**
- 50 concurrent: 100% success, ~210 users/min
- System self-heals after load spikes

### Phase 2: Attempted Optimizations

Changes made to improve performance:

| Change | File | Rationale |
|--------|------|-----------|
| httpx connection pooling | billing_client.py | Reuse connections instead of new per request |
| Async password hashing | auth_service.py | Use `asyncio.to_thread()` for bcrypt |
| Database pool tuning | database.py | Increased min_size 5→10 |
| Shared httpx client | killbill_client.py | Connection pooling for KillBill calls |

**Results after optimizations:**
- 30 concurrent: 74% success, 69.5 users/min
- 50 concurrent: 69% success, 120 users/min
- Significant regression

### Phase 3: Component Isolation Testing

To identify the bottleneck, we tested each component independently:

| Test | Concurrency | Success Rate | Throughput |
|------|-------------|--------------|------------|
| billing-service → KillBill direct | 20 | 100% | 804 accounts/min |
| billing-service → KillBill direct | 50 | 100% | 593 accounts/min |
| Full registration flow | 20 | 0% | Timeouts |
| Full registration flow | 30 | 74% | 69.5 users/min |

**Key Finding:** billing-service and KillBill performed excellently in isolation. The bottleneck was in user-service.

### Phase 4: Reversion Testing

Reverted user-service to c262e24 (original simpler code):

| Concurrency | Success Rate | Throughput |
|-------------|--------------|------------|
| 30 | 100% | 554 users/min |
| 50 | 100% | 495 users/min |
| 70 | 100% | 554 users/min |
| 100 | 100% | 567 users/min |
| 150 | 100% | 517 users/min |
| 200 | 0% | All timeout, service stuck |

---

## Root Cause Analysis

### Why "Optimizations" Made Things Worse

#### 1. Connection Pooling in billing_client.py

**Original (working):**
```python
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.request(method, url, **kwargs)
```

**"Optimized" (broken):**
```python
# Class-level shared client
_client: Optional[httpx.AsyncClient] = None

def _get_client(self):
    if self._client is None:
        self._client = httpx.AsyncClient(...)
    return self._client
```

**Problems:**
- Class-level client doesn't work with multiple uvicorn workers (separate processes)
- Each worker sees `_client = None` and creates its own, but reference management breaks
- Connection pool settings (max_connections=100, keepalive_expiry=5s) caused connection churn

#### 2. Async Password Hashing

**Original:**
```python
password_hash = AuthService.hash_password(customer_data.password)
```

**"Optimized":**
```python
password_hash = await AuthService.hash_password_async(customer_data.password)

async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(AuthService.hash_password, password)
```

**Problems:**
- `asyncio.to_thread()` adds thread pool overhead
- At high concurrency, thread pool becomes contention point
- Original blocking bcrypt was fast enough (~100ms) to not block event loop significantly

#### 3. Database Pool Changes

**Original:** `min_size=5, max_size=20, command_timeout=60`
**"Optimized":** `min_size=10, max_size=20, command_timeout=30`

**Problems:**
- Higher min_size means more idle connections competing
- Shorter command_timeout caused premature failures under load

### Why Service Gets Stuck at 200 Concurrent

At extreme load, the original code creates 200+ simultaneous httpx.AsyncClient instances:

```python
# Each request creates a new client
async with httpx.AsyncClient(timeout=30.0) as client:
    response = await client.request(...)
```

This causes:
1. **File descriptor exhaustion**: Each client opens TCP connections
2. **Connection table saturation**: OS limits on concurrent connections
3. **No backpressure**: Requests keep piling up with no rejection mechanism
4. **Event loop starvation**: Too many pending coroutines

Once saturated, the service cannot process even health checks, appearing "stuck."

---

## Current Performance Metrics

### After Final Configuration

| Metric | Value |
|--------|-------|
| Max Safe Concurrency | 150 |
| Throughput at 150 concurrent | 517 users/min |
| Success Rate at 150 concurrent | 100% |
| Average Response Time | 9-15 seconds |
| P95 Response Time | 14-20 seconds |
| Danger Zone | 175+ concurrent |
| Failure Mode | 200+ concurrent (complete timeout) |

### Resource Usage Under Load

| Pod | CPU | Memory |
|-----|-----|--------|
| user-service (x2) | 11-15m | 270-380Mi |
| billing-service (x2) | 11-14m | 318-322Mi |
| killbill (x1) | 32-50m | 800-900Mi |

**Note:** CPU usage is very low, indicating the bottleneck is I/O and connection management, not compute.

---

## Recommendations

### Immediate Actions (No Code Changes)

1. **Set operational limit at 150 concurrent**
   - Monitor concurrent connections
   - Implement rate limiting at Traefik/ingress level

2. **Add health check with connection status**
   - Monitor httpx client state
   - Alert when approaching limits

3. **Implement automatic restart on stuck detection**
   - Kubernetes liveness probe with registration endpoint test
   - Not just `/health` which may pass when stuck

### Short-Term Improvements

#### 1. Proper Connection Pooling (Recommended)

```python
# billing_client.py - Correct implementation
class BillingServiceClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or os.getenv('BILLING_SERVICE_URL')
        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Initialize on app startup"""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
            limits=httpx.Limits(
                max_connections=50,           # Per worker
                max_keepalive_connections=10,
                keepalive_expiry=30.0         # Longer keepalive
            )
        )

    async def stop(self):
        """Cleanup on app shutdown"""
        if self._client:
            await self._client.aclose()

    async def _make_request(self, method: str, endpoint: str, **kwargs):
        # Fallback if not initialized
        if not self._client:
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.request(method, f"{self.base_url}{endpoint}", **kwargs)
        return await self._client.request(method, endpoint, **kwargs)

# main.py - Lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    await billing_client.start()
    yield
    await billing_client.stop()
```

**Key principles:**
- Initialize client in app lifespan, not class variable
- Use reasonable limits (50 connections per worker)
- Longer keepalive (30s) to reduce connection churn
- Shorter pool timeout (10s) to fail fast
- Fallback to per-request client if pool fails

#### 2. Circuit Breaker Pattern

```python
from circuitbreaker import circuit

class BillingServiceClient:
    @circuit(failure_threshold=5, recovery_timeout=30)
    async def create_customer_account(self, ...):
        # Fails fast after 5 failures
        # Waits 30s before retrying
        pass
```

#### 3. Semaphore-Based Concurrency Limiting

```python
# Limit concurrent billing requests per worker
_billing_semaphore = asyncio.Semaphore(25)

async def create_customer_account(self, ...):
    async with _billing_semaphore:
        return await self._make_request(...)
```

### Medium-Term Improvements

#### 1. Scale KillBill Horizontally

Current: 1 replica → Target: 2-3 replicas

**Considerations:**
- KillBill uses database for state, should scale safely
- Previous attempt caused duplicate webhook issues (needs investigation)
- MariaDB may need connection pool tuning

#### 2. Async Registration with Queue

```
Current Flow (Synchronous):
Client → user-service → billing-service → KillBill → Response

Proposed Flow (Async):
Client → user-service → Queue → Response (202 Accepted)
                          ↓
                    Worker → billing-service → KillBill
                          ↓
                    Webhook/Polling for status
```

Benefits:
- Immediate response to client
- Natural backpressure via queue depth
- Retry handling built-in
- Better resource utilization

#### 3. Read-Through Cache for Account Existence Check

```python
# Redis cache for account existence
async def get_or_create_account(customer_id: str):
    cached = await redis.get(f"kb_account:{customer_id}")
    if cached:
        return json.loads(cached)

    account = await killbill.create_account(customer_id, ...)
    await redis.setex(f"kb_account:{customer_id}", 3600, json.dumps(account))
    return account
```

### Long-Term Architecture Changes

#### 1. Event-Driven Registration

```
┌────────┐     ┌─────────────┐     ┌─────────┐
│ Client │────▶│ API Gateway │────▶│ Kafka/  │
└────────┘     └─────────────┘     │ RabbitMQ│
                                   └────┬────┘
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
            │ User Worker  │   │Billing Worker│   │ Email Worker │
            └──────────────┘   └──────────────┘   └──────────────┘
```

#### 2. Dedicated Billing Microservice with CQRS

Separate read and write paths:
- Write: Registration creates events
- Read: Materialized views for account status

#### 3. KillBill Replacement Evaluation

If KillBill continues to be a bottleneck, evaluate:
- Stripe Billing (managed service)
- Chargebee
- Custom billing implementation for simpler use cases

---

## Monitoring Recommendations

### Key Metrics to Track

```yaml
# Prometheus metrics to add
- user_service_registration_total{status="success|failure"}
- user_service_registration_duration_seconds
- user_service_billing_client_requests_total
- user_service_billing_client_errors_total
- user_service_concurrent_registrations_gauge
- billing_service_killbill_requests_total
- billing_service_killbill_latency_seconds
```

### Alerting Rules

```yaml
# Alert when approaching limits
- alert: HighRegistrationConcurrency
  expr: user_service_concurrent_registrations_gauge > 100
  for: 1m
  labels:
    severity: warning

- alert: RegistrationFailureRate
  expr: rate(user_service_registration_total{status="failure"}[5m]) > 0.1
  for: 2m
  labels:
    severity: critical

- alert: UserServiceStuck
  expr: up{job="user-service"} == 1 AND rate(user_service_registration_total[1m]) == 0
  for: 5m
  labels:
    severity: critical
```

---

## Lessons Learned

1. **Measure before optimizing**: The "optimizations" were applied without baseline measurements, making it impossible to detect regression immediately.

2. **Simpler is often better**: Creating a new httpx client per request (simple) outperformed shared connection pooling (complex) due to worker isolation issues.

3. **Test at production scale**: Unit tests passed, but issues only appeared at 50+ concurrent requests.

4. **Connection pooling is tricky**: Shared state across async workers/processes requires careful lifecycle management.

5. **Fail fast, recover fast**: The system should reject requests at capacity rather than queue indefinitely and become stuck.

6. **Component isolation testing**: Testing each service independently quickly identified that user-service was the bottleneck, not billing-service or KillBill.

---

## Action Items

| Priority | Item | Owner | Status |
|----------|------|-------|--------|
| P0 | Set operational limit at 150 concurrent | DevOps | Pending |
| P0 | Add liveness probe with registration test | DevOps | Pending |
| P1 | Implement proper connection pooling | Backend | Pending |
| P1 | Add concurrency metrics | Backend | Pending |
| P2 | Implement circuit breaker | Backend | Pending |
| P2 | Investigate KillBill scaling | Backend | Pending |
| P3 | Evaluate async registration queue | Architecture | Pending |

---

## References

- Commit c262e24: Working baseline (210 users/min)
- Commit 9c478c9: Current state with billing-service optimizations
- [httpx Connection Pooling Docs](https://www.python-httpx.org/advanced/#pool-limit-configuration)
- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)
- [asyncio.to_thread Performance](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread)

---

## Appendix A: Test Commands

```bash
# Run capacity test
cd /root/Projects/saasodoo/load_tests
python3 capacity_test.py --host http://api.62.171.153.219.nip.io --users 100 --concurrent 50 -y

# Check service health
curl http://api.62.171.153.219.nip.io/user/health
curl http://api.62.171.153.219.nip.io/billing/health

# Restart stuck service
kubectl rollout restart deployment/user-service -n saasodoo

# Check logs for errors
kubectl logs -n saasodoo -l app.kubernetes.io/name=user-service --tail=100 | grep ERROR

# Monitor pod resources
kubectl top pods -n saasodoo | grep -E "(user|billing|killbill)"
```

## Appendix B: Configuration Files

### Current Working Configuration

**user-service** (c262e24 - simple approach):
- New httpx client per request
- Synchronous bcrypt password hashing
- Database pool: min=5, max=20

**billing-service** (optimized):
- Shared httpx connection pool for KillBill
- Location header for account ID (no GET after POST)
- Optimistic account creation
