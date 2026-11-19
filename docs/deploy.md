# Deployment and operations

## Zero-cost demonstration

Run Docker Compose on the development machine or an existing Linux host. The app, database, and reference carrier publish loopback ports by default. An interviewer can review the local screen via screen sharing, or an authorized user with access to an existing Linux host can use an SSH tunnel to the host’s loopback port.

```sh
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T api python -m desk.seed
curl -fsS http://127.0.0.1:8765/api/health/ready
```

The seed imports only synthetic data. When using the sample environment, the order and carrier state advances on the fixed demo date. Remove `DESK_AS_OF_DATE` for a current UTC business date. For deployment on an existing private host, use a unique database password and choose how the host provisions users before exposing access. The Compose database DSN assumes URL-safe credentials. For browser access over HTTPS set `DESK_COOKIE_SECURE=true` and terminate TLS at a trusted proxy that preserves the request host. Configure site access and login throttling before exposing the app beyond a private demo. The default design assumes one team and offers no self-service account enrollment.

A container restart preserves data in the named database volume. `docker compose down` stops the stack while retaining the database volume. The verification script uses a dedicated Compose project and clears its temporary volumes when it exits.

## Backup and restore

From the repository root, make a PostgreSQL archive and restore it to a separate empty database to check recoverability. Protect the archive because it contains user records and session digests. When restoring production data to another environment, drop or revoke existing sessions there and validate user provisioning and retention requirements first.

```sh
docker compose exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > desk.backup
docker compose exec -T db sh -c 'createdb -U "$POSTGRES_USER" exception_desk_restore'
docker compose exec -T db sh -c 'pg_restore --exit-on-error -U "$POSTGRES_USER" -d exception_desk_restore' < desk.backup
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d exception_desk_restore -c "SELECT count(*) FROM order_lines"'
```

## Triage

| What you see | What to check |
| --- | --- |
| Readiness returns 503 | Run `docker compose ps` and check the database health and migration logs with `docker compose logs db api`. The API can be alive while PostgreSQL is unavailable. |
| Carrier sync returns 502 | Open the corresponding run in Data intake. Check the carrier service status and `docker compose logs carrier`. Restore service and retry. The last usable sync time stays visible during the outage. |
| CSV run is partial | Open the recorded validation details. Correct invalid rows in the source export and resubmit. Unchanged rows are idempotent. |
| Case change returns 409 | Refresh the case version and reapply the action after inspecting the updated evidence and activity. |
| A request returns HTTP 500 | Find the `X-Request-ID` in the response and search `docker compose logs api` for the same ID. Correlate the request with the failure or intake event before retrying. |

A GitHub Actions definition runs the same verification script on a hosted Linux runner once the repository is connected to GitHub. Local checks use an isolated stack and require only the project dependencies, Docker Compose, and Chromium.
