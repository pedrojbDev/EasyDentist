from __future__ import annotations

import asyncpg
import pytest
from conftest import SeededTenants


@pytest.mark.anyio
async def test_agenda_membership_lock_is_scoped_without_update_grants(
    app_connection: asyncpg.Connection,
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
) -> None:
    async with app_connection.transaction():
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(seeded_tenants.user_a),
            str(seeded_tenants.clinic_a),
        )
        assert not await app_connection.fetchval(
            "SELECT has_table_privilege(current_user, 'app.memberships', 'UPDATE')"
        )
        assert (
            await app_connection.fetchval(
                "SELECT app.lock_agenda_membership($1, $2)",
                seeded_tenants.clinic_a,
                seeded_tenants.membership_a,
            )
            == seeded_tenants.membership_a
        )
        assert (
            await app_connection.fetchval(
                "SELECT app.lock_agenda_membership($1, $2)",
                seeded_tenants.clinic_a,
                seeded_tenants.membership_b,
            )
            is None
        )
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with app_connection.transaction():
                await app_connection.fetchval(
                    "SELECT app.lock_agenda_membership($1, $2)",
                    seeded_tenants.clinic_b,
                    seeded_tenants.membership_b,
                )
        with pytest.raises(asyncpg.LockNotAvailableError):
            async with migrator_connection.transaction():
                await migrator_connection.execute("SET LOCAL lock_timeout = '100ms'")
                await migrator_connection.execute(
                    "UPDATE app.memberships SET status = status WHERE id = $1",
                    seeded_tenants.membership_a,
                )


@pytest.mark.anyio
async def test_agenda_membership_lock_rejects_missing_context(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await app_connection.fetchval(
            "SELECT app.lock_agenda_membership($1, $2)",
            seeded_tenants.clinic_a,
            seeded_tenants.membership_a,
        )
