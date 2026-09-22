from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PatientDocument(Base):
    __tablename__ = "patient_documents"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
        ),
        CheckConstraint("category IN ('ADMINISTRATIVE', 'CLINICAL')", name="category"),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archived_at",
        ),
        CheckConstraint("size_bytes > 0", name="size_bytes"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    category: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(Text)
    detected_mime: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.users.id")
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
