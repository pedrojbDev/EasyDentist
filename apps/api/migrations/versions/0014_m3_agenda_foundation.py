"""Shared clinic agenda foundation with RLS and immutable appointment history.

Revision ID: 0014_m3_agenda_foundation
Revises: 0013_m2_anamnesis_base_integrity
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_m3_agenda_foundation"
down_revision: str | None = "0013_m2_anamnesis_base_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"

TENANT_TABLES = (
    "agenda_professionals",
    "agenda_rooms",
    "professional_availabilities",
    "schedule_events",
    "appointments",
    "appointment_history",
)

TENANT_SCOPE = (
    "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

APP_POLICIES = (
    tuple((table, f"{table}_tenant_select") for table in TENANT_TABLES)
    + tuple((table, f"{table}_tenant_insert") for table in TENANT_TABLES)
    + tuple(
        (table, f"{table}_tenant_update")
        for table in TENANT_TABLES
        if table != "appointment_history"
    )
)


def upgrade() -> None:
    op.create_table(
        "agenda_professionals",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cro_number", sa.Text(), nullable=True),
        sa.Column("cro_state", sa.CHAR(length=2), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')", name=op.f("ck_agenda_professionals_status")
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name=op.f("ck_agenda_professionals_archived_at"),
        ),
        sa.CheckConstraint(
            "(cro_number IS NULL AND cro_state IS NULL) "
            "OR (cro_number IS NOT NULL AND cro_state IS NOT NULL)",
            name=op.f("ck_agenda_professionals_cro"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["app.clinics.id"],
            name=op.f("fk_agenda_professionals_clinic_id_clinics"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "membership_id"],
            ["app.memberships.clinic_id", "app.memberships.id"],
            name=op.f("fk_agenda_professionals_clinic_id_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agenda_professionals")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_agenda_professionals_clinic_id")),
        sa.UniqueConstraint(
            "clinic_id", "membership_id", name="uq_agenda_professionals_clinic_membership"
        ),
        schema="app",
    )
    op.create_index(
        "ix_agenda_professionals_clinic_id_status_name",
        "agenda_professionals",
        ["clinic_id", "status", "name"],
        schema="app",
    )
    op.create_table(
        "agenda_rooms",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name=op.f("ck_agenda_rooms_status")),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name=op.f("ck_agenda_rooms_archived_at"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["app.clinics.id"], name=op.f("fk_agenda_rooms_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agenda_rooms")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_agenda_rooms_clinic_id")),
        sa.UniqueConstraint("clinic_id", "name", name="uq_agenda_rooms_clinic_name"),
        schema="app",
    )
    op.create_table(
        "professional_availabilities",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("professional_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.Time(), nullable=False),
        sa.Column("ends_at", sa.Time(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_professional_availabilities_weekday")
        ),
        sa.CheckConstraint(
            "starts_at < ends_at", name=op.f("ck_professional_availabilities_time_range")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "professional_id"],
            ["app.agenda_professionals.clinic_id", "app.agenda_professionals.id"],
            name=op.f("fk_professional_availabilities_clinic_id_agenda_professionals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_professional_availabilities")),
        schema="app",
    )
    op.create_index(
        "ix_professional_availabilities_clinic_id_professional_id_weekday",
        "professional_availabilities",
        ["clinic_id", "professional_id", "weekday", "starts_at"],
        schema="app",
    )
    op.create_table(
        "schedule_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("professional_id", sa.Uuid(), nullable=True),
        sa.Column("patient_id", sa.Uuid(), nullable=True),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "occupancy_state", sa.Text(), server_default=sa.text("'OCCUPYING'"), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('APPOINTMENT', 'BLOCK')", name=op.f("ck_schedule_events_event_type")
        ),
        sa.CheckConstraint(
            "occupancy_state IN ('OCCUPYING', 'RELEASED')",
            name=op.f("ck_schedule_events_occupancy_state"),
        ),
        sa.CheckConstraint("starts_at < ends_at", name=op.f("ck_schedule_events_time_range")),
        sa.CheckConstraint(
            "(event_type = 'APPOINTMENT' AND professional_id IS NOT NULL "
            "AND patient_id IS NOT NULL) "
            "OR (event_type = 'BLOCK' AND patient_id IS NULL "
            "AND (professional_id IS NOT NULL OR room_id IS NOT NULL))",
            name=op.f("ck_schedule_events_resource_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "professional_id"],
            ["app.agenda_professionals.clinic_id", "app.agenda_professionals.id"],
            name=op.f("fk_schedule_events_clinic_id_agenda_professionals"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
            name=op.f("fk_schedule_events_clinic_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "room_id"],
            ["app.agenda_rooms.clinic_id", "app.agenda_rooms.id"],
            name=op.f("fk_schedule_events_clinic_id_agenda_rooms"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_schedule_events")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_schedule_events_clinic_id")),
        postgresql.ExcludeConstraint(
            ("clinic_id", "="),
            ("professional_id", "="),
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_professional_occupancy",
            using="gist",
            where=sa.text("professional_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),
        postgresql.ExcludeConstraint(
            ("clinic_id", "="),
            ("patient_id", "="),
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_patient_occupancy",
            using="gist",
            where=sa.text("patient_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),
        postgresql.ExcludeConstraint(
            ("clinic_id", "="),
            ("room_id", "="),
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            name="ex_schedule_events_room_occupancy",
            using="gist",
            where=sa.text("room_id IS NOT NULL AND occupancy_state = 'OCCUPYING'"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_schedule_events_clinic_id_starts_at",
        "schedule_events",
        ["clinic_id", "starts_at"],
        schema="app",
    )
    op.create_table(
        "appointments",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_event_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'SCHEDULED'"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("administrative_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('SCHEDULED', 'CONFIRMED', 'CHECKED_IN', 'IN_PROGRESS', "
            "'COMPLETED', 'CANCELLED', 'NO_SHOW')",
            name=op.f("ck_appointments_status"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_appointments_version")),
        sa.ForeignKeyConstraint(
            ["clinic_id", "schedule_event_id"],
            ["app.schedule_events.clinic_id", "app.schedule_events.id"],
            name=op.f("fk_appointments_clinic_id_schedule_events"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointments")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_appointments_clinic_id")),
        sa.UniqueConstraint(
            "clinic_id", "schedule_event_id", name="uq_appointments_schedule_event"
        ),
        schema="app",
    )
    op.create_index(
        "ix_appointments_clinic_id_status", "appointments", ["clinic_id", "status"], schema="app"
    )
    op.create_table(
        "appointment_history",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_id", sa.Uuid(), nullable=False),
        sa.Column("appointment_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "old_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "new_values",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('CREATED', 'RESCHEDULED', 'STATUS_CHANGED')",
            name=op.f("ck_appointment_history_event_type"),
        ),
        sa.CheckConstraint(
            "appointment_version >= 1", name=op.f("ck_appointment_history_appointment_version")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "appointment_id"],
            ["app.appointments.clinic_id", "app.appointments.id"],
            name=op.f("fk_appointment_history_clinic_id_appointments"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.id"],
            name=op.f("fk_appointment_history_actor_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_appointment_history")),
        sa.UniqueConstraint(
            "clinic_id",
            "appointment_id",
            "appointment_version",
            name=op.f("uq_appointment_history_clinic_id"),
        ),
        schema="app",
    )
    op.create_index(
        "ix_appointment_history_clinic_id_appointment_id_occurred_at",
        "appointment_history",
        ["clinic_id", "appointment_id", "occurred_at"],
        schema="app",
    )

    _create_integrity_triggers()
    _enable_row_security()
    _create_app_policies()

    for table in TENANT_TABLES:
        permissions = (
            "SELECT, INSERT" if table == "appointment_history" else "SELECT, INSERT, UPDATE"
        )
        op.execute(f"GRANT {permissions} ON app.{table} TO {APP_ROLE}")


def _create_integrity_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION app.lock_agenda_clinic_settings() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_clinic_id uuid;
        BEGIN
          v_clinic_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.clinic_id ELSE NEW.clinic_id END;
          PERFORM 1 FROM app.clinic_settings WHERE clinic_id = v_clinic_id FOR UPDATE;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'clinic_settings_required' USING ERRCODE = 'P0001';
          END IF;
          RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    for table in (
        "agenda_professionals",
        "agenda_rooms",
        "professional_availabilities",
        "schedule_events",
        "appointments",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_lock_clinic_settings "
            f"BEFORE INSERT OR UPDATE OR DELETE ON app.{table} "
            "FOR EACH ROW EXECUTE FUNCTION app.lock_agenda_clinic_settings()"
        )
    op.execute(
        """
        CREATE FUNCTION app.require_appointment_schedule_event() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_event_type text;
        BEGIN
          SELECT event_type INTO v_event_type
          FROM app.schedule_events
          WHERE clinic_id = NEW.clinic_id AND id = NEW.schedule_event_id;
          IF v_event_type IS DISTINCT FROM 'APPOINTMENT' THEN
            RAISE EXCEPTION 'appointment_schedule_event_invalid' USING ERRCODE = 'P0001';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER appointments_require_schedule_event
        BEFORE INSERT OR UPDATE OF clinic_id, schedule_event_id ON app.appointments
        FOR EACH ROW EXECUTE FUNCTION app.require_appointment_schedule_event()
        """
    )
    op.execute(
        """
        CREATE FUNCTION app.sync_appointment_occupancy() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          UPDATE app.schedule_events
          SET occupancy_state = CASE
              WHEN NEW.status IN ('CANCELLED', 'NO_SHOW') THEN 'RELEASED'
              ELSE 'OCCUPYING'
            END,
            updated_at = now()
          WHERE clinic_id = NEW.clinic_id AND id = NEW.schedule_event_id;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER appointments_sync_occupancy
        AFTER INSERT OR UPDATE OF status ON app.appointments
        FOR EACH ROW EXECUTE FUNCTION app.sync_appointment_occupancy()
        """
    )
    op.execute(
        """
        CREATE FUNCTION app.reject_appointment_history_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          RAISE EXCEPTION 'appointment_history_immutable'
            USING ERRCODE = 'P0001', HINT = 'Appointment history is append-only';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER appointment_history_immutable
        BEFORE UPDATE OR DELETE ON app.appointment_history
        FOR EACH ROW EXECUTE FUNCTION app.reject_appointment_history_mutation()
        """
    )
    op.execute(
        """
        CREATE FUNCTION app.reject_appointment_history_note() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          IF NEW.old_values ? 'administrative_note' OR NEW.new_values ? 'administrative_note' THEN
            RAISE EXCEPTION 'appointment_history_note_forbidden' USING ERRCODE = 'P0001';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER appointment_history_reject_note
        BEFORE INSERT OR UPDATE ON app.appointment_history
        FOR EACH ROW EXECUTE FUNCTION app.reject_appointment_history_note()
        """
    )
    op.execute(
        """
        CREATE FUNCTION app.reject_agenda_resource_deletion() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          RAISE EXCEPTION 'agenda_resource_immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    for table in ("agenda_professionals", "agenda_rooms"):
        op.execute(
            f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON app.{table} "
            "FOR EACH ROW EXECUTE FUNCTION app.reject_agenda_resource_deletion()"
        )
    for function in (
        "lock_agenda_clinic_settings()",
        "require_appointment_schedule_event()",
        "sync_appointment_occupancy()",
        "reject_appointment_history_mutation()",
        "reject_appointment_history_note()",
        "reject_agenda_resource_deletion()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION app.{function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{function} TO {APP_ROLE}")


def _enable_row_security() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_migrator_all ON app.{table} "
            f"FOR ALL TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)"
        )


def _create_app_policies() -> None:
    for table in TENANT_TABLES:
        op.execute(
            f"CREATE POLICY {table}_tenant_select ON app.{table} "
            f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
        )
        op.execute(
            f"CREATE POLICY {table}_tenant_insert ON app.{table} "
            f"FOR INSERT TO {APP_ROLE} WITH CHECK ({TENANT_SCOPE})"
        )
        if table != "appointment_history":
            op.execute(
                f"CREATE POLICY {table}_tenant_update ON app.{table} "
                f"FOR UPDATE TO {APP_ROLE} USING ({TENANT_SCOPE}) WITH CHECK ({TENANT_SCOPE})"
            )


def downgrade() -> None:
    for table, policy in APP_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.{table}")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_migrator_all ON app.{table}")
        op.execute(f"ALTER TABLE app.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} DISABLE ROW LEVEL SECURITY")
    for table in ("agenda_professionals", "agenda_rooms"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_delete ON app.{table}")
    op.execute("DROP TRIGGER IF EXISTS appointment_history_reject_note ON app.appointment_history")
    op.execute("DROP TRIGGER IF EXISTS appointment_history_immutable ON app.appointment_history")
    op.execute("DROP TRIGGER IF EXISTS appointments_sync_occupancy ON app.appointments")
    op.execute("DROP TRIGGER IF EXISTS appointments_require_schedule_event ON app.appointments")
    for table in (
        "agenda_professionals",
        "agenda_rooms",
        "professional_availabilities",
        "schedule_events",
        "appointments",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_lock_clinic_settings ON app.{table}")
    for function in (
        "reject_agenda_resource_deletion()",
        "reject_appointment_history_note()",
        "reject_appointment_history_mutation()",
        "sync_appointment_occupancy()",
        "require_appointment_schedule_event()",
        "lock_agenda_clinic_settings()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS app.{function}")
    op.drop_index(
        "ix_appointment_history_clinic_id_appointment_id_occurred_at",
        table_name="appointment_history",
        schema="app",
    )
    op.drop_table("appointment_history", schema="app")
    op.drop_index("ix_appointments_clinic_id_status", table_name="appointments", schema="app")
    op.drop_table("appointments", schema="app")
    op.drop_index(
        "ix_schedule_events_clinic_id_starts_at", table_name="schedule_events", schema="app"
    )
    op.drop_table("schedule_events", schema="app")
    op.drop_index(
        "ix_professional_availabilities_clinic_id_professional_id_weekday",
        table_name="professional_availabilities",
        schema="app",
    )
    op.drop_table("professional_availabilities", schema="app")
    op.drop_table("agenda_rooms", schema="app")
    op.drop_index(
        "ix_agenda_professionals_clinic_id_status_name",
        table_name="agenda_professionals",
        schema="app",
    )
    op.drop_table("agenda_professionals", schema="app")
