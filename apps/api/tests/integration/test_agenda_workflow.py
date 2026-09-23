from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_clinic_settings, insert_membership, insert_patient

from app.appointments.schedule_service import AgendaService
from app.appointments.schemas import AppointmentCreateRequest
from app.clinics.rbac import Role
from app.core.context import TenantContext
from app.core.errors import ConflictError

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"
BAHIA = ZoneInfo("America/Bahia")


@dataclass(frozen=True, slots=True)
class AgendaScenario:
    clinic_id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: str
    dentist_email: str
    dentist_membership_id: uuid.UUID
    patient_id: uuid.UUID


async def login(client: httpx.AsyncClient, email: str) -> str:
    csrf_response = await client.get("/api/v1/auth/csrf")
    csrf = csrf_response.json()["csrf_token"]
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    client.cookies.clear()
    assert response.status_code == 200
    token = response.cookies.get(SESSION_COOKIE)
    assert token
    return token


async def mutate(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> httpx.Response:
    csrf_response = await client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    csrf = csrf_response.json()["csrf_token"]
    response = await client.request(
        method,
        url,
        json=payload,
        headers={
            "Cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


async def read(client: httpx.AsyncClient, url: str, token: str) -> httpx.Response:
    response = await client.get(url, headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    client.cookies.clear()
    return response


@pytest.fixture
async def agenda_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[AgendaScenario]:
    suffix = uuid.uuid4().hex[:10]
    clinic_id = await insert_clinic(migrator_connection, f"agenda-{suffix}")
    provisioned_clinics.append(clinic_id)
    await insert_clinic_settings(migrator_connection, clinic_id)
    owner_email = make_test_email("agenda-owner")
    dentist_email = make_test_email("agenda-dentist")
    owner_id = await seed_user_with_password(email=owner_email, password=PASSWORD)
    dentist_id = await seed_user_with_password(email=dentist_email, password=PASSWORD)
    await insert_membership(
        migrator_connection, clinic_id=clinic_id, user_id=owner_id, role=Role.OWNER.value
    )
    dentist_membership_id = await insert_membership(
        migrator_connection, clinic_id=clinic_id, user_id=dentist_id, role=Role.DENTIST.value
    )
    patient_id = await insert_patient(
        migrator_connection,
        clinic_id=clinic_id,
        full_name="Paciente da Agenda",
        cpf="52998224725",
    )
    yield AgendaScenario(
        clinic_id=clinic_id,
        owner_id=owner_id,
        owner_email=owner_email,
        dentist_email=dentist_email,
        dentist_membership_id=dentist_membership_id,
        patient_id=patient_id,
    )


def future_local_start(days: int, hour: int = 9) -> datetime:
    local_day = datetime.now(BAHIA).date() + timedelta(days=days)
    return datetime.combine(local_day, datetime.min.time()).replace(hour=hour)


@pytest.mark.anyio
async def test_agenda_lifecycle_conflicts_versioning_and_timezone_policy(
    api_client: httpx.AsyncClient,
    migrator_connection: asyncpg.Connection,
    agenda_scenario: AgendaScenario,
    session_factory,
) -> None:
    clinic_id = agenda_scenario.clinic_id
    base_url = f"/api/v1/clinics/{clinic_id}"
    owner = await login(api_client, agenda_scenario.owner_email)
    dentist = await login(api_client, agenda_scenario.dentist_email)

    professional = await mutate(
        api_client,
        "POST",
        f"{base_url}/professionals",
        owner,
        {
            "name": "Dra. Própria",
            "membership_id": str(agenda_scenario.dentist_membership_id),
            "cro_number": "12345",
            "cro_state": "BA",
        },
    )
    assert professional.status_code == 201
    professional_id = professional.json()["id"]
    foreign_professional = await mutate(
        api_client,
        "POST",
        f"{base_url}/professionals",
        owner,
        {"name": "Profissional sem vínculo"},
    )
    assert foreign_professional.status_code == 201
    room = await mutate(api_client, "POST", f"{base_url}/rooms", owner, {"name": "Consultório 1"})
    assert room.status_code == 201
    room_id = room.json()["id"]

    hours = [{"weekday": weekday, "starts_at": "08:00", "ends_at": "18:00"} for weekday in range(7)]
    configured = await mutate(
        api_client,
        "PUT",
        f"{base_url}/professionals/{professional_id}/working-hours",
        owner,
        {"intervals": hours},
    )
    assert configured.status_code == 200
    assert len(configured.json()["intervals"]) == 7

    first_start = future_local_start(2)
    availability = await read(
        api_client,
        f"{base_url}/availability?professional_id={professional_id}"
        f"&local_date={first_start.date().isoformat()}&duration_minutes=30"
        f"&patient_id={agenda_scenario.patient_id}&room_id={room_id}",
        owner,
    )
    assert availability.status_code == 200
    assert availability.json()["starts_at"]

    first_payload = {
        "patient_id": str(agenda_scenario.patient_id),
        "professional_id": professional_id,
        "room_id": room_id,
        "local_start": first_start.isoformat(timespec="minutes"),
        "duration_minutes": 30,
        "administrative_note": "Informação interna não registrada no histórico",
    }
    created = await mutate(api_client, "POST", f"{base_url}/appointments", owner, first_payload)
    assert created.status_code == 201
    appointment_id = created.json()["id"]
    assert created.json()["status"] == "SCHEDULED"
    assert created.json()["administrative_note"] == first_payload["administrative_note"]

    conflicting = await mutate(api_client, "POST", f"{base_url}/appointments", owner, first_payload)
    assert conflicting.status_code == 409

    race_payload = AppointmentCreateRequest(
        patient_id=agenda_scenario.patient_id,
        professional_id=uuid.UUID(professional_id),
        local_start=future_local_start(5, hour=15),
        duration_minutes=30,
    )
    race_context = TenantContext(user_id=agenda_scenario.owner_id, clinic_id=clinic_id)
    service = AgendaService(session_factory)
    race_results = await asyncio.gather(
        service.create_appointment(race_context, Role.OWNER, race_payload),
        service.create_appointment(race_context, Role.OWNER, race_payload),
        return_exceptions=True,
    )
    raced_successes = [result for result in race_results if not isinstance(result, BaseException)]
    raced_conflicts = [result for result in race_results if isinstance(result, ConflictError)]
    assert len(raced_successes) == 1
    assert len(raced_conflicts) == 1
    raced_appointment_id = raced_successes[0].id
    raced_cancelled = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments/{raced_appointment_id}/status",
        owner,
        {
            "expected_version": 1,
            "status": "CANCELLED",
            "cancellation_reason": "Reserva de concorrência do teste",
        },
    )
    assert raced_cancelled.status_code == 200

    out_of_scope = await mutate(
        api_client,
        "PATCH",
        f"{base_url}/appointments/{appointment_id}",
        dentist,
        {"expected_version": 1, "professional_id": foreign_professional.json()["id"]},
    )
    assert out_of_scope.status_code == 403

    transitions = (
        ("CONFIRMED", 1),
        ("CHECKED_IN", 2),
        ("IN_PROGRESS", 3),
        ("COMPLETED", 4),
    )
    for status_value, expected_version in transitions:
        response = await mutate(
            api_client,
            "POST",
            f"{base_url}/appointments/{appointment_id}/status",
            owner,
            {"expected_version": expected_version, "status": status_value},
        )
        assert response.status_code == 200
        assert response.json()["version"] == expected_version + 1
        assert response.json()["status"] == status_value

    stale_edit = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments/{appointment_id}/reschedule",
        owner,
        {
            "expected_version": 1,
            "local_start": (first_start + timedelta(days=1)).isoformat(timespec="minutes"),
            "duration_minutes": 30,
        },
    )
    assert stale_edit.status_code == 409

    history = await read(api_client, f"{base_url}/appointments/{appointment_id}/history", owner)
    assert history.status_code == 200
    assert history.json()["total"] == 5
    assert all(
        "administrative_note" not in item["old_values"]
        and "administrative_note" not in item["new_values"]
        for item in history.json()["items"]
    )

    second_start = future_local_start(3)
    second = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments",
        owner,
        {
            "patient_id": str(agenda_scenario.patient_id),
            "professional_id": professional_id,
            "local_start": second_start.isoformat(timespec="minutes"),
            "duration_minutes": 30,
        },
    )
    assert second.status_code == 201
    second_id = second.json()["id"]
    reduced_hours = await mutate(
        api_client,
        "PUT",
        f"{base_url}/professionals/{professional_id}/working-hours",
        owner,
        {
            "intervals": [
                {"weekday": weekday, "starts_at": "10:00", "ends_at": "18:00"}
                for weekday in range(7)
            ]
        },
    )
    assert reduced_hours.status_code == 409
    new_start = second_start + timedelta(days=1)
    rescheduled = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments/{second_id}/reschedule",
        owner,
        {
            "expected_version": 1,
            "local_start": new_start.isoformat(timespec="minutes"),
            "duration_minutes": 45,
        },
    )
    assert rescheduled.status_code == 200
    assert rescheduled.json()["id"] == second_id
    assert rescheduled.json()["status"] == "SCHEDULED"
    assert rescheduled.json()["version"] == 2
    cancelled = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments/{second_id}/status",
        owner,
        {
            "expected_version": 2,
            "status": "CANCELLED",
            "cancellation_reason": "Paciente solicitou cancelamento",
        },
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["cancellation_reason"] == "Paciente solicitou cancelamento"

    no_show_start = future_local_start(-1)
    no_show = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments",
        owner,
        {
            "patient_id": str(agenda_scenario.patient_id),
            "professional_id": professional_id,
            "local_start": no_show_start.isoformat(timespec="minutes"),
            "duration_minutes": 30,
        },
    )
    assert no_show.status_code == 201
    marked_absent = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments/{no_show.json()['id']}/status",
        owner,
        {"expected_version": 1, "status": "NO_SHOW"},
    )
    assert marked_absent.status_code == 200
    assert marked_absent.json()["status"] == "NO_SHOW"

    reduced_hours_after_resolution = await mutate(
        api_client,
        "PUT",
        f"{base_url}/professionals/{professional_id}/working-hours",
        owner,
        {
            "intervals": [
                {"weekday": weekday, "starts_at": "10:00", "ends_at": "18:00"}
                for weekday in range(7)
            ]
        },
    )
    assert reduced_hours_after_resolution.status_code == 200

    block_start = future_local_start(4, hour=14)
    block_end = block_start + timedelta(days=2, hours=1)
    block = await mutate(
        api_client,
        "POST",
        f"{base_url}/schedule-blocks",
        owner,
        {
            "room_id": room_id,
            "local_start": block_start.isoformat(timespec="minutes"),
            "local_end": block_end.isoformat(timespec="minutes"),
            "label": "Manutenção",
        },
    )
    assert block.status_code == 201
    overlap_with_block = await mutate(
        api_client,
        "POST",
        f"{base_url}/appointments",
        owner,
        {
            "patient_id": str(agenda_scenario.patient_id),
            "professional_id": foreign_professional.json()["id"],
            "room_id": room_id,
            "local_start": (block_start + timedelta(minutes=15)).isoformat(timespec="minutes"),
            "duration_minutes": 30,
        },
    )
    assert overlap_with_block.status_code == 409
    timezone_blocked = await mutate(
        api_client,
        "PATCH",
        f"{base_url}/settings",
        owner,
        {"timezone": "UTC"},
    )
    assert timezone_blocked.status_code == 409
    cancelled_block = await mutate(
        api_client,
        "POST",
        f"{base_url}/schedule-blocks/{block.json()['id']}/cancel",
        owner,
        {"reason": "Manutenção finalizada"},
    )
    assert cancelled_block.status_code == 200

    patient_history = await read(
        api_client,
        f"{base_url}/patients/{agenda_scenario.patient_id}/appointments?limit=100",
        dentist,
    )
    assert patient_history.status_code == 200
    assert patient_history.json()["total"] == 4

    appointment_row = await migrator_connection.fetchrow(
        """
        SELECT a.status, e.occupancy_state
        FROM app.appointments a
        JOIN app.schedule_events e ON e.clinic_id = a.clinic_id AND e.id = a.schedule_event_id
        WHERE a.id = $1
        """,
        uuid.UUID(appointment_id),
    )
    assert appointment_row["status"] == "COMPLETED"
    assert appointment_row["occupancy_state"] == "OCCUPYING"

    timezone_updated = await mutate(
        api_client,
        "PATCH",
        f"{base_url}/settings",
        owner,
        {"timezone": "UTC"},
    )
    assert timezone_updated.status_code == 200
