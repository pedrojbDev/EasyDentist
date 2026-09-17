from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_membership
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.auth.principal import Principal
from app.clinics.dependencies import ClinicMembership, get_membership
from app.clinics.rbac import Role
from app.core.errors import NotFoundError

PASSWORD = "correct horse battery staple"


def make_request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def principal_for(user_id: uuid.UUID) -> Principal:
    return Principal(user_id=user_id, session_id=uuid.uuid4(), auth_method="password")


class Scenario:
    def __init__(self) -> None:
        self.user_id: uuid.UUID
        self.active_clinic: uuid.UUID
        self.pending_clinic: uuid.UUID
        self.suspended_clinic: uuid.UUID


@pytest.fixture
async def scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[Scenario]:
    built = Scenario()
    built.user_id = await seed_user_with_password(
        email=make_test_email("clinic-access"), password=PASSWORD
    )
    suffix = uuid.uuid4().hex[:10]
    built.active_clinic = await insert_clinic(migrator_connection, f"active-{suffix}")
    built.pending_clinic = await insert_clinic(migrator_connection, f"pending-{suffix}")
    built.suspended_clinic = await insert_clinic(migrator_connection, f"suspended-{suffix}")
    provisioned_clinics.extend([built.active_clinic, built.pending_clinic, built.suspended_clinic])
    await insert_membership(
        migrator_connection,
        clinic_id=built.active_clinic,
        user_id=built.user_id,
        role="ADMIN",
        status="ACTIVE",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.pending_clinic,
        user_id=built.user_id,
        role="DENTIST",
        status="PENDING",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.suspended_clinic,
        user_id=built.user_id,
        role="RECEPTIONIST",
        status="SUSPENDED",
    )
    yield built


async def resolve(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    clinic_id: uuid.UUID | None = None,
    request: Request | None = None,
) -> ClinicMembership:
    return await get_membership(
        request if request is not None else make_request(),
        clinic_id if clinic_id is not None else scenario.active_clinic,
        principal_for(scenario.user_id),
        session_factory,
    )


@pytest.mark.anyio
async def test_active_member_resolves_context_and_role(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    membership = await resolve(scenario, session_factory)

    assert membership.role is Role.ADMIN
    assert membership.context.user_id == scenario.user_id
    assert membership.context.clinic_id == scenario.active_clinic


@pytest.mark.anyio
async def test_non_member_is_hidden(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
) -> None:
    foreign_user = await migrator_connection.fetchval(
        "INSERT INTO app.users (email) VALUES ($1) RETURNING id",
        make_test_email("clinic-foreign"),
    )

    with pytest.raises(NotFoundError):
        await get_membership(
            make_request(),
            scenario.active_clinic,
            principal_for(foreign_user),
            session_factory,
        )


@pytest.mark.anyio
async def test_pending_and_suspended_memberships_are_hidden(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(NotFoundError):
        await resolve(scenario, session_factory, clinic_id=scenario.pending_clinic)
    with pytest.raises(NotFoundError):
        await resolve(scenario, session_factory, clinic_id=scenario.suspended_clinic)


@pytest.mark.anyio
async def test_unknown_clinic_is_hidden(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(NotFoundError):
        await resolve(scenario, session_factory, clinic_id=uuid.uuid4())


@pytest.mark.anyio
async def test_result_is_cached_per_request(
    scenario: Scenario,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    request = make_request()

    first = await resolve(scenario, session_factory, request=request)
    second = await resolve(scenario, session_factory, request=request)

    assert first is second
