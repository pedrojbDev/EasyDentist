from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_membership, insert_user

TARGET_ROLE = "ASSISTANT"


class GuardScenario:
    def __init__(self) -> None:
        self.clinic_id: uuid.UUID
        self.foreign_clinic_id: uuid.UUID
        self.owner_id: uuid.UUID
        self.attacker_id: uuid.UUID
        self.foreign_owner_id: uuid.UUID
        self.target_membership_id: uuid.UUID


@pytest.fixture
async def guard_scenario(
    migrator_connection: asyncpg.Connection,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[GuardScenario]:
    built = GuardScenario()
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"guard-{suffix}")
    built.foreign_clinic_id = await insert_clinic(migrator_connection, f"guard-foreign-{suffix}")
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    built.owner_id = await insert_user(migrator_connection, make_test_email("guard-owner"))
    built.attacker_id = await insert_user(migrator_connection, make_test_email("guard-attacker"))
    built.foreign_owner_id = await insert_user(
        migrator_connection, make_test_email("guard-foreign-owner")
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.clinic_id,
        user_id=built.owner_id,
        role="OWNER",
        status="ACTIVE",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.clinic_id,
        user_id=built.attacker_id,
        role="DENTIST",
        status="ACTIVE",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=built.foreign_owner_id,
        role="OWNER",
        status="ACTIVE",
    )
    target_id = await insert_user(migrator_connection, make_test_email("guard-target"))
    built.target_membership_id = await insert_membership(
        migrator_connection,
        clinic_id=built.clinic_id,
        user_id=target_id,
        role="DENTIST",
        status="ACTIVE",
    )
    yield built


async def set_context(
    connection: asyncpg.Connection, *, user_id: uuid.UUID, clinic_id: uuid.UUID
) -> None:
    await connection.execute(
        "SELECT set_config('app.current_user_id', $1, true), "
        "set_config('app.current_clinic_id', $2, true)",
        str(user_id),
        str(clinic_id),
    )


async def call_change_role(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    actor_id: uuid.UUID,
    membership_id: uuid.UUID,
    new_role: str = TARGET_ROLE,
):
    return await connection.fetchrow(
        "SELECT * FROM app.change_member_role($1, $2, $3, $4)",
        clinic_id,
        actor_id,
        membership_id,
        new_role,
    )


async def call_remove(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    actor_id: uuid.UUID,
    membership_id: uuid.UUID,
):
    return await connection.fetchrow(
        "SELECT * FROM app.remove_membership($1, $2, $3)",
        clinic_id,
        actor_id,
        membership_id,
    )


async def call_invite(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    actor_id: uuid.UUID,
    email: str,
):
    return await connection.fetchrow(
        "SELECT * FROM app.create_member_invitation($1, $2, $3, 'DENTIST', $4)",
        clinic_id,
        actor_id,
        email,
        uuid.uuid4().bytes,
    )


@pytest.mark.anyio
async def test_functions_fail_closed_without_transaction_context(
    app_connection: asyncpg.Connection, guard_scenario: GuardScenario
) -> None:
    scenario = guard_scenario

    with pytest.raises(asyncpg.PostgresError) as mismatch:
        await call_change_role(
            app_connection,
            clinic_id=scenario.clinic_id,
            actor_id=scenario.owner_id,
            membership_id=scenario.target_membership_id,
        )
    with pytest.raises(asyncpg.PostgresError) as removal:
        await call_remove(
            app_connection,
            clinic_id=scenario.clinic_id,
            actor_id=scenario.owner_id,
            membership_id=scenario.target_membership_id,
        )
    with pytest.raises(asyncpg.PostgresError) as invitation:
        await call_invite(
            app_connection,
            clinic_id=scenario.clinic_id,
            actor_id=scenario.owner_id,
            email=make_test_email("guard-invite"),
        )

    assert "context_mismatch" in str(mismatch.value)
    assert "context_mismatch" in str(removal.value)
    assert "context_mismatch" in str(invitation.value)


@pytest.mark.anyio
async def test_foreign_actor_uuid_cannot_be_smuggled_into_own_context(
    app_connection: asyncpg.Connection, guard_scenario: GuardScenario
) -> None:
    scenario = guard_scenario

    async with app_connection.transaction():
        await set_context(
            app_connection, user_id=scenario.attacker_id, clinic_id=scenario.clinic_id
        )
        with pytest.raises(asyncpg.PostgresError) as smuggled:
            await call_change_role(
                app_connection,
                clinic_id=scenario.clinic_id,
                actor_id=scenario.owner_id,
                membership_id=scenario.target_membership_id,
            )
        assert "context_mismatch" in str(smuggled.value)


@pytest.mark.anyio
async def test_foreign_clinic_uuid_cannot_be_smuggled_into_own_context(
    app_connection: asyncpg.Connection, guard_scenario: GuardScenario
) -> None:
    scenario = guard_scenario

    async with app_connection.transaction():
        await set_context(app_connection, user_id=scenario.owner_id, clinic_id=scenario.clinic_id)
        with pytest.raises(asyncpg.PostgresError) as smuggle_clinic:
            await call_change_role(
                app_connection,
                clinic_id=scenario.foreign_clinic_id,
                actor_id=scenario.foreign_owner_id,
                membership_id=scenario.target_membership_id,
            )
        assert "context_mismatch" in str(smuggle_clinic.value)

    async with app_connection.transaction():
        await set_context(app_connection, user_id=scenario.owner_id, clinic_id=scenario.clinic_id)
        with pytest.raises(asyncpg.PostgresError) as smuggle_invite:
            await call_invite(
                app_connection,
                clinic_id=scenario.foreign_clinic_id,
                actor_id=scenario.foreign_owner_id,
                email=make_test_email("guard-foreign-invite"),
            )
        assert "context_mismatch" in str(smuggle_invite.value)


@pytest.mark.anyio
async def test_matching_context_still_allows_the_operation(
    app_connection: asyncpg.Connection, guard_scenario: GuardScenario
) -> None:
    scenario = guard_scenario

    async with app_connection.transaction():
        await set_context(app_connection, user_id=scenario.owner_id, clinic_id=scenario.clinic_id)
        changed = await call_change_role(
            app_connection,
            clinic_id=scenario.clinic_id,
            actor_id=scenario.owner_id,
            membership_id=scenario.target_membership_id,
        )
        invited = await call_invite(
            app_connection,
            clinic_id=scenario.clinic_id,
            actor_id=scenario.owner_id,
            email=make_test_email("guard-allowed"),
        )

    assert changed["new_role"] == TARGET_ROLE
    assert invited["membership_id"] is not None


@pytest.mark.anyio
async def test_attacker_cannot_promote_through_own_context(
    app_connection: asyncpg.Connection, guard_scenario: GuardScenario
) -> None:
    scenario = guard_scenario

    async with app_connection.transaction():
        await set_context(
            app_connection, user_id=scenario.attacker_id, clinic_id=scenario.clinic_id
        )
        with pytest.raises(asyncpg.exceptions.RaiseError) as not_owner:
            await call_change_role(
                app_connection,
                clinic_id=scenario.clinic_id,
                actor_id=scenario.attacker_id,
                membership_id=scenario.target_membership_id,
                new_role="OWNER",
            )
    assert "not_permitted" in str(not_owner.value)
