#!/usr/bin/env python3
"""
Billing Service Direct Capacity Test
Tests account creation via billing-service API (billing-service -> KillBill).
"""

import requests
import time
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List
import sys
import argparse
import uuid


@dataclass
class TestResult:
    success: bool
    status_code: int
    response_time_ms: float
    error: str = None


class BillingServiceTester:
    def __init__(self, host: str):
        self.host = host.rstrip("/")
        self.account_url = f"{self.host}/api/billing/accounts/"
        self.health_url = f"{self.host}/health"

    def generate_customer_id(self) -> str:
        return str(uuid.uuid4())

    def generate_payload(self) -> dict:
        ts = int(time.time() * 1000000)
        suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
        return {
            "customer_id": self.generate_customer_id(),
            "email": f"billing_test_{ts}_{suffix}@loadtest.com",
            "name": f"Test User {suffix}",
            "company": "LoadTest Corp"
        }

    def check_health(self) -> bool:
        try:
            resp = requests.get(self.health_url, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    def create_account(self) -> TestResult:
        payload = self.generate_payload()
        start = time.perf_counter()
        try:
            resp = requests.post(self.account_url, json=payload, timeout=30)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code in [200, 201]:
                data = resp.json()
                if data.get("success"):
                    return TestResult(True, resp.status_code, elapsed_ms)
                return TestResult(False, resp.status_code, elapsed_ms, str(data)[:100])
            return TestResult(False, resp.status_code, elapsed_ms, resp.text[:100])
        except requests.Timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(False, 0, elapsed_ms, "Timeout")
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(False, 0, elapsed_ms, str(e)[:100])

    def run_test(self, total: int, concurrency: int) -> dict:
        print("Checking billing-service health...")
        if not self.check_health():
            return {"error": "Billing service health check failed"}

        print(f"Starting: {total} accounts, {concurrency} concurrent")
        print("-" * 50)

        results: List[TestResult] = []
        start_time = time.perf_counter()
        completed = 0

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(self.create_account) for _ in range(total)]

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1

                if completed % 10 == 0 or completed == total:
                    success = sum(1 for r in results if r.success)
                    print(f"Progress: {completed}/{total} (Success: {success}, Failed: {completed - success})")

        total_time = time.perf_counter() - start_time
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        response_times = [r.response_time_ms for r in results]

        metrics = {
            "total": total,
            "concurrency": concurrency,
            "total_time_seconds": round(total_time, 2),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": round(len(successful) / total * 100, 2),
            "per_minute": round(len(successful) / total_time * 60, 2),
            "per_second": round(len(successful) / total_time, 2),
            "avg_response_ms": round(sum(response_times) / len(response_times), 2),
            "min_response_ms": round(min(response_times), 2),
            "max_response_ms": round(max(response_times), 2),
            "p50_ms": round(sorted(response_times)[len(response_times)//2], 2),
            "p95_ms": round(sorted(response_times)[int(len(response_times)*0.95)], 2),
        }

        if failed:
            error_counts = {}
            for r in failed:
                key = (r.error or "Unknown")[:50]
                error_counts[key] = error_counts.get(key, 0) + 1
            metrics["errors"] = error_counts

        return metrics


def print_results(m: dict, title: str):
    if "error" in m:
        print(f"\nERROR: {m['error']}")
        return

    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)
    print(f"\n  ACCOUNTS PER MINUTE:       {m['per_minute']:>10.1f}")
    print(f"  ACCOUNTS PER SECOND:       {m['per_second']:>10.2f}")
    print("-" * 60)
    print(f"  Total Attempted:           {m['total']:>10}")
    print(f"  Successful:                {m['successful']:>10}")
    print(f"  Failed:                    {m['failed']:>10}")
    print(f"  Success Rate:              {m['success_rate']:>9.1f}%")
    print(f"  Total Time:                {m['total_time_seconds']:>9.1f}s")
    print(f"  Concurrency:               {m['concurrency']:>10}")
    print("-" * 60)
    print(f"  Avg Response:              {m['avg_response_ms']:>9.0f}ms")
    print(f"  Min Response:              {m['min_response_ms']:>9.0f}ms")
    print(f"  Max Response:              {m['max_response_ms']:>9.0f}ms")
    print(f"  P50 (Median):              {m['p50_ms']:>9.0f}ms")
    print(f"  P95:                       {m['p95_ms']:>9.0f}ms")

    if "errors" in m:
        print("-" * 60)
        print("  ERRORS:")
        for err, count in m["errors"].items():
            print(f"    {err[:45]:45} x{count}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Billing service direct capacity test")
    parser.add_argument("--host", default="http://api.62.171.153.219.nip.io/billing")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--concurrent", type=int, default=50)
    parser.add_argument("-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════╗
║         Billing Service Direct Capacity Test               ║
╠════════════════════════════════════════════════════════════╣
║  Host:       {args.host:<44} ║
║  Accounts:   {args.count:<44} ║
║  Concurrent: {args.concurrent:<44} ║
╚════════════════════════════════════════════════════════════╝
""")

    if not args.y:
        confirm = input("Continue? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    tester = BillingServiceTester(args.host)
    metrics = tester.run_test(args.count, args.concurrent)
    print_results(metrics, "BILLING SERVICE DIRECT TEST RESULTS")
