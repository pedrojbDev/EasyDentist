from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.context import TenantContext, UserContext
from app.core.database import create_session_factory
from app.core.tenancy import tenant_transaction, user_transaction


@pytest.mark.anyio
async def test_tenant_transaction_sets_session_context(app_engine: AsyncEngine) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=uuid4(), clinic_id=uuid4())

    async with tenant_transaction(session_factory, context) as session:
        row = (
            await session.execute(
                text(
                    "SELECT current_setting('app.current_user_id', true) AS user_id, "
                    "current_setting('app.current_clinic_id', true) AS clinic_id"
                )
            )
        ).one()

    assert row.user_id == str(context.user_id)
    assert row.clinic_id == str(context.clinic_id)


@pytest.mark.anyio
async def test_user_transaction_sets_only_user_context(app_engine: AsyncEngine) -> None:
    session_factory = create_session_factory(app_engine)
    context = UserContext(user_id=uuid4())

    async with user_transaction(session_factory, context) as session:
        user_id = await session.scalar(text("SELECT current_setting('app.current_user_id', true)"))
        clinic_id = await session.scalar(
            text("SELECT current_setting('app.current_clinic_id', true)")
        )

    assert user_id == str(context.user_id)
    assert clinic_id is None


@pytest.mark.anyio
async def test_context_does_not_leak_out_of_the_transaction(app_async_url: str) -> None:
    engine = create_async_engine(app_async_url, pool_size=1, max_overflow=0)
    try:
        session_factory = create_session_factory(engine)
        context = TenantContext(user_id=uuid4(), clinic_id=uuid4())
        async with tenant_transaction(session_factory, context):
            pass

        async with session_factory() as session:
            leaked = await session.scalar(
                text("SELECT current_setting('app.current_clinic_id', true)")
            )

        assert leaked == ""
        assert leaked != str(context.clinic_id)
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_context_is_cleared_on_rollback(app_async_url: str) -> None:
    engine = create_async_engine(app_async_url, pool_size=1, max_overflow=0)
    try:
        session_factory = create_session_factory(engine)
        context = TenantContext(user_id=uuid4(), clinic_id=uuid4())
        with pytest.raises(RuntimeError, match="boom"):
            async with tenant_transaction(session_factory, context):
                raise RuntimeError("boom")

        async with session_factory() as session:
            leaked = await session.scalar(
                text("SELECT current_setting('app.current_clinic_id', true)")
            )

        assert leaked == ""
        assert leaked != str(context.clinic_id)
    finally:
        await engine.dispose()
