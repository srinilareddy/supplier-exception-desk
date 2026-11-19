import json
import os
import threading
from dataclasses import dataclass
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from desk.config import Settings
from desk.main import create_app
from desk.seed import seed_accounts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "fixtures"
TEST_PASSWORD = "test-fixture-password"


@dataclass
class Carrier:
    url: str = ""
    status: int = 200
    body: bytes = b""


@pytest.fixture
def carrier():
    state = Carrier(body=(FIXTURES / "carrier_shipments.json").read_bytes())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/v1/shipments"
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(state.body)

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        state.url = f"http://127.0.0.1:{server.server_port}"
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}
        )
        thread.start()
        try:
            yield state
        finally:
            server.shutdown()
            thread.join()


@pytest.fixture(scope="session")
def test_database():
    url = os.environ.get("DESK_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set DESK_TEST_DATABASE_URL to run PostgreSQL integration tests.")
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail("The integration database name must end in _test.")
    config = Config(PROJECT_ROOT / "alembic.ini")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DESK_DATABASE_URL", url)
        command.upgrade(config, "head")
        command.check(config)
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


@pytest.fixture
def app(test_database, carrier, tmp_path):
    url, engine = test_database
    with engine.begin() as connection:
        connection.execute(
            text("TRUNCATE users, order_lines, ingestion_runs RESTART IDENTITY CASCADE")
        )
    settings = Settings(
        database_url=url,
        cookie_secure=False,
        as_of_date=date(2026, 11, 19),
        carrier_url=carrier.url,
        web_dist=tmp_path,
    )
    api = create_app(settings)
    with api.state.sessions.begin() as db:
        seed_accounts(db, TEST_PASSWORD)
    return api


@pytest.fixture
def client(app):
    with TestClient(app) as browser:
        yield browser


def login(client: TestClient, name: str = "buyer") -> dict[str, str]:
    response = client.post(
        "/api/session",
        json={"email": f"{name}@example.test", "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def signed_in(client):
    return client, login(client)


def upload(client: TestClient, headers: dict[str, str], filename: str = "orders.csv"):
    return client.post(
        "/api/imports/orders",
        headers=headers | {"Content-Type": "text/csv"},
        content=(FIXTURES / filename).read_bytes(),
    )


@pytest.fixture
def imported(signed_in):
    client, headers = signed_in
    assert upload(client, headers).status_code == 200
    response = client.post("/api/sync/carrier", headers=headers)
    assert response.status_code == 200, response.text
    return client, headers


def set_carrier_entries(carrier: Carrier, entries: list[dict]) -> None:
    carrier.body = json.dumps({"schema_version": 1, "shipments": entries}).encode()
