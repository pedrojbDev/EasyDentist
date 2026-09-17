from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.models import Clinic, Membership
from app.core.context import TenantContext, UserContext
from app.core.tenancy import ensure_context_matches


class ClinicRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, context: UserContext) -> Sequence[Clinic]:
        ensure_context_matches(self._session, context)
        statement = (
            select(Clinic)
            .where(
                Clinic.id.in_(
                    select(Membership.clinic_id).where(
                        Membership.user_id == context.user_id,
                        Membership.status == "ACTIVE",
                    )
                )
            )
            .order_by(Clinic.slug)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def get(self, context: TenantContext) -> Clinic | None:
        ensure_context_matches(self._session, context)
        return await self._session.get(Clinic, context.clinic_id)

    async def update_legal_name(self, context: TenantContext, legal_name: str) -> Clinic | None:
        ensure_context_matches(self._session, context)
        clinic = await self.get(context)
        if clinic is None:
            return None
        clinic.legal_name = legal_name
        clinic.updated_at = datetime.now(UTC)
        await self._session.flush()
        return clinic
