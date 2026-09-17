from __future__ import annotations

import os

import asyncpg
import pytest


def required_url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for PostgreSQL integration tests")
    return value


@pytest.mark.anyio
async def test_database_roles_have_least_privilege() -> None:
    admin = await asyncpg.connect(required_url("TEST_ADMIN_DATABASE_URL"))
    try:
        roles = {
            record["rolname"]: record
            for record in await admin.fetch(
                """
                SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolinherit, rolbypassrls
                FROM pg_roles
                WHERE rolname IN ('easydentist_app', 'easydentist_migrator')
                """
            )
        }
        schema_owner = await admin.fetchval(
            """
            SELECT owner.rolname
            FROM pg_namespace namespace
            JOIN pg_roles owner ON owner.oid = namespace.nspowner
            WHERE namespace.nspname = 'app'
            """
        )
        public_can_connect = await admin.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_database database,
                     aclexplode(COALESCE(database.datacl, acldefault('d', database.datdba))) acl
                WHERE database.datname = current_database()
                  AND acl.grantee = 0
                  AND acl.privilege_type = 'CONNECT'
            )
            """
        )
        public_can_create_temporary = await admin.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_database database,
                     aclexplode(COALESCE(database.datacl, acldefault('d', database.datdba))) acl
                WHERE database.datname = current_database()
                  AND acl.grantee = 0
                  AND acl.privilege_type = 'TEMPORARY'
            )
            """
        )
    finally:
        await admin.close()

    assert set(roles) == {"easydentist_app", "easydentist_migrator"}
    for role in roles.values():
        assert role["rolsuper"] is False
        assert role["rolcreatedb"] is False
        assert role["rolcreaterole"] is False
        assert role["rolinherit"] is False
        assert role["rolbypassrls"] is False
    assert schema_owner == "easydentist_migrator"
    assert public_can_connect is False
    assert public_can_create_temporary is False


@pytest.mark.anyio
async def test_runtime_cannot_create_objects_in_app_schema() -> None:
    runtime = await asyncpg.connect(required_url("TEST_APP_DATABASE_URL"))
    try:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await runtime.execute("CREATE TABLE app.runtime_must_not_create (id integer)")
    finally:
        await runtime.close()


@pytest.mark.anyio
async def test_migrator_can_create_objects_in_app_schema() -> None:
    migrator = await asyncpg.connect(required_url("TEST_MIGRATION_DATABASE_URL"))
    transaction = migrator.transaction()
    await transaction.start()
    try:
        await migrator.execute("CREATE TABLE app.migrator_can_create (id integer)")
    finally:
        await transaction.rollback()
        await migrator.close()


@pytest.mark.anyio
async def test_foundation_contains_alembic_control_table() -> None:
    admin = await asyncpg.connect(required_url("TEST_ADMIN_DATABASE_URL"))
    try:
        tables = await admin.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'app' ORDER BY tablename"
        )
    finally:
        await admin.close()

    assert "alembic_version" in {record["tablename"] for record in tables}
