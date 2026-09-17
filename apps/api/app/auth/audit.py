from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthAuditEvent


class AuthAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        event_type: str,
        *,
        user_id: UUID | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            AuthAuditEvent(
                event_type=event_type,
                user_id=user_id,
                event_metadata=metadata if metadata is not None else {},
            )
        )
        await self._session.flush()
