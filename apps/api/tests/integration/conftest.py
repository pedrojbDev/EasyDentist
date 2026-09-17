from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import pytest
from helpers import (
    insert_clinic,
    insert_clinic_settings,
    insert_invitation,
    insert_membership,
    insert_user,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.database import create_database_engine


@dataclass(frozen=True, slots=True)
class SeededTenants:
    user_a: uuid.UUID
    user_b: uuid.UUID
    clinic_a: uuid.UUID
    clinic_b: uuid.UUID
    membership_a: uuid.UUID
    membership_b: uuid.UUID


def required_url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for PostgreSQL integration tests")
    return value


@pytest.fixture
def app_async_url() -> str:
    url = make_url(required_url("TEST_APP_DATABASE_URL")).set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


@pytest.fixture
async def app_engine(app_async_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(app_async_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _connect(variable: str) -> asyncpg.Connection:
    return await asyncpg.connect(required_url(variable))


@pytest.fixture
async def admin_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_ADMIN_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def app_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_APP_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def migrator_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_MIGRATION_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def seeded_tenants(
    migrator_connection: asyncpg.Connection,
) -> AsyncIterator[SeededTenants]:
    suffix = uuid.uuid4().hex
    user_a = await insert_user(migrator_connection, f"tenant-a-{suffix}@example.com")
    user_b = await insert_user(migrator_connection, f"tenant-b-{suffix}@example.com")
    clinic_a = await insert_clinic(migrator_connection, f"clinic-a-{suffix}")
    clinic_b = await insert_clinic(migrator_connection, f"clinic-b-{suffix}")
    membership_a = await insert_membership(migrator_connection, clinic_id=clinic_a, user_id=user_a)
    membership_b = await insert_membership(migrator_connection, clinic_id=clinic_b, user_id=user_b)
    await insert_clinic_settings(migrator_connection, clinic_a)
    await insert_clinic_settings(migrator_connection, clinic_b)
    await insert_invitation(
        migrator_connection,
        clinic_id=clinic_a,
        membership_id=membership_a,
        email=f"invitee-a-{suffix}@example.com",
        token_hash=uuid.uuid4().bytes,
    )
    await migrator_connection.execute(
        "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled) "
        "VALUES ($1, 'odontogram', true)",
        clinic_a,
    )
    await migrator_connection.execute(
        "INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type) "
        "VALUES ($1, $2, 'membership.created')",
        clinic_a,
        user_a,
    )

    try:
        yield SeededTenants(
            user_a=user_a,
            user_b=user_b,
            clinic_a=clinic_a,
            clinic_b=clinic_b,
            membership_a=membership_a,
            membership_b=membership_b,
        )
    finally:
        clinic_ids = [clinic_a, clinic_b]
        await migrator_connection.execute(
            "DELETE FROM app.membership_invitations WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_audit_events WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_feature_flags WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_settings WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.memberships WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinics WHERE id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.users WHERE id = ANY($1::uuid[])", [user_a, user_b]
        )
