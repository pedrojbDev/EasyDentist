from __future__ import annotations

from enum import StrEnum

import asyncpg
import pytest
from conftest import SeededTenants
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.feature_flags import FeatureFlagRepository, FeatureFlagService
from app.core.context import TenantContext
from app.core.database import create_session_factory
from app.core.tenancy import tenant_transaction

SampleKey = StrEnum(
    "SampleKey",
    {
        "ENABLED": "odontogram",
        "DISABLED": "sample-disabled",
        "ABSENT": "sample-absent",
        "CONFIGURED": "sample-configured",
    },
)


@pytest.mark.anyio
async def test_absent_flag_defaults_to_disabled(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        enabled = await FeatureFlagService(FeatureFlagRepository(session)).is_enabled(
            context, SampleKey.ABSENT
        )

    assert enabled is False


@pytest.mark.anyio
async def test_enabled_flag_is_true(app_engine: AsyncEngine, seeded_tenants: SeededTenants) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        enabled = await FeatureFlagService(FeatureFlagRepository(session)).is_enabled(
            context, SampleKey.ENABLED
        )

    assert enabled is True


@pytest.mark.anyio
async def test_disabled_flag_is_false(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    await migrator_connection.execute(
        "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled) "
        "VALUES ($1, 'sample-disabled', false)",
        seeded_tenants.clinic_a,
    )
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        enabled = await FeatureFlagService(FeatureFlagRepository(session)).is_enabled(
            context, SampleKey.DISABLED
        )

    assert enabled is False


@pytest.mark.anyio
async def test_flag_configuration_is_available(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    await migrator_connection.execute(
        "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled, config) "
        "VALUES ($1, 'sample-configured', true, '{\"threshold\": 5}'::jsonb)",
        seeded_tenants.clinic_a,
    )
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        row = await FeatureFlagRepository(session).get_row(context, SampleKey.CONFIGURED.value)

    assert row is not None
    assert row.enabled is True
    assert row.config == {"threshold": 5}


@pytest.mark.anyio
async def test_flag_of_another_tenant_is_not_visible(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        repository = FeatureFlagRepository(session)
        row = await repository.get_row(context, SampleKey.ENABLED.value)
        enabled = await FeatureFlagService(repository).is_enabled(context, SampleKey.ENABLED)

    assert row is None
    assert enabled is False
