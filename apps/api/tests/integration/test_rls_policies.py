from __future__ import annotations

import asyncpg
import pytest
from conftest import SeededTenants

POLICY_MATRIX = {
    "clinics": [
        ("clinics_user_select", "SELECT", "easydentist_app"),
        ("clinics_tenant_update", "UPDATE", "easydentist_app"),
        ("clinics_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "memberships": [
        ("memberships_user_select", "SELECT", "easydentist_app"),
        ("memberships_tenant_select", "SELECT", "easydentist_app"),
        ("memberships_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "clinic_settings": [
        ("clinic_settings_tenant_select", "SELECT", "easydentist_app"),
        ("clinic_settings_tenant_update", "UPDATE", "easydentist_app"),
        ("clinic_settings_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "clinic_feature_flags": [
        ("clinic_feature_flags_tenant_select", "SELECT", "easydentist_app"),
        ("clinic_feature_flags_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "membership_invitations": [
        ("membership_invitations_tenant_select", "SELECT", "easydentist_app"),
        ("membership_invitations_tenant_insert", "INSERT", "easydentist_app"),
        ("membership_invitations_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "clinic_audit_events": [
        ("clinic_audit_events_tenant_select", "SELECT", "easydentist_app"),
        ("clinic_audit_events_tenant_insert", "INSERT", "easydentist_app"),
        ("clinic_audit_events_migrator_all", "ALL", "easydentist_migrator"),
    ],
}


async def _set_context(
    connection: asyncpg.Connection, *, user_id: object, clinic_id: object | None = None
) -> None:
    if clinic_id is None:
        await connection.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
    else:
        await connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(user_id),
            str(clinic_id),
        )


@pytest.mark.anyio
async def test_policies_catalog_matches_the_matrix(admin_connection: asyncpg.Connection) -> None:
    records = await admin_connection.fetch(
        "SELECT tablename, policyname, cmd, roles FROM pg_policies WHERE schemaname = 'app'"
    )
    actual = {
        (record["tablename"], record["policyname"], record["cmd"], tuple(record["roles"]))
        for record in records
    }
    expected = {
        (table, policy, command, (role,))
        for table, policies in POLICY_MATRIX.items()
        for policy, command, role in policies
    }

    assert actual == expected


@pytest.mark.anyio
async def test_user_scope_lists_own_memberships_and_clinics(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(app_connection, user_id=seeded_tenants.user_a)

        memberships = await app_connection.fetch("SELECT id FROM app.memberships")
        clinics = await app_connection.fetch("SELECT id FROM app.clinics")

        assert [record["id"] for record in memberships] == [seeded_tenants.membership_a]
        assert [record["id"] for record in clinics] == [seeded_tenants.clinic_a]
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_tenant_scope_with_active_membership_sees_tenant_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a
        )

        for table in (
            "clinic_settings",
            "clinic_feature_flags",
            "membership_invitations",
            "clinic_audit_events",
        ):
            count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

            assert count == 1, table
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_tenant_scope_without_membership_hides_tenant_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b
        )

        for table in (
            "clinic_settings",
            "clinic_feature_flags",
            "membership_invitations",
            "clinic_audit_events",
        ):
            count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

            assert count == 0, table
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_settings_update_is_tenant_scoped(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a
        )

        own_update = await app_connection.execute(
            "UPDATE app.clinic_settings SET display_name = 'Updated A' WHERE clinic_id = $1",
            seeded_tenants.clinic_a,
        )
        cross_update = await app_connection.execute(
            "UPDATE app.clinic_settings SET display_name = 'Intruder' WHERE clinic_id = $1",
            seeded_tenants.clinic_b,
        )

        assert own_update == "UPDATE 1"
        assert cross_update == "UPDATE 0"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_mutations_outside_policies_are_denied(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute(
            "UPDATE app.clinic_audit_events SET event_type = 'tampered' WHERE clinic_id = $1",
            seeded_tenants.clinic_a,
        )

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute(
            "INSERT INTO app.clinic_feature_flags (clinic_id, key) VALUES ($1, 'intruder')",
            seeded_tenants.clinic_a,
        )

    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.execute(
            "DELETE FROM app.clinic_audit_events WHERE clinic_id = $1",
            seeded_tenants.clinic_a,
        )


async def _attempt_denied_in_tenant(
    connection: asyncpg.Connection,
    user_id: object,
    clinic_id: object,
    statement: str,
    *args: object,
) -> None:
    transaction = connection.transaction()
    await transaction.start()
    try:
        await _set_context(connection, user_id=user_id, clinic_id=clinic_id)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(statement, *args)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_membership_writes_are_denied_for_active_members(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    await _attempt_denied_in_tenant(
        app_connection,
        seeded_tenants.user_a,
        seeded_tenants.clinic_a,
        "UPDATE app.memberships SET role = 'RECEPTIONIST' WHERE id = $1",
        seeded_tenants.membership_a,
    )
    await _attempt_denied_in_tenant(
        app_connection,
        seeded_tenants.user_a,
        seeded_tenants.clinic_a,
        "INSERT INTO app.memberships (clinic_id, user_id, role, status) "
        "VALUES ($1, $2, 'OWNER', 'ACTIVE')",
        seeded_tenants.clinic_a,
        seeded_tenants.user_a,
    )
    await _attempt_denied_in_tenant(
        app_connection,
        seeded_tenants.user_a,
        seeded_tenants.clinic_a,
        "DELETE FROM app.memberships WHERE id = $1",
        seeded_tenants.membership_a,
    )

    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(app_connection, user_id=seeded_tenants.user_a)
        role = await app_connection.fetchval(
            "SELECT role FROM app.memberships WHERE id = $1", seeded_tenants.membership_a
        )
    finally:
        await transaction.rollback()

    assert role == "OWNER"
