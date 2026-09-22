from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Anamnesis(Base):
    __tablename__ = "anamneses"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id", name="uq_anamneses_clinic_id"),
        UniqueConstraint("clinic_id", "patient_id", "id", name="uq_anamneses_clinic_id_patient_id"),
        UniqueConstraint(
            "clinic_id", "patient_id", "version_number", name="uq_anamneses_patient_version"
        ),
        CheckConstraint("status IN ('DRAFT', 'FINAL')", name="status"),
        CheckConstraint(
            "(status = 'DRAFT' AND version_number IS NULL) "
            "OR (status = 'FINAL' AND version_number IS NOT NULL)",
            name="version_number",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND finalized_at IS NULL) "
            "OR (status = 'FINAL' AND finalized_at IS NOT NULL)",
            name="finalized_at",
        ),
        CheckConstraint(
            "(status = 'DRAFT' AND author_professional_name IS NULL "
            "AND author_cro_number IS NULL AND author_cro_state IS NULL) "
            "OR (status = 'FINAL' AND author_professional_name IS NOT NULL "
            "AND author_cro_number IS NOT NULL AND author_cro_state IS NOT NULL)",
            name="author_snapshot",
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id", "base_version_id"],
            ["app.anamneses.clinic_id", "app.anamneses.patient_id", "app.anamneses.id"],
        ),
        Index(
            "uq_anamneses_draft_per_patient",
            "clinic_id",
            "patient_id",
            unique=True,
            postgresql_where=text("status = 'DRAFT'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, server_default=text("'DRAFT'"))
    version_number: Mapped[int | None] = mapped_column(Integer)
    template: Mapped[str] = mapped_column(Text, server_default=text("'cfo_2026_v1'"))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'"))
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    author_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.users.id")
    )
    author_professional_name: Mapped[str | None] = mapped_column(Text)
    author_cro_number: Mapped[str | None] = mapped_column(Text)
    author_cro_state: Mapped[str | None] = mapped_column(CHAR(2))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
