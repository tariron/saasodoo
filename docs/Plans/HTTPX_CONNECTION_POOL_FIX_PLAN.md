# HTTPX Connection Pool & Service Resilience Fix Plan

## Problem Statement

During capacity testing, the user-service became unresponsive after handling ~50 concurrent registration requests. Even after the load stopped, the service remained stuck and required a restart.

### Root Causes

1. **Single Uvicorn Worker**: No `--workers` flag means single asyncio event loop
2. **New httpx Client Per Request**: Each request creates its own connection pool
3. **No Concurrency Limits**: Unlimited concurrent calls to external services (KillBill, billing-service)
4. **Resource Exhaustion**: OS sockets and connections not properly released after failures
5. **Blocking bcrypt Calls**: `bcrypt.hashpw()` is CPU-bound (~100-300ms) and blocks the event loop

### Observed Behavior

- 50 concurrent requests → all waiting on KillBill (5-10s each)
- Event loop overwhelmed, new requests can't start
- Health checks still pass (already queued)
- Service stuck even after load stops
- Required pod restart to recover

## KillBill Performance Baseline

From KillBill documentation:
- **Sustained rate**: ~133 account creations/second under load
- **Average latency**: ~200ms under normal load
- **Our observed**: 5-10s per account creation (indicates bottleneck elsewhere)

This suggests our slowness is not KillBill itself but our connection handling.

## Solution

### Phase 1: Immediate Fixes (This PR)

#### 1.1 Add Uvicorn Workers
```dockerfile
# user-service/Dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
```

#### 1.2 Update Uvicorn Version
```
# requirements.txt
uvicorn[standard]>=0.30.0
```

### Phase 2: Connection Pool Optimization (Future)

#### 2.1 Run bcrypt in Thread Pool

**File**: `services/user-service/app/services/auth_service.py`

bcrypt is CPU-bound and blocks the asyncio event loop. Run it in a thread pool:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
import bcrypt

# Create a thread pool for CPU-bound operations
_executor = ThreadPoolExecutor(max_workers=4)

class AuthService:
    @staticmethod
    async def hash_password_async(password: str) -> str:
        """Hash password using bcrypt in a thread pool (non-blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            AuthService._hash_password_sync,
            password
        )

    @staticmethod
    def _hash_password_sync(password: str) -> str:
        """Synchronous bcrypt hashing (for thread pool)"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    @staticmethod
    async def verify_password_async(password: str, hashed_password: str) -> bool:
        """Verify password in thread pool (non-blocking)"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            bcrypt.checkpw,
            password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
```

Then update `register_customer()`:
```python
# Before (blocking):
password_hash = AuthService.hash_password(customer_data.password)

# After (non-blocking):
password_hash = await AuthService.hash_password_async(customer_data.password)
```

#### 2.2 Shared httpx Client with Limits

**File**: `services/user-service/app/utils/billing_client.py`

```python
import asyncio
import httpx

class BillingServiceClient:
    _instance = None
    _client: httpx.AsyncClient = None
    _semaphore: asyncio.Semaphore = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, base_url: str = None, max_concurrent: int = 10):
        if self._client is not None:
            return

        self.base_url = base_url or os.getenv('BILLING_SERVICE_URL', 'http://billing-service:8004')
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=30.0,
                write=5.0,
                pool=10.0
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0
            )
        )

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        async with self._semaphore:  # Limit concurrent external calls
            response = await self._client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
```

#### 2.3 Graceful Shutdown

**File**: `services/user-service/app/main.py`

```python
from contextlib import asynccontextmanager
from app.utils.billing_client import billing_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown - cleanup connections
    await billing_client.close()

app = FastAPI(lifespan=lifespan)
```

### Phase 3: Circuit Breaker (Future)

Add circuit breaker pattern to fail fast when external services are slow:

```python
from circuitbreaker import circuit

class BillingServiceClient:
    @circuit(failure_threshold=5, recovery_timeout=60, expected_exception=Exception)
    async def create_customer_account(self, ...):
        ...
```

## Services to Update

| Service | File | Changes |
|---------|------|---------|
| user-service | Dockerfile | Add `--workers 4` ✅ |
| user-service | requirements.txt | uvicorn>=0.30.0, httpx>=0.27.0 ✅ |
| user-service | auth_service.py | Run bcrypt in thread pool |
| user-service | billing_client.py | Shared client + semaphore |
| billing-service | Dockerfile | Add `--workers 4` ✅ |
| billing-service | requirements.txt | httpx>=0.27.0 ✅ |
| billing-service | killbill_client.py | Shared client + semaphore |
| instance-service | Dockerfile | Add `--workers 4` ✅ |
| instance-service | requirements.txt | uvicorn>=0.30.0, httpx>=0.27.0 ✅ |

## Testing

After implementing:

1. Run capacity test: `python load_tests/capacity_test.py --users 100 --concurrent 20`
2. Verify no service degradation
3. Stop test and verify service recovers without restart
4. Check connection pool metrics

## Expected Results

| Metric | Before (1 worker) | Phase 1 (4 workers) | Phase 2 Target |
|--------|-------------------|---------------------|----------------|
| Max concurrent | ~20 | 50+ ✅ | 100+ |
| Recovery after load | Requires restart | Self-healing ✅ | Self-healing |
| Users/minute | ~100 | ~210 ✅ | ~400+ |
| Service stability | Fragile | Improved ✅ | Resilient |
| Latency @ 10 concurrent | 5.4s avg | 2.9s avg ✅ | <1s avg |

**Note**: Phase 1 achieved ~2x improvement. Phase 2 (bcrypt + connection pooling) should approach KillBill's 133 accounts/sec capability.

## References

- [KillBill Performance Numbers](https://blog.killbill.io/blog/performance-numbers/)
- [httpx Connection Pooling](https://www.python-httpx.org/advanced/#pool-limit-configuration)
- [Uvicorn Deployment](https://www.uvicorn.org/deployment/)
