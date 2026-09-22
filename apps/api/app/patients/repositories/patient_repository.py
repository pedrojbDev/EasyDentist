from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches
from app.patients.models import Patient
from app.patients.schemas import PatientStatus


def _contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class PatientRepository:
    """Every method is clinic-scoped; there is no unscoped entry point."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _filters(
        self,
        context: TenantContext,
        *,
        status: PatientStatus | None,
        search: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [Patient.clinic_id == context.clinic_id]
        if status is not None:
            filters.append(Patient.status == status)
        if search:
            pattern = _contains_pattern(search)
            digits = "".join(character for character in search if character.isdigit())
            matches: list[ColumnElement[bool]] = [
                Patient.full_name.ilike(pattern, escape="\\"),
                Patient.phone.ilike(pattern, escape="\\"),
                Patient.phone_secondary.ilike(pattern, escape="\\"),
                Patient.email.ilike(pattern, escape="\\"),
            ]
            if digits:
                matches.append(Patient.cpf.like(f"{digits}%"))
            filters.append(or_(*matches))
        return filters

    async def list(
        self,
        context: TenantContext,
        *,
        status: PatientStatus,
        search: str | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Patient], int]:
        ensure_context_matches(self._session, context)
        filters = self._filters(context, status=status, search=search)
        statement: Select[tuple[Patient]] = (
            select(Patient)
            .where(*filters)
            .order_by(Patient.full_name, Patient.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(Patient).where(*filters)
        )
        return rows, int(total or 0)

    async def get(self, context: TenantContext, patient_id: UUID) -> Patient | None:
        ensure_context_matches(self._session, context)
        patient = await self._session.scalar(
            select(Patient).where(
                Patient.id == patient_id,
                Patient.clinic_id == context.clinic_id,
            )
        )
        return patient

    async def lock(self, context: TenantContext, patient_id: UUID) -> Patient | None:
        """Lock the patient row as the serialization point for finalization.

        Callers must already be inside a tenant transaction; the row lock is
        held until commit and serializes concurrent finalizations per patient.
        """

        ensure_context_matches(self._session, context)
        patient = await self._session.scalar(
            select(Patient)
            .where(
                Patient.id == patient_id,
                Patient.clinic_id == context.clinic_id,
            )
            .with_for_update()
        )
        return patient

    async def find_by_cpf(self, context: TenantContext, cpf: str) -> Patient | None:
        ensure_context_matches(self._session, context)
        patient = await self._session.scalar(
            select(Patient).where(
                Patient.clinic_id == context.clinic_id,
                Patient.cpf == cpf,
            )
        )
        return patient

    async def add(self, context: TenantContext, **fields: object) -> Patient:
        ensure_context_matches(self._session, context)
        patient = Patient(clinic_id=context.clinic_id, **fields)
        self._session.add(patient)
        await self._session.flush()
        return patient

    async def update(
        self, context: TenantContext, patient_id: UUID, **fields: object
    ) -> Patient | None:
        ensure_context_matches(self._session, context)
        if not fields:
            return await self.get(context, patient_id)
        statement = (
            update(Patient)
            .where(
                Patient.id == patient_id,
                Patient.clinic_id == context.clinic_id,
            )
            .values(**fields)
            .returning(Patient)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
