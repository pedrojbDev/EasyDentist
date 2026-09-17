from __future__ import annotations

import asyncpg
import pytest
from conftest import SeededTenants

TENANT_SCOPED_TABLES = (
    "clinic_settings",
    "clinic_feature_flags",
    "membership_invitations",
    "clinic_audit_events",
)


@pytest.mark.anyio
async def test_explicit_context_of_another_tenant_returns_no_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(seeded_tenants.user_a),
            str(seeded_tenants.clinic_b),
        )

        for table in TENANT_SCOPED_TABLES:
            count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

            assert count == 0, table
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_updates_with_foreign_ids_affect_no_rows(
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

        settings_update = await app_connection.execute(
            "UPDATE app.clinic_settings SET display_name = 'breach' WHERE clinic_id = $1",
            seeded_tenants.clinic_b,
        )
        clinic_update = await app_connection.execute(
            "UPDATE app.clinics SET legal_name = 'breach' WHERE id = $1",
            seeded_tenants.clinic_b,
        )

        assert settings_update == "UPDATE 0"
        assert clinic_update == "UPDATE 0"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_select_without_where_only_returns_context_rows(
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

        settings_rows = await app_connection.fetch("SELECT clinic_id FROM app.clinic_settings")
        audit_rows = await app_connection.fetch("SELECT clinic_id FROM app.clinic_audit_events")
        membership_rows = await app_connection.fetch("SELECT clinic_id FROM app.memberships")

        assert [record["clinic_id"] for record in settings_rows] == [seeded_tenants.clinic_a]
        assert [record["clinic_id"] for record in audit_rows] == [seeded_tenants.clinic_a]
        assert [record["clinic_id"] for record in membership_rows] == [seeded_tenants.clinic_a]
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_cross_tenant_aggregates_count_only_context_rows(
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

        count = await app_connection.fetchval(
            "SELECT count(*) FROM app.clinic_settings WHERE clinic_id = ANY($1::uuid[])",
            [seeded_tenants.clinic_a, seeded_tenants.clinic_b],
        )

        assert count == 1
    finally:
        await transaction.rollback()
