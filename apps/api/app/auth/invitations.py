from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.audit import AuthAuditService
from app.auth.passwords import PasswordHasher
from app.auth.settings import AuthSettings
from app.auth.tokens import token_digest
from app.core.clock import utcnow
from app.core.database import transaction_scope

UNUSABLE_INVITATION_SQLSTATE = "P0001"


def is_invitation_unusable(error: DBAPIError) -> bool:
    return getattr(
        error.orig, "sqlstate", None
    ) == UNUSABLE_INVITATION_SQLSTATE and "invitation_unusable" in str(error.orig)


@dataclass(frozen=True, slots=True)
class AcceptedInvitation:
    user_id: UUID
    clinic_id: UUID


class InvitationService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: AuthSettings,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._clock = clock

    async def accept(self, *, token: str, password: str) -> AcceptedInvitation | None:
        password_hash = PasswordHasher(self._settings).hash(password)
        try:
            async with transaction_scope(self._session_factory) as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT user_id, clinic_id "
                            "FROM app.consume_invitation(:token_hash, :password_hash)"
                        ),
                        {"token_hash": token_digest(token), "password_hash": password_hash},
                    )
                ).one()
                await AuthAuditService(session).record("invitation_accepted", user_id=row.user_id)
        except DBAPIError as error:
            if is_invitation_unusable(error):
                return None
            raise
        return AcceptedInvitation(user_id=row.user_id, clinic_id=row.clinic_id)
