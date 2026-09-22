"""Versioned anamnesis table with immutability trigger and tenant isolation.

Revision ID: 0010_m2_anamnesis
Revises: 0009_m2_patient_foundation
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_m2_anamnesis"
down_revision: str | None = "0009_m2_patient_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"

TENANT_SCOPE = (
    "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

APP_POLICIES = (
    ("anamneses", "anamneses_tenant_select"),
    ("anamneses", "anamneses_tenant_insert"),
    ("anamneses", "anamneses_tenant_update"),
)


def upgrade() -> None:
    op.create_table(
        "anamneses",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'DRAFT'"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("template", sa.Text(), server_default=sa.text("'cfo_2026_v1'"), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("base_version_id", sa.Uuid(), nullable=True),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("author_professional_name", sa.Text(), nullable=True),
        sa.Column("author_cro_number", sa.Text(), nullable=True),
        sa.Column("author_cro_state", sa.CHAR(length=2), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("status IN ('DRAFT', 'FINAL')", name=op.f("ck_anamneses_status")),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND version_number IS NULL) "
            "OR (status = 'FINAL' AND version_number IS NOT NULL)",
            name=op.f("ck_anamneses_version_number"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND finalized_at IS NULL) "
            "OR (status = 'FINAL' AND finalized_at IS NOT NULL)",
            name=op.f("ck_anamneses_finalized_at"),
        ),
        sa.CheckConstraint(
            "(status = 'DRAFT' AND author_professional_name IS NULL "
            "AND author_cro_number IS NULL AND author_cro_state IS NULL) "
            "OR (status = 'FINAL' AND author_professional_name IS NOT NULL "
            "AND author_cro_number IS NOT NULL AND author_cro_state IS NOT NULL)",
            name=op.f("ck_anamneses_author_snapshot"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
            name=op.f("fk_anamneses_clinic_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "base_version_id"],
            ["app.anamneses.clinic_id", "app.anamneses.id"],
            name=op.f("fk_anamneses_clinic_id_anamneses"),
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["app.users.id"],
            name=op.f("fk_anamneses_author_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anamneses")),
        sa.UniqueConstraint("clinic_id", "id", name="uq_anamneses_clinic_id"),
        sa.UniqueConstraint(
            "clinic_id", "patient_id", "version_number", name="uq_anamneses_patient_version"
        ),
        schema="app",
    )
    op.create_index(
        "uq_anamneses_draft_per_patient",
        "anamneses",
        ["clinic_id", "patient_id"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("status = 'DRAFT'"),
    )

    op.execute(
        """
        CREATE FUNCTION app.reject_final_anamnesis_mutation() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        BEGIN
          RAISE EXCEPTION 'anamnesis_final_immutable'
            USING ERRCODE = 'P0001',
                  HINT = 'Final anamnesis versions cannot be changed or removed';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER anamneses_final_immutable
        BEFORE UPDATE OR DELETE ON app.anamneses
        FOR EACH ROW WHEN (OLD.status = 'FINAL')
        EXECUTE FUNCTION app.reject_final_anamnesis_mutation()
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.reject_final_anamnesis_mutation() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.reject_final_anamnesis_mutation() TO {APP_ROLE}")

    op.execute("ALTER TABLE app.anamneses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.anamneses FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY anamneses_migrator_all ON app.anamneses "
        f"FOR ALL TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)"
    )
    op.execute(
        f"CREATE POLICY anamneses_tenant_select ON app.anamneses "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY anamneses_tenant_insert ON app.anamneses "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY anamneses_tenant_update ON app.anamneses "
        f"FOR UPDATE TO {APP_ROLE} USING ({TENANT_SCOPE}) WITH CHECK ({TENANT_SCOPE})"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.anamneses TO {APP_ROLE}")


def downgrade() -> None:
    for table, policy in APP_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.{table}")
    op.execute("DROP POLICY IF EXISTS anamneses_migrator_all ON app.anamneses")
    op.execute("ALTER TABLE app.anamneses NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.anamneses DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TRIGGER IF EXISTS anamneses_final_immutable ON app.anamneses")
    op.execute("DROP FUNCTION IF EXISTS app.reject_final_anamnesis_mutation()")
    op.drop_index("uq_anamneses_draft_per_patient", table_name="anamneses", schema="app")
    op.drop_table("anamneses", schema="app")
