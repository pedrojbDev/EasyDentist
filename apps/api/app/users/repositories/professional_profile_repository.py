from __future__ import annotations

from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import UserContext
from app.core.tenancy import ensure_context_matches
from app.users.models import ProfessionalProfile


class ProfessionalProfileRepository:
    """Owner-scoped access to the global professional profile of a user.

    There is no unscoped entry point: every statement relies on the owner RLS
    policy (``user_id = app.current_user_id``) and on the session context.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, context: UserContext) -> ProfessionalProfile | None:
        ensure_context_matches(self._session, context)
        profile = await self._session.get(ProfessionalProfile, context.user_id)
        return profile

    async def upsert(
        self,
        context: UserContext,
        *,
        professional_name: str,
        cro_number: str,
        cro_state: str,
        updated_at: datetime,
    ) -> ProfessionalProfile:
        ensure_context_matches(self._session, context)
        values = {
            "user_id": context.user_id,
            "professional_name": professional_name,
            "cro_number": cro_number,
            "cro_state": cro_state,
            "updated_at": updated_at,
        }
        statement = (
            pg_insert(ProfessionalProfile)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[ProfessionalProfile.user_id],
                set_={
                    "professional_name": professional_name,
                    "cro_number": cro_number,
                    "cro_state": cro_state,
                    "updated_at": updated_at,
                },
            )
            .returning(ProfessionalProfile)
        )
        result = await self._session.execute(statement)
        return result.scalar_one()
