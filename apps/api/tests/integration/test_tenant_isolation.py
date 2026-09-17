from __future__ import annotations

from enum import StrEnum

import asyncpg
import pytest
from conftest import SeededTenants
from helpers import insert_membership
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.feature_flags import FeatureFlagRepository, FeatureFlagService
from app.clinics.repositories.clinic_repository import ClinicRepository
from app.clinics.repositories.clinic_settings_repository import ClinicSettingsRepository
from app.clinics.repositories.membership_repository import MembershipRepository
from app.core.context import TenantContext, UserContext
from app.core.database import create_session_factory
from app.core.errors import ContextMismatchError
from app.core.tenancy import tenant_transaction, user_transaction

FlagKey = StrEnum("FlagKey", {"ODONTOGRAM": "odontogram"})


@pytest.mark.anyio
async def test_clinic_repository_isolates_both_directions(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        repository = ClinicRepository(session)
        assert await repository.get(context_a) is not None
        with pytest.raises(ContextMismatchError):
            await repository.get(context_b)

    async with tenant_transaction(session_factory, context_b) as session:
        repository = ClinicRepository(session)
        assert await repository.get(context_b) is not None
        with pytest.raises(ContextMismatchError):
            await repository.get(context_a)


@pytest.mark.anyio
async def test_user_scope_lists_are_isolated(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)

    async with user_transaction(
        session_factory, UserContext(user_id=seeded_tenants.user_a)
    ) as session:
        clinics = await ClinicRepository(session).list_for_user(
            UserContext(user_id=seeded_tenants.user_a)
        )

    assert [clinic.id for clinic in clinics] == [seeded_tenants.clinic_a]

    async with user_transaction(
        session_factory, UserContext(user_id=seeded_tenants.user_b)
    ) as session:
        clinics = await ClinicRepository(session).list_for_user(
            UserContext(user_id=seeded_tenants.user_b)
        )

    assert [clinic.id for clinic in clinics] == [seeded_tenants.clinic_b]


@pytest.mark.anyio
async def test_membership_repository_isolates_both_directions(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        repository = MembershipRepository(session)
        assert [item.id for item in await repository.list_for_clinic(context_a)] == [
            seeded_tenants.membership_a
        ]
        assert await repository.get(context_a, seeded_tenants.membership_b) is None
        assert await repository.get(context_a, seeded_tenants.membership_a) is not None

    async with tenant_transaction(session_factory, context_b) as session:
        repository = MembershipRepository(session)
        assert [item.id for item in await repository.list_for_clinic(context_b)] == [
            seeded_tenants.membership_b
        ]
        assert await repository.get(context_b, seeded_tenants.membership_a) is None
        assert await repository.get(context_b, seeded_tenants.membership_b) is not None


@pytest.mark.anyio
async def test_clinic_settings_repository_isolates_both_directions(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        repository = ClinicSettingsRepository(session)
        own = await repository.get(context_a)
        assert own is not None
        assert own.clinic_id == seeded_tenants.clinic_a
        with pytest.raises(ContextMismatchError):
            await repository.get(context_b)
        with pytest.raises(ContextMismatchError):
            await repository.update(context_b, display_name="Intruder")

    async with tenant_transaction(session_factory, context_b) as session:
        repository = ClinicSettingsRepository(session)
        own = await repository.get(context_b)
        assert own is not None
        assert own.clinic_id == seeded_tenants.clinic_b
        with pytest.raises(ContextMismatchError):
            await repository.get(context_a)
        with pytest.raises(ContextMismatchError):
            await repository.update(context_a, display_name="Intruder")

    clinic_b_display_name = await migrator_connection.fetchval(
        "SELECT display_name FROM app.clinic_settings WHERE clinic_id = $1",
        seeded_tenants.clinic_b,
    )
    assert clinic_b_display_name == f"Clinic {seeded_tenants.clinic_b}"


@pytest.mark.anyio
async def test_feature_flags_isolate_tenants(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        repository = FeatureFlagRepository(session)
        assert await FeatureFlagService(repository).is_enabled(context_a, FlagKey.ODONTOGRAM)
        with pytest.raises(ContextMismatchError):
            await repository.get_row(context_b, FlagKey.ODONTOGRAM.value)

    async with tenant_transaction(session_factory, context_b) as session:
        repository = FeatureFlagRepository(session)
        assert not await FeatureFlagService(repository).is_enabled(context_b, FlagKey.ODONTOGRAM)
        with pytest.raises(ContextMismatchError):
            await repository.get_row(context_a, FlagKey.ODONTOGRAM.value)


@pytest.mark.anyio
async def test_divergent_context_is_rejected_for_dual_membership_user(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    await insert_membership(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_b,
        user_id=seeded_tenants.user_a,
    )
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        assert await ClinicRepository(session).get(context_a) is not None
        with pytest.raises(ContextMismatchError):
            await ClinicRepository(session).get(context_b)
        with pytest.raises(ContextMismatchError):
            await ClinicSettingsRepository(session).get(context_b)
        with pytest.raises(ContextMismatchError):
            await MembershipRepository(session).get(context_b, seeded_tenants.membership_b)
        with pytest.raises(ContextMismatchError):
            await FeatureFlagRepository(session).get_row(context_b, FlagKey.ODONTOGRAM.value)

    async with tenant_transaction(session_factory, context_b) as session:
        assert await ClinicRepository(session).get(context_b) is not None
        with pytest.raises(ContextMismatchError):
            await ClinicRepository(session).get(context_a)


@pytest.mark.anyio
async def test_tenant_scope_requires_a_tenant_transaction(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    user_context = UserContext(user_id=seeded_tenants.user_a)

    async with user_transaction(session_factory, user_context) as session:
        clinics = await ClinicRepository(session).list_for_user(user_context)

        assert [clinic.id for clinic in clinics] == [seeded_tenants.clinic_a]
        with pytest.raises(ContextMismatchError):
            await ClinicRepository(session).get(context)
