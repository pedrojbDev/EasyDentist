from __future__ import annotations

import uuid

import asyncpg
import pytest
from conftest import SeededTenants

M3_TABLES = (
    "agenda_professionals",
    "agenda_rooms",
    "professional_availabilities",
    "schedule_events",
    "appointments",
    "appointment_history",
)


@pytest.mark.anyio
async def test_m3_agenda_tables_force_tenant_rls_and_expose_no_delete_to_runtime(
    admin_connection: asyncpg.Connection,
) -> None:
    # This catches an agenda table that is created without fail-closed tenant
    # isolation or with a runtime physical-delete capability.
    rows = await admin_connection.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               has_table_privilege('easydentist_app', c.oid, 'DELETE') AS can_delete
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND c.relname = ANY($1::text[])
        """,
        list(M3_TABLES),
    )

    actual = {
        row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"], row["can_delete"])
        for row in rows
    }
    assert set(actual) == set(M3_TABLES)
    assert all(state == (True, True, False) for state in actual.values())


@pytest.mark.anyio
async def test_m3_occupancy_constraints_use_half_open_ranges(
    admin_connection: asyncpg.Connection,
) -> None:
    # This catches losing one resource constraint or changing `[)` into a range
    # that rejects legal adjacent bookings.
    rows = await admin_connection.fetch(
        """
        SELECT conname, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = 'app.schedule_events'::regclass AND contype = 'x'
        """
    )
    constraints = {row["conname"]: row["definition"] for row in rows}

    assert set(constraints) == {
        "ex_schedule_events_professional_occupancy",
        "ex_schedule_events_patient_occupancy",
        "ex_schedule_events_room_occupancy",
    }
    for definition in constraints.values():
        assert "tstzrange(starts_at, ends_at, '[)'::text)" in definition
        assert "occupancy_state = 'OCCUPYING'" in definition


@pytest.mark.anyio
async def test_m3_history_is_append_only_and_excludes_administrative_notes(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
) -> None:
    # This catches a trigger omission that lets history be rewritten/deleted or
    # leaks administrative appointment notes into audit snapshots.
    transaction = migrator_connection.transaction()
    await transaction.start()
    try:
        professional_id = uuid.uuid4()
        await migrator_connection.execute(
            "INSERT INTO app.agenda_professionals (id, clinic_id, name) "
            "VALUES ($1, $2, 'Dr. Test')",
            professional_id,
            seeded_tenants.clinic_a,
        )
        patient_id = await migrator_connection.fetchval(
            """
            INSERT INTO app.patients (clinic_id, full_name, birth_date, phone)
            VALUES ($1, 'Patient Test', CURRENT_DATE - 1, '5500000000000')
            RETURNING id
            """,
            seeded_tenants.clinic_a,
        )
        event_id = await migrator_connection.fetchval(
            """
            INSERT INTO app.schedule_events
              (clinic_id, event_type, professional_id, patient_id, starts_at, ends_at)
            VALUES ($1, 'APPOINTMENT', $2, $3, now() + interval '1 day',
                    now() + interval '1 day 30 minutes')
            RETURNING id
            """,
            seeded_tenants.clinic_a,
            professional_id,
            patient_id,
        )
        appointment_id = await migrator_connection.fetchval(
            """
            INSERT INTO app.appointments (clinic_id, schedule_event_id)
            VALUES ($1, $2) RETURNING id
            """,
            seeded_tenants.clinic_a,
            event_id,
        )
        history_id = await migrator_connection.fetchval(
            """
            INSERT INTO app.appointment_history
              (clinic_id, appointment_id, appointment_version, event_type, actor_user_id)
            VALUES ($1, $2, 1, 'CREATED', $3)
            RETURNING id
            """,
            seeded_tenants.clinic_a,
            appointment_id,
            seeded_tenants.user_a,
        )

        with pytest.raises(asyncpg.RaiseError, match="appointment_history_immutable"):
            await migrator_connection.execute(
                "UPDATE app.appointment_history SET event_type = 'RESCHEDULED' WHERE id = $1",
                history_id,
            )
        with pytest.raises(asyncpg.RaiseError, match="appointment_history_immutable"):
            await migrator_connection.execute(
                "DELETE FROM app.appointment_history WHERE id = $1", history_id
            )
        with pytest.raises(asyncpg.RaiseError, match="appointment_history_note_forbidden"):
            await migrator_connection.execute(
                """
                INSERT INTO app.appointment_history
                  (clinic_id, appointment_id, appointment_version, event_type,
                   actor_user_id, new_values)
                VALUES ($1, $2, 2, 'STATUS_CHANGED', $3, '{"administrative_note":"private"}'::jsonb)
                """,
                seeded_tenants.clinic_a,
                appointment_id,
                seeded_tenants.user_a,
            )
    finally:
        await transaction.rollback()
