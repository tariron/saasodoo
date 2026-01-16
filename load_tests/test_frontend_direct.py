#!/usr/bin/env python3
"""
Frontend Service Direct Capacity Test
Tests static file serving performance (Flask serving React build files).

Measures:
- Requests per second for static assets
- Response times (latency)
- Concurrent connection handling
- Transfer rates
"""

import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict
import sys
import argparse


@dataclass
class TestResult:
    success: bool
    status_code: int
    response_time_ms: float
    bytes_received: int = 0
    error: str = None


class FrontendServiceTester:
    def __init__(self, host: str):
        self.host = host.rstrip("/")
        self.session = requests.Session()

        # Endpoints to test (different file types/sizes)
        self.endpoints = {
            "index": "/",                    # Main HTML page
            "health": "/health",             # Health check (if available)
        }

    def check_health(self) -> Dict:
        """Check frontend service and discover available assets"""
        info = {"healthy": False, "assets": []}

        try:
            # Check main page
            resp = self.session.get(f"{self.host}/", timeout=10)
            if resp.status_code == 200:
                info["healthy"] = True
                info["index_size"] = len(resp.content)

                # Try to find JS/CSS assets from the HTML
                content = resp.text

                # Look for static assets in the HTML
                import re
                js_files = re.findall(r'src="(/static/js/[^"]+)"', content)
                css_files = re.findall(r'href="(/static/css/[^"]+)"', content)

                for js in js_files[:2]:  # Limit to 2 JS files
                    info["assets"].append({"path": js, "type": "js"})
                for css in css_files[:2]:  # Limit to 2 CSS files
                    info["assets"].append({"path": css, "type": "css"})

        except Exception as e:
            info["error"] = str(e)

        return info

    def fetch_url(self, path: str) -> TestResult:
        """Fetch a single URL and measure performance"""
        url = f"{self.host}{path}"
        start = time.perf_counter()

        try:
            resp = self.session.get(url, timeout=30)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                return TestResult(
                    success=True,
                    status_code=resp.status_code,
                    response_time_ms=elapsed_ms,
                    bytes_received=len(resp.content)
                )
            return TestResult(
                success=False,
                status_code=resp.status_code,
                response_time_ms=elapsed_ms,
                error=f"HTTP {resp.status_code}"
            )
        except requests.Timeout:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(False, 0, elapsed_ms, 0, "Timeout")
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return TestResult(False, 0, elapsed_ms, 0, str(e)[:100])

    def run_test(self, total: int, concurrency: int, path: str = "/") -> dict:
        """Run load test against a specific path"""
        print(f"Testing path: {path}")
        print(f"Starting: {total} requests, {concurrency} concurrent")
        print("-" * 50)

        results: List[TestResult] = []
        start_time = time.perf_counter()
        completed = 0

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(self.fetch_url, path) for _ in range(total)]

            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1

                if completed % 50 == 0 or completed == total:
                    success = sum(1 for r in results if r.success)
                    print(f"Progress: {completed}/{total} (Success: {success}, Failed: {completed - success})")

        total_time = time.perf_counter() - start_time
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        response_times = [r.response_time_ms for r in results]
        total_bytes = sum(r.bytes_received for r in results)

        metrics = {
            "path": path,
            "total": total,
            "concurrency": concurrency,
            "total_time_seconds": round(total_time, 2),
            "successful": len(successful),
            "failed": len(failed),
            "success_rate": round(len(successful) / total * 100, 2) if total > 0 else 0,
            "per_minute": round(len(successful) / total_time * 60, 2) if total_time > 0 else 0,
            "per_second": round(len(successful) / total_time, 2) if total_time > 0 else 0,
            "avg_response_ms": round(sum(response_times) / len(response_times), 2) if response_times else 0,
            "min_response_ms": round(min(response_times), 2) if response_times else 0,
            "max_response_ms": round(max(response_times), 2) if response_times else 0,
            "p50_ms": round(sorted(response_times)[len(response_times)//2], 2) if response_times else 0,
            "p95_ms": round(sorted(response_times)[int(len(response_times)*0.95)], 2) if response_times else 0,
            "total_bytes": total_bytes,
            "mb_per_second": round((total_bytes / 1024 / 1024) / total_time, 2) if total_time > 0 else 0,
        }

        if failed:
            error_counts = {}
            for r in failed:
                key = (r.error or "Unknown")[:50]
                error_counts[key] = error_counts.get(key, 0) + 1
            metrics["errors"] = error_counts

        return metrics


def print_results(m: dict, title: str):
    if "error" in m and not isinstance(m.get("error"), dict):
        print(f"\nERROR: {m['error']}")
        return

    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)
    print(f"\n  Path Tested:               {m['path']}")
    print(f"\n  REQUESTS PER MINUTE:       {m['per_minute']:>10.1f}")
    print(f"  REQUESTS PER SECOND:       {m['per_second']:>10.2f}")
    print(f"  TRANSFER RATE:             {m['mb_per_second']:>9.2f} MB/s")
    print("-" * 60)
    print(f"  Total Attempted:           {m['total']:>10}")
    print(f"  Successful:                {m['successful']:>10}")
    print(f"  Failed:                    {m['failed']:>10}")
    print(f"  Success Rate:              {m['success_rate']:>9.1f}%")
    print(f"  Total Time:                {m['total_time_seconds']:>9.1f}s")
    print(f"  Concurrency:               {m['concurrency']:>10}")
    print(f"  Total Transferred:         {m['total_bytes']/1024:>9.1f} KB")
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


def print_comparison(results: List[dict]):
    """Print comparison of multiple test results"""
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    print(f"{'Path':<30} {'Req/s':>10} {'Avg(ms)':>10} {'P95(ms)':>10} {'MB/s':>10}")
    print("-" * 70)
    for m in results:
        path = m['path'][:28] if len(m['path']) > 28 else m['path']
        print(f"{path:<30} {m['per_second']:>10.1f} {m['avg_response_ms']:>10.0f} {m['p95_ms']:>10.0f} {m['mb_per_second']:>10.2f}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Frontend service capacity test")
    parser.add_argument("--host", default="http://app.109.199.108.243.nip.io")
    parser.add_argument("--count", type=int, default=100, help="Number of requests")
    parser.add_argument("--concurrent", type=int, default=10, help="Concurrent connections")
    parser.add_argument("--path", default="/", help="Path to test (default: /)")
    parser.add_argument("--full", action="store_true", help="Run full test including JS/CSS assets")
    parser.add_argument("-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    print(f"""
╔════════════════════════════════════════════════════════════╗
║         Frontend Service Capacity Test                     ║
╠════════════════════════════════════════════════════════════╣
║  Host:       {args.host:<44} ║
║  Requests:   {args.count:<44} ║
║  Concurrent: {args.concurrent:<44} ║
║  Path:       {args.path:<44} ║
╚════════════════════════════════════════════════════════════╝
""")

    tester = FrontendServiceTester(args.host)

    # Check health and discover assets
    print("Checking frontend service...")
    info = tester.check_health()

    if not info["healthy"]:
        print(f"\nERROR: Frontend service health check failed")
        if "error" in info:
            print(f"  {info['error']}")
        sys.exit(1)

    print(f"  Index page size: {info['index_size']/1024:.1f} KB")
    if info["assets"]:
        print(f"  Found {len(info['assets'])} static assets")
        for asset in info["assets"]:
            print(f"    - {asset['path']} ({asset['type']})")

    if not args.y:
        confirm = input("\nContinue? (y/N): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(0)

    all_results = []

    # Test main path
    metrics = tester.run_test(args.count, args.concurrent, args.path)
    print_results(metrics, "FRONTEND SERVICE TEST RESULTS")
    all_results.append(metrics)

    # If full test, also test discovered assets
    if args.full and info["assets"]:
        print("\n" + "=" * 60)
        print("Testing static assets...")
        print("=" * 60)

        for asset in info["assets"]:
            metrics = tester.run_test(args.count // 2, args.concurrent, asset["path"])
            print_results(metrics, f"ASSET TEST: {asset['type'].upper()}")
            all_results.append(metrics)

    # Print comparison if multiple tests
    if len(all_results) > 1:
        print_comparison(all_results)
