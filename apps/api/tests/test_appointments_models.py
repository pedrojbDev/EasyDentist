from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.schema import AddConstraint

from app import models as registered_models
from app.appointments.models import (
    AgendaProfessional,
    AgendaRoom,
    Appointment,
    AppointmentHistory,
    ProfessionalAvailability,
    ScheduleEvent,
)
from app.core.database import Base


def _check_expressions(model: type) -> set[str]:
    return {
        str(constraint.sqltext)
        for constraint in model.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }


def _foreign_key_targets(model: type) -> set[str]:
    return {foreign_key.target_fullname for foreign_key in model.__table__.foreign_keys}


def _composite_foreign_key_columns(model: type) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in model.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def test_appointment_models_are_registered_in_the_shared_metadata() -> None:
    # This catches a missing app.models import, which otherwise makes Alembic and
    # mapper foreign-key resolution silently incomplete.
    assert registered_models is not None
    assert {
        "agenda_professionals",
        "agenda_rooms",
        "professional_availabilities",
        "schedule_events",
        "appointments",
        "appointment_history",
    } <= {table.name for table in Base.metadata.tables.values()}


def test_agenda_resources_are_clinic_scoped_without_reusing_global_profiles() -> None:
    # This catches an accidental FK to professional_profiles, which would make
    # account ownership a prerequisite for a clinic agenda professional.
    assert AgendaProfessional.__table__.schema == "app"
    assert AgendaRoom.__table__.schema == "app"
    assert _foreign_key_targets(AgendaProfessional) == {
        "app.clinics.id",
        "app.memberships.clinic_id",
        "app.memberships.id",
    }
    assert _foreign_key_targets(AgendaRoom) == {"app.clinics.id"}
    assert "user_id" not in AgendaProfessional.__table__.c
    assert "cro_number" in AgendaProfessional.__table__.c
    assert "cro_state" in AgendaProfessional.__table__.c
    assert AgendaProfessional.__table__.c.membership_id.nullable is True
    assert ("clinic_id", "membership_id") in _composite_foreign_key_columns(AgendaProfessional)
    professional_uniques = [
        [column.name for column in constraint.columns]
        for constraint in AgendaProfessional.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert ["clinic_id", "membership_id"] in professional_uniques
    assert "status IN ('ACTIVE', 'ARCHIVED')" in _check_expressions(AgendaProfessional)
    assert "status IN ('ACTIVE', 'ARCHIVED')" in _check_expressions(AgendaRoom)


def test_availability_and_schedule_events_cannot_cross_clinic_boundaries() -> None:
    # This catches replacing the composite tenant FKs with independent UUID FKs.
    assert ("clinic_id", "professional_id") in _composite_foreign_key_columns(
        ProfessionalAvailability
    )
    assert ("clinic_id", "professional_id") in _composite_foreign_key_columns(ScheduleEvent)
    assert ("clinic_id", "patient_id") in _composite_foreign_key_columns(ScheduleEvent)
    assert ("clinic_id", "room_id") in _composite_foreign_key_columns(ScheduleEvent)
    checks = _check_expressions(ProfessionalAvailability)
    assert "weekday BETWEEN 0 AND 6" in checks
    assert "starts_at < ends_at" in checks


def test_schedule_event_occupancy_uses_half_open_exclusion_constraints() -> None:
    # This catches a normal unique index or closed range, both of which allow
    # overlapping booking races or reject legal adjacent appointments.
    exclusions = [
        constraint
        for constraint in ScheduleEvent.__table__.constraints
        if isinstance(constraint, ExcludeConstraint)
    ]

    assert {constraint.name for constraint in exclusions} == {
        "ex_schedule_events_professional_occupancy",
        "ex_schedule_events_patient_occupancy",
        "ex_schedule_events_room_occupancy",
    }
    for constraint in exclusions:
        compiled = str(AddConstraint(constraint).compile(dialect=postgresql.dialect()))
        assert "tstzrange" in compiled
        assert "'[)'" in compiled
        assert "occupancy_state = 'OCCUPYING'" in compiled


def test_appointments_are_versioned_and_history_is_structured() -> None:
    # This catches losing optimistic concurrency or storing history as free-form
    # text that cannot faithfully represent old/new state.
    assert Appointment.__table__.c.version.nullable is False
    assert str(Appointment.__table__.c.version.server_default.arg) == "1"
    assert "version >= 1" in _check_expressions(Appointment)
    assert ("clinic_id", "schedule_event_id") in _composite_foreign_key_columns(Appointment)
    assert isinstance(AppointmentHistory.__table__.c.old_values.type, JSONB)
    assert isinstance(AppointmentHistory.__table__.c.new_values.type, JSONB)
    assert "event_type IN ('CREATED', 'RESCHEDULED', 'STATUS_CHANGED')" in _check_expressions(
        AppointmentHistory
    )
    assert ("clinic_id", "appointment_id") in _composite_foreign_key_columns(AppointmentHistory)


def test_schedule_events_keep_appointment_and_block_states_separate() -> None:
    # This catches cancelled/no-show appointments still blocking a resource, or
    # completed appointments incorrectly releasing historical occupancy.
    checks = _check_expressions(ScheduleEvent)
    assert "event_type IN ('APPOINTMENT', 'BLOCK')" in checks
    assert "occupancy_state IN ('OCCUPYING', 'RELEASED')" in checks
    assert "starts_at < ends_at" in checks
    assert "event_type = 'APPOINTMENT'" in " ".join(checks)


def test_appointment_statuses_cover_the_agenda_lifecycle() -> None:
    # This catches a persistence layer that cannot represent a documented
    # lifecycle transition (including cancellation and no-show).
    assert (
        "status IN ('SCHEDULED', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', "
        "'COMPLETED', 'CANCELLED', 'NO_SHOW')"
    ) in _check_expressions(Appointment)


def test_history_has_a_single_event_per_appointment_version() -> None:
    # This catches a retry recording duplicate history for the same committed
    # optimistic-concurrency version.
    constraints = [
        constraint
        for constraint in AppointmentHistory.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert ["clinic_id", "appointment_id", "appointment_version"] in [
        [column.name for column in constraint.columns] for constraint in constraints
    ]
