from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.appointments.models import (
    AgendaProfessional,
    AgendaRoom,
    Appointment,
    AppointmentHistory,
    ProfessionalAvailability,
    ScheduleBlock,
    ScheduleEvent,
)
from app.appointments.schemas import (
    AgendaListParams,
    AppointmentCreateRequest,
    AppointmentHistoryListResponse,
    AppointmentHistoryResponse,
    AppointmentListResponse,
    AppointmentRescheduleRequest,
    AppointmentResponse,
    AppointmentStatus,
    AppointmentStatusRequest,
    AppointmentUpdateRequest,
    AvailabilityRequest,
    AvailabilityResponse,
    ScheduleBlockCancelRequest,
    ScheduleBlockCreateRequest,
    ScheduleBlockListParams,
    ScheduleBlockListResponse,
    ScheduleBlockResponse,
    ScheduleBlockUpdateRequest,
    WorkingHourInterval,
    WorkingHoursReplaceRequest,
    WorkingHoursResponse,
)
from app.clinics.audit import ClinicAuditService
from app.clinics.models import ClinicSettings, Membership
from app.clinics.rbac import Role
from app.core.clock import utcnow
from app.core.context import TenantContext
from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    translate_integrity_error,
)
from app.core.tenancy import ensure_context_matches, tenant_transaction
from app.patients.models import Patient

PENDING_STATUSES = frozenset(
    {
        AppointmentStatus.SCHEDULED.value,
        AppointmentStatus.CONFIRMED.value,
        AppointmentStatus.CHECKED_IN.value,
        AppointmentStatus.IN_PROGRESS.value,
    }
)
type AppointmentRow = tuple[
    Appointment, ScheduleEvent, Patient, AgendaProfessional, AgendaRoom | None
]


def _clinic_timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise InvalidInputError("clinic timezone is not available") from error


def _resolve_local(value: datetime, timezone: ZoneInfo) -> datetime:
    """Resolve a wall-clock value only when it maps to exactly one instant."""

    if value.tzinfo is not None and value.utcoffset() is not None:
        raise InvalidInputError("local date-time must not include a timezone offset")
    candidates: dict[datetime, datetime] = {}
    for fold in (0, 1):
        localized = value.replace(tzinfo=timezone, fold=fold)
        instant = localized.astimezone(UTC)
        round_trip = instant.astimezone(timezone)
        if round_trip.replace(tzinfo=None) == value and round_trip.fold == fold:
            candidates[instant] = localized
    if len(candidates) != 1:
        reason = "nonexistent" if not candidates else "ambiguous"
        raise InvalidInputError(f"local date-time is {reason} in the clinic timezone")
    return next(iter(candidates))


def _local_appointment_span(
    local_start: datetime, duration_minutes: int, timezone: ZoneInfo
) -> tuple[datetime, datetime]:
    if local_start.tzinfo is not None and local_start.utcoffset() is not None:
        raise InvalidInputError("local_start must not include a timezone offset")
    local_end = local_start + timedelta(minutes=duration_minutes)
    if local_end.date() != local_start.date():
        raise InvalidInputError("an appointment must start and end on the same local day")
    starts_at = _resolve_local(local_start, timezone)
    ends_at = _resolve_local(local_end, timezone)
    if starts_at >= ends_at:
        raise InvalidInputError("appointment end must follow its start")
    return starts_at, ends_at


def _local_day_boundary(value: date, timezone: ZoneInfo) -> datetime:
    """Return the first instant on or after local midnight for a clinic day.

    Some IANA zones change offset at midnight. In that case midnight can be
    nonexistent or ambiguous; using fold=0 yields the earliest valid boundary
    (or its forward round-trip when the wall time falls inside a gap).
    """

    local_midnight = datetime.combine(value, time.min)
    candidate = local_midnight.replace(tzinfo=timezone, fold=0).astimezone(UTC)
    round_trip = candidate.astimezone(timezone).replace(tzinfo=None)
    if round_trip >= local_midnight:
        return candidate
    for minute in range(1, 48 * 60 + 1):
        local_value = local_midnight + timedelta(minutes=minute)
        candidate = local_value.replace(tzinfo=timezone, fold=0).astimezone(UTC)
        round_trip = candidate.astimezone(timezone).replace(tzinfo=None)
        if round_trip >= local_value:
            return candidate
    raise InvalidInputError("local date has no usable boundary in the clinic timezone")


def _snapshot(appointment: Appointment, event: ScheduleEvent) -> dict[str, object]:
    return {
        "patient_id": str(event.patient_id) if event.patient_id else None,
        "professional_id": str(event.professional_id) if event.professional_id else None,
        "room_id": str(event.room_id) if event.room_id else None,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat(),
        "status": appointment.status,
    }


def _appointment_response(row: AppointmentRow) -> AppointmentResponse:
    appointment, event, patient, professional, room = row
    return AppointmentResponse(
        id=appointment.id,
        clinic_id=appointment.clinic_id,
        patient_id=patient.id,
        patient_name=patient.social_name or patient.full_name,
        professional_id=professional.id,
        professional_name=professional.name,
        room_id=room.id if room else None,
        room_name=room.name if room else None,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        status=AppointmentStatus(appointment.status),
        administrative_note=appointment.administrative_note,
        cancellation_reason=appointment.cancellation_reason,
        version=appointment.version,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
    )


class AgendaService:
    """Tenant-scoped agenda operations; clinic settings row serializes mutations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    @staticmethod
    async def _lock_agenda(session: AsyncSession, context: TenantContext) -> ClinicSettings:
        ensure_context_matches(session, context)
        settings = await session.scalar(
            select(ClinicSettings)
            .where(ClinicSettings.clinic_id == context.clinic_id)
            .with_for_update()
        )
        if settings is None:
            raise NotFoundError("clinic settings not found")
        return settings

    @staticmethod
    async def _settings(session: AsyncSession, context: TenantContext) -> ClinicSettings:
        ensure_context_matches(session, context)
        settings = await session.get(ClinicSettings, context.clinic_id)
        if settings is None:
            raise NotFoundError("clinic settings not found")
        return settings

    @staticmethod
    async def _own_professional_id(session: AsyncSession, context: TenantContext) -> UUID:
        ensure_context_matches(session, context)
        professional_id = await session.scalar(
            select(AgendaProfessional.id)
            .join(
                Membership,
                (Membership.clinic_id == AgendaProfessional.clinic_id)
                & (Membership.id == AgendaProfessional.membership_id),
            )
            .where(
                AgendaProfessional.clinic_id == context.clinic_id,
                AgendaProfessional.status == "ACTIVE",
                Membership.user_id == context.user_id,
                Membership.status == "ACTIVE",
                Membership.role == Role.DENTIST.value,
            )
            .limit(1)
        )
        if professional_id is None:
            raise PermissionDeniedError("dentist is not linked to an active agenda professional")
        return professional_id

    @classmethod
    async def _enforce_professional_scope(
        cls,
        session: AsyncSession,
        context: TenantContext,
        role: Role,
        professional_id: UUID | None,
    ) -> None:
        if role is Role.DENTIST:
            own_professional_id = await cls._own_professional_id(session, context)
            if professional_id != own_professional_id:
                raise PermissionDeniedError("dentists may only change their own agenda")

    @staticmethod
    async def _active_professional(
        session: AsyncSession, context: TenantContext, professional_id: UUID
    ) -> AgendaProfessional:
        professional = await session.scalar(
            select(AgendaProfessional).where(
                AgendaProfessional.clinic_id == context.clinic_id,
                AgendaProfessional.id == professional_id,
            )
        )
        if professional is None:
            raise NotFoundError("agenda professional not found")
        if professional.status != "ACTIVE":
            raise ConflictError("archived professionals cannot receive agenda events")
        return professional

    @staticmethod
    async def _active_room(
        session: AsyncSession, context: TenantContext, room_id: UUID | None
    ) -> AgendaRoom | None:
        if room_id is None:
            return None
        room = await session.scalar(
            select(AgendaRoom).where(
                AgendaRoom.clinic_id == context.clinic_id,
                AgendaRoom.id == room_id,
            )
        )
        if room is None:
            raise NotFoundError("agenda room not found")
        if room.status != "ACTIVE":
            raise ConflictError("archived rooms cannot receive agenda events")
        return room

    @staticmethod
    async def _active_patient(
        session: AsyncSession, context: TenantContext, patient_id: UUID
    ) -> Patient:
        patient = await session.scalar(
            select(Patient).where(
                Patient.clinic_id == context.clinic_id,
                Patient.id == patient_id,
            )
        )
        if patient is None:
            raise NotFoundError("patient not found")
        if patient.status != "ACTIVE":
            raise ConflictError("archived patients cannot receive new appointments")
        return patient

    @staticmethod
    async def _availability_intervals(
        session: AsyncSession, context: TenantContext, professional_id: UUID, weekday: int
    ) -> Sequence[ProfessionalAvailability]:
        ensure_context_matches(session, context)
        result = await session.execute(
            select(ProfessionalAvailability)
            .where(
                ProfessionalAvailability.clinic_id == context.clinic_id,
                ProfessionalAvailability.professional_id == professional_id,
                ProfessionalAvailability.weekday == weekday,
                ProfessionalAvailability.is_active.is_(True),
            )
            .order_by(ProfessionalAvailability.starts_at)
        )
        return result.scalars().all()

    @classmethod
    async def _ensure_within_availability(
        cls,
        session: AsyncSession,
        context: TenantContext,
        professional_id: UUID,
        starts_at: datetime,
        ends_at: datetime,
        timezone: ZoneInfo,
    ) -> None:
        local_start = starts_at.astimezone(timezone).replace(tzinfo=None)
        local_end = ends_at.astimezone(timezone).replace(tzinfo=None)
        if local_start.date() != local_end.date():
            raise InvalidInputError("an appointment must start and end on the same local day")
        intervals = await cls._availability_intervals(
            session, context, professional_id, local_start.weekday()
        )
        for interval in intervals:
            if interval.starts_at <= local_start.time() and local_end.time() <= interval.ends_at:
                return
        raise ConflictError("appointment must fit entirely within professional availability")

    @staticmethod
    async def _ensure_no_event_conflict(
        session: AsyncSession,
        context: TenantContext,
        *,
        starts_at: datetime,
        ends_at: datetime,
        professional_id: UUID | None = None,
        patient_id: UUID | None = None,
        room_id: UUID | None = None,
        exclude_event_id: UUID | None = None,
    ) -> None:
        resource_filters = []
        if professional_id is not None:
            resource_filters.append(ScheduleEvent.professional_id == professional_id)
        if patient_id is not None:
            resource_filters.append(ScheduleEvent.patient_id == patient_id)
        if room_id is not None:
            resource_filters.append(ScheduleEvent.room_id == room_id)
        if not resource_filters:
            return
        filters = [
            ScheduleEvent.clinic_id == context.clinic_id,
            ScheduleEvent.occupancy_state == "OCCUPYING",
            ScheduleEvent.starts_at < ends_at,
            ScheduleEvent.ends_at > starts_at,
            or_(*resource_filters),
        ]
        if exclude_event_id is not None:
            filters.append(ScheduleEvent.id != exclude_event_id)
        conflict = await session.scalar(select(ScheduleEvent.id).where(*filters).limit(1))
        if conflict is not None:
            raise ConflictError("requested time conflicts with another agenda event")

    @staticmethod
    async def _appointment_row(
        session: AsyncSession, context: TenantContext, appointment_id: UUID
    ) -> AppointmentRow:
        statement: Select[
            tuple[Appointment, ScheduleEvent, Patient, AgendaProfessional, AgendaRoom]
        ] = (
            select(Appointment, ScheduleEvent, Patient, AgendaProfessional, AgendaRoom)
            .join(
                ScheduleEvent,
                (ScheduleEvent.clinic_id == Appointment.clinic_id)
                & (ScheduleEvent.id == Appointment.schedule_event_id),
            )
            .join(
                Patient,
                (Patient.clinic_id == ScheduleEvent.clinic_id)
                & (Patient.id == ScheduleEvent.patient_id),
            )
            .join(
                AgendaProfessional,
                (AgendaProfessional.clinic_id == ScheduleEvent.clinic_id)
                & (AgendaProfessional.id == ScheduleEvent.professional_id),
            )
            .outerjoin(
                AgendaRoom,
                (AgendaRoom.clinic_id == ScheduleEvent.clinic_id)
                & (AgendaRoom.id == ScheduleEvent.room_id),
            )
            .where(
                Appointment.clinic_id == context.clinic_id,
                Appointment.id == appointment_id,
            )
        )
        row = (await session.execute(statement)).one_or_none()
        if row is None:
            raise NotFoundError("appointment not found")
        return cast(AppointmentRow, tuple(row))

    async def list_appointments(
        self, context: TenantContext, params: AgendaListParams
    ) -> AppointmentListResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            ensure_context_matches(session, context)
            filters = [
                Appointment.clinic_id == context.clinic_id,
                ScheduleEvent.starts_at < params.ends_at,
                ScheduleEvent.ends_at > params.starts_at,
            ]
            if params.professional_id is not None:
                filters.append(ScheduleEvent.professional_id == params.professional_id)
            if params.room_id is not None:
                filters.append(ScheduleEvent.room_id == params.room_id)
            if params.patient_id is not None:
                filters.append(ScheduleEvent.patient_id == params.patient_id)
            if params.status is not None:
                filters.append(Appointment.status == params.status.value)
            base = (
                select(Appointment, ScheduleEvent, Patient, AgendaProfessional, AgendaRoom)
                .join(
                    ScheduleEvent,
                    (ScheduleEvent.clinic_id == Appointment.clinic_id)
                    & (ScheduleEvent.id == Appointment.schedule_event_id),
                )
                .join(
                    Patient,
                    (Patient.clinic_id == ScheduleEvent.clinic_id)
                    & (Patient.id == ScheduleEvent.patient_id),
                )
                .join(
                    AgendaProfessional,
                    (AgendaProfessional.clinic_id == ScheduleEvent.clinic_id)
                    & (AgendaProfessional.id == ScheduleEvent.professional_id),
                )
                .outerjoin(
                    AgendaRoom,
                    (AgendaRoom.clinic_id == ScheduleEvent.clinic_id)
                    & (AgendaRoom.id == ScheduleEvent.room_id),
                )
                .where(*filters)
            )
            rows = (
                await session.execute(
                    base.order_by(ScheduleEvent.starts_at, Appointment.id)
                    .limit(params.limit)
                    .offset(params.offset)
                )
            ).all()
            total = await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .join(
                    ScheduleEvent,
                    (ScheduleEvent.clinic_id == Appointment.clinic_id)
                    & (ScheduleEvent.id == Appointment.schedule_event_id),
                )
                .where(*filters)
            )
        return AppointmentListResponse(
            items=[_appointment_response(cast(AppointmentRow, tuple(row))) for row in rows],
            total=int(total or 0),
            limit=params.limit,
            offset=params.offset,
        )

    async def get_appointment(
        self, context: TenantContext, appointment_id: UUID
    ) -> AppointmentResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            row = await self._appointment_row(session, context, appointment_id)
        return _appointment_response(row)

    async def patient_appointments(
        self,
        context: TenantContext,
        patient_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> AppointmentListResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            patient_exists = await session.scalar(
                select(Patient.id).where(
                    Patient.clinic_id == context.clinic_id,
                    Patient.id == patient_id,
                )
            )
            if patient_exists is None:
                raise NotFoundError("patient not found")
            filters = [
                Appointment.clinic_id == context.clinic_id,
                ScheduleEvent.patient_id == patient_id,
            ]
            rows = (
                await session.execute(
                    select(Appointment, ScheduleEvent, Patient, AgendaProfessional, AgendaRoom)
                    .join(
                        ScheduleEvent,
                        (ScheduleEvent.clinic_id == Appointment.clinic_id)
                        & (ScheduleEvent.id == Appointment.schedule_event_id),
                    )
                    .join(
                        Patient,
                        (Patient.clinic_id == ScheduleEvent.clinic_id)
                        & (Patient.id == ScheduleEvent.patient_id),
                    )
                    .join(
                        AgendaProfessional,
                        (AgendaProfessional.clinic_id == ScheduleEvent.clinic_id)
                        & (AgendaProfessional.id == ScheduleEvent.professional_id),
                    )
                    .outerjoin(
                        AgendaRoom,
                        (AgendaRoom.clinic_id == ScheduleEvent.clinic_id)
                        & (AgendaRoom.id == ScheduleEvent.room_id),
                    )
                    .where(*filters)
                    .order_by(ScheduleEvent.starts_at.desc(), Appointment.id)
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            total = await session.scalar(
                select(func.count())
                .select_from(Appointment)
                .join(
                    ScheduleEvent,
                    (ScheduleEvent.clinic_id == Appointment.clinic_id)
                    & (ScheduleEvent.id == Appointment.schedule_event_id),
                )
                .where(*filters)
            )
        return AppointmentListResponse(
            items=[_appointment_response(cast(AppointmentRow, tuple(row))) for row in rows],
            total=int(total or 0),
            limit=limit,
            offset=offset,
        )

    async def create_appointment(
        self, context: TenantContext, role: Role, payload: AppointmentCreateRequest
    ) -> AppointmentResponse:
        try:
            async with tenant_transaction(self._session_factory, context) as session:
                settings = await self._lock_agenda(session, context)
                await self._enforce_professional_scope(
                    session, context, role, payload.professional_id
                )
                await self._active_professional(session, context, payload.professional_id)
                await self._active_patient(session, context, payload.patient_id)
                await self._active_room(session, context, payload.room_id)
                timezone = _clinic_timezone(settings.timezone)
                starts_at, ends_at = _local_appointment_span(
                    payload.local_start, payload.duration_minutes, timezone
                )
                await self._ensure_within_availability(
                    session, context, payload.professional_id, starts_at, ends_at, timezone
                )
                await self._ensure_no_event_conflict(
                    session,
                    context,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    professional_id=payload.professional_id,
                    patient_id=payload.patient_id,
                    room_id=payload.room_id,
                )
                event = ScheduleEvent(
                    clinic_id=context.clinic_id,
                    event_type="APPOINTMENT",
                    professional_id=payload.professional_id,
                    patient_id=payload.patient_id,
                    room_id=payload.room_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    occupancy_state="OCCUPYING",
                )
                session.add(event)
                await session.flush()
                appointment = Appointment(
                    clinic_id=context.clinic_id,
                    schedule_event_id=event.id,
                    status=AppointmentStatus.SCHEDULED.value,
                    version=1,
                    administrative_note=payload.administrative_note,
                    updated_at=self._clock(),
                )
                session.add(appointment)
                await session.flush()
                session.add(
                    AppointmentHistory(
                        clinic_id=context.clinic_id,
                        appointment_id=appointment.id,
                        appointment_version=1,
                        event_type="CREATED",
                        actor_user_id=context.user_id,
                        new_values=_snapshot(appointment, event),
                    )
                )
                await ClinicAuditService(session).record(
                    "agenda.appointment.created",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="appointment",
                    entity_id=appointment.id,
                )
                await session.flush()
                result = await self._appointment_row(session, context, appointment.id)
        except IntegrityError as error:
            raise translate_integrity_error(error) from error
        return _appointment_response(result)

    async def update_appointment(
        self,
        context: TenantContext,
        role: Role,
        appointment_id: UUID,
        payload: AppointmentUpdateRequest,
    ) -> AppointmentResponse:
        try:
            async with tenant_transaction(self._session_factory, context) as session:
                await self._lock_agenda(session, context)
                row = await self._appointment_row(session, context, appointment_id)
                appointment, event, _, current_professional, _ = row
                self._require_version(appointment, payload.expected_version)
                if appointment.status not in PENDING_STATUSES:
                    raise ConflictError("terminal appointments cannot be edited")
                await self._enforce_professional_scope(
                    session, context, role, current_professional.id
                )
                updates = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
                updates.pop("expected_version", None)
                if not updates:
                    return _appointment_response(row)
                patient_id = updates.pop("patient_id", event.patient_id)
                professional_id = updates.pop("professional_id", event.professional_id)
                room_id = updates.pop("room_id", event.room_id)
                local_start = updates.pop("local_start", None)
                duration_minutes = updates.pop("duration_minutes", None)
                administrative_note = updates.pop(
                    "administrative_note", appointment.administrative_note
                )
                if not isinstance(patient_id, UUID) or not isinstance(professional_id, UUID):
                    raise InvalidInputError("patient_id and professional_id may not be null")
                if (local_start is None) != (duration_minutes is None):
                    raise InvalidInputError(
                        "local_start and duration_minutes must be supplied together"
                    )
                await self._enforce_professional_scope(session, context, role, professional_id)
                await self._active_professional(session, context, professional_id)
                await self._active_patient(session, context, patient_id)
                await self._active_room(session, context, room_id)
                settings = await self._settings(session, context)
                timezone = _clinic_timezone(settings.timezone)
                starts_at = event.starts_at
                ends_at = event.ends_at
                if local_start is not None and duration_minutes is not None:
                    if not isinstance(local_start, datetime) or not isinstance(
                        duration_minutes, int
                    ):
                        raise InvalidInputError("local_start and duration_minutes are invalid")
                    if appointment.status not in {
                        AppointmentStatus.SCHEDULED.value,
                        AppointmentStatus.CONFIRMED.value,
                    }:
                        raise ConflictError("appointments after arrival cannot be rescheduled")
                    starts_at, ends_at = _local_appointment_span(
                        local_start, duration_minutes, timezone
                    )
                changed_time = starts_at != event.starts_at or ends_at != event.ends_at
                changed_resources = (
                    patient_id != event.patient_id
                    or professional_id != event.professional_id
                    or room_id != event.room_id
                )
                changed_event = changed_time or changed_resources
                if changed_resources and appointment.status in {
                    AppointmentStatus.CHECKED_IN.value,
                    AppointmentStatus.IN_PROGRESS.value,
                }:
                    raise ConflictError("agenda resources cannot change after patient arrival")
                await self._ensure_within_availability(
                    session,
                    context,
                    professional_id,
                    starts_at,
                    ends_at,
                    timezone,
                )
                if changed_event:
                    await self._ensure_no_event_conflict(
                        session,
                        context,
                        starts_at=starts_at,
                        ends_at=ends_at,
                        professional_id=professional_id,
                        patient_id=patient_id,
                        room_id=room_id,
                        exclude_event_id=event.id,
                    )
                old_values = _snapshot(appointment, event)
                event.patient_id = patient_id
                event.professional_id = professional_id
                event.room_id = room_id
                event.starts_at = starts_at
                event.ends_at = ends_at
                event.updated_at = self._clock()
                appointment.administrative_note = administrative_note
                if changed_time:
                    appointment.status = AppointmentStatus.SCHEDULED.value
                appointment.version += 1
                appointment.updated_at = self._clock()
                await session.flush()
                if changed_event:
                    session.add(
                        AppointmentHistory(
                            clinic_id=context.clinic_id,
                            appointment_id=appointment.id,
                            appointment_version=appointment.version,
                            event_type="RESCHEDULED",
                            actor_user_id=context.user_id,
                            old_values=old_values,
                            new_values=_snapshot(appointment, event),
                        )
                    )
                await ClinicAuditService(session).record(
                    "agenda.appointment.updated",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="appointment",
                    entity_id=appointment.id,
                )
                await session.flush()
                result = await self._appointment_row(session, context, appointment.id)
        except IntegrityError as error:
            raise translate_integrity_error(error) from error
        return _appointment_response(result)

    async def reschedule_appointment(
        self,
        context: TenantContext,
        role: Role,
        appointment_id: UUID,
        payload: AppointmentRescheduleRequest,
    ) -> AppointmentResponse:
        try:
            async with tenant_transaction(self._session_factory, context) as session:
                settings = await self._lock_agenda(session, context)
                row = await self._appointment_row(session, context, appointment_id)
                appointment, event, patient, professional, room = row
                self._require_version(appointment, payload.expected_version)
                if appointment.status not in {
                    AppointmentStatus.SCHEDULED.value,
                    AppointmentStatus.CONFIRMED.value,
                }:
                    raise ConflictError("only appointments before arrival may be rescheduled")
                await self._enforce_professional_scope(session, context, role, professional.id)
                await self._active_patient(session, context, patient.id)
                await self._active_professional(session, context, professional.id)
                if room is not None:
                    await self._active_room(session, context, room.id)
                timezone = _clinic_timezone(settings.timezone)
                starts_at, ends_at = _local_appointment_span(
                    payload.local_start, payload.duration_minutes, timezone
                )
                await self._ensure_within_availability(
                    session, context, professional.id, starts_at, ends_at, timezone
                )
                await self._ensure_no_event_conflict(
                    session,
                    context,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    professional_id=professional.id,
                    patient_id=patient.id,
                    room_id=room.id if room else None,
                    exclude_event_id=event.id,
                )
                old_values = _snapshot(appointment, event)
                event.starts_at = starts_at
                event.ends_at = ends_at
                event.updated_at = self._clock()
                appointment.status = AppointmentStatus.SCHEDULED.value
                appointment.cancellation_reason = None
                appointment.version += 1
                appointment.updated_at = self._clock()
                await session.flush()
                session.add(
                    AppointmentHistory(
                        clinic_id=context.clinic_id,
                        appointment_id=appointment.id,
                        appointment_version=appointment.version,
                        event_type="RESCHEDULED",
                        actor_user_id=context.user_id,
                        old_values=old_values,
                        new_values=_snapshot(appointment, event),
                    )
                )
                await ClinicAuditService(session).record(
                    "agenda.appointment.rescheduled",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="appointment",
                    entity_id=appointment.id,
                )
                await session.flush()
                result = await self._appointment_row(session, context, appointment.id)
        except IntegrityError as error:
            raise translate_integrity_error(error) from error
        return _appointment_response(result)

    async def change_appointment_status(
        self,
        context: TenantContext,
        role: Role,
        appointment_id: UUID,
        payload: AppointmentStatusRequest,
    ) -> AppointmentResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            row = await self._appointment_row(session, context, appointment_id)
            appointment, event, _, professional, _ = row
            self._require_version(appointment, payload.expected_version)
            await self._enforce_professional_scope(session, context, role, professional.id)
            next_status = payload.status.value
            if not self._allowed_transition(appointment.status, next_status):
                raise ConflictError("appointment status transition is not allowed")
            if next_status == AppointmentStatus.CANCELLED.value and not payload.cancellation_reason:
                raise InvalidInputError("cancellation reason is required")
            if next_status == AppointmentStatus.NO_SHOW.value and self._clock() < event.starts_at:
                raise ConflictError("an appointment may only be marked as no-show after it starts")
            old_status = appointment.status
            old_values = {"status": old_status}
            appointment.status = next_status
            appointment.cancellation_reason = (
                payload.cancellation_reason
                if next_status == AppointmentStatus.CANCELLED.value
                else None
            )
            appointment.version += 1
            appointment.updated_at = self._clock()
            await session.flush()
            session.add(
                AppointmentHistory(
                    clinic_id=context.clinic_id,
                    appointment_id=appointment.id,
                    appointment_version=appointment.version,
                    event_type="STATUS_CHANGED",
                    actor_user_id=context.user_id,
                    old_values=old_values,
                    new_values={"status": next_status},
                )
            )
            await ClinicAuditService(session).record(
                "agenda.appointment.status_changed",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="appointment",
                entity_id=appointment.id,
            )
            await session.flush()
            result = await self._appointment_row(session, context, appointment.id)
        return _appointment_response(result)

    @staticmethod
    def _allowed_transition(current: str, target: str) -> bool:
        transitions = {
            AppointmentStatus.SCHEDULED.value: {
                AppointmentStatus.CONFIRMED.value,
                AppointmentStatus.CHECKED_IN.value,
                AppointmentStatus.CANCELLED.value,
                AppointmentStatus.NO_SHOW.value,
            },
            AppointmentStatus.CONFIRMED.value: {
                AppointmentStatus.CHECKED_IN.value,
                AppointmentStatus.CANCELLED.value,
                AppointmentStatus.NO_SHOW.value,
            },
            AppointmentStatus.CHECKED_IN.value: {
                AppointmentStatus.IN_PROGRESS.value,
                AppointmentStatus.CANCELLED.value,
            },
            AppointmentStatus.IN_PROGRESS.value: {AppointmentStatus.COMPLETED.value},
        }
        return target in transitions.get(current, set())

    @staticmethod
    def _require_version(appointment: Appointment, expected_version: int) -> None:
        if appointment.version != expected_version:
            raise ConflictError("appointment was changed by another user; refresh and retry")

    async def appointment_history(
        self,
        context: TenantContext,
        appointment_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> AppointmentHistoryListResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._appointment_row(session, context, appointment_id)
            filters = [
                AppointmentHistory.clinic_id == context.clinic_id,
                AppointmentHistory.appointment_id == appointment_id,
            ]
            rows = (
                (
                    await session.execute(
                        select(AppointmentHistory)
                        .where(*filters)
                        .order_by(AppointmentHistory.occurred_at.desc(), AppointmentHistory.id)
                        .limit(limit)
                        .offset(offset)
                    )
                )
                .scalars()
                .all()
            )
            total = await session.scalar(
                select(func.count()).select_from(AppointmentHistory).where(*filters)
            )
        items = [
            AppointmentHistoryResponse.model_validate(
                {
                    "id": row.id,
                    "appointment_id": row.appointment_id,
                    "appointment_version": row.appointment_version,
                    "event_type": row.event_type,
                    "actor_user_id": row.actor_user_id,
                    "old_values": row.old_values,
                    "new_values": row.new_values,
                    "occurred_at": row.occurred_at,
                }
            )
            for row in rows
        ]
        return AppointmentHistoryListResponse(
            items=items, total=int(total or 0), limit=limit, offset=offset
        )

    async def replace_working_hours(
        self,
        context: TenantContext,
        role: Role,
        professional_id: UUID,
        payload: WorkingHoursReplaceRequest,
    ) -> WorkingHoursResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            settings = await self._lock_agenda(session, context)
            await self._enforce_professional_scope(session, context, role, professional_id)
            await self._active_professional(session, context, professional_id)
            timezone = _clinic_timezone(settings.timezone)
            now = self._clock()
            future_rows = (
                (
                    await session.execute(
                        select(ScheduleEvent)
                        .join(
                            Appointment,
                            (Appointment.clinic_id == ScheduleEvent.clinic_id)
                            & (Appointment.schedule_event_id == ScheduleEvent.id),
                        )
                        .where(
                            ScheduleEvent.clinic_id == context.clinic_id,
                            ScheduleEvent.professional_id == professional_id,
                            ScheduleEvent.occupancy_state == "OCCUPYING",
                            ScheduleEvent.starts_at >= now,
                            Appointment.status.in_(PENDING_STATUSES),
                        )
                    )
                )
                .scalars()
                .all()
            )
            proposed_by_day: dict[int, list[tuple[time, time]]] = {}
            for interval in payload.intervals:
                proposed_by_day.setdefault(interval.weekday, []).append(
                    (interval.starts_at, interval.ends_at)
                )
            for event in future_rows:
                local_start = event.starts_at.astimezone(timezone)
                local_end = event.ends_at.astimezone(timezone)
                if local_start.date() != local_end.date() or not any(
                    start <= local_start.time() and local_end.time() <= end
                    for start, end in proposed_by_day.get(local_start.weekday(), [])
                ):
                    raise ConflictError(
                        "resolve future appointments outside the proposed working hours first"
                    )
            await session.execute(
                update(ProfessionalAvailability)
                .where(
                    ProfessionalAvailability.clinic_id == context.clinic_id,
                    ProfessionalAvailability.professional_id == professional_id,
                    ProfessionalAvailability.is_active.is_(True),
                )
                .values(is_active=False, updated_at=now)
            )
            for interval in payload.intervals:
                session.add(
                    ProfessionalAvailability(
                        clinic_id=context.clinic_id,
                        professional_id=professional_id,
                        weekday=interval.weekday,
                        starts_at=interval.starts_at,
                        ends_at=interval.ends_at,
                        updated_at=now,
                    )
                )
            await session.flush()
            await ClinicAuditService(session).record(
                "agenda.working_hours.replaced",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_professional",
                entity_id=professional_id,
                metadata={"interval_count": len(payload.intervals)},
            )
        return WorkingHoursResponse(professional_id=professional_id, intervals=payload.intervals)

    async def working_hours(
        self, context: TenantContext, professional_id: UUID
    ) -> WorkingHoursResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            professional = await session.scalar(
                select(AgendaProfessional).where(
                    AgendaProfessional.clinic_id == context.clinic_id,
                    AgendaProfessional.id == professional_id,
                )
            )
            if professional is None:
                raise NotFoundError("agenda professional not found")
            result = await session.execute(
                select(ProfessionalAvailability)
                .where(
                    ProfessionalAvailability.clinic_id == context.clinic_id,
                    ProfessionalAvailability.professional_id == professional_id,
                    ProfessionalAvailability.is_active.is_(True),
                )
                .order_by(
                    ProfessionalAvailability.weekday,
                    ProfessionalAvailability.starts_at,
                )
            )
            rows = result.scalars().all()
        return WorkingHoursResponse(
            professional_id=professional_id,
            intervals=[
                WorkingHourInterval(
                    weekday=row.weekday,
                    starts_at=row.starts_at,
                    ends_at=row.ends_at,
                )
                for row in rows
            ],
        )

    async def find_availability(
        self, context: TenantContext, request: AvailabilityRequest
    ) -> AvailabilityResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            settings = await self._settings(session, context)
            timezone = _clinic_timezone(settings.timezone)
            await self._active_professional(session, context, request.professional_id)
            if request.patient_id is not None:
                await self._active_patient(session, context, request.patient_id)
            await self._active_room(session, context, request.room_id)
            intervals = await self._availability_intervals(
                session, context, request.professional_id, request.local_date.weekday()
            )
            day_start = _local_day_boundary(request.local_date, timezone)
            next_day = request.local_date + timedelta(days=1)
            day_end = _local_day_boundary(next_day, timezone)
            resource_filters = [ScheduleEvent.professional_id == request.professional_id]
            if request.patient_id is not None:
                resource_filters.append(ScheduleEvent.patient_id == request.patient_id)
            if request.room_id is not None:
                resource_filters.append(ScheduleEvent.room_id == request.room_id)
            busy_result = await session.execute(
                select(ScheduleEvent).where(
                    ScheduleEvent.clinic_id == context.clinic_id,
                    ScheduleEvent.occupancy_state == "OCCUPYING",
                    ScheduleEvent.starts_at < day_end,
                    ScheduleEvent.ends_at > day_start,
                    or_(*resource_filters),
                )
            )
            busy_events = busy_result.scalars().all()
        candidates: list[datetime] = []
        duration = timedelta(minutes=request.duration_minutes)
        step = timedelta(minutes=request.step_minutes)
        for interval in intervals:
            cursor = datetime.combine(request.local_date, interval.starts_at)
            interval_end = datetime.combine(request.local_date, interval.ends_at)
            while cursor + duration <= interval_end:
                local_end = cursor + duration
                try:
                    starts_at = _resolve_local(cursor, timezone)
                    ends_at = _resolve_local(local_end, timezone)
                except InvalidInputError:
                    cursor += step
                    continue
                if not any(
                    event.starts_at < ends_at and event.ends_at > starts_at for event in busy_events
                ):
                    candidates.append(starts_at.astimezone(timezone))
                cursor += step
        candidates.sort()
        return AvailabilityResponse(
            professional_id=request.professional_id,
            local_date=request.local_date,
            timezone=settings.timezone,
            starts_at=candidates,
        )

    async def list_schedule_blocks(
        self,
        context: TenantContext,
        params: ScheduleBlockListParams,
    ) -> ScheduleBlockListResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            filters = [
                ScheduleBlock.clinic_id == context.clinic_id,
                ScheduleEvent.starts_at < params.ends_at,
                ScheduleEvent.ends_at > params.starts_at,
            ]
            if not params.include_cancelled:
                filters.append(ScheduleBlock.status == "ACTIVE")
            if params.professional_id is not None:
                filters.append(ScheduleEvent.professional_id == params.professional_id)
            if params.room_id is not None:
                filters.append(ScheduleEvent.room_id == params.room_id)
            rows = (
                await session.execute(
                    select(ScheduleBlock, ScheduleEvent)
                    .join(
                        ScheduleEvent,
                        (ScheduleEvent.clinic_id == ScheduleBlock.clinic_id)
                        & (ScheduleEvent.id == ScheduleBlock.schedule_event_id),
                    )
                    .where(*filters)
                    .order_by(ScheduleEvent.starts_at, ScheduleBlock.id)
                    .limit(params.limit)
                    .offset(params.offset)
                )
            ).all()
            total = await session.scalar(
                select(func.count())
                .select_from(ScheduleBlock)
                .join(
                    ScheduleEvent,
                    (ScheduleEvent.clinic_id == ScheduleBlock.clinic_id)
                    & (ScheduleEvent.id == ScheduleBlock.schedule_event_id),
                )
                .where(*filters)
            )
        return ScheduleBlockListResponse(
            items=[self._block_response(block, event) for block, event in rows],
            total=int(total or 0),
            limit=params.limit,
            offset=params.offset,
        )

    @staticmethod
    def _block_response(block: ScheduleBlock, event: ScheduleEvent) -> ScheduleBlockResponse:
        return ScheduleBlockResponse(
            id=block.id,
            clinic_id=block.clinic_id,
            professional_id=event.professional_id,
            room_id=event.room_id,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            label=block.label,
            status=block.status,
            cancellation_reason=block.cancellation_reason,
            created_at=block.created_at,
            updated_at=block.updated_at,
        )

    @staticmethod
    async def _block_row(
        session: AsyncSession, context: TenantContext, block_id: UUID
    ) -> tuple[ScheduleBlock, ScheduleEvent]:
        row = await session.execute(
            select(ScheduleBlock, ScheduleEvent)
            .join(
                ScheduleEvent,
                (ScheduleEvent.clinic_id == ScheduleBlock.clinic_id)
                & (ScheduleEvent.id == ScheduleBlock.schedule_event_id),
            )
            .where(ScheduleBlock.clinic_id == context.clinic_id, ScheduleBlock.id == block_id)
        )
        result = row.one_or_none()
        if result is None:
            raise NotFoundError("schedule block not found")
        return cast(tuple[ScheduleBlock, ScheduleEvent], tuple(result))

    async def create_schedule_block(
        self, context: TenantContext, role: Role, payload: ScheduleBlockCreateRequest
    ) -> ScheduleBlockResponse:
        try:
            async with tenant_transaction(self._session_factory, context) as session:
                settings = await self._lock_agenda(session, context)
                await self._enforce_professional_scope(
                    session, context, role, payload.professional_id
                )
                if payload.professional_id is not None:
                    await self._active_professional(session, context, payload.professional_id)
                elif role is Role.DENTIST:
                    raise PermissionDeniedError(
                        "dentists may only create blocks on their own agenda"
                    )
                await self._active_room(session, context, payload.room_id)
                timezone = _clinic_timezone(settings.timezone)
                starts_at = _resolve_local(payload.local_start, timezone)
                ends_at = _resolve_local(payload.local_end, timezone)
                await self._ensure_no_event_conflict(
                    session,
                    context,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    professional_id=payload.professional_id,
                    room_id=payload.room_id,
                )
                event = ScheduleEvent(
                    clinic_id=context.clinic_id,
                    event_type="BLOCK",
                    professional_id=payload.professional_id,
                    room_id=payload.room_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    occupancy_state="OCCUPYING",
                )
                session.add(event)
                await session.flush()
                block = ScheduleBlock(
                    clinic_id=context.clinic_id,
                    schedule_event_id=event.id,
                    label=payload.label,
                    status="ACTIVE",
                    updated_at=self._clock(),
                )
                session.add(block)
                await session.flush()
                await ClinicAuditService(session).record(
                    "agenda.block.created",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="schedule_block",
                    entity_id=block.id,
                )
        except IntegrityError as error:
            raise translate_integrity_error(error) from error
        return self._block_response(block, event)

    async def update_schedule_block(
        self,
        context: TenantContext,
        role: Role,
        block_id: UUID,
        payload: ScheduleBlockUpdateRequest,
    ) -> ScheduleBlockResponse:
        try:
            async with tenant_transaction(self._session_factory, context) as session:
                settings = await self._lock_agenda(session, context)
                block, event = await self._block_row(session, context, block_id)
                if block.status != "ACTIVE":
                    raise ConflictError("cancelled schedule blocks cannot be edited")
                own_professional = event.professional_id
                await self._enforce_professional_scope(session, context, role, own_professional)
                fields = payload.model_dump(exclude_unset=True)
                local_start_provided = "local_start" in fields
                local_end_provided = "local_end" in fields
                if local_start_provided != local_end_provided:
                    raise InvalidInputError("local_start and local_end must be supplied together")
                if local_start_provided and (
                    fields.get("local_start") is None or fields.get("local_end") is None
                ):
                    raise InvalidInputError("local_start and local_end may not be null")
                professional_id = fields.pop("professional_id", event.professional_id)
                room_id = fields.pop("room_id", event.room_id)
                if professional_id is not None and not isinstance(professional_id, UUID):
                    raise InvalidInputError("professional_id must be a UUID or omitted")
                if room_id is not None and not isinstance(room_id, UUID):
                    raise InvalidInputError("room_id must be a UUID or omitted")
                if professional_id is None and room_id is None:
                    raise InvalidInputError("a block must include a professional or room")
                await self._enforce_professional_scope(session, context, role, professional_id)
                if professional_id is not None:
                    await self._active_professional(session, context, professional_id)
                await self._active_room(session, context, room_id)
                timezone = _clinic_timezone(settings.timezone)
                starts_at = (
                    _resolve_local(cast(datetime, fields.pop("local_start")), timezone)
                    if local_start_provided
                    else event.starts_at
                )
                ends_at = (
                    _resolve_local(cast(datetime, fields.pop("local_end")), timezone)
                    if local_end_provided
                    else event.ends_at
                )
                if starts_at >= ends_at:
                    raise InvalidInputError("local_start must be earlier than local_end")
                await self._ensure_no_event_conflict(
                    session,
                    context,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    professional_id=professional_id,
                    room_id=room_id,
                    exclude_event_id=event.id,
                )
                event.professional_id = professional_id
                event.room_id = room_id
                event.starts_at = starts_at
                event.ends_at = ends_at
                event.updated_at = self._clock()
                if "label" in fields:
                    block.label = cast(str | None, fields["label"])
                block.updated_at = self._clock()
                await session.flush()
                await ClinicAuditService(session).record(
                    "agenda.block.updated",
                    clinic_id=context.clinic_id,
                    actor_user_id=context.user_id,
                    entity_type="schedule_block",
                    entity_id=block.id,
                )
        except IntegrityError as error:
            raise translate_integrity_error(error) from error
        return self._block_response(block, event)

    async def cancel_schedule_block(
        self,
        context: TenantContext,
        role: Role,
        block_id: UUID,
        payload: ScheduleBlockCancelRequest,
    ) -> ScheduleBlockResponse:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            block, event = await self._block_row(session, context, block_id)
            await self._enforce_professional_scope(session, context, role, event.professional_id)
            if block.status == "CANCELLED":
                return self._block_response(block, event)
            block.status = "CANCELLED"
            block.cancellation_reason = payload.reason
            block.cancelled_at = self._clock()
            block.updated_at = self._clock()
            await session.flush()
            await ClinicAuditService(session).record(
                "agenda.block.cancelled",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="schedule_block",
                entity_id=block.id,
            )
        return self._block_response(block, event)
