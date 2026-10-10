"""Run a bounded concurrency smoke against the local readiness endpoint."""

from __future__ import annotations

import argparse
import ipaddress
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import httpx


def run(base_url: str, requests: int = 200, concurrency: int = 8):
    parsed = urlsplit(base_url)
    try:
        loopback = parsed.hostname.casefold() == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
    except (AttributeError, ValueError):
        loopback = False
    if parsed.scheme not in {"http", "https"} or not loopback or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("The smoke runner accepts only a local loopback base URL.")
    if not 1 <= requests <= 1000 or not 1 <= concurrency <= 32:
        raise ValueError("Use 1–1,000 requests and 1–32 concurrent workers.")
    url = base_url.rstrip("/") + "/api/v1/health"
    durations = []

    def request(client):
        started = time.perf_counter()
        response = client.get(url)
        elapsed = time.perf_counter() - started
        body = response.json()
        if response.status_code != 200 or body.get("status") != "ok" or body.get("database") != "ready":
            raise RuntimeError("Local readiness endpoint returned an unhealthy response.")
        return elapsed

    started = time.perf_counter()
    with httpx.Client(timeout=5, trust_env=False, limits=httpx.Limits(max_connections=concurrency)) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            durations = list(executor.map(lambda _: request(client), range(requests)))
    elapsed = time.perf_counter() - started
    ordered = sorted(durations)
    percentile = lambda value: round(ordered[max(0, math.ceil(value * len(ordered)) - 1)] * 1000, 2)
    return {"endpoint": url, "requests": len(durations), "concurrency": concurrency,
        "elapsed_seconds": round(elapsed, 3), "requests_per_second": round(len(durations) / elapsed, 2),
        "latency_ms": {"median": round(statistics.median(durations) * 1000, 2), "p95": percentile(.95), "max": round(ordered[-1] * 1000, 2)},
        "scope": "loopback readiness endpoint only; not a capacity or full-workflow load test"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(run(args.url, args.requests, args.concurrency), indent=2))


if __name__ == "__main__":
    main()
