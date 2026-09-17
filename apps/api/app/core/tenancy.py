from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.context import TenantContext, UserContext
from app.core.database import transaction_scope
from app.core.errors import ContextMismatchError

SESSION_CONTEXT_KEY = "easydentist.context"


@asynccontextmanager
async def user_transaction(
    session_factory: async_sessionmaker[AsyncSession], context: UserContext
) -> AsyncIterator[AsyncSession]:
    async with transaction_scope(session_factory) as session:
        await session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(context.user_id)},
        )
        session.info[SESSION_CONTEXT_KEY] = context
        yield session


@asynccontextmanager
async def tenant_transaction(
    session_factory: async_sessionmaker[AsyncSession], context: TenantContext
) -> AsyncIterator[AsyncSession]:
    async with transaction_scope(session_factory) as session:
        await session.execute(
            text(
                "SELECT set_config('app.current_user_id', :user_id, true), "
                "set_config('app.current_clinic_id', :clinic_id, true)"
            ),
            {"user_id": str(context.user_id), "clinic_id": str(context.clinic_id)},
        )
        session.info[SESSION_CONTEXT_KEY] = context
        yield session


def ensure_context_matches(session: AsyncSession, context: UserContext | TenantContext) -> None:
    """Reject repository calls whose context diverges from the transaction.

    Reads scoped only by user (clinic selector) stay valid inside a tenant
    transaction when the user matches. Tenant-scoped calls require an equal
    clinic. Any divergence fails closed instead of relying on RLS alone.
    """

    stored: UserContext | TenantContext | None = session.info.get(SESSION_CONTEXT_KEY)
    if stored is None:
        raise ContextMismatchError("session has no transaction context")
    if stored.user_id != context.user_id:
        raise ContextMismatchError("session context belongs to another user")
    if isinstance(context, TenantContext) and (
        not isinstance(stored, TenantContext) or stored.clinic_id != context.clinic_id
    ):
        raise ContextMismatchError("session context belongs to another clinic")
