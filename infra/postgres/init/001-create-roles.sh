#!/usr/bin/env sh
set -eu

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${APP_DB_USER:?APP_DB_USER is required}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD is required}"
: "${MIGRATION_DB_USER:?MIGRATION_DB_USER is required}"
: "${MIGRATION_DB_PASSWORD:?MIGRATION_DB_PASSWORD is required}"

psql --set=ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_user="$APP_DB_USER" \
  --set=app_password="$APP_DB_PASSWORD" \
  --set=migration_user="$MIGRATION_DB_USER" \
  --set=migration_password="$MIGRATION_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I', :'migration_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'migration_user') \gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
  :'migration_user',
  :'migration_password'
) \gexec

SELECT format('CREATE ROLE %I', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format(
  'ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
  :'app_user',
  :'app_password'
) \gexec

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database()) \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'migration_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user') \gexec

SELECT format('CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION %I', :'migration_user') \gexec
SELECT format('ALTER SCHEMA app OWNER TO %I', :'migration_user') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA app FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA app TO %I', :'app_user') \gexec
SELECT format('REVOKE CREATE ON SCHEMA app FROM %I', :'app_user') \gexec

-- M1.2.2: case-insensitive identifiers (users.email, clinics.slug).
CREATE EXTENSION IF NOT EXISTS citext;
-- M3.1: GiST equality operators used by tenant/resource exclusion constraints.
-- This is administrative bootstrap DDL; the runtime and migration roles never
-- receive CREATE privileges for extensions.
CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL
