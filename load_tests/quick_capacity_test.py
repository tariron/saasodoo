#!/usr/bin/env python3
"""
Quick Capacity Test - Simple throughput measurement

Measures how many users can be created per minute without Locust overhead.
This gives you a direct measurement of your registration pipeline capacity.

Usage:
    python quick_capacity_test.py --host http://api.62.171.153.219.nip.io --users 100
    python quick_capacity_test.py --host http://api.62.171.153.219.nip.io --users 100 --concurrent 10
"""

import argparse
import asyncio
import aiohttp
import time
import random
import string
from dataclasses import dataclass
from typing import List
import sys


@dataclass
class TestResult:
    success: bool
    status_code: int
    response_time_ms: float
    error: str = None
    customer_id: str = None


class CapacityTester:
    """Async capacity tester for user registration."""

    def __init__(self, host: str, user_prefix: str = "/user"):
        self.host = host.rstrip("/")
        self.user_prefix = user_prefix
        self.register_url = f"{self.host}{user_prefix}/auth/register"
        self.health_url = f"{self.host}{user_prefix}/health"
        self.password = "LoadTest123!"
        self.email_domain = "capacitytest.saasodoo.local"

    def generate_email(self) -> str:
        """Generate unique email."""
        ts = int(time.time() * 1000000)
        suffix = ''.join(random.choices(string.ascii_lowercase, k=4))
        return f"cap_{ts}_{suffix}@{self.email_domain}"

    def generate_payload(self) -> dict:
        """Generate registration payload."""
        first_names = ["John", "Jane", "Mike", "Sarah", "Alex", "Emma"]
        last_names = ["Smith", "Johnson", "Brown", "Garcia", "Miller"]

        return {
            "email": self.generate_email(),
            "password": self.password,
            "first_name": random.choice(first_names),
            "last_name": random.choice(last_names),
            "accept_terms": True
        }

    async def check_health(self, session: aiohttp.ClientSession) -> bool:
        """Check if service is healthy."""
        try:
            async with session.get(self.health_url, timeout=5) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Health check failed: {e}")
            return False

    async def register_user(self, session: aiohttp.ClientSession) -> TestResult:
        """Register a single user and measure time."""
        payload = self.generate_payload()
        start = time.perf_counter()

        try:
            async with session.post(
                self.register_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                elapsed_ms = (time.perf_counter() - start) * 1000
                body = await resp.json()

                if resp.status == 201 and body.get("success"):
                    return TestResult(
                        success=True,
                        status_code=resp.status,
                        response_time_ms=elapsed_ms,
                        customer_id=body.get("customer", {}).get("id")
                    )
                else:
                    return TestResult(
                        success=False,
                        status_code=resp.status,
                        response_time_ms=elapsed_ms,
                        error=body.get("detail", str(body))
                    )
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                success=False,
                status_code=0,
                response_time_ms=elapsed_ms,
                error="Timeout"
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                success=False,
                status_code=0,
                response_time_ms=elapsed_ms,
                error=str(e)
            )

    async def run_batch(
        self,
        session: aiohttp.ClientSession,
        count: int,
        semaphore: asyncio.Semaphore
    ) -> List[TestResult]:
        """Run a batch of registrations with concurrency limit."""

        async def limited_register():
            async with semaphore:
                return await self.register_user(session)

        tasks = [limited_register() for _ in range(count)]
        return await asyncio.gather(*tasks)

    async def run_test(
        self,
        total_users: int,
        concurrency: int,
        progress_callback=None
    ) -> dict:
        """Run capacity test and return metrics."""

        connector = aiohttp.TCPConnector(
            limit=concurrency * 2,
            limit_per_host=concurrency * 2
        )

        async with aiohttp.ClientSession(connector=connector) as session:
            # Health check first
            print("Checking service health...")
            if not await self.check_health(session):
                return {"error": "Service health check failed"}

            print(f"Starting capacity test: {total_users} users, {concurrency} concurrent")
            print("-" * 50)

            semaphore = asyncio.Semaphore(concurrency)
            results: List[TestResult] = []
            start_time = time.perf_counter()

            # Run in smaller batches for progress reporting
            batch_size = min(concurrency * 2, total_users)
            remaining = total_users

            while remaining > 0:
                batch = min(batch_size, remaining)
                batch_results = await self.run_batch(session, batch, semaphore)
                results.extend(batch_results)
                remaining -= batch

                if progress_callback:
                    progress_callback(len(results), total_users)
                else:
                    success_count = sum(1 for r in results if r.success)
                    print(f"Progress: {len(results)}/{total_users} "
                          f"(Success: {success_count}, "
                          f"Failed: {len(results) - success_count})")

            total_time = time.perf_counter() - start_time

            # Calculate metrics
            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]

            response_times = [r.response_time_ms for r in results]
            success_times = [r.response_time_ms for r in successful] or [0]

            metrics = {
                "total_users": total_users,
                "concurrency": concurrency,
                "total_time_seconds": round(total_time, 2),
                "successful_registrations": len(successful),
                "failed_registrations": len(failed),
                "success_rate_percent": round(len(successful) / total_users * 100, 2),
                "users_per_minute": round(len(successful) / total_time * 60, 2),
                "users_per_second": round(len(successful) / total_time, 2),
                "avg_response_time_ms": round(sum(response_times) / len(response_times), 2),
                "avg_success_response_time_ms": round(sum(success_times) / len(success_times), 2),
                "min_response_time_ms": round(min(response_times), 2),
                "max_response_time_ms": round(max(response_times), 2),
                "p50_response_time_ms": round(sorted(response_times)[len(response_times)//2], 2),
                "p95_response_time_ms": round(sorted(response_times)[int(len(response_times)*0.95)], 2),
                "p99_response_time_ms": round(sorted(response_times)[int(len(response_times)*0.99)], 2),
            }

            # Error breakdown
            if failed:
                error_counts = {}
                for r in failed:
                    error_counts[r.error] = error_counts.get(r.error, 0) + 1
                metrics["errors"] = error_counts

            return metrics


def print_results(metrics: dict):
    """Print test results in a readable format."""
    if "error" in metrics:
        print(f"\nERROR: {metrics['error']}")
        return

    print("\n" + "=" * 60)
    print("CAPACITY TEST RESULTS")
    print("=" * 60)

    print(f"\n{'THROUGHPUT':^60}")
    print("-" * 60)
    print(f"  Users Created Per Minute:  {metrics['users_per_minute']:>15.2f}")
    print(f"  Users Created Per Second:  {metrics['users_per_second']:>15.2f}")

    print(f"\n{'SUMMARY':^60}")
    print("-" * 60)
    print(f"  Total Users Attempted:     {metrics['total_users']:>15}")
    print(f"  Successful Registrations:  {metrics['successful_registrations']:>15}")
    print(f"  Failed Registrations:      {metrics['failed_registrations']:>15}")
    print(f"  Success Rate:              {metrics['success_rate_percent']:>14.2f}%")
    print(f"  Total Test Time:           {metrics['total_time_seconds']:>13.2f}s")
    print(f"  Concurrency Level:         {metrics['concurrency']:>15}")

    print(f"\n{'RESPONSE TIMES':^60}")
    print("-" * 60)
    print(f"  Average:                   {metrics['avg_response_time_ms']:>13.2f}ms")
    print(f"  Average (success only):    {metrics['avg_success_response_time_ms']:>13.2f}ms")
    print(f"  Minimum:                   {metrics['min_response_time_ms']:>13.2f}ms")
    print(f"  Maximum:                   {metrics['max_response_time_ms']:>13.2f}ms")
    print(f"  P50 (Median):              {metrics['p50_response_time_ms']:>13.2f}ms")
    print(f"  P95:                       {metrics['p95_response_time_ms']:>13.2f}ms")
    print(f"  P99:                       {metrics['p99_response_time_ms']:>13.2f}ms")

    if "errors" in metrics:
        print(f"\n{'ERRORS':^60}")
        print("-" * 60)
        for error, count in metrics["errors"].items():
            print(f"  {error[:40]:40} {count:>5}")

    print("\n" + "=" * 60)


async def main():
    parser = argparse.ArgumentParser(
        description="Quick capacity test for SaaSOdoo user registration"
    )
    parser.add_argument(
        "--host",
        default="http://api.62.171.153.219.nip.io",
        help="API host URL"
    )
    parser.add_argument(
        "--users",
        type=int,
        default=50,
        help="Number of users to create (default: 50)"
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=10,
        help="Concurrent requests (default: 10)"
    )
    parser.add_argument(
        "--prefix",
        default="/user",
        help="User service URL prefix (default: /user)"
    )

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           SaaSOdoo Quick Capacity Test                       ║
╠══════════════════════════════════════════════════════════════╣
║  Host:        {args.host:<45} ║
║  Users:       {args.users:<45} ║
║  Concurrent:  {args.concurrent:<45} ║
╠══════════════════════════════════════════════════════════════╣
║  WARNING: This creates REAL users and KillBill accounts!     ║
╚══════════════════════════════════════════════════════════════╝
""")

    confirm = input("Continue? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    tester = CapacityTester(args.host, args.prefix)
    metrics = await tester.run_test(args.users, args.concurrent)
    print_results(metrics)


if __name__ == "__main__":
    asyncio.run(main())
