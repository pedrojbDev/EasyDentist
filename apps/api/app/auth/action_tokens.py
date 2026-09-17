from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repositories.action_token_repository import ActionTokenRepository
from app.auth.tokens import generate_token, token_digest
from app.core.clock import utcnow

PURPOSE_EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
PURPOSE_PASSWORD_RESET = "PASSWORD_RESET"

EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(minutes=30)


class ActionTokenService:
    def __init__(self, *, clock: Callable[[], datetime] = utcnow) -> None:
        self._clock = clock

    async def issue(
        self,
        session: AsyncSession,
        *,
        purpose: str,
        user_id: UUID,
        ttl: timedelta,
    ) -> str:
        token = generate_token()
        repository = ActionTokenRepository(session)
        repository.add(
            user_id=user_id,
            token_hash=token_digest(token),
            purpose=purpose,
            expires_at=self._clock() + ttl,
        )
        await repository.flush()
        return token

    async def consume(
        self,
        session: AsyncSession,
        *,
        purpose: str,
        token: str,
    ) -> UUID | None:
        now = self._clock()
        repository = ActionTokenRepository(session)
        row = await repository.lock_by_token_hash(token_digest(token))
        if (
            row is None
            or row.purpose != purpose
            or row.consumed_at is not None
            or row.expires_at <= now
        ):
            return None
        repository.mark_consumed(row, now=now)
        await repository.flush()
        return row.user_id
