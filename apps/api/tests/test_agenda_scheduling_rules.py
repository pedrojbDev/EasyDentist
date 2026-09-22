from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app.appointments.schedule_service import (
    _local_appointment_span,
    _local_day_boundary,
    _resolve_local,
)
from app.appointments.schemas import (
    AppointmentUpdateRequest,
    ScheduleBlockCreateRequest,
    WorkingHoursReplaceRequest,
)
from app.core.errors import InvalidInputError


def test_local_time_resolves_to_one_timezone_aware_instant() -> None:
    value = _resolve_local(datetime(2026, 9, 22, 9, 30), ZoneInfo("America/Bahia"))

    assert value.tzinfo is UTC
    assert value.isoformat() == "2026-09-22T12:30:00+00:00"


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 3, 8, 2, 30), datetime(2026, 11, 1, 1, 30)],
)
def test_nonexistent_and_ambiguous_local_times_are_rejected(value: datetime) -> None:
    with pytest.raises(InvalidInputError):
        _resolve_local(value, ZoneInfo("America/New_York"))


def test_availability_day_boundary_handles_midnight_dst_gap() -> None:
    timezone = ZoneInfo("America/Sao_Paulo")
    boundary = _local_day_boundary(date(2018, 11, 4), timezone)

    assert boundary.astimezone(timezone).date() == date(2018, 11, 4)
    assert boundary.astimezone(timezone).hour == 1


def test_appointment_duration_may_not_cross_its_local_day() -> None:
    with pytest.raises(InvalidInputError, match="same local day"):
        _local_appointment_span(datetime(2026, 9, 22, 23, 45), 30, ZoneInfo("America/Bahia"))


def test_weekly_hours_reject_overlap_but_allow_adjacent_intervals() -> None:
    payload = WorkingHoursReplaceRequest(
        intervals=[
            {"weekday": 0, "starts_at": "08:00", "ends_at": "12:00"},
            {"weekday": 0, "starts_at": "12:00", "ends_at": "17:00"},
        ]
    )
    assert len(payload.intervals) == 2

    with pytest.raises(ValidationError):
        WorkingHoursReplaceRequest(
            intervals=[
                {"weekday": 0, "starts_at": "08:00", "ends_at": "12:00"},
                {"weekday": 0, "starts_at": "11:59", "ends_at": "17:00"},
            ]
        )


def test_block_requires_a_professional_or_room() -> None:
    with pytest.raises(ValidationError):
        ScheduleBlockCreateRequest(
            local_start="2026-09-22T10:00",
            local_end="2026-09-22T11:00",
        )

    payload = ScheduleBlockCreateRequest(
        local_start="2026-09-22T10:00",
        local_end="2026-09-22T11:00",
        room_id=uuid4(),
    )
    assert payload.room_id is not None


def test_appointment_update_rejects_null_reschedule_pair() -> None:
    with pytest.raises(ValidationError):
        AppointmentUpdateRequest(
            expected_version=1,
            local_start=None,
            duration_minutes=None,
        )
