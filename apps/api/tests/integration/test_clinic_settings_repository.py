from __future__ import annotations

import pytest
from conftest import SeededTenants
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.repositories.clinic_settings_repository import ClinicSettingsRepository
from app.core.context import TenantContext
from app.core.database import create_session_factory
from app.core.tenancy import tenant_transaction


@pytest.mark.anyio
async def test_get_returns_settings_for_active_member(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        settings = await ClinicSettingsRepository(session).get(context)

    assert settings is not None
    assert settings.clinic_id == seeded_tenants.clinic_a
    assert settings.timezone == "America/Bahia"
    assert settings.locale == "pt-BR"
    assert settings.currency == "BRL"


@pytest.mark.anyio
async def test_get_returns_none_for_cross_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        settings = await ClinicSettingsRepository(session).get(context)

    assert settings is None


@pytest.mark.anyio
async def test_update_changes_only_provided_fields_and_persists(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        updated = await ClinicSettingsRepository(session).update(
            context, display_name="Clinica A", timezone="America/Sao_Paulo"
        )

    assert updated is not None
    assert updated.display_name == "Clinica A"
    assert updated.timezone == "America/Sao_Paulo"
    assert updated.locale == "pt-BR"
    assert updated.currency == "BRL"

    async with tenant_transaction(session_factory, context) as session:
        fetched = await ClinicSettingsRepository(session).get(context)

    assert fetched is not None
    assert fetched.display_name == "Clinica A"
    assert fetched.timezone == "America/Sao_Paulo"


@pytest.mark.anyio
async def test_update_returns_none_for_cross_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        updated = await ClinicSettingsRepository(session).update(context, display_name="Intruder")

    assert updated is None
