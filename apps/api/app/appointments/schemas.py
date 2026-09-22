from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NAME_MAX_LENGTH = 200
CRO_MAX_LENGTH = 50


class AgendaResourceStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required(value: str) -> str:
    return value.strip()


class AgendaProfessionalFields(BaseModel):
    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)
    membership_id: UUID | None = None
    cro_number: str | None = Field(default=None, max_length=CRO_MAX_LENGTH)
    cro_state: str | None = Field(default=None, max_length=2)

    @field_validator("cro_number")
    @classmethod
    def clean_cro_number(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @field_validator("cro_state")
    @classmethod
    def clean_cro_state(cls, value: str | None) -> str | None:
        cleaned = _clean_optional(value)
        if cleaned is None:
            return None
        cleaned = cleaned.upper()
        if len(cleaned) != 2 or not cleaned.isalpha():
            raise ValueError("cro_state must be a two-letter UF")
        return cleaned

    @model_validator(mode="after")
    def require_cro_pair(self) -> AgendaProfessionalFields:
        if (self.cro_number is None) != (self.cro_state is None):
            raise ValueError("cro_number and cro_state must be informed together")
        return self


class AgendaProfessionalCreateRequest(AgendaProfessionalFields):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned


class AgendaProfessionalUpdateRequest(AgendaProfessionalFields):
    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def reject_explicit_null_name(self) -> AgendaProfessionalUpdateRequest:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class AgendaProfessionalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    membership_id: UUID | None
    name: str
    cro_number: str | None
    cro_state: str | None
    status: AgendaResourceStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgendaProfessionalListParams(BaseModel):
    status: AgendaResourceStatus = AgendaResourceStatus.ACTIVE
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AgendaProfessionalListResponse(BaseModel):
    items: list[AgendaProfessionalResponse]
    total: int
    limit: int
    offset: int


class AgendaRoomFields(BaseModel):
    name: str | None = Field(default=None, max_length=NAME_MAX_LENGTH)


class AgendaRoomCreateRequest(AgendaRoomFields):
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned


class AgendaRoomUpdateRequest(AgendaRoomFields):
    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = _clean_required(value)
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned

    @model_validator(mode="after")
    def reject_explicit_null_name(self) -> AgendaRoomUpdateRequest:
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class AgendaRoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    clinic_id: UUID
    name: str
    status: AgendaResourceStatus
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AgendaRoomListParams(BaseModel):
    status: AgendaResourceStatus = AgendaResourceStatus.ACTIVE
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AgendaRoomListResponse(BaseModel):
    items: list[AgendaRoomResponse]
    total: int
    limit: int
    offset: int


class WorkingHourInterval(BaseModel):
    weekday: int = Field(ge=0, le=6, description="Monday is 0; Sunday is 6")
    starts_at: time
    ends_at: time

    @model_validator(mode="after")
    def validate_interval(self) -> WorkingHourInterval:
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        return self


class WorkingHoursReplaceRequest(BaseModel):
    intervals: list[WorkingHourInterval] = Field(max_length=28)

    @model_validator(mode="after")
    def reject_overlaps(self) -> WorkingHoursReplaceRequest:
        by_day: dict[int, list[WorkingHourInterval]] = {}
        for interval in self.intervals:
            by_day.setdefault(interval.weekday, []).append(interval)
        for intervals in by_day.values():
            ordered = sorted(intervals, key=lambda item: item.starts_at)
            if any(
                left.ends_at > right.starts_at
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise ValueError("working-hour intervals may not overlap")
        return self


class WorkingHoursResponse(BaseModel):
    professional_id: UUID
    intervals: list[WorkingHourInterval]


class LocalIntervalFields(BaseModel):
    local_start: datetime
    local_end: datetime

    @field_validator("local_start", "local_end")
    @classmethod
    def require_naive_local_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local date-times must not include a timezone offset")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> LocalIntervalFields:
        if self.local_start >= self.local_end:
            raise ValueError("local_start must be earlier than local_end")
        return self


class ScheduleBlockCreateRequest(LocalIntervalFields):
    professional_id: UUID | None = None
    room_id: UUID | None = None
    label: str | None = Field(default=None, max_length=200)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str | None) -> str | None:
        return _clean_optional(value)

    @model_validator(mode="after")
    def require_resource(self) -> ScheduleBlockCreateRequest:
        if self.professional_id is None and self.room_id is None:
            raise ValueError("a block must include a professional or room")
        return self


class ScheduleBlockUpdateRequest(BaseModel):
    local_start: datetime | None = None
    local_end: datetime | None = None
    professional_id: UUID | None = None
    room_id: UUID | None = None
    label: str | None = Field(default=None, max_length=200)

    @field_validator("local_start", "local_end")
    @classmethod
    def require_naive_local_datetime(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local date-times must not include a timezone offset")
        return value

    @field_validator("label")
    @classmethod
    def clean_label(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class ScheduleBlockResponse(BaseModel):
    id: UUID
    clinic_id: UUID
    professional_id: UUID | None
    room_id: UUID | None
    starts_at: datetime
    ends_at: datetime
    label: str | None
    status: str
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class ScheduleBlockListResponse(BaseModel):
    items: list[ScheduleBlockResponse]
    total: int
    limit: int
    offset: int


class ScheduleBlockListParams(BaseModel):
    starts_at: datetime
    ends_at: datetime
    professional_id: UUID | None = None
    room_id: UUID | None = None
    include_cancelled: bool = False
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> ScheduleBlockListParams:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must include a timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        if (self.ends_at - self.starts_at).total_seconds() > 31 * 24 * 60 * 60:
            raise ValueError("agenda range may not exceed 31 days")
        return self


class ScheduleBlockCancelRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class AppointmentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class AgendaListParams(BaseModel):
    starts_at: datetime
    ends_at: datetime
    professional_id: UUID | None = None
    room_id: UUID | None = None
    patient_id: UUID | None = None
    status: AppointmentStatus | None = None
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> AgendaListParams:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
            raise ValueError("ends_at must include a timezone offset")
        if self.starts_at >= self.ends_at:
            raise ValueError("starts_at must be earlier than ends_at")
        if (self.ends_at - self.starts_at).total_seconds() > 31 * 24 * 60 * 60:
            raise ValueError("agenda range may not exceed 31 days")
        return self


class AppointmentCreateRequest(BaseModel):
    patient_id: UUID
    professional_id: UUID
    room_id: UUID | None = None
    local_start: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)
    administrative_note: str | None = Field(default=None, max_length=2000)

    @field_validator("local_start")
    @classmethod
    def require_naive_local_start(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local_start must not include a timezone offset")
        return value


class AppointmentUpdateRequest(BaseModel):
    expected_version: int = Field(ge=1)
    patient_id: UUID | None = None
    professional_id: UUID | None = None
    room_id: UUID | None = None
    local_start: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=480)
    administrative_note: str | None = Field(default=None, max_length=2000)

    @field_validator("local_start")
    @classmethod
    def require_naive_local_start(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local_start must not include a timezone offset")
        return value

    @model_validator(mode="after")
    def require_reschedule_pair(self) -> AppointmentUpdateRequest:
        if ("local_start" in self.model_fields_set) != (
            "duration_minutes" in self.model_fields_set
        ):
            raise ValueError("local_start and duration_minutes must be supplied together")
        if "local_start" in self.model_fields_set and (
            self.local_start is None or self.duration_minutes is None
        ):
            raise ValueError("local_start and duration_minutes may not be null")
        return self


class AppointmentRescheduleRequest(BaseModel):
    expected_version: int = Field(ge=1)
    local_start: datetime
    duration_minutes: int = Field(default=30, ge=5, le=480)

    @field_validator("local_start")
    @classmethod
    def require_naive_local_start(cls, value: datetime) -> datetime:
        if value.tzinfo is not None and value.utcoffset() is not None:
            raise ValueError("local_start must not include a timezone offset")
        return value


class AppointmentStatusRequest(BaseModel):
    expected_version: int = Field(ge=1)
    status: AppointmentStatus
    cancellation_reason: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("cancellation_reason")
    @classmethod
    def clean_cancellation_reason(cls, value: str | None) -> str | None:
        return _clean_optional(value)


class AppointmentResponse(BaseModel):
    id: UUID
    clinic_id: UUID
    patient_id: UUID
    patient_name: str
    professional_id: UUID
    professional_name: str
    room_id: UUID | None
    room_name: str | None
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    administrative_note: str | None
    cancellation_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class AppointmentListResponse(BaseModel):
    items: list[AppointmentResponse]
    total: int
    limit: int
    offset: int


class AppointmentHistoryResponse(BaseModel):
    id: UUID
    appointment_id: UUID
    appointment_version: int
    event_type: str
    actor_user_id: UUID
    old_values: dict[str, object]
    new_values: dict[str, object]
    occurred_at: datetime


class AppointmentHistoryListResponse(BaseModel):
    items: list[AppointmentHistoryResponse]
    total: int
    limit: int
    offset: int


class AvailabilityRequest(BaseModel):
    professional_id: UUID
    local_date: date
    duration_minutes: int = Field(default=30, ge=5, le=480)
    patient_id: UUID | None = None
    room_id: UUID | None = None
    step_minutes: int = Field(default=15, ge=5, le=60)


class AvailabilityResponse(BaseModel):
    professional_id: UUID
    local_date: date
    timezone: str
    starts_at: list[datetime]
