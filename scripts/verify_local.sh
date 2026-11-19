#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# This project is unique to this run. Cleanup never targets the default demo stack.
verify_project="supplier-desk-verify-$$"
export DESK_APP_PORT="${DESK_VERIFY_APP_PORT:-18765}"
export DESK_DB_PORT="${DESK_VERIFY_DB_PORT:-15432}"
export DESK_CARRIER_PORT="${DESK_VERIFY_CARRIER_PORT:-18766}"
export DESK_TEST_APP_URL="http://127.0.0.1:$DESK_APP_PORT"
export DESK_TEST_DEMO_PASSWORD="local-demo-only"
export DESK_TEST_DATABASE_URL="postgresql+psycopg://exception_desk:local-demo-db@127.0.0.1:$DESK_DB_PORT/exception_desk_test"

compose() {
  docker compose --env-file .env.example -p "$verify_project" "$@"
}

cleanup() {
  result=$?
  if [[ $result -ne 0 ]]; then
    compose logs --tail=18 || true
  fi
  compose down --volumes >/dev/null || true
  return "$result"
}
trap cleanup EXIT

.venv/bin/ruff check desk migrations tests scripts
.venv/bin/ruff format --check desk migrations tests scripts
npm --prefix frontend run build

compose --progress quiet up -d --build --wait --wait-timeout 90
compose exec -T db createdb -U exception_desk exception_desk_test
compose exec -T api python -m desk.seed
compose exec -T api python -m desk.seed
compose exec -T db createdb -U exception_desk exception_desk_restore
compose exec -T db pg_dump -Fc -U exception_desk exception_desk \
  | compose exec -T db pg_restore --exit-on-error -U exception_desk -d exception_desk_restore
restored_count="$(compose exec -T db psql -U exception_desk -d exception_desk_restore -tAc 'SELECT count(*) FROM order_lines')"
[[ "$restored_count" == 12 ]]
echo "PostgreSQL backup and restore check passed."
.venv/bin/pytest --cov=desk --cov-report=term-missing -q

.venv/bin/python -m scripts.check_live baseline --url "$DESK_TEST_APP_URL"
compose stop carrier
.venv/bin/python -m scripts.check_live outage --url "$DESK_TEST_APP_URL"
compose up -d --wait --wait-timeout 45 carrier
.venv/bin/python -m scripts.check_live recovered --url "$DESK_TEST_APP_URL"
if [[ "${DESK_RUN_BENCHMARK:-}" == 1 ]]; then
  .venv/bin/python -m scripts.benchmark --url "$DESK_TEST_APP_URL"
fi
npm --prefix frontend run test:e2e
