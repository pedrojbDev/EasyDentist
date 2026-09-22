from __future__ import annotations

import copy
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.anamnesis.models import Anamnesis
from app.anamnesis.repositories import AnamnesisRepository
from app.anamnesis.schemas import (
    AnamnesisCompletePayload,
    AnamnesisCreateRequest,
    AnamnesisListParams,
    AnamnesisStatus,
    AnamnesisUpdateRequest,
    merge_payload,
    payload_updates,
)
from app.clinics.audit import ClinicAuditService
from app.core.clock import utcnow
from app.core.context import TenantContext, UserContext
from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    translate_integrity_error,
)
from app.core.tenancy import tenant_transaction
from app.patients.repositories.patient_repository import PatientRepository
from app.users.repositories.professional_profile_repository import (
    ProfessionalProfileRepository,
)


@dataclass(frozen=True, slots=True)
class AnamnesisPage:
    items: Sequence[Anamnesis]
    total: int


class AnamnesisService:
    """Orchestrates the versioned anamnesis lifecycle of one patient."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def list_anamneses(
        self, context: TenantContext, patient_id: UUID, params: AnamnesisListParams
    ) -> AnamnesisPage:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._require_patient(session, context, patient_id)
            items, total = await AnamnesisRepository(session).list(
                context,
                patient_id,
                status=params.status,
                limit=params.limit,
                offset=params.offset,
            )
        return AnamnesisPage(items=items, total=total)

    async def get_anamnesis(
        self, context: TenantContext, patient_id: UUID, anamnesis_id: UUID
    ) -> Anamnesis:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._require_patient(session, context, patient_id)
            anamnesis = await AnamnesisRepository(session).get(context, patient_id, anamnesis_id)
        if anamnesis is None:
            raise NotFoundError("anamnesis not found")
        return anamnesis

    async def create_draft(
        self,
        context: TenantContext,
        patient_id: UUID,
        request: AnamnesisCreateRequest,
    ) -> Anamnesis:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._require_patient(session, context, patient_id)
            repository = AnamnesisRepository(session)
            payload: dict[str, object] = {}
            if request.base_version_id is not None:
                base = await repository.get_final(context, patient_id, request.base_version_id)
                if base is None:
                    raise NotFoundError("base version not found")
                payload = copy.deepcopy(base.payload)
            try:
                anamnesis = await repository.add_draft(
                    context,
                    patient_id,
                    payload=payload,
                    base_version_id=request.base_version_id,
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            await ClinicAuditService(session).record(
                "anamnesis.created",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="anamnesis",
                entity_id=anamnesis.id,
                metadata={"patient_id": str(patient_id), "status": anamnesis.status},
            )
        return anamnesis

    async def update_draft(
        self,
        context: TenantContext,
        patient_id: UUID,
        anamnesis_id: UUID,
        request: AnamnesisUpdateRequest,
    ) -> Anamnesis:
        async with tenant_transaction(self._session_factory, context) as session:
            repository = AnamnesisRepository(session)
            anamnesis = await repository.get(context, patient_id, anamnesis_id)
            if anamnesis is None:
                raise NotFoundError("anamnesis not found")
            if anamnesis.status != AnamnesisStatus.DRAFT.value:
                raise ConflictError("final anamnesis versions cannot be changed")
            updates = payload_updates(request.payload)
            merged = merge_payload(anamnesis.payload, updates)
            updated = await repository.update_draft(
                context,
                patient_id,
                anamnesis_id,
                payload=merged,
                updated_at=self._clock(),
            )
            if updated is None:
                raise ConflictError("final anamnesis versions cannot be changed")
            await ClinicAuditService(session).record(
                "anamnesis.updated",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="anamnesis",
                entity_id=updated.id,
                metadata={"patient_id": str(patient_id), "status": updated.status},
            )
        return updated

    async def finalize_anamnesis(
        self, context: TenantContext, patient_id: UUID, anamnesis_id: UUID
    ) -> Anamnesis:
        async with tenant_transaction(self._session_factory, context) as session:
            patient = await PatientRepository(session).lock(context, patient_id)
            if patient is None:
                raise NotFoundError("patient not found")
            repository = AnamnesisRepository(session)
            anamnesis = await repository.get(context, patient_id, anamnesis_id)
            if anamnesis is None:
                raise NotFoundError("anamnesis not found")
            if anamnesis.status != AnamnesisStatus.DRAFT.value:
                raise ConflictError("anamnesis is already final")

            profile = await ProfessionalProfileRepository(session).get(
                UserContext(user_id=context.user_id)
            )
            if profile is None:
                raise ConflictError("a professional profile is required to finalize")

            try:
                AnamnesisCompletePayload.model_validate(anamnesis.payload)
            except ValidationError as error:
                raise InvalidInputError("anamnesis payload is incomplete") from error

            version_number = await repository.next_version_number(context, patient_id)
            now = self._clock()
            try:
                updated = await repository.finalize(
                    context,
                    patient_id,
                    anamnesis_id,
                    version_number=version_number,
                    professional_name=profile.professional_name,
                    cro_number=profile.cro_number,
                    cro_state=profile.cro_state,
                    finalized_at=now,
                    updated_at=now,
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            if updated is None:
                raise ConflictError("anamnesis is already final")
            await ClinicAuditService(session).record(
                "anamnesis.finalized",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="anamnesis",
                entity_id=updated.id,
                metadata={
                    "patient_id": str(patient_id),
                    "status": updated.status,
                    "version_number": updated.version_number,
                },
            )
        return updated

    async def _require_patient(
        self, session: AsyncSession, context: TenantContext, patient_id: UUID
    ) -> None:
        patient = await PatientRepository(session).get(context, patient_id)
        if patient is None:
            raise NotFoundError("patient not found")
