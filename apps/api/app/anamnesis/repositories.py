from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.anamnesis.models import Anamnesis
from app.anamnesis.schemas import AnamnesisStatus
from app.anamnesis.templates.cfo_2026_v1 import TEMPLATE_ID
from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches


class AnamnesisRepository:
    """Clinic-scoped persistence of anamnesis rows; no unscoped entry point."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _filters(
        self, context: TenantContext, patient_id: UUID, *, status: AnamnesisStatus | None
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            Anamnesis.clinic_id == context.clinic_id,
            Anamnesis.patient_id == patient_id,
        ]
        if status is not None:
            filters.append(Anamnesis.status == status.value)
        return filters

    async def list(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        status: AnamnesisStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[Anamnesis], int]:
        ensure_context_matches(self._session, context)
        filters = self._filters(context, patient_id, status=status)
        statement: Select[tuple[Anamnesis]] = (
            select(Anamnesis)
            .where(*filters)
            .order_by(Anamnesis.created_at.desc(), Anamnesis.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(Anamnesis).where(*filters)
        )
        return rows, int(total or 0)

    async def get(
        self, context: TenantContext, patient_id: UUID, anamnesis_id: UUID
    ) -> Anamnesis | None:
        ensure_context_matches(self._session, context)
        anamnesis: Anamnesis | None = await self._session.scalar(
            select(Anamnesis).where(
                Anamnesis.id == anamnesis_id,
                Anamnesis.clinic_id == context.clinic_id,
                Anamnesis.patient_id == patient_id,
            )
        )
        return anamnesis

    async def get_final(
        self, context: TenantContext, patient_id: UUID, anamnesis_id: UUID
    ) -> Anamnesis | None:
        ensure_context_matches(self._session, context)
        anamnesis: Anamnesis | None = await self._session.scalar(
            select(Anamnesis).where(
                Anamnesis.id == anamnesis_id,
                Anamnesis.clinic_id == context.clinic_id,
                Anamnesis.patient_id == patient_id,
                Anamnesis.status == AnamnesisStatus.FINAL.value,
            )
        )
        return anamnesis

    async def add_draft(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        payload: dict[str, object],
        base_version_id: UUID | None,
    ) -> Anamnesis:
        ensure_context_matches(self._session, context)
        anamnesis = Anamnesis(
            clinic_id=context.clinic_id,
            patient_id=patient_id,
            status=AnamnesisStatus.DRAFT.value,
            template=TEMPLATE_ID,
            payload=payload,
            base_version_id=base_version_id,
            author_user_id=context.user_id,
        )
        self._session.add(anamnesis)
        await self._session.flush()
        return anamnesis

    async def update_draft(
        self,
        context: TenantContext,
        patient_id: UUID,
        anamnesis_id: UUID,
        *,
        payload: dict[str, object],
        updated_at: datetime,
    ) -> Anamnesis | None:
        ensure_context_matches(self._session, context)
        statement = (
            update(Anamnesis)
            .where(
                Anamnesis.id == anamnesis_id,
                Anamnesis.clinic_id == context.clinic_id,
                Anamnesis.patient_id == patient_id,
                Anamnesis.status == AnamnesisStatus.DRAFT.value,
            )
            .values(payload=payload, updated_at=updated_at)
            .returning(Anamnesis)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def next_version_number(self, context: TenantContext, patient_id: UUID) -> int:
        ensure_context_matches(self._session, context)
        next_number = await self._session.scalar(
            select(func.coalesce(func.max(Anamnesis.version_number), 0) + 1).where(
                Anamnesis.clinic_id == context.clinic_id,
                Anamnesis.patient_id == patient_id,
            )
        )
        return int(next_number or 1)

    async def finalize(
        self,
        context: TenantContext,
        patient_id: UUID,
        anamnesis_id: UUID,
        *,
        version_number: int,
        professional_name: str,
        cro_number: str,
        cro_state: str,
        finalized_at: datetime,
        updated_at: datetime,
    ) -> Anamnesis | None:
        ensure_context_matches(self._session, context)
        statement = (
            update(Anamnesis)
            .where(
                Anamnesis.id == anamnesis_id,
                Anamnesis.clinic_id == context.clinic_id,
                Anamnesis.patient_id == patient_id,
                Anamnesis.status == AnamnesisStatus.DRAFT.value,
            )
            .values(
                status=AnamnesisStatus.FINAL.value,
                version_number=version_number,
                author_professional_name=professional_name,
                author_cro_number=cro_number,
                author_cro_state=cro_state,
                finalized_at=finalized_at,
                updated_at=updated_at,
            )
            .returning(Anamnesis)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
