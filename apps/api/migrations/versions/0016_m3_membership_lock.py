"""Lock an agenda membership without granting runtime membership updates.

Revision ID: 0016_m3_membership_lock
Revises: 0015_m3_schedule_blocks
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0016_m3_membership_lock"
down_revision: str | None = "0015_m3_schedule_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.lock_agenda_membership(p_clinic_id uuid, p_membership_id uuid)
        RETURNS uuid
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE v_membership_id uuid;
        BEGIN
          IF p_clinic_id IS NULL OR p_clinic_id::text IS DISTINCT FROM
              NULLIF(current_setting('app.current_clinic_id', true), '')
              OR NOT EXISTS (
                SELECT 1 FROM app.memberships m
                WHERE m.clinic_id = p_clinic_id
                  AND m.user_id::text = NULLIF(current_setting('app.current_user_id', true), '')
                  AND m.status = 'ACTIVE' AND m.role IN ('OWNER', 'ADMIN')
              ) THEN
            RAISE EXCEPTION 'not_permitted' USING ERRCODE = '42501';
          END IF;
          SELECT m.id INTO v_membership_id FROM app.memberships m
            WHERE m.clinic_id = p_clinic_id AND m.id = p_membership_id
            FOR UPDATE;
          RETURN v_membership_id;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.lock_agenda_membership(uuid, uuid) FROM PUBLIC")
    op.execute(
        "GRANT EXECUTE ON FUNCTION app.lock_agenda_membership(uuid, uuid) TO easydentist_app"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION app.lock_agenda_membership(uuid, uuid)")
