import json
from concurrent.futures import ThreadPoolExecutor

from conftest import TEST_PASSWORD, login, set_carrier_entries, upload
from fastapi.testclient import TestClient

from desk import cases


def test_health_and_logged_out(client):
    assert client.get("/api/health/live").json() == {"status": "ok"}
    assert client.get("/api/health/ready").json() == {"status": "ready"}
    assert client.get("/api/exceptions").status_code == 401


def test_login_and_csrf(client):
    response = client.post(
        "/api/session", json={"email": "buyer@example.test", "password": "wrong"}
    )
    assert response.status_code == 401
    response = client.post(
        "/api/session",
        json={"email": "buyer@example.test", "password": TEST_PASSWORD},
        headers={"Origin": "https://other.example.test"},
    )
    assert response.status_code == 403
    headers = login(client)
    assert client.get("/api/session").json()["user"]["role"] == "operator"
    assert client.post("/api/sync/carrier").status_code == 403
    assert client.delete("/api/session", headers=headers).status_code == 204
    assert client.get("/api/session").status_code == 401


def test_mixed_import_replay_and_row_numbers(imported):
    client, headers = imported
    result = upload(client, headers, "orders-mixed.csv").json()
    assert result["status"] == "partial"
    assert (
        result["total"],
        result["added"],
        result["duplicates"],
        result["rejected"],
    ) == (5, 1, 1, 3)
    assert [issue["row"] for issue in result["issues"]] == [4, 5, 6]
    replay = upload(client, headers, "orders-mixed.csv").json()
    assert (replay["added"], replay["duplicates"], replay["rejected"]) == (0, 2, 3)
    assert client.get("/api/overview").json()["order_lines"] == 13


def test_carrier_outage_recovery_and_unknown_order(imported, carrier):
    client, headers = imported
    initial = client.get("/api/overview").json()
    count = initial["shipments"]
    carrier.status = 503
    response = client.post(
        "/api/sync/carrier", headers=headers | {"X-Request-ID": "carrier-demo"}
    )
    assert response.status_code == 502
    assert response.headers["x-request-id"] == "carrier-demo"
    assert response.json()["issues"][0]["reason"] == "Carrier returned HTTP 503."
    unavailable = client.get("/api/overview").json()
    assert unavailable["shipments"] == count
    assert unavailable["latest_carrier"]["status"] == "failed"
    carrier.status = 200
    replay = client.post("/api/sync/carrier", headers=headers).json()
    assert replay["status"] == "success"
    assert (replay["added"], replay["duplicates"]) == (0, count)
    shipments = json.loads(carrier.body)["shipments"]
    set_carrier_entries(
        carrier,
        [
            {
                **shipments[0],
                "shipment_id": "SH-UNKNOWN",
                "order_number": "PO-MISSING",
            }
        ],
    )
    rejected = client.post("/api/sync/carrier", headers=headers).json()
    assert rejected["rejected"] == 1
    assert "unknown" in rejected["issues"][0]["reason"].lower()


def test_newer_snapshot_updates_evidence_and_older_snapshot_is_rejected(
    imported, carrier
):
    client, headers = imported
    shipments = json.loads(carrier.body)["shipments"]
    pending = next(item for item in shipments if item["shipment_id"] == "SH-88711")
    newer = {**pending, "status": "delivered", "updated_at": "2026-11-19T12:00:00Z"}
    set_carrier_entries(carrier, [newer])
    assert client.post("/api/sync/carrier", headers=headers).json()["updated"] == 1
    before = client.get("/api/exceptions", params={"q": "PO-48109"}).json()["items"][0]
    assert before["delivered_quantity"] == 90
    set_carrier_entries(carrier, [pending])
    assert client.post("/api/sync/carrier", headers=headers).json()["rejected"] == 1
    after = client.get(f"/api/exceptions/{before['id']}").json()
    assert after["version"] == before["version"]
    assert after["shipments"][0]["status"] == "delivered"


def test_transaction_rollback_after_unexpected_failure(signed_in, monkeypatch):
    client, headers = signed_in

    def fail_after_write(*_args):
        raise RuntimeError("synthetic failure")

    with monkeypatch.context() as patch:
        patch.setattr(cases, "reconcile", fail_after_write)
        response = upload(client, headers)
    assert response.status_code == 500
    assert client.get("/api/overview").json()["order_lines"] == 0
    assert client.get("/api/runs").json() == []
    assert upload(client, headers).json()["added"] == 12


def test_concurrent_replays_are_serialized(app):
    def run_import():
        with TestClient(app) as browser:
            headers = login(browser)
            response = upload(browser, headers)
            assert response.status_code == 200, response.text
            return response.json()

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: run_import(), range(2)))
    assert sorted(row["added"] for row in results) == [0, 12]
    assert sorted(row["duplicates"] for row in results) == [0, 12]


def test_browser_workflow_contract_and_stale_version(imported):
    client, headers = imported
    page = client.get("/api/exceptions", params={"q": "PO-48109"}).json()
    item = page["items"][0]
    assert page["total"] == 1 and item["severity"] == "critical"
    assert item["delivered_quantity"] == 60
    endpoint = f"/api/exceptions/{item['id']}"
    operators = client.get("/api/operators").json()
    assigned = client.patch(
        endpoint,
        headers=headers,
        json={
            "action": "assign",
            "version": item["version"],
            "assigned_to_id": operators[0]["id"],
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["assigned_to_name"] == operators[0]["name"]
    stale = client.patch(
        endpoint,
        headers=headers,
        json={"action": "acknowledge", "version": item["version"]},
    )
    assert stale.status_code == 409
    ack = client.patch(
        endpoint,
        headers=headers,
        json={
            "action": "acknowledge",
            "version": assigned.json()["version"],
        },
    ).json()
    assert ack["status"] == "acknowledged"
    resolved = client.patch(
        endpoint,
        headers=headers,
        json={
            "action": "resolve",
            "version": ack["version"],
            "reason": "Replacement delivery confirmed.",
        },
    ).json()
    assert resolved["status"] == "resolved"
    assert resolved["events"][0]["actor_name"] == "Maya Chen"
    assert resolved["events"][0]["note"] == "Replacement delivery confirmed."
    assert client.get("/api/exceptions", params={"q": "PO-48109"}).json()["total"] == 0
    assert (
        client.get("/api/exceptions", params={"status": "resolved"}).json()["total"]
        == 1
    )


def test_viewer_can_read_but_cannot_write(imported):
    client, _ = imported
    viewer_headers = login(client, "viewer")
    items = client.get("/api/exceptions").json()["items"]
    item = items[0]
    assert client.get(f"/api/exceptions/{item['id']}").status_code == 200
    assert client.post("/api/sync/carrier", headers=viewer_headers).status_code == 403
    assert (
        client.patch(
            f"/api/exceptions/{item['id']}",
            headers=viewer_headers,
            json={
                "action": "acknowledge",
                "version": item["version"],
            },
        ).status_code
        == 403
    )
    assert upload(client, viewer_headers).status_code == 403


def test_invalid_headers_and_feed_contract_are_recorded(signed_in, carrier):
    client, headers = signed_in
    invalid = client.post(
        "/api/imports/orders",
        headers=headers | {"Content-Type": "text/csv"},
        content=b"other\n",
    )
    assert invalid.status_code == 422 and invalid.json()["status"] == "failed"
    carrier.body = b'{"schema_version": 2, "shipments": []}'
    invalid_feed = client.post("/api/sync/carrier", headers=headers)
    assert invalid_feed.status_code == 502
    assert invalid_feed.json()["status"] == "failed"
