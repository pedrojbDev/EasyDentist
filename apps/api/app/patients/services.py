from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clinics.audit import ClinicAuditService
from app.core.clock import utcnow
from app.core.context import TenantContext
from app.core.errors import ConflictError, NotFoundError, translate_integrity_error
from app.core.tenancy import tenant_transaction
from app.patients.models import Patient, PatientAlert
from app.patients.repositories.patient_alert_repository import PatientAlertRepository
from app.patients.repositories.patient_repository import PatientRepository
from app.patients.rules import validate_patient_rules
from app.patients.schemas import (
    PatientAlertCreateRequest,
    PatientAlertListParams,
    PatientAlertStatus,
    PatientAlertUpdateRequest,
    PatientCreateRequest,
    PatientListParams,
    PatientStatus,
    PatientUpdateRequest,
)

_RULE_FIELDS = (
    "guardian_name",
    "guardian_relationship",
    "guardian_phone",
    "emergency_contact_name",
    "emergency_contact_relationship",
    "emergency_contact_phone",
)


@dataclass(frozen=True, slots=True)
class PatientPage:
    items: Sequence[Patient]
    total: int


@dataclass(frozen=True, slots=True)
class PatientAlertPage:
    items: Sequence[PatientAlert]
    total: int


class PatientService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        today: Callable[[], date] = date.today,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._today = today
        self._clock = clock

    async def list_patients(self, context: TenantContext, params: PatientListParams) -> PatientPage:
        async with tenant_transaction(self._session_factory, context) as session:
            items, total = await PatientRepository(session).list(
                context,
                status=params.status,
                search=params.search,
                limit=params.limit,
                offset=params.offset,
            )
        return PatientPage(items=items, total=total)

    async def get_patient(self, context: TenantContext, patient_id: UUID) -> Patient:
        async with tenant_transaction(self._session_factory, context) as session:
            patient = await PatientRepository(session).get(context, patient_id)
        if patient is None:
            raise NotFoundError("patient not found")
        return patient

    async def create_patient(
        self, context: TenantContext, payload: PatientCreateRequest
    ) -> Patient:
        values = payload.model_dump()
        self._validate_rules(values)
        async with tenant_transaction(self._session_factory, context) as session:
            repository = PatientRepository(session)
            cpf = values.get("cpf")
            if cpf is not None and await repository.find_by_cpf(context, str(cpf)) is not None:
                raise ConflictError("cpf already registered in this clinic")
            try:
                patient = await repository.add(context, **values)
                await ClinicAuditService(session).record(
                    "patient.created",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="patient",
                    entity_id=patient.id,
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
        return patient

    async def update_patient(
        self, context: TenantContext, patient_id: UUID, payload: PatientUpdateRequest
    ) -> Patient:
        updates = payload.model_dump(exclude_unset=True)
        async with tenant_transaction(self._session_factory, context) as session:
            repository = PatientRepository(session)
            patient = await repository.get(context, patient_id)
            if patient is None:
                raise NotFoundError("patient not found")
            self._validate_rules(self._merged_values(patient, updates))
            cpf = updates.get("cpf")
            if cpf is not None:
                existing = await repository.find_by_cpf(context, str(cpf))
                if existing is not None and existing.id != patient.id:
                    raise ConflictError("cpf already registered in this clinic")
            if not updates:
                return patient
            updates["updated_at"] = self._clock()
            try:
                updated = await repository.update(context, patient_id, **updates)
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            if updated is None:
                raise NotFoundError("patient not found")
            await ClinicAuditService(session).record(
                "patient.updated",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="patient",
                entity_id=updated.id,
            )
        return updated

    async def archive_patient(self, context: TenantContext, patient_id: UUID) -> Patient:
        return await self._set_archived(context, patient_id, archived=True)

    async def restore_patient(self, context: TenantContext, patient_id: UUID) -> Patient:
        return await self._set_archived(context, patient_id, archived=False)

    async def list_alerts(
        self,
        context: TenantContext,
        patient_id: UUID,
        params: PatientAlertListParams,
    ) -> PatientAlertPage:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._require_patient(session, context, patient_id)
            items, total = await PatientAlertRepository(session).list(
                context,
                patient_id,
                status=params.status,
                limit=params.limit,
                offset=params.offset,
            )
        return PatientAlertPage(items=items, total=total)

    async def create_alert(
        self,
        context: TenantContext,
        patient_id: UUID,
        payload: PatientAlertCreateRequest,
    ) -> PatientAlert:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._require_patient(session, context, patient_id)
            repository = PatientAlertRepository(session)
            try:
                alert = await repository.add(
                    context,
                    patient_id,
                    kind=payload.kind.value,
                    description=payload.description,
                    created_by_user_id=context.user_id,
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            await ClinicAuditService(session).record(
                "patient_alert.created",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="patient_alert",
                entity_id=alert.id,
                metadata={"patient_id": str(patient_id), "kind": alert.kind},
            )
        return alert

    async def update_alert(
        self,
        context: TenantContext,
        patient_id: UUID,
        alert_id: UUID,
        payload: PatientAlertUpdateRequest,
    ) -> PatientAlert:
        updates = payload.model_dump(exclude_unset=True)
        async with tenant_transaction(self._session_factory, context) as session:
            repository = PatientAlertRepository(session)
            alert = await repository.get(context, patient_id, alert_id)
            if alert is None:
                raise NotFoundError("patient alert not found")
            if not updates:
                return alert
            now = self._clock()
            values: dict[str, object] = {"updated_at": now}
            if "description" in updates:
                values["description"] = updates["description"]
            status = updates.get("status")
            if status is not None:
                resolved = status == PatientAlertStatus.RESOLVED
                values["status"] = PatientAlertStatus(status).value
                values["resolved_at"] = now if resolved else None
            updated = await repository.update(context, patient_id, alert_id, **values)
            if updated is None:
                raise NotFoundError("patient alert not found")
            await ClinicAuditService(session).record(
                "patient_alert.updated",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="patient_alert",
                entity_id=updated.id,
                metadata={"patient_id": str(patient_id), "status": updated.status},
            )
        return updated

    async def _set_archived(
        self, context: TenantContext, patient_id: UUID, *, archived: bool
    ) -> Patient:
        target = PatientStatus.ARCHIVED if archived else PatientStatus.ACTIVE
        async with tenant_transaction(self._session_factory, context) as session:
            repository = PatientRepository(session)
            patient = await repository.get(context, patient_id)
            if patient is None:
                raise NotFoundError("patient not found")
            if patient.status == target.value:
                return patient
            now = self._clock()
            updated = await repository.update(
                context,
                patient_id,
                status=target.value,
                archived_at=now if archived else None,
                updated_at=now,
            )
            if updated is None:
                raise NotFoundError("patient not found")
            event_type = "patient.archived" if archived else "patient.restored"
            await ClinicAuditService(session).record(
                event_type,
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="patient",
                entity_id=updated.id,
                metadata={"status": updated.status},
            )
        return updated

    async def _require_patient(
        self, session: AsyncSession, context: TenantContext, patient_id: UUID
    ) -> Patient:
        patient = await PatientRepository(session).get(context, patient_id)
        if patient is None:
            raise NotFoundError("patient not found")
        return patient

    def _validate_rules(self, values: Mapping[str, object]) -> None:
        birth_date = values.get("birth_date")
        if not isinstance(birth_date, date):
            return
        validate_patient_rules(
            birth_date=birth_date,
            guardian_name=self._optional(values.get("guardian_name")),
            guardian_relationship=self._optional(values.get("guardian_relationship")),
            guardian_phone=self._optional(values.get("guardian_phone")),
            emergency_contact_name=self._optional(values.get("emergency_contact_name")),
            emergency_contact_relationship=self._optional(
                values.get("emergency_contact_relationship")
            ),
            emergency_contact_phone=self._optional(values.get("emergency_contact_phone")),
            today=self._today(),
        )

    @staticmethod
    def _merged_values(patient: Patient, updates: Mapping[str, object]) -> dict[str, object]:
        values: dict[str, object] = {
            "birth_date": updates["birth_date"] if "birth_date" in updates else patient.birth_date,
        }
        for field in _RULE_FIELDS:
            values[field] = updates[field] if field in updates else getattr(patient, field)
        return values

    @staticmethod
    def _optional(value: object) -> str | None:
        return value if isinstance(value, str) else None
