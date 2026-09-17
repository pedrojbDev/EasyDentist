from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.models import Membership
from app.core.context import TenantContext, UserContext
from app.core.tenancy import ensure_context_matches


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, context: UserContext) -> Sequence[Membership]:
        ensure_context_matches(self._session, context)
        statement = (
            select(Membership)
            .where(Membership.user_id == context.user_id)
            .order_by(Membership.created_at, Membership.id)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def list_for_clinic(self, context: TenantContext) -> Sequence[Membership]:
        ensure_context_matches(self._session, context)
        statement = (
            select(Membership)
            .where(Membership.clinic_id == context.clinic_id)
            .order_by(Membership.created_at, Membership.id)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get(self, context: TenantContext, membership_id: UUID) -> Membership | None:
        ensure_context_matches(self._session, context)
        membership: Membership | None = await self._session.scalar(
            select(Membership).where(
                Membership.id == membership_id,
                Membership.clinic_id == context.clinic_id,
            )
        )
        return membership
