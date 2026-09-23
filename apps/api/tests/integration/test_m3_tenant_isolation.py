"""Cross-tenant isolation gate for M3 agenda resources and schedule records."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

import asyncpg
import httpx
import pytest
from conftest import SeededTenants
from helpers import insert_patient
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.appointments.repositories.resource_repository import AgendaResourceRepository
from app.appointments.schedule_service import AgendaService
from app.appointments.schemas import (
    AgendaListParams,
    AgendaResourceStatus,
    ScheduleBlockCancelRequest,
    ScheduleBlockListParams,
)
from app.auth.sessions import SessionService
from app.auth.settings import AuthSettings
from app.clinics.rbac import Role
from app.core.context import TenantContext
from app.core.database import create_session_factory
from app.core.errors import NotFoundError
from app.core.tenancy import tenant_transaction

SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"
M3_TENANT_TABLES = (
    "agenda_professionals",
    "agenda_rooms",
    "professional_availabilities",
    "schedule_events",
    "schedule_blocks",
    "appointments",
    "appointment_history",
)


@dataclass(frozen=True, slots=True)
class ClinicAgendaRows:
    clinic_id: uuid.UUID
    professional_id: uuid.UUID
    room_id: uuid.UUID
    availability_id: uuid.UUID
    patient_id: uuid.UUID
    appointment_event_id: uuid.UUID
    appointment_id: uuid.UUID
    history_id: uuid.UUID
    block_event_id: uuid.UUID
    block_id: uuid.UUID

    def ids_by_table(self) -> dict[str, tuple[uuid.UUID, ...]]:
        return {
            "agenda_professionals": (self.professional_id,),
            "agenda_rooms": (self.room_id,),
            "professional_availabilities": (self.availability_id,),
            "schedule_events": (self.appointment_event_id, self.block_event_id),
            "schedule_blocks": (self.block_id,),
            "appointments": (self.appointment_id,),
            "appointment_history": (self.history_id,),
        }


@dataclass(frozen=True, slots=True)
class M3AgendaRows:
    clinic_a: ClinicAgendaRows
    clinic_b: ClinicAgendaRows
    starts_at: datetime
    window_starts_at: datetime
    window_ends_at: datetime


async def _seed_clinic_agenda_rows(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    user_id: uuid.UUID,
    label: str,
    starts_at: datetime,
) -> ClinicAgendaRows:
    professional_id = await connection.fetchval(
        "INSERT INTO app.agenda_professionals (clinic_id, name) VALUES ($1, $2) RETURNING id",
        clinic_id,
        f"Profissional {label}",
    )
    room_id = await connection.fetchval(
        "INSERT INTO app.agenda_rooms (clinic_id, name) VALUES ($1, $2) RETURNING id",
        clinic_id,
        f"Sala {label}",
    )
    availability_id = await connection.fetchval(
        "INSERT INTO app.professional_availabilities "
        "(clinic_id, professional_id, weekday, starts_at, ends_at) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        clinic_id,
        professional_id,
        starts_at.weekday(),
        time(8),
        time(17),
    )
    patient_id = await insert_patient(
        connection,
        clinic_id=clinic_id,
        full_name=f"Paciente {label}",
        phone=f"+557190000{label}",
    )
    appointment_event_id = await connection.fetchval(
        "INSERT INTO app.schedule_events "
        "(clinic_id, event_type, professional_id, patient_id, room_id, starts_at, ends_at) "
        "VALUES ($1, 'APPOINTMENT', $2, $3, $4, $5, $6) RETURNING id",
        clinic_id,
        professional_id,
        patient_id,
        room_id,
        starts_at,
        starts_at + timedelta(minutes=30),
    )
    appointment_id = await connection.fetchval(
        "INSERT INTO app.appointments (clinic_id, schedule_event_id) VALUES ($1, $2) RETURNING id",
        clinic_id,
        appointment_event_id,
    )
    history_id = await connection.fetchval(
        "INSERT INTO app.appointment_history "
        "(clinic_id, appointment_id, appointment_version, event_type, actor_user_id) "
        "VALUES ($1, $2, 1, 'CREATED', $3) RETURNING id",
        clinic_id,
        appointment_id,
        user_id,
    )
    block_start = starts_at + timedelta(hours=3)
    block_event_id = await connection.fetchval(
        "INSERT INTO app.schedule_events "
        "(clinic_id, event_type, professional_id, room_id, starts_at, ends_at) "
        "VALUES ($1, 'BLOCK', $2, $3, $4, $5) RETURNING id",
        clinic_id,
        professional_id,
        room_id,
        block_start,
        block_start + timedelta(hours=1),
    )
    block_id = await connection.fetchval(
        "INSERT INTO app.schedule_blocks (clinic_id, schedule_event_id, label) "
        "VALUES ($1, $2, $3) RETURNING id",
        clinic_id,
        block_event_id,
        f"Bloqueio {label}",
    )
    return ClinicAgendaRows(
        clinic_id=clinic_id,
        professional_id=professional_id,
        room_id=room_id,
        availability_id=availability_id,
        patient_id=patient_id,
        appointment_event_id=appointment_event_id,
        appointment_id=appointment_id,
        history_id=history_id,
        block_event_id=block_event_id,
        block_id=block_id,
    )


@pytest.fixture
async def m3_agenda_rows(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> AsyncIterator[M3AgendaRows]:
    starts_at = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=15)
    clinic_a = await _seed_clinic_agenda_rows(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_a,
        user_id=seeded_tenants.user_a,
        label="A",
        starts_at=starts_at,
    )
    clinic_b = await _seed_clinic_agenda_rows(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_b,
        user_id=seeded_tenants.user_b,
        label="B",
        starts_at=starts_at,
    )
    yield M3AgendaRows(
        clinic_a=clinic_a,
        clinic_b=clinic_b,
        starts_at=starts_at,
        window_starts_at=starts_at - timedelta(days=1),
        window_ends_at=starts_at + timedelta(days=1),
    )


def _session_headers(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


async def _api_get(
    client: httpx.AsyncClient,
    url: str,
    token: str,
    *,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    response = await client.get(url, params=params, headers=_session_headers(token))
    client.cookies.clear()
    return response


async def _api_mutate(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    payload: dict[str, object],
) -> httpx.Response:
    csrf_response = await client.get("/api/v1/auth/csrf", headers=_session_headers(token))
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


@pytest.mark.anyio
async def test_m3_api_hides_valid_foreign_clinic_rows(
    api_client: httpx.AsyncClient,
    auth_settings: AuthSettings,
    session_factory: async_sessionmaker,
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    m3_agenda_rows: M3AgendaRows,
) -> None:
    sessions = SessionService(session_factory, auth_settings)
    session_ids: list[uuid.UUID] = []
    tokens: dict[uuid.UUID, str] = {}
    for user_id in (seeded_tenants.user_a, seeded_tenants.user_b):
        session_id, token = await sessions.create(user_id)
        session_ids.append(session_id)
        tokens[user_id] = token

    try:
        pairs = (
            (m3_agenda_rows.clinic_a, m3_agenda_rows.clinic_b, tokens[seeded_tenants.user_a]),
            (m3_agenda_rows.clinic_b, m3_agenda_rows.clinic_a, tokens[seeded_tenants.user_b]),
        )
        range_params = {
            "starts_at": m3_agenda_rows.window_starts_at.isoformat(),
            "ends_at": m3_agenda_rows.window_ends_at.isoformat(),
        }
        for own, foreign, token in pairs:
            root = f"/api/v1/clinics/{own.clinic_id}"
            professionals = await _api_get(api_client, f"{root}/professionals", token)
            rooms = await _api_get(api_client, f"{root}/rooms", token)
            blocks = await _api_get(
                api_client, f"{root}/schedule-blocks", token, params=range_params
            )
            appointments = await _api_get(
                api_client, f"{root}/appointments", token, params=range_params
            )
            assert professionals.status_code == rooms.status_code == 200
            assert blocks.status_code == appointments.status_code == 200
            assert [item["id"] for item in professionals.json()["items"]] == [
                str(own.professional_id)
            ]
            assert [item["id"] for item in rooms.json()["items"]] == [str(own.room_id)]
            assert [item["id"] for item in blocks.json()["items"]] == [str(own.block_id)]
            assert [item["id"] for item in appointments.json()["items"]] == [
                str(own.appointment_id)
            ]

            own_hours = await _api_get(
                api_client,
                f"{root}/professionals/{own.professional_id}/working-hours",
                token,
            )
            foreign_hours = await _api_get(
                api_client,
                f"{root}/professionals/{foreign.professional_id}/working-hours",
                token,
            )
            assert own_hours.status_code == 200
            assert own_hours.json()["professional_id"] == str(own.professional_id)
            assert foreign_hours.status_code == 404

            foreign_paths = (
                f"{root}/professionals/{foreign.professional_id}",
                f"{root}/rooms/{foreign.room_id}",
                f"{root}/appointments/{foreign.appointment_id}",
                f"{root}/appointments/{foreign.appointment_id}/history",
            )
            for path in foreign_paths:
                response = await _api_get(api_client, path, token)
                assert response.status_code == 404, path
                assert str(foreign.clinic_id) not in response.text, path
                assert str(foreign.appointment_id) not in response.text, path

            own_history = await _api_get(
                api_client, f"{root}/appointments/{own.appointment_id}/history", token
            )
            assert own_history.status_code == 200
            assert [item["id"] for item in own_history.json()["items"]] == [str(own.history_id)]

            foreign_block_update = await _api_mutate(
                api_client,
                "PATCH",
                f"{root}/schedule-blocks/{foreign.block_id}",
                token,
                {"label": "tentativa cross-tenant"},
            )
            foreign_appointment_update = await _api_mutate(
                api_client,
                "PATCH",
                f"{root}/appointments/{foreign.appointment_id}",
                token,
                {"expected_version": 1, "administrative_note": "tentativa cross-tenant"},
            )
            assert foreign_block_update.status_code == 404
            assert foreign_appointment_update.status_code == 404

            foreign_clinic_routes = (
                (f"/api/v1/clinics/{foreign.clinic_id}/professionals", None),
                (f"/api/v1/clinics/{foreign.clinic_id}/rooms", None),
                (f"/api/v1/clinics/{foreign.clinic_id}/schedule-blocks", range_params),
                (f"/api/v1/clinics/{foreign.clinic_id}/appointments", range_params),
            )
            for path, params in foreign_clinic_routes:
                response = await _api_get(api_client, path, token, params=params)
                assert response.status_code == 404, path
    finally:
        await migrator_connection.execute(
            "DELETE FROM app.auth_sessions WHERE id = ANY($1::uuid[])", session_ids
        )


@pytest.mark.anyio
async def test_m3_repository_and_service_reads_are_tenant_scoped(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    m3_agenda_rows: M3AgendaRows,
) -> None:
    session_factory = create_session_factory(app_engine)
    service = AgendaService(session_factory)
    range_args = {
        "starts_at": m3_agenda_rows.window_starts_at,
        "ends_at": m3_agenda_rows.window_ends_at,
    }
    contexts = (
        (
            TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a),
            m3_agenda_rows.clinic_a,
            m3_agenda_rows.clinic_b,
        ),
        (
            TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b),
            m3_agenda_rows.clinic_b,
            m3_agenda_rows.clinic_a,
        ),
    )
    for context, own, foreign in contexts:
        async with tenant_transaction(session_factory, context) as session:
            repository = AgendaResourceRepository(session)
            professionals, professional_total = await repository.list_professionals(
                context,
                status=AgendaResourceStatus.ACTIVE,
                limit=20,
                offset=0,
            )
            rooms, room_total = await repository.list_rooms(
                context,
                status=AgendaResourceStatus.ACTIVE,
                limit=20,
                offset=0,
            )
            assert professional_total == room_total == 1
            assert [item.id for item in professionals] == [own.professional_id]
            assert [item.id for item in rooms] == [own.room_id]
            assert await repository.get_professional(context, foreign.professional_id) is None
            assert await repository.get_room(context, foreign.room_id) is None

        # Schedule records are currently queried through AgendaService's
        # tenant_transaction read methods rather than a separate repository.
        appointments = await service.list_appointments(context, AgendaListParams(**range_args))
        blocks = await service.list_schedule_blocks(context, ScheduleBlockListParams(**range_args))
        history = await service.appointment_history(context, own.appointment_id)
        assert [item.id for item in appointments.items] == [own.appointment_id]
        assert [item.id for item in blocks.items] == [own.block_id]
        assert [item.id for item in history.items] == [own.history_id]

        with pytest.raises(NotFoundError):
            await service.get_appointment(context, foreign.appointment_id)
        with pytest.raises(NotFoundError):
            await service.appointment_history(context, foreign.appointment_id)
        with pytest.raises(NotFoundError):
            await service.working_hours(context, foreign.professional_id)
        with pytest.raises(NotFoundError):
            await service.cancel_schedule_block(
                context, Role.OWNER, foreign.block_id, ScheduleBlockCancelRequest()
            )


@pytest.mark.anyio
async def test_m3_runtime_role_sql_only_sees_rows_for_current_tenant(
    app_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    m3_agenda_rows: M3AgendaRows,
) -> None:
    cases = (
        (
            seeded_tenants.user_a,
            seeded_tenants.clinic_a,
            m3_agenda_rows.clinic_a,
            m3_agenda_rows.clinic_b,
        ),
        (
            seeded_tenants.user_b,
            seeded_tenants.clinic_b,
            m3_agenda_rows.clinic_b,
            m3_agenda_rows.clinic_a,
        ),
    )
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true)", str(seeded_tenants.user_a)
        )
        for table in M3_TENANT_TABLES:
            rows = await app_connection.fetch(f"SELECT id FROM app.{table}")
            assert rows == [], table
    finally:
        await transaction.rollback()

    for user_id, clinic_id, own, foreign in cases:
        transaction = app_connection.transaction()
        await transaction.start()
        try:
            await app_connection.execute(
                "SELECT set_config('app.current_user_id', $1, true), "
                "set_config('app.current_clinic_id', $2, true)",
                str(user_id),
                str(clinic_id),
            )
            own_ids = own.ids_by_table()
            foreign_ids = foreign.ids_by_table()
            for table in M3_TENANT_TABLES:
                visible = await app_connection.fetch(f"SELECT id FROM app.{table}")
                assert {row["id"] for row in visible} == set(own_ids[table]), table
                foreign_visible = await app_connection.fetch(
                    f"SELECT id FROM app.{table} WHERE id = ANY($1::uuid[])",
                    list(foreign_ids[table]),
                )
                assert foreign_visible == [], table
        finally:
            await transaction.rollback()
