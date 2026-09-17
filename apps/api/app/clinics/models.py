from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (
        CheckConstraint("status IN ('PROVISIONING', 'ACTIVE', 'SUSPENDED')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    slug: Mapped[str] = mapped_column(CITEXT, unique=True)
    legal_name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'PROVISIONING'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicSettings(Base):
    __tablename__ = "clinic_settings"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.clinics.id"), primary_key=True
    )
    display_name: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, server_default=text("'America/Bahia'"))
    locale: Mapped[str] = mapped_column(Text, server_default=text("'pt-BR'"))
    currency: Mapped[str] = mapped_column(CHAR(3), server_default=text("'BRL'"))
    preferences: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicFeatureFlag(Base):
    __tablename__ = "clinic_feature_flags"

    clinic_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.clinics.id"), primary_key=True
    )
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    config: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.users.id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "clinic_id"),
        UniqueConstraint("clinic_id", "id"),
        CheckConstraint(
            "role IN ('OWNER', 'ADMIN', 'DENTIST', 'ASSISTANT', 'RECEPTIONIST')", name="role"
        ),
        CheckConstraint("status IN ('PENDING', 'ACTIVE', 'SUSPENDED')", name="status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.clinics.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.users.id"))
    role: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'PENDING'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MembershipInvitation(Base):
    __tablename__ = "membership_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "membership_id"],
            ["app.memberships.clinic_id", "app.memberships.id"],
        ),
        UniqueConstraint("clinic_id", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    email: Mapped[str] = mapped_column(CITEXT)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicAuditEvent(Base):
    __tablename__ = "clinic_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.clinics.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("app.users.id")
    )
    event_type: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
