#!/usr/bin/env python3
"""
Async User Service Capacity Test
Uses asyncio with aiohttp-like approach via urllib + ThreadPoolExecutor for comparison.
"""

import asyncio
import urllib.request
import urllib.error
import json
import time
import random
import string
import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

def register_user_sync(url, timeout):
    """Synchronous registration - called from thread pool"""
    ts = int(time.time() * 1000000)
    suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
    payload = {
        "email": f"async_{ts}_{suffix}@loadtest.saasodoo.com",
        "password": "LoadTest123@",
        "first_name": "Test",
        "last_name": "User",
        "accept_terms": True
    }

    start = time.perf_counter()
    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=data,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed = (time.perf_counter() - start) * 1000
            return resp.status == 201, elapsed, None
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return False, elapsed, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        elapsed = (time.perf_counter() - start) * 1000
        return False, elapsed, f"URL Error: {str(e.reason)[:30]}"
    except TimeoutError:
        elapsed = (time.perf_counter() - start) * 1000
        return False, elapsed, "Timeout"
    except Exception as e:
        elapsed = (time.perf_counter() - start) * 1000
        return False, elapsed, str(e)[:40]

async def register_user_async(url, timeout, executor, semaphore):
    """Async wrapper around sync call"""
    async with semaphore:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, register_user_sync, url, timeout)

async def main(total, concurrent, timeout):
    url = "http://api.62.171.153.219.nip.io/user/auth/register"
    semaphore = asyncio.Semaphore(concurrent)

    # Use larger thread pool to avoid executor bottleneck
    executor = ThreadPoolExecutor(max_workers=concurrent * 2)

    print(f"Starting async test: {total} users, {concurrent} concurrent, {timeout}s timeout")
    print(f"Thread pool size: {concurrent * 2}")
    print("-" * 60)

    start = time.perf_counter()
    tasks = [register_user_async(url, timeout, executor, semaphore) for _ in range(total)]
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    executor.shutdown(wait=False)

    success_count = sum(1 for r, _, _ in results if r)
    failed = [(t, e) for r, t, e in results if not r]
    times = [t for _, t, _ in results]

    # Calculate percentiles
    sorted_times = sorted(times)
    p50 = sorted_times[len(sorted_times)//2]
    p95 = sorted_times[int(len(sorted_times)*0.95)]
    p99 = sorted_times[int(len(sorted_times)*0.99)]

    print(f"\n{'='*60}")
    print("ASYNC USER SERVICE TEST RESULTS")
    print(f"{'='*60}")
    print(f"\n  USERS PER MINUTE:          {60*success_count/elapsed:>10.1f}")
    print(f"  USERS PER SECOND:          {success_count/elapsed:>10.2f}")
    print("-" * 60)
    print(f"  Total Attempted:           {total:>10}")
    print(f"  Successful:                {success_count:>10}")
    print(f"  Failed:                    {len(failed):>10}")
    print(f"  Success Rate:              {100*success_count/total:>9.1f}%")
    print(f"  Total Time:                {elapsed:>9.1f}s")
    print(f"  Concurrency:               {concurrent:>10}")
    print("-" * 60)
    print(f"  Avg Response:              {sum(times)/len(times):>9.0f}ms")
    print(f"  Min Response:              {min(times):>9.0f}ms")
    print(f"  Max Response:              {max(times):>9.0f}ms")
    print(f"  P50 (Median):              {p50:>9.0f}ms")
    print(f"  P95:                       {p95:>9.0f}ms")
    print(f"  P99:                       {p99:>9.0f}ms")

    if failed:
        print("-" * 60)
        print("  ERRORS:")
        error_counts = {}
        for t, e in failed:
            error_counts[e or "Unknown"] = error_counts.get(e or "Unknown", 0) + 1
        for err, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            print(f"    {str(err)[:45]:45} x{count}")

    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Async user service capacity test")
    parser.add_argument("--count", type=int, default=100, help="Total requests")
    parser.add_argument("--concurrent", type=int, default=50, help="Concurrent requests")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds")
    parser.add_argument("-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════╗
║         Async User Service Capacity Test                   ║
╠════════════════════════════════════════════════════════════╣
║  Host:       http://api.62.171.153.219.nip.io/user        ║
║  Users:      {args.count:<44} ║
║  Concurrent: {args.concurrent:<44} ║
║  Timeout:    {args.timeout}s{' '*(43-len(str(args.timeout)))} ║
║  Threads:    {args.concurrent * 2:<44} ║
╚════════════════════════════════════════════════════════════╝
""")

    if not args.y:
        confirm = input("Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    asyncio.run(main(args.count, args.concurrent, args.timeout))
