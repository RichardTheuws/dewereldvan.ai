#!/usr/bin/env bash
# Postgres-pariteit lokaal — spint een wegwerp-Postgres in Docker en draait de
# pariteit-test (alembic upgrade head + smoke-CRUD tegen ECHTE Postgres).
#
# Waarom: de gewone `pytest` draait op SQLite (snel, default). Dialect-bugs
# (varchar-lengte, boolean-default, type-mismatch) zijn daar onzichtbaar — ze
# faalden tot nu toe pas in productie. Dit script vangt die klasse vóór deploy.
#
# Gebruik:  ./scripts/test-postgres.sh            (alle pariteit-tests)
#           ./scripts/test-postgres.sh -k upgrade (specifieke test)
set -euo pipefail

NAME="dwv-pgtest"
PORT="${PG_TEST_PORT:-5544}"
IMAGE="postgres:16"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "→ wegwerp-Postgres starten ($IMAGE op poort $PORT)…"
docker run -d --name "$NAME" \
  -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=dewereldvan_test \
  -p "${PORT}:5432" "$IMAGE" >/dev/null

echo -n "→ wachten tot Postgres healthy is"
for _ in $(seq 1 30); do
  if docker exec "$NAME" pg_isready -U app -d dewereldvan_test >/dev/null 2>&1; then
    echo " ✓"; break
  fi
  echo -n "."; sleep 1
done

export TEST_DATABASE_URL="postgresql+psycopg://app:app@localhost:${PORT}/dewereldvan_test"
echo "→ pytest tests/test_postgres_parity.py"
python -m pytest tests/test_postgres_parity.py "$@"
