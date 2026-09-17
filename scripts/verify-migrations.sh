#!/usr/bin/env sh
set -eu

# Validates the whole migration chain against a disposable Compose project.
# The regular development project and its volumes are never touched: the
# database is published on a separate host port and removed at the end.
compose_file=infra/docker-compose.yml
compose_project=easydentist-migrations-verify
export POSTGRES_HOST_PORT=${VERIFY_POSTGRES_HOST_PORT:-5434}

cleanup() {
  docker compose -p "$compose_project" -f "$compose_file" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

run_migrate() {
  docker compose -p "$compose_project" -f "$compose_file" --profile tools run --rm migrate "$@"
}

echo 'building the api image used by the migration task'
docker compose -p "$compose_project" -f "$compose_file" build api

echo 'starting the disposable database'
docker compose -p "$compose_project" -f "$compose_file" up -d --wait db

echo 'applying migrations from scratch'
run_migrate

echo 'checking metadata against the database'
run_migrate alembic check

echo 'reverting the whole chain'
run_migrate alembic downgrade base

echo 'reapplying migrations'
run_migrate alembic upgrade head

echo 'checking the final state'
run_migrate alembic check

echo 'migration chain: healthy'
