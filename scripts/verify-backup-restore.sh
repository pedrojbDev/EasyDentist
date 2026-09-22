#!/usr/bin/env sh
set -eu

# Proves that a custom-format backup restores into a clean PostgreSQL with
# schema, migrations, grants, policies, RLS and data intact. Two disposable
# Compose projects are used (source and target); the regular development
# project is never touched and its host port is never bound. No credential is
# printed: the client authenticates over the project network.

compose_file=infra/docker-compose.yml
dump_project=easydentist-backup-verify
restore_project=easydentist-restore-verify
dump_port=${BACKUP_VERIFY_POSTGRES_HOST_PORT:-5435}
restore_port=${RESTORE_VERIFY_POSTGRES_HOST_PORT:-5436}

db_user=${POSTGRES_USER:-easydentist}
db_name=${POSTGRES_DB:-easydentist}
app_user=${APP_DB_USER:-easydentist_app}
migration_user=${MIGRATION_DB_USER:-easydentist_migrator}

suffix="$(date +%s)-$$"
slug_a="restore-a-${suffix}"
slug_b="restore-b-${suffix}"
sentinel_a="SENTINELA-RESTORE-A-${suffix}"
sentinel_b="SENTINELA-RESTORE-B-${suffix}"
# Every table with FORCE ROW LEVEL SECURITY: the six tenant-aware M1 tables
# plus the four clinic-scoped M2 tables and the owner-scoped professional
# profile. A backup must restore all of them forced.
forced_rls_tables="clinics clinic_settings clinic_feature_flags memberships membership_invitations clinic_audit_events patients patient_alerts anamneses patient_documents professional_profiles"

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/easydentist-backup-verify.XXXXXX")
dump_file="$tmp_dir/easydentist.dump"

cleanup() {
  docker compose -p "$restore_project" -f "$compose_file" down --volumes --remove-orphans >/dev/null 2>&1 || true
  docker compose -p "$dump_project" -f "$compose_file" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT HUP INT TERM

dump_compose() {
  POSTGRES_HOST_PORT="$dump_port" docker compose -p "$dump_project" -f "$compose_file" "$@"
}

restore_compose() {
  POSTGRES_HOST_PORT="$restore_port" docker compose -p "$restore_project" -f "$compose_file" "$@"
}

dump_psql() {
  dump_compose exec -T db psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -tA "$@"
}

restore_psql() {
  restore_compose exec -T db psql -U "$db_user" -d "$db_name" -v ON_ERROR_STOP=1 -tA "$@"
}

app_psql() {
  restore_compose exec -T db psql -U "$app_user" -d "$db_name" -v ON_ERROR_STOP=1 -tA "$@"
}

fail() {
  echo "$1" >&2
  exit 1
}

expect_equal() {
  actual=$1
  expected=$2
  label=$3
  if [ "$actual" != "$expected" ]; then
    fail "$label: expected '$expected', found '$actual'"
  fi
}

# psql prints command tags (BEGIN/COMMIT) around the selects; keep the last
# pipe-separated numeric row produced inside the transaction.
counts_row() {
  grep -E '^[0-9]+(\|[0-9]+)+$' | tail -n 1
}

# Keeps the last plain numeric result, ignoring command tags and set_config UUIDs.
numeric_row() {
  grep -E '^[0-9]+$' | tail -n 1
}

echo 'building the api image used by migration tasks'
docker compose -p "$dump_project" -f "$compose_file" build api >/dev/null

echo 'starting the disposable source database'
dump_compose up -d --wait db

echo 'applying migrations to the source database'
dump_compose --profile tools run --rm migrate >/dev/null

echo 'inserting two clinics with sentinel data'
user_a_id=$(dump_psql -c 'SELECT gen_random_uuid()')
user_b_id=$(dump_psql -c 'SELECT gen_random_uuid()')
clinic_a_id=$(dump_psql -c 'SELECT gen_random_uuid()')
clinic_b_id=$(dump_psql -c 'SELECT gen_random_uuid()')
membership_a_id=$(dump_psql -c 'SELECT gen_random_uuid()')
membership_b_id=$(dump_psql -c 'SELECT gen_random_uuid()')

dump_psql <<SQL >/dev/null
INSERT INTO app.users (id, email, status, email_verified_at)
VALUES ('$user_a_id', 'restore-a-$suffix@example.com', 'ACTIVE', now()),
       ('$user_b_id', 'restore-b-$suffix@example.com', 'ACTIVE', now());
INSERT INTO app.clinics (id, slug, legal_name, status)
VALUES ('$clinic_a_id', '$slug_a', '$sentinel_a', 'ACTIVE'),
       ('$clinic_b_id', '$slug_b', '$sentinel_b', 'ACTIVE');
INSERT INTO app.clinic_settings (clinic_id, display_name)
VALUES ('$clinic_a_id', '$sentinel_a'), ('$clinic_b_id', '$sentinel_b');
INSERT INTO app.memberships (id, clinic_id, user_id, role, status)
VALUES ('$membership_a_id', '$clinic_a_id', '$user_a_id', 'OWNER', 'ACTIVE'),
       ('$membership_b_id', '$clinic_b_id', '$user_b_id', 'OWNER', 'ACTIVE');
SQL

echo 'generating a custom-format backup with pg_dump -Fc'
dump_compose --profile tools run --rm -T --entrypoint pg_dump pg-client \
  -h db -U "$db_user" -d "$db_name" -Fc >"$dump_file"
[ -s "$dump_file" ] || fail 'the backup file is empty'

echo 'starting the independent disposable restore database'
restore_compose up -d --wait db

echo 'recreating the target database while keeping the cluster roles'
restore_compose exec -T db psql -U "$db_user" -d postgres -v ON_ERROR_STOP=1 -q \
  -c "DROP DATABASE IF EXISTS $db_name" \
  -c "CREATE DATABASE $db_name OWNER $db_user"

echo 'restoring with pg_restore'
restore_compose --profile tools run --rm -T --entrypoint pg_restore pg-client \
  -h db -U "$db_user" -d "$db_name" --exit-on-error <"$dump_file" >/dev/null

echo 'checking schema, migrations and sentinel data'
expect_equal "$(restore_psql -c "SELECT legal_name FROM app.clinics WHERE slug = '$slug_a'")" "$sentinel_a" 'clinic A sentinel'
expect_equal "$(restore_psql -c "SELECT legal_name FROM app.clinics WHERE slug = '$slug_b'")" "$sentinel_b" 'clinic B sentinel'
expect_equal "$(restore_psql -c 'SELECT count(*) FROM app.memberships')" '2' 'memberships restored'
expect_equal "$(restore_psql -c 'SELECT count(*) FROM app.clinic_settings')" '2' 'clinic settings restored'
expect_equal "$(restore_psql -c 'SELECT version_num FROM app.alembic_version')" \
  "$(dump_psql -c 'SELECT version_num FROM app.alembic_version')" 'alembic revision'

echo 'checking grants, policies and role guarantees'
expect_equal "$(restore_psql -c "SELECT has_table_privilege('$app_user', 'app.memberships', 'SELECT')")" 't' 'runtime reads memberships'
expect_equal "$(restore_psql -c "SELECT has_table_privilege('$app_user', 'app.memberships', 'UPDATE')")" 'f' 'runtime cannot update memberships'
expect_equal "$(restore_psql -c "SELECT has_table_privilege('$app_user', 'app.users', 'DELETE')")" 'f' 'runtime cannot delete users'
expect_equal "$(restore_psql -c "SELECT has_table_privilege('$app_user', 'app.auth_audit_events', 'INSERT')")" 't' 'runtime appends audit'
expect_equal "$(restore_psql -c "SELECT has_table_privilege('$app_user', 'app.auth_audit_events', 'UPDATE')")" 'f' 'audit is append-only'
expect_equal "$(restore_psql -c 'SELECT count(*) FROM pg_policies WHERE schemaname = '\''app'\''')" \
  "$(dump_psql -c 'SELECT count(*) FROM pg_policies WHERE schemaname = '\''app'\''')" 'policy count'
expect_equal "$(restore_psql -c "
  SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'app' AND c.relkind = 'r' AND c.relforcerowsecurity")" \
  "$(printf '%s\n' $forced_rls_tables | wc -l | tr -d ' ')" 'forced RLS tables'
expect_equal "$(restore_psql -c "
  SELECT count(*) FROM pg_roles
  WHERE rolname IN ('$app_user', '$migration_user') AND rolbypassrls")" '0' 'roles without BYPASSRLS'

echo 'proving runtime role isolation with reused connections'
counts_a=$(app_psql <<SQL
BEGIN;
SELECT set_config('app.current_user_id', '$user_a_id', true);
SELECT set_config('app.current_clinic_id', '$clinic_a_id', true);
SELECT (SELECT count(*) FROM app.clinics) || '|' || (SELECT count(*) FROM app.memberships) || '|' || (SELECT count(*) FROM app.clinic_settings);
COMMIT;
SQL
)
expect_equal "$(printf '%s\n' "$counts_a" | counts_row)" '1|1|1' 'clinic A context sees only clinic A'
sentinel_b_from_a=$(app_psql <<SQL
BEGIN;
SELECT set_config('app.current_user_id', '$user_a_id', true);
SELECT set_config('app.current_clinic_id', '$clinic_a_id', true);
SELECT count(*) FROM app.clinic_settings WHERE display_name = '$sentinel_b';
COMMIT;
SQL
)
expect_equal "$(printf '%s\n' "$sentinel_b_from_a" | numeric_row)" '0' \
  'clinic A context cannot read clinic B settings'

counts_b=$(app_psql <<SQL
BEGIN;
SELECT set_config('app.current_user_id', '$user_b_id', true);
SELECT set_config('app.current_clinic_id', '$clinic_b_id', true);
SELECT (SELECT count(*) FROM app.clinics) || '|' || (SELECT count(*) FROM app.memberships) || '|' || (SELECT count(*) FROM app.clinic_settings);
COMMIT;
SQL
)
expect_equal "$(printf '%s\n' "$counts_b" | counts_row)" '1|1|1' 'clinic B context sees only clinic B'

mismatched=$(app_psql <<SQL
BEGIN;
SELECT set_config('app.current_user_id', '$user_a_id', true);
SELECT set_config('app.current_clinic_id', '$clinic_b_id', true);
SELECT (SELECT count(*) FROM app.clinics) || '|' || (SELECT count(*) FROM app.memberships) || '|' || (SELECT count(*) FROM app.clinic_settings);
SELECT count(*) FROM app.clinic_settings WHERE display_name = '$sentinel_b';
COMMIT;
SQL
)
expect_equal "$(printf '%s\n' "$mismatched" | counts_row)" '1|1|0' 'mismatched clinic cannot see tenant data'
expect_equal "$(printf '%s\n' "$mismatched" | numeric_row)" '0' 'mismatched clinic cannot see the other sentinel'

without_context=$(app_psql -c \
  "SELECT (SELECT count(*) FROM app.clinics) || '|' || (SELECT count(*) FROM app.memberships) || '|' || (SELECT count(*) FROM app.clinic_settings)")
expect_equal "$without_context" '0|0|0' 'missing context fails closed'

echo 'checking metadata against the restored database'
restore_compose --profile tools run --rm migrate alembic check >/dev/null

echo 'backup restore: healthy'
