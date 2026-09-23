from __future__ import annotations

import uuid
from datetime import datetime, time

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
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AgendaProfessional(Base):
    """A clinic-local agenda resource, independent from a user profile."""

    __tablename__ = "agenda_professionals"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        UniqueConstraint(
            "clinic_id", "membership_id", name="uq_agenda_professionals_clinic_membership"
        ),
        ForeignKeyConstraint(
            ["clinic_id", "membership_id"], ["app.memberships.clinic_id", "app.memberships.id"]
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archived_at",
        ),
        CheckConstraint(
            "(cro_number IS NULL AND cro_state IS NULL) "
            "OR (cro_number IS NOT NULL AND cro_state IS NOT NULL)",
            name="cro",
        ),
        Index("ix_agenda_professionals_clinic_id_status_name", "clinic_id", "status", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.clinics.id"))
    membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    cro_number: Mapped[str | None] = mapped_column(Text)
    cro_state: Mapped[str | None] = mapped_column(CHAR(2))
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AgendaRoom(Base):
    """A clinic-local chair or room that may be archived but never deleted."""

    __tablename__ = "agenda_rooms"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name="archived_at",
        ),
        UniqueConstraint("clinic_id", "name", name="uq_agenda_rooms_clinic_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.clinics.id"))
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProfessionalAvailability(Base):
    """One local weekly interval; multiple rows allow a lunch break."""

    __tablename__ = "professional_availabilities"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "professional_id"],
            ["app.agenda_professionals.clinic_id", "app.agenda_professionals.id"],
        ),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("starts_at < ends_at", name="time_range"),
        Index(
            "ix_prof_avail_clinic_prof_weekday_start",
            "clinic_id",
            "professional_id",
            "weekday",
            "starts_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    professional_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    weekday: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[time] = mapped_column()
    ends_at: Mapped[time] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=text("true"))


class ScheduleEvent(Base):
    """Shared internal occupancy record for appointments and calendar blocks."""

    __tablename__ = "schedule_events"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        ForeignKeyConstraint(
            ["clinic_id", "professional_id"],
            ["app.agenda_professionals.clinic_id", "app.agenda_professionals.id"],
        ),
        ForeignKeyConstraint(
            ["clinic_id", "patient_id"], ["app.patients.clinic_id", "app.patients.id"]
        ),
        ForeignKeyConstraint(
            ["clinic_id", "room_id"], ["app.agenda_rooms.clinic_id", "app.agenda_rooms.id"]
        ),
        CheckConstraint("event_type IN ('APPOINTMENT', 'BLOCK')", name="event_type"),
        CheckConstraint("occupancy_state IN ('OCCUPYING', 'RELEASED')", name="occupancy_state"),
        CheckConstraint("starts_at < ends_at", name="time_range"),
        CheckConstraint(
            "(event_type = 'APPOINTMENT' AND professional_id IS NOT NULL "
            "AND patient_id IS NOT NULL) "
            "OR (event_type = 'BLOCK' AND patient_id IS NULL "
            "AND (professional_id IS NOT NULL OR room_id IS NOT NULL))",
            name="resource_shape",
        ),
        ExcludeConstraint(
            ("clinic_id", "="),
            ("professional_id", "="),
            (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_professional_occupancy",
            using="gist",
            where=text("professional_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),  # type: ignore[no-untyped-call]  # sqlalchemy-stubs has no ExcludeConstraint stub
        ExcludeConstraint(
            ("clinic_id", "="),
            ("patient_id", "="),
            (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_patient_occupancy",
            using="gist",
            where=text("patient_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),  # type: ignore[no-untyped-call]  # sqlalchemy-stubs has no ExcludeConstraint stub
        ExcludeConstraint(
            ("clinic_id", "="),
            ("room_id", "="),
            (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_room_occupancy",
            using="gist",
            where=text("room_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),  # type: ignore[no-untyped-call]  # sqlalchemy-stubs has no ExcludeConstraint stub
        Index("ix_schedule_events_clinic_id_starts_at", "clinic_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    event_type: Mapped[str] = mapped_column(Text)
    professional_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    patient_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occupancy_state: Mapped[str] = mapped_column(Text, server_default=text("'OCCUPYING'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScheduleBlock(Base):
    """Public block record backed by a shared schedule event for occupancy."""

    __tablename__ = "schedule_blocks"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        UniqueConstraint("clinic_id", "schedule_event_id", name="uq_schedule_blocks_event"),
        ForeignKeyConstraint(
            ["clinic_id", "schedule_event_id"],
            ["app.schedule_events.clinic_id", "app.schedule_events.id"],
        ),
        CheckConstraint("status IN ('ACTIVE', 'CANCELLED')", name="status"),
        CheckConstraint(
            "(status = 'ACTIVE' AND cancelled_at IS NULL) "
            "OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL)",
            name="cancelled_at",
        ),
        Index("ix_schedule_blocks_clinic_id_status", "clinic_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    schedule_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    label: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default=text("'ACTIVE'"))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        UniqueConstraint("clinic_id", "id"),
        UniqueConstraint("clinic_id", "schedule_event_id", name="uq_appointments_schedule_event"),
        ForeignKeyConstraint(
            ["clinic_id", "schedule_event_id"],
            ["app.schedule_events.clinic_id", "app.schedule_events.id"],
        ),
        CheckConstraint(
            "status IN ('SCHEDULED', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', "
            "'COMPLETED', 'CANCELLED', 'NO_SHOW')",
            name="status",
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_appointments_clinic_id_status", "clinic_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    schedule_event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(Text, server_default=text("'SCHEDULED'"))
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    administrative_note: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AppointmentHistory(Base):
    __tablename__ = "appointment_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["clinic_id", "appointment_id"], ["app.appointments.clinic_id", "app.appointments.id"]
        ),
        UniqueConstraint("clinic_id", "appointment_id", "appointment_version"),
        CheckConstraint(
            "event_type IN ('CREATED', 'RESCHEDULED', 'STATUS_CHANGED')", name="event_type"
        ),
        CheckConstraint("appointment_version >= 1", name="appointment_version"),
        Index(
            "ix_appointment_history_clinic_id_appointment_id_occurred_at",
            "clinic_id",
            "appointment_id",
            "occurred_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    appointment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    appointment_version: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("app.users.id"))
    old_values: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'"))
    new_values: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
