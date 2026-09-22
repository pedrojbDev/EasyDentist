from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches
from app.patients.models import PatientAlert
from app.patients.schemas import PatientAlertStatus


class PatientAlertRepository:
    """Every method is scoped by clinic and patient; no unscoped entry point."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _filters(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        status: PatientAlertStatus | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            PatientAlert.clinic_id == context.clinic_id,
            PatientAlert.patient_id == patient_id,
        ]
        if status is not None:
            filters.append(PatientAlert.status == status)
        return filters

    async def list(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        status: PatientAlertStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[PatientAlert], int]:
        ensure_context_matches(self._session, context)
        filters = self._filters(context, patient_id, status=status)
        statement = (
            select(PatientAlert)
            .where(*filters)
            .order_by(PatientAlert.created_at.desc(), PatientAlert.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(PatientAlert).where(*filters)
        )
        return rows, int(total or 0)

    async def get(
        self, context: TenantContext, patient_id: UUID, alert_id: UUID
    ) -> PatientAlert | None:
        ensure_context_matches(self._session, context)
        alert = await self._session.scalar(
            select(PatientAlert).where(
                PatientAlert.id == alert_id,
                PatientAlert.clinic_id == context.clinic_id,
                PatientAlert.patient_id == patient_id,
            )
        )
        return alert

    async def add(self, context: TenantContext, patient_id: UUID, **fields: object) -> PatientAlert:
        ensure_context_matches(self._session, context)
        alert = PatientAlert(
            clinic_id=context.clinic_id,
            patient_id=patient_id,
            **fields,
        )
        self._session.add(alert)
        await self._session.flush()
        return alert

    async def update(
        self,
        context: TenantContext,
        patient_id: UUID,
        alert_id: UUID,
        **fields: object,
    ) -> PatientAlert | None:
        ensure_context_matches(self._session, context)
        if not fields:
            return await self.get(context, patient_id, alert_id)
        statement = (
            update(PatientAlert)
            .where(
                PatientAlert.id == alert_id,
                PatientAlert.clinic_id == context.clinic_id,
                PatientAlert.patient_id == patient_id,
            )
            .values(**fields)
            .returning(PatientAlert)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
