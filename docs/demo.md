# Five-minute interview demo

Start with a freshly seeded local stack. Use the buyer account from the [README](../README.md). The fixture is dated November 19, 2026 so every run starts with the same business-day exceptions. The seed has 12 order lines, eight shipment snapshots, and seven active exceptions. For a disposable full replay, use the fresh-stack verification command in the README.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:45 | Open the queue and point to the critical cases. Filter for `PO-48109`. | The distributor has an order export and separate carrier updates. A buyer needs to know which line is late and what to do about it. |
| 0:45–1:40 | Open `PO-48109` line 1. Show 60 of 120 delivered and the second shipment in transit. Assign Jordan Avery and acknowledge the case. | Delivered quantity is computed from delivered snapshots. The database stores purchase order lines and carrier shipments under separate source keys. |
| 1:40–2:30 | Choose Resolve and enter a reason. Close the drawer and switch the Status filter to Resolved. Show the activity trail. | The mutation checks the submitted version and stores the audit event in the same transaction. Two tabs using the same version cannot silently overwrite each other. |
| 2:30–3:20 | Open Data intake and upload `fixtures/orders-mixed.csv`. Review the line-level issues and upload the same file again. | First upload adds one line and reports three bad rows. The replay adds zero lines. Conflicting data requires a usable source revision to overwrite safely. |
| 3:20–4:20 | Run `docker compose stop carrier`. Press Sync carrier and show the failed run, previous usable sync timestamp, and preserved shipment evidence. Run `docker compose up -d --wait carrier`, then sync again. | An unavailable dependency records a failed attempt. It leaves the latest accepted evidence in place. Recovery matches the eight existing shipments. |
| 4:20–5:00 | Sign in as the viewer or highlight the test output and show the [architecture diagram](architecture.md). | The viewer can read the evidence. The write endpoints enforce the role and CSRF checks, even outside the browser UI. |

For the rollback example, cite the test that injects a failure after inserts are flushed and verifies that both the order rows and the run record disappear. For the concurrency example, cite the test that imports the same file from two sessions and observes one set of inserts.

The Compose demo uses synthetic fixtures. Report performance results with their seed size and local hardware. Use the actual production readiness requirements of a future customer to decide what must change before real deployment.
