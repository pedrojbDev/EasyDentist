from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthActionToken


class ActionTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        user_id: UUID,
        token_hash: bytes,
        purpose: str,
        expires_at: datetime,
    ) -> AuthActionToken:
        token = AuthActionToken(
            user_id=user_id,
            token_hash=token_hash,
            purpose=purpose,
            expires_at=expires_at,
        )
        self._session.add(token)
        return token

    async def lock_by_token_hash(self, token_hash: bytes) -> AuthActionToken | None:
        found: AuthActionToken | None = await self._session.scalar(
            select(AuthActionToken)
            .where(AuthActionToken.token_hash == token_hash)
            .with_for_update()
        )
        return found

    def mark_consumed(self, token: AuthActionToken, *, now: datetime) -> None:
        token.consumed_at = now

    async def flush(self) -> None:
        await self._session.flush()
