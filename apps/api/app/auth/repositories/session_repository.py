from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthSession


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        user_id: UUID,
        token_hash: bytes,
        last_seen_at: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            token_hash=token_hash,
            last_seen_at=last_seen_at,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
        )
        self._session.add(auth_session)
        return auth_session

    async def find_by_token_hash(self, token_hash: bytes) -> AuthSession | None:
        found: AuthSession | None = await self._session.scalar(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        )
        return found

    async def get_for_user(self, session_id: UUID, user_id: UUID) -> AuthSession | None:
        found: AuthSession | None = await self._session.scalar(
            select(AuthSession).where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
            )
        )
        return found

    async def list_for_user(self, user_id: UUID) -> Sequence[AuthSession]:
        result = await self._session.execute(
            select(AuthSession)
            .where(AuthSession.user_id == user_id)
            .order_by(AuthSession.created_at, AuthSession.id)
        )
        return result.scalars().all()

    def touch(self, auth_session: AuthSession, *, now: datetime, idle_expires_at: datetime) -> None:
        auth_session.last_seen_at = now
        auth_session.idle_expires_at = idle_expires_at

    def revoke(self, auth_session: AuthSession, *, now: datetime) -> None:
        auth_session.revoked_at = now

    async def revoke_all_for_user(self, user_id: UUID, *, now: datetime) -> int:
        result = await self._session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        return cast("CursorResult[Any]", result).rowcount

    async def flush(self) -> None:
        await self._session.flush()
