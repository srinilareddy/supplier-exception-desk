"""Measure sequential HTTP latency on a seeded local desk."""

import argparse
import json
import math
import platform
from statistics import median
from time import perf_counter

from scripts.check_live import open_demo


def measure(base_url: str, count: int) -> dict:
    with open_demo(base_url) as (client, _headers):
        overview = client.get("/api/overview").raise_for_status().json()
        rows = []
        for endpoint in ("/api/overview", "/api/exceptions?status=active&limit=20"):
            for _ in range(10):
                client.get(endpoint).raise_for_status()
            times = []
            for _ in range(count):
                start = perf_counter()
                client.get(endpoint).raise_for_status()
                times.append(1000 * (perf_counter() - start))
            rows.append(
                {
                    "endpoint": endpoint,
                    "requests": count,
                    "median_ms": round(median(times), 2),
                    "p95_ms": round(sorted(times)[math.ceil(len(times) * 0.95) - 1], 2),
                }
            )
    return {
        "client_platform": platform.platform(),
        "order_lines": overview["order_lines"],
        "shipments": overview["shipments"],
        "active_cases": overview["active_cases"],
        "warmups_per_endpoint": 10,
        "concurrency": 1,
        "results": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    parser.add_argument("--requests", default=120, type=int)
    arguments = parser.parse_args()
    if arguments.requests < 1:
        parser.error("--requests must be positive")
    print(json.dumps(measure(arguments.url, arguments.requests), indent=2))
