from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_email(self, email: str) -> User | None:
        user: User | None = await self._session.scalar(select(User).where(User.email == email))
        return user

    async def get(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    def set_email_verified(self, user: User, *, now: datetime) -> None:
        user.email_verified_at = now
        user.updated_at = now

    async def flush(self) -> None:
        await self._session.flush()
