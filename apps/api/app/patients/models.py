from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archived_at",
        ),
        CheckConstraint("birth_date <= CURRENT_DATE", name="birth_date_not_future"),
        CheckConstraint(
            "(emergency_contact_name IS NULL AND emergency_contact_relationship IS NULL "
            "AND emergency_contact_phone IS NULL) "
            "OR (emergency_contact_name IS NOT NULL AND emergency_contact_phone IS NOT NULL)",
            name="emergency_contact",
        ),
        Index(
            "ix_patients_clinic_id_cpf",
            "clinic_id",
            "cpf",
            unique=True,
            postgresql_where=text("cpf IS NOT NULL"),
        ),
        Index("ix_patients_clinic_id_status_full_name", "clinic_id", "status", "full_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.clinics.id"))
    full_name: Mapped[str] = mapped_column(Text)
    social_name: Mapped[str | None] = mapped_column(Text)
    birth_date: Mapped[date] = mapped_column(Date)
    cpf: Mapped[str | None] = mapped_column(CHAR(11))
    phone: Mapped[str] = mapped_column(Text)
    phone_secondary: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    street: Mapped[str | None] = mapped_column(Text)
    number: Mapped[str | None] = mapped_column(Text)
    complement: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(CHAR(2))
    occupation: Mapped[str | None] = mapped_column(Text)
    nationality: Mapped[str | None] = mapped_column(Text)
    birthplace: Mapped[str | None] = mapped_column(Text)
    emergency_contact_name: Mapped[str | None] = mapped_column(Text)
    emergency_contact_relationship: Mapped[str | None] = mapped_column(Text)
    emergency_contact_phone: Mapped[str | None] = mapped_column(Text)
    guardian_name: Mapped[str | None] = mapped_column(Text)
    guardian_relationship: Mapped[str | None] = mapped_column(Text)
    guardian_phone: Mapped[str | None] = mapped_column(Text)
    administrative_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientAlert(Base):
    __tablename__ = "patient_alerts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
        ),
        CheckConstraint("kind IN ('ALLERGY', 'MEDICATION', 'CLINICAL_RISK', 'OTHER')", name="kind"),
        CheckConstraint("status IN ('ACTIVE', 'RESOLVED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND resolved_at IS NULL) "
            "OR (status = 'RESOLVED' AND resolved_at IS NOT NULL)",
            name="resolved_at",
        ),
        Index(
            "ix_patient_alerts_clinic_id_patient_id_created_at",
            "clinic_id",
            "patient_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    patient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
