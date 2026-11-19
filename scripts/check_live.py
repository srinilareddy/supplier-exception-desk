"""Check the seeded desk and an actual outage and recovery on the Compose network."""

import argparse
import os
from contextlib import contextmanager

import httpx


@contextmanager
def open_demo(base_url: str):
    with httpx.Client(base_url=base_url, timeout=10, trust_env=False) as client:
        login = client.post(
            "/api/session",
            json={
                "email": "buyer@example.test",
                "password": os.environ.get(
                    "DESK_TEST_DEMO_PASSWORD", "local-demo-only"
                ),
            },
        )
        login.raise_for_status()
        yield client, {"X-CSRF-Token": login.json()["csrf_token"]}


def run(state: str, base_url: str) -> None:
    with open_demo(base_url) as (client, headers):
        for endpoint in ("/api/health/live", "/api/health/ready"):
            client.get(endpoint).raise_for_status()
        initial = client.get("/api/overview").raise_for_status().json()
        assert (
            initial["order_lines"],
            initial["shipments"],
            initial["active_cases"],
        ) == (12, 8, 7)
        assert initial["critical_cases"] == 2
        if state != "baseline":
            sync = client.post("/api/sync/carrier", headers=headers)
            overview = client.get("/api/overview").raise_for_status().json()
            assert overview["shipments"] == 8
            assert overview["carrier_last_available_at"]
            if state == "outage":
                assert sync.status_code == 502, sync.text
                assert overview["latest_carrier"]["status"] == "failed"
                assert (
                    overview["carrier_last_available_at"]
                    == initial["carrier_last_available_at"]
                )
            else:
                sync.raise_for_status()
                assert sync.json()["duplicates"] == 8 and sync.json()["added"] == 0
                assert overview["latest_carrier"]["status"] == "success"
    print(
        f"Compose {state} check passed. 12 order lines, 8 shipments, 7 active exceptions."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", choices=["baseline", "outage", "recovered"])
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    arguments = parser.parse_args()
    run(arguments.state, arguments.url)
