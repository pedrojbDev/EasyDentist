from __future__ import annotations

import asyncpg
import pytest
from helpers import insert_user

GLOBAL_TABLES = [
    "auth_action_tokens",
    "auth_audit_events",
    "auth_rate_limit_buckets",
    "auth_sessions",
    "email_outbox",
    "external_identities",
    "password_credentials",
    "users",
]

APP_PRIVILEGES = {
    "users": {"SELECT", "INSERT", "UPDATE"},
    "password_credentials": {"SELECT", "INSERT", "UPDATE"},
    "external_identities": {"SELECT", "INSERT", "UPDATE"},
    "auth_sessions": {"SELECT", "INSERT", "UPDATE"},
    "auth_action_tokens": {"SELECT", "INSERT", "UPDATE"},
    "auth_rate_limit_buckets": {"SELECT", "INSERT", "UPDATE", "DELETE"},
    "auth_audit_events": {"SELECT", "INSERT"},
    "email_outbox": {"SELECT", "INSERT", "UPDATE"},
}


@pytest.mark.anyio
async def test_global_identity_tables_exist(admin_connection: asyncpg.Connection) -> None:
    records = await admin_connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'app'"
    )

    assert {record["tablename"] for record in records} >= set(GLOBAL_TABLES)


@pytest.mark.anyio
async def test_app_role_privileges_are_exact(admin_connection: asyncpg.Connection) -> None:
    records = await admin_connection.fetch(
        """
        SELECT table_name, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = 'app' AND grantee = 'easydentist_app'
        """
    )
    granted: dict[str, set[str]] = {}
    for record in records:
        granted.setdefault(record["table_name"], set()).add(record["privilege_type"])

    for table, privileges in APP_PRIVILEGES.items():
        assert granted.get(table, set()) == privileges, table


@pytest.mark.anyio
async def test_app_role_can_write_and_read_users(app_connection: asyncpg.Connection) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        user_id = await insert_user(app_connection, "owner@example.com")
        email = await app_connection.fetchval("SELECT email FROM app.users WHERE id = $1", user_id)

        assert email == "owner@example.com"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_app_role_cannot_delete_auth_audit_events(app_connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute("DELETE FROM app.auth_audit_events")


@pytest.mark.anyio
async def test_app_role_cannot_delete_users(app_connection: asyncpg.Connection) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute("DELETE FROM app.users")
