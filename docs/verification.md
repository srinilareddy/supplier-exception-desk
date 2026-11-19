# Verification

Completed November 19, 2026 on macOS arm64 using Docker Desktop, PostgreSQL 17.12, CPython 3.13, Node 24, and headless Chrome through Playwright.

| Check | Result |
| --- | --- |
| Dependency and frontend build | Locked Python and npm dependencies installed. Ruff checks and the TypeScript/Vite production build passed. |
| Clean Compose startup | PostgreSQL, the API, and the reference carrier started healthy in an isolated Compose project. The migration applied and Alembic reported no schema drift. |
| Demo seed and replay | First seed added 12 order lines and eight shipments, yielding seven active exceptions. The second seed added zero order lines and zero shipments. |
| Python tests | 20 passed, with 91% statement coverage of the `desk` Python package. The tests covered row-level validation, concurrent replay, transaction rollback, session/role/CSRF checks, and stale case updates. |
| Browser tests | Three passed. They covered the buyer’s assignment and resolution flow, a mixed CSV upload and validation report, and the read-only workflow at a 390-pixel viewport. |
| Real carrier outage | Stopping the carrier made sync return 502. The eight shipment snapshots and previous usable sync time remained available. Restarting the carrier and retrying found eight unchanged records and inserted zero. |
| PostgreSQL backup and restore | Restored a custom-format dump into a separate empty database and checked the count of 12 order lines. |
| Running local demo | Confirmed the production UI root, authentication, health endpoints, and the expected seed counts at `http://127.0.0.1:8765`. |

The Python suite emitted a deprecation warning for Starlette’s test client using `httpx`. The Compose outage check and Playwright drive the application over real HTTP independently of that test client. The GitHub Actions definition delegates to the same verification script used locally.

## Read latency

The client ran through the loopback port to the Dockerized API and PostgreSQL with the fresh demo data. Each endpoint had ten warmups and 120 measured sequential requests over a reused HTTP connection. The workload included 12 order lines, eight shipment snapshots, and seven active cases.

| Endpoint | Median | p95 |
| --- | --- | --- |
| `GET /api/overview` | 3.43 ms | 5.38 ms |
| `GET /api/exceptions?status=active&limit=20` | 2.67 ms | 3.26 ms |

These measurements describe the seeded workload on this machine. Use the same [benchmark command](../scripts/benchmark.py) to rerun it with a documented dataset and environment.

```sh
DESK_RUN_BENCHMARK=1 bash scripts/verify_local.sh
```
