from __future__ import annotations

import asyncpg
import pytest
from helpers import (
    insert_clinic,
    insert_clinic_settings,
    insert_invitation,
    insert_membership,
    insert_user,
)

TENANT_TABLES = [
    "clinic_audit_events",
    "clinic_feature_flags",
    "clinic_settings",
    "clinics",
    "membership_invitations",
    "memberships",
]


@pytest.mark.anyio
async def test_tenant_tables_exist(admin_connection: asyncpg.Connection) -> None:
    records = await admin_connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'app'"
    )

    assert {record["tablename"] for record in records} >= set(TENANT_TABLES)


@pytest.mark.anyio
async def test_composite_foreign_key_rejects_cross_tenant_invitation(
    migrator_connection: asyncpg.Connection,
) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        user_id = await insert_user(migrator_connection, "owner@example.com")
        clinic_a = await insert_clinic(migrator_connection, "clinic-a")
        clinic_b = await insert_clinic(migrator_connection, "clinic-b")
        membership_b = await insert_membership(
            migrator_connection, clinic_id=clinic_b, user_id=user_id
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_invitation(
                migrator_connection,
                clinic_id=clinic_a,
                membership_id=membership_b,
                email="invitee@example.com",
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_composite_foreign_key_accepts_same_tenant_invitation(
    migrator_connection: asyncpg.Connection,
) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        user_id = await insert_user(migrator_connection, "owner@example.com")
        clinic_id = await insert_clinic(migrator_connection, "clinic-a")
        membership_id = await insert_membership(
            migrator_connection, clinic_id=clinic_id, user_id=user_id
        )

        invitation_id = await insert_invitation(
            migrator_connection,
            clinic_id=clinic_id,
            membership_id=membership_id,
            email="invitee@example.com",
        )

        assert invitation_id is not None
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_membership_is_unique_per_user_and_clinic(
    migrator_connection: asyncpg.Connection,
) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        user_id = await insert_user(migrator_connection, "owner@example.com")
        clinic_id = await insert_clinic(migrator_connection, "clinic-a")
        await insert_membership(migrator_connection, clinic_id=clinic_id, user_id=user_id)

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_membership(migrator_connection, clinic_id=clinic_id, user_id=user_id)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_clinic_feature_flags_use_composite_primary_key(
    migrator_connection: asyncpg.Connection,
) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        clinic_id = await insert_clinic(migrator_connection, "clinic-a")
        await migrator_connection.execute(
            "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled) "
            "VALUES ($1, 'odontogram', true)",
            clinic_id,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await migrator_connection.execute(
                "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled) "
                "VALUES ($1, 'odontogram', false)",
                clinic_id,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_clinic_settings_are_one_per_clinic(migrator_connection: asyncpg.Connection) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        clinic_id = await insert_clinic(migrator_connection, "clinic-a")
        await insert_clinic_settings(migrator_connection, clinic_id)

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_clinic_settings(migrator_connection, clinic_id)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_clinic_settings_defaults(migrator_connection: asyncpg.Connection) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        clinic_id = await insert_clinic(migrator_connection, "clinic-a")
        await insert_clinic_settings(migrator_connection, clinic_id)

        settings = await migrator_connection.fetchrow(
            "SELECT timezone, locale, currency, preferences "
            "FROM app.clinic_settings WHERE clinic_id = $1",
            clinic_id,
        )

        assert settings["timezone"] == "America/Bahia"
        assert settings["locale"] == "pt-BR"
        assert settings["currency"] == "BRL"
        assert settings["preferences"] == "{}"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_clinic_slug_is_case_insensitive(migrator_connection: asyncpg.Connection) -> None:
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        await insert_clinic(migrator_connection, "Clinic-A")

        stored = await migrator_connection.fetchval(
            "SELECT slug FROM app.clinics WHERE slug = $1", "clinic-a"
        )
        assert stored == "Clinic-A"

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_clinic(migrator_connection, "CLINIC-a")
    finally:
        await transaction.rollback()
