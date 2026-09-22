"""Separate public schedule-block records from shared occupancy rows.

Revision ID: 0015_m3_schedule_blocks
Revises: 0014_m3_agenda_foundation
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_m3_schedule_blocks"
down_revision: str | None = "0014_m3_agenda_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"


def upgrade() -> None:
    op.add_column(
        "appointments", sa.Column("cancellation_reason", sa.Text(), nullable=True), schema="app"
    )
    op.create_table(
        "schedule_blocks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("schedule_event_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("status IN ('ACTIVE', 'CANCELLED')", name="ck_schedule_blocks_status"),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND cancelled_at IS NULL) "
            "OR (status = 'CANCELLED' AND cancelled_at IS NOT NULL)",
            name="ck_schedule_blocks_cancelled_at",
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "schedule_event_id"],
            ["app.schedule_events.clinic_id", "app.schedule_events.id"],
            name="fk_schedule_blocks_clinic_event",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_schedule_blocks"),
        sa.UniqueConstraint("clinic_id", "id", name="uq_schedule_blocks_clinic_id"),
        sa.UniqueConstraint("clinic_id", "schedule_event_id", name="uq_schedule_blocks_event"),
        schema="app",
    )
    op.create_index(
        "ix_schedule_blocks_clinic_id_status",
        "schedule_blocks",
        ["clinic_id", "status"],
        schema="app",
    )
    op.execute("ALTER TABLE app.schedule_blocks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.schedule_blocks FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY schedule_blocks_migrator_all ON app.schedule_blocks "
        f"FOR ALL TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)"
    )
    tenant_scope = (
        "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
        "AND app.is_active_member()"
    )
    op.execute(
        "CREATE POLICY schedule_blocks_tenant_select ON app.schedule_blocks "
        f"FOR SELECT TO {APP_ROLE} USING ({tenant_scope})"
    )
    op.execute(
        "CREATE POLICY schedule_blocks_tenant_insert ON app.schedule_blocks "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({tenant_scope})"
    )
    op.execute(
        "CREATE POLICY schedule_blocks_tenant_update ON app.schedule_blocks "
        f"FOR UPDATE TO {APP_ROLE} USING ({tenant_scope}) WITH CHECK ({tenant_scope})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.schedule_blocks TO {APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION app.require_block_schedule_event() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        DECLARE v_event_type text;
        BEGIN
          SELECT event_type INTO v_event_type
          FROM app.schedule_events
          WHERE clinic_id = NEW.clinic_id AND id = NEW.schedule_event_id;
          IF v_event_type IS DISTINCT FROM 'BLOCK' THEN
            RAISE EXCEPTION 'block_schedule_event_invalid' USING ERRCODE = 'P0001';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER schedule_blocks_require_event "
        "BEFORE INSERT OR UPDATE OF clinic_id, schedule_event_id ON app.schedule_blocks "
        "FOR EACH ROW EXECUTE FUNCTION app.require_block_schedule_event()"
    )
    op.execute(
        """
        CREATE FUNCTION app.sync_schedule_block_occupancy() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          UPDATE app.schedule_events
          SET occupancy_state = CASE
                WHEN NEW.status = 'CANCELLED' THEN 'RELEASED'
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
        "CREATE TRIGGER schedule_blocks_sync_occupancy "
        "AFTER INSERT OR UPDATE OF status ON app.schedule_blocks "
        "FOR EACH ROW EXECUTE FUNCTION app.sync_schedule_block_occupancy()"
    )
    op.execute(
        """
        CREATE FUNCTION app.guard_linked_block_schedule_event() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_status text;
          v_expected_occupancy text;
        BEGIN
          SELECT status INTO v_status
          FROM app.schedule_blocks
          WHERE clinic_id = NEW.clinic_id AND schedule_event_id = NEW.id;
          IF FOUND THEN
            IF NEW.event_type <> 'BLOCK' THEN
              RAISE EXCEPTION 'linked_block_event_type_invalid' USING ERRCODE = 'P0001';
            END IF;
            v_expected_occupancy := CASE
              WHEN v_status = 'CANCELLED' THEN 'RELEASED'
              ELSE 'OCCUPYING'
            END;
            IF NEW.occupancy_state <> v_expected_occupancy THEN
              RAISE EXCEPTION 'linked_block_occupancy_invalid' USING ERRCODE = 'P0001';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER schedule_events_guard_linked_block "
        "BEFORE UPDATE OF event_type, occupancy_state ON app.schedule_events "
        "FOR EACH ROW EXECUTE FUNCTION app.guard_linked_block_schedule_event()"
    )
    op.execute(
        """
        CREATE FUNCTION app.reject_schedule_block_deletion() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          RAISE EXCEPTION 'schedule_block_immutable' USING ERRCODE = 'P0001';
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER schedule_blocks_no_delete BEFORE DELETE ON app.schedule_blocks "
        "FOR EACH ROW EXECUTE FUNCTION app.reject_schedule_block_deletion()"
    )
    for function in (
        "require_block_schedule_event()",
        "sync_schedule_block_occupancy()",
        "guard_linked_block_schedule_event()",
        "reject_schedule_block_deletion()",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION app.{function} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION app.{function} TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS schedule_blocks_no_delete ON app.schedule_blocks")
    op.execute("DROP TRIGGER IF EXISTS schedule_events_guard_linked_block ON app.schedule_events")
    op.execute("DROP TRIGGER IF EXISTS schedule_blocks_sync_occupancy ON app.schedule_blocks")
    op.execute("DROP TRIGGER IF EXISTS schedule_blocks_require_event ON app.schedule_blocks")
    for function in (
        "reject_schedule_block_deletion()",
        "guard_linked_block_schedule_event()",
        "sync_schedule_block_occupancy()",
        "require_block_schedule_event()",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS app.{function}")
    for policy in (
        "schedule_blocks_tenant_select",
        "schedule_blocks_tenant_insert",
        "schedule_blocks_tenant_update",
        "schedule_blocks_migrator_all",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.schedule_blocks")
    op.execute("ALTER TABLE app.schedule_blocks NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.schedule_blocks DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_schedule_blocks_clinic_id_status", table_name="schedule_blocks", schema="app")
    op.drop_table("schedule_blocks", schema="app")
    op.drop_column("appointments", "cancellation_reason", schema="app")
