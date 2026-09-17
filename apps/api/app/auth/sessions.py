from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.principal import Principal
from app.auth.repositories.session_repository import SessionRepository
from app.auth.settings import AuthSettings
from app.auth.tokens import generate_token, token_digest
from app.core.clock import utcnow
from app.core.database import transaction_scope


class SessionService:
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

    async def create(self, user_id: UUID) -> tuple[UUID, str]:
        token = generate_token()
        now = self._clock()
        async with transaction_scope(self._session_factory) as session:
            row = SessionRepository(session).add(
                user_id=user_id,
                token_hash=token_digest(token),
                last_seen_at=now,
                idle_expires_at=now + self._settings.session_idle_ttl,
                absolute_expires_at=now + self._settings.session_absolute_ttl,
            )
            await session.flush()
            return row.id, token

    async def resolve(self, token: str) -> Principal | None:
        now = self._clock()
        async with transaction_scope(self._session_factory) as session:
            repository = SessionRepository(session)
            row = await repository.find_by_token_hash(token_digest(token))
            if row is None or row.revoked_at is not None:
                return None
            if row.idle_expires_at <= now or row.absolute_expires_at <= now:
                return None
            if now - row.last_seen_at >= self._settings.last_seen_throttle:
                extended: datetime = min(
                    now + self._settings.session_idle_ttl, row.absolute_expires_at
                )
                repository.touch(row, now=now, idle_expires_at=extended)
            return Principal(user_id=row.user_id, session_id=row.id, auth_method="password")

    async def revoke(self, user_id: UUID, session_id: UUID) -> bool:
        async with transaction_scope(self._session_factory) as session:
            repository = SessionRepository(session)
            row = await repository.get_for_user(session_id, user_id)
            if row is None:
                return False
            if row.revoked_at is None:
                repository.revoke(row, now=self._clock())
            return True

    async def revoke_all(self, user_id: UUID) -> int:
        async with transaction_scope(self._session_factory) as session:
            return await SessionRepository(session).revoke_all_for_user(user_id, now=self._clock())
