from __future__ import annotations

import asyncpg
import pytest
from conftest import SeededTenants
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.repositories.clinic_repository import ClinicRepository
from app.core.context import TenantContext, UserContext
from app.core.database import create_session_factory
from app.core.errors import ContextMismatchError
from app.core.tenancy import tenant_transaction, user_transaction


@pytest.mark.anyio
async def test_list_for_user_returns_only_own_clinics(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = UserContext(user_id=seeded_tenants.user_a)

    async with user_transaction(session_factory, context) as session:
        clinics = await ClinicRepository(session).list_for_user(context)

    assert [clinic.id for clinic in clinics] == [seeded_tenants.clinic_a]


@pytest.mark.anyio
async def test_get_returns_clinic_for_active_member(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        clinic = await ClinicRepository(session).get(context)

    assert clinic is not None
    assert clinic.id == seeded_tenants.clinic_a


@pytest.mark.anyio
async def test_get_returns_none_for_cross_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        clinic = await ClinicRepository(session).get(context)

    assert clinic is None


@pytest.mark.anyio
async def test_get_raises_when_session_has_no_context(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with session_factory() as session:
        with pytest.raises(ContextMismatchError):
            await ClinicRepository(session).get(context)


@pytest.mark.anyio
async def test_update_legal_name_persists_within_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        updated = await ClinicRepository(session).update_legal_name(context, "Clinica A Renomeada")

    assert updated is not None
    assert updated.legal_name == "Clinica A Renomeada"

    async with tenant_transaction(session_factory, context) as session:
        fetched = await ClinicRepository(session).get(context)

    assert fetched is not None
    assert fetched.legal_name == "Clinica A Renomeada"


@pytest.mark.anyio
async def test_update_legal_name_cross_tenant_returns_none(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        updated = await ClinicRepository(session).update_legal_name(context, "Intruder")

    assert updated is None
    legal_name = await migrator_connection.fetchval(
        "SELECT legal_name FROM app.clinics WHERE id = $1", seeded_tenants.clinic_b
    )
    assert legal_name != "Intruder"
