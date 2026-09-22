from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches
from app.documents.models import PatientDocument
from app.documents.schemas import DocumentStatus


class DocumentRepository:
    """Every method is clinic-scoped; there is no unscoped entry point."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _filters(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        categories: frozenset[str],
        status: DocumentStatus | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            PatientDocument.clinic_id == context.clinic_id,
            PatientDocument.patient_id == patient_id,
            PatientDocument.category.in_(sorted(categories)),
        ]
        if status is not None:
            filters.append(PatientDocument.status == status.value)
        return filters

    async def list(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        categories: frozenset[str],
        status: DocumentStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[PatientDocument], int]:
        ensure_context_matches(self._session, context)
        filters = self._filters(context, patient_id, categories=categories, status=status)
        statement: Select[tuple[PatientDocument]] = (
            select(PatientDocument)
            .where(*filters)
            .order_by(PatientDocument.created_at.desc(), PatientDocument.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(PatientDocument).where(*filters)
        )
        return rows, int(total or 0)

    async def get(
        self, context: TenantContext, patient_id: UUID, document_id: UUID
    ) -> PatientDocument | None:
        ensure_context_matches(self._session, context)
        document: PatientDocument | None = await self._session.scalar(
            select(PatientDocument).where(
                PatientDocument.id == document_id,
                PatientDocument.clinic_id == context.clinic_id,
                PatientDocument.patient_id == patient_id,
            )
        )
        return document

    async def add(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        category: str,
        title: str,
        original_filename: str,
        detected_mime: str,
        size_bytes: int,
        sha256: str,
        storage_key: str,
        uploaded_by_user_id: UUID,
    ) -> PatientDocument:
        ensure_context_matches(self._session, context)
        document = PatientDocument(
            clinic_id=context.clinic_id,
            patient_id=patient_id,
            category=category,
            title=title,
            original_filename=original_filename,
            detected_mime=detected_mime,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_key=storage_key,
            uploaded_by_user_id=uploaded_by_user_id,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def update_status(
        self,
        context: TenantContext,
        patient_id: UUID,
        document_id: UUID,
        *,
        status: str,
        archived_at: datetime | None,
        updated_at: datetime,
    ) -> PatientDocument | None:
        ensure_context_matches(self._session, context)
        statement = (
            update(PatientDocument)
            .where(
                PatientDocument.id == document_id,
                PatientDocument.clinic_id == context.clinic_id,
                PatientDocument.patient_id == patient_id,
            )
            .values(status=status, archived_at=archived_at, updated_at=updated_at)
            .returning(PatientDocument)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
