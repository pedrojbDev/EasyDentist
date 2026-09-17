from __future__ import annotations

from uuid import uuid4

import asyncpg
import pytest
from conftest import SeededTenants

TENANT_TABLES = (
    "clinics",
    "memberships",
    "clinic_settings",
    "clinic_feature_flags",
    "membership_invitations",
    "clinic_audit_events",
)


@pytest.mark.anyio
async def test_every_tenant_table_returns_no_rows_without_context(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    for table in TENANT_TABLES:
        count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

        assert count == 0, table


@pytest.mark.anyio
async def test_context_of_unknown_tenant_returns_no_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(uuid4()),
            str(uuid4()),
        )

        for table in TENANT_TABLES:
            count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

            assert count == 0, table
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_insert_without_context_is_rejected(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute(
            "INSERT INTO app.clinic_audit_events (clinic_id, event_type) VALUES ($1, 'intruder')",
            seeded_tenants.clinic_a,
        )


@pytest.mark.anyio
async def test_insert_for_another_tenant_is_rejected(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(seeded_tenants.user_a),
            str(seeded_tenants.clinic_a),
        )

        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app_connection.execute(
                "INSERT INTO app.clinic_audit_events (clinic_id, event_type) "
                "VALUES ($1, 'intruder')",
                seeded_tenants.clinic_b,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_membership_function_catalog_hardening(
    admin_connection: asyncpg.Connection,
) -> None:
    record = await admin_connection.fetchrow(
        """
        SELECT p.prosecdef, p.proconfig, p.proacl, r.rolname AS owner, r.rolsuper
        FROM pg_proc p
        JOIN pg_roles r ON r.oid = p.proowner
        WHERE p.proname = 'is_active_member'
          AND p.pronamespace = 'app'::regnamespace
        """
    )

    assert record is not None
    assert record["prosecdef"] is True
    assert record["proconfig"] == ["search_path=app, pg_temp"]
    assert record["owner"] == "easydentist_migrator"
    assert record["rolsuper"] is False
    assert "easydentist_app=X/easydentist_migrator" in record["proacl"]
    assert not any(entry.startswith("=") for entry in record["proacl"])
