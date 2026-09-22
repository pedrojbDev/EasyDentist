from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.clinics.models import ClinicAuditEvent

CLINIC_EVENT_METADATA_ALLOWLIST: dict[str, frozenset[str]] = {
    "patient.created": frozenset(),
    "patient.updated": frozenset(),
    "patient.archived": frozenset({"status"}),
    "patient.restored": frozenset({"status"}),
    "patient_alert.created": frozenset({"patient_id", "kind"}),
    "patient_alert.updated": frozenset({"patient_id", "status"}),
    "anamnesis.created": frozenset({"patient_id", "status"}),
    "anamnesis.updated": frozenset({"patient_id", "status"}),
    "anamnesis.finalized": frozenset({"patient_id", "status", "version_number"}),
}


def sanitize_clinic_event_metadata(
    event_type: str, metadata: Mapping[str, object] | None
) -> dict[str, object]:
    """Keep only the fields declared for the event; unknown keys are dropped.

    Clinical identifiers, CPF, names, alert descriptions and file data must
    never reach the audit trail, so metadata is allowlisted per event type.
    """

    if not metadata:
        return {}
    allowed = CLINIC_EVENT_METADATA_ALLOWLIST.get(event_type, frozenset())
    return {key: value for key, value in metadata.items() if key in allowed}


class ClinicAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        event_type: str,
        *,
        clinic_id: UUID,
        actor_user_id: UUID | None = None,
        entity_type: str | None = None,
        entity_id: UUID | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        self._session.add(
            ClinicAuditEvent(
                clinic_id=clinic_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                event_metadata=sanitize_clinic_event_metadata(event_type, metadata),
            )
        )
        await self._session.flush()
