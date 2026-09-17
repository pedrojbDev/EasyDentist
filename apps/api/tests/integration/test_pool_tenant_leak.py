from __future__ import annotations

import asyncio

import pytest
from conftest import SeededTenants
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clinics.repositories.clinic_settings_repository import ClinicSettingsRepository
from app.core.context import TenantContext
from app.core.database import create_session_factory
from app.core.errors import ContextMismatchError
from app.core.tenancy import tenant_transaction


@pytest.mark.anyio
async def test_interleaved_transactions_keep_tenants_isolated(
    seeded_tenants: SeededTenants, app_async_url: str
) -> None:
    engine = create_async_engine(app_async_url, pool_size=2, max_overflow=0)
    try:
        session_factory = create_session_factory(engine)
        context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
        context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

        async with tenant_transaction(session_factory, context_a) as session_a:
            async with tenant_transaction(session_factory, context_b) as session_b:
                settings_a = await ClinicSettingsRepository(session_a).get(context_a)
                settings_b = await ClinicSettingsRepository(session_b).get(context_b)
                with pytest.raises(ContextMismatchError):
                    await ClinicSettingsRepository(session_a).get(context_b)
                with pytest.raises(ContextMismatchError):
                    await ClinicSettingsRepository(session_b).get(context_a)

        assert settings_a is not None
        assert settings_a.clinic_id == seeded_tenants.clinic_a
        assert settings_b is not None
        assert settings_b.clinic_id == seeded_tenants.clinic_b
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_concurrent_tenants_do_not_cross_contaminate(
    seeded_tenants: SeededTenants, app_async_url: str
) -> None:
    engine = create_async_engine(app_async_url, pool_size=2, max_overflow=0)
    try:
        session_factory = create_session_factory(engine)
        context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
        context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

        async def read_clinic_id(context: TenantContext) -> object:
            async with tenant_transaction(session_factory, context) as session:
                settings = await ClinicSettingsRepository(session).get(context)
                return settings.clinic_id if settings is not None else None

        results = await asyncio.gather(
            read_clinic_id(context_a),
            read_clinic_id(context_b),
            read_clinic_id(context_a),
            read_clinic_id(context_b),
        )

        assert results == [
            seeded_tenants.clinic_a,
            seeded_tenants.clinic_b,
            seeded_tenants.clinic_a,
            seeded_tenants.clinic_b,
        ]
    finally:
        await engine.dispose()


async def _read_once(
    session_factory: async_sessionmaker[AsyncSession], context: TenantContext
) -> None:
    async with tenant_transaction(session_factory, context) as session:
        await ClinicSettingsRepository(session).get(context)


@pytest.mark.anyio
async def test_reused_pooled_connection_has_empty_context(
    seeded_tenants: SeededTenants, app_async_url: str
) -> None:
    engine = create_async_engine(app_async_url, pool_size=2, max_overflow=0)
    try:
        session_factory = create_session_factory(engine)
        context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

        await _read_once(session_factory, context_a)

        async with session_factory() as session:
            leftover = await session.scalar(
                text("SELECT current_setting('app.current_clinic_id', true)")
            )
            with pytest.raises(ContextMismatchError):
                await ClinicSettingsRepository(session).get(context_a)

        assert leftover == ""
    finally:
        await engine.dispose()
