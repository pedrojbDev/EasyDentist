from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import PasswordCredential


class PasswordCredentialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> PasswordCredential | None:
        return await self._session.get(PasswordCredential, user_id)

    async def upsert(
        self, *, user_id: UUID, password_hash: str, changed_at: datetime
    ) -> PasswordCredential:
        credential = await self.get(user_id)
        if credential is None:
            credential = PasswordCredential(
                user_id=user_id,
                password_hash=password_hash,
                changed_at=changed_at,
            )
            self._session.add(credential)
        else:
            credential.password_hash = password_hash
            credential.changed_at = changed_at
        return credential

    async def flush(self) -> None:
        await self._session.flush()
