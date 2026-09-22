from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import AuthAuditEvent

EVENT_METADATA_ALLOWLIST: dict[str, frozenset[str]] = {
    "session_revoked": frozenset({"session_id"}),
}


def sanitize_event_metadata(
    event_type: str, metadata: Mapping[str, object] | None
) -> dict[str, object]:
    """Keeps only the fields declared for the event; unknown keys are dropped."""

    if not metadata:
        return {}
    allowed = EVENT_METADATA_ALLOWLIST.get(event_type, frozenset())
    return {key: value for key, value in metadata.items() if key in allowed}


class AuthAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        event_type: str,
        *,
        user_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self._session.add(
            AuthAuditEvent(
                event_type=event_type,
                user_id=user_id,
                event_metadata=sanitize_event_metadata(event_type, metadata),
            )
        )
        await self._session.flush()
