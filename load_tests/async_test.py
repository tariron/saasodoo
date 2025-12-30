import asyncio
import httpx
import time
import random
import string

async def register_user(client, url, semaphore):
    ts = int(time.time() * 1000000)
    suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
    payload = {
        "email": f"async_{ts}_{suffix}@loadtest.saasodoo.com",
        "password": "LoadTest123@",
        "first_name": "Test",
        "last_name": "User",
        "accept_terms": True
    }
    async with semaphore:
        start = time.perf_counter()
        try:
            resp = await client.post(url, json=payload, timeout=30)
            elapsed = (time.perf_counter() - start) * 1000
            return resp.status_code == 201, elapsed
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return False, elapsed

async def main(total=100, concurrent=50):
    url = "http://api.62.171.153.219.nip.io/user/auth/register"
    semaphore = asyncio.Semaphore(concurrent)
    
    limits = httpx.Limits(max_connections=concurrent*2, max_keepalive_connections=concurrent)
    async with httpx.AsyncClient(limits=limits) as client:
        start = time.perf_counter()
        tasks = [register_user(client, url, semaphore) for _ in range(total)]
        results = await asyncio.gather(*tasks)
        elapsed = time.perf_counter() - start
        
        success = sum(1 for r, _ in results if r)
        times = [t for _, t in results]
        
        print(f"\n{'='*50}")
        print(f"Total: {total}, Concurrent: {concurrent}")
        print(f"Success: {success}/{total} ({100*success/total:.1f}%)")
        print(f"Time: {elapsed:.1f}s")
        print(f"Users/min: {60*total/elapsed:.1f}")
        print(f"Avg: {sum(times)/len(times):.0f}ms, Min: {min(times):.0f}ms, Max: {max(times):.0f}ms")
        print(f"{'='*50}")

asyncio.run(main(100, 50))
