#!/usr/bin/env sh
set -eu

# Validates the whole migration chain against a disposable Compose project.
# The regular development project and its volumes are never touched: the
# database is published on a separate host port and removed at the end.
compose_file=infra/docker-compose.yml
compose_project="easydentist-migrations-verify-$(date +%s)-$$"
export POSTGRES_HOST_PORT=${VERIFY_POSTGRES_HOST_PORT:-5434}

cleanup() {
  docker compose -p "$compose_project" -f "$compose_file" down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT HUP INT TERM

run_migrate() {
  docker compose -p "$compose_project" -f "$compose_file" --profile tools run --rm migrate "$@"
}

db_psql() {
  docker compose -p "$compose_project" -f "$compose_file" exec -T db \
    psql -U "${POSTGRES_USER:-easydentist}" -d "${POSTGRES_DB:-easydentist}" -v ON_ERROR_STOP=1 -tA "$@"
}

echo 'building the api image used by the migration task'
docker compose -p "$compose_project" -f "$compose_file" build api

echo 'starting the disposable database'
docker compose -p "$compose_project" -f "$compose_file" up -d --wait db

echo 'applying the existing M2 schema through revision 0013'
run_migrate alembic upgrade 0013_m2_anamnesis_base_integrity

suffix="$(date +%s)-$$"
m2_slug="m3-upgrade-${suffix}"
m2_email="m3-upgrade-${suffix}@example.invalid"
m2_patient="M2 patient preserved across M3 upgrade ${suffix}"
echo 'seeding a minimal M2 clinic and patient before upgrading'
db_psql <<SQL >/dev/null
INSERT INTO app.users (email, status, email_verified_at)
VALUES ('$m2_email', 'ACTIVE', now());
INSERT INTO app.clinics (slug, legal_name, status)
VALUES ('$m2_slug', '$m2_slug', 'ACTIVE');
INSERT INTO app.clinic_settings (clinic_id, display_name)
SELECT id, '$m2_slug' FROM app.clinics WHERE slug = '$m2_slug';
INSERT INTO app.memberships (clinic_id, user_id, role, status)
SELECT c.id, u.id, 'OWNER', 'ACTIVE'
FROM app.clinics c CROSS JOIN app.users u
WHERE c.slug = '$m2_slug' AND u.email = '$m2_email';
INSERT INTO app.patients (clinic_id, full_name, birth_date, phone)
SELECT id, '$m2_patient', CURRENT_DATE - 1, '+5571900000000'
FROM app.clinics WHERE slug = '$m2_slug';
SQL

echo 'upgrading the populated M2 database through M3'
run_migrate
preserved_patient_count="$(db_psql -c "SELECT count(*) FROM app.patients WHERE full_name = '$m2_patient'")"
if [ "$preserved_patient_count" != '1' ]; then
  echo 'M2 patient did not survive the upgrade to M3' >&2
  exit 1
fi

echo 'checking metadata against the database'
run_migrate alembic check

echo 'reverting the whole chain'
run_migrate alembic downgrade base

echo 'reapplying migrations from a clean database'
run_migrate alembic upgrade head

echo 'checking the final state'
run_migrate alembic check

echo 'migration chain: healthy'
