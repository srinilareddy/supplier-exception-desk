# Requirements

The procurement team receives purchase order lines from an ERP export and shipment snapshots from a carrier. Buyers need to see late and short deliveries in one queue, verify the underlying evidence, and leave a record of how each exception was handled.

| ID | Requirement | Acceptance check |
| --- | --- | --- |
| F1 | Import order lines through a documented CSV contract. | A mixed file reports rejected rows with line numbers. Replaying the same file adds zero order lines. |
| F2 | Retrieve shipment snapshots through HTTP. | A carrier outage preserves the previous evidence and records the failed run. A subsequent retry succeeds. |
| F3 | Reconcile shipment evidence against due orders. | Past-due lines with no delivered quantity are overdue. Past-due lines with some delivered units are short. In-transit units do not count as delivered. |
| F4 | Assign, acknowledge, and resolve cases. | Each accepted action has an actor and audit entry. A stale version returns 409. Closing a case requires a reason. |
| F5 | Restrict access by role. | A viewer can read queue and source evidence and receives 403 when attempting a protected write. |
| F6 | Present an operable browser workflow. | A buyer can filter and prioritize the queue, inspect evidence, review source health and run an authorized intake. |
| N1 | Keep data consistent on retries and failures. | PostgreSQL uniqueness and a transaction protect ingestion. Integration tests intentionally fail a write before commit and check for rollback. |
| N2 | Require local secrets and expose operational diagnostics. | Password hashes and session token digests are stored in the database. Request logs carry correlation IDs. Readiness checks include the migrated database. |
| N3 | Make setup reproducible. | Start from a clean PostgreSQL database, migrate it, seed it, run automated checks, and follow the five-minute demo. Report the median and p95 API timings with environment and workload. |

The demonstration clock is configurable. The seed uses November 19, 2026. Without a configured value the server uses the current UTC date. The application operates on synthetic data for one procurement team. Order quantities are whole units and a supplier order number plus line number identifies a source row.
