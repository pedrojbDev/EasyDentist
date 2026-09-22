"""Patient foundation tables with tenant isolation.

Revision ID: 0009_m2_patient_foundation
Revises: 0008_membership_management
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_m2_patient_foundation"
down_revision: str | None = "0008_membership_management"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"

TENANT_TABLES = ("patients", "patient_alerts")
OWNER_TABLES = ("professional_profiles",)

TENANT_SCOPE = (
    "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

OWNER_SCOPE = "user_id::text = NULLIF(current_setting('app.current_user_id', true), '')"

APP_POLICIES = (
    ("patients", "patients_tenant_select"),
    ("patients", "patients_tenant_insert"),
    ("patients", "patients_tenant_update"),
    ("patient_alerts", "patient_alerts_tenant_select"),
    ("patient_alerts", "patient_alerts_tenant_insert"),
    ("patient_alerts", "patient_alerts_tenant_update"),
    ("professional_profiles", "professional_profiles_owner_select"),
    ("professional_profiles", "professional_profiles_owner_insert"),
    ("professional_profiles", "professional_profiles_owner_update"),
)


def upgrade() -> None:
    op.create_table(
        "professional_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("professional_name", sa.Text(), nullable=False),
        sa.Column("cro_number", sa.Text(), nullable=False),
        sa.Column("cro_state", sa.CHAR(length=2), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_professional_profiles_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_professional_profiles")),
        schema="app",
    )
    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("social_name", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("cpf", sa.CHAR(length=11), nullable=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("phone_secondary", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("street", sa.Text(), nullable=True),
        sa.Column("number", sa.Text(), nullable=True),
        sa.Column("complement", sa.Text(), nullable=True),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("state", sa.CHAR(length=2), nullable=True),
        sa.Column("occupation", sa.Text(), nullable=True),
        sa.Column("nationality", sa.Text(), nullable=True),
        sa.Column("birthplace", sa.Text(), nullable=True),
        sa.Column("emergency_contact_name", sa.Text(), nullable=True),
        sa.Column("emergency_contact_relationship", sa.Text(), nullable=True),
        sa.Column("emergency_contact_phone", sa.Text(), nullable=True),
        sa.Column("guardian_name", sa.Text(), nullable=True),
        sa.Column("guardian_relationship", sa.Text(), nullable=True),
        sa.Column("guardian_phone", sa.Text(), nullable=True),
        sa.Column("administrative_notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name=op.f("ck_patients_status")),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name=op.f("ck_patients_archived_at"),
        ),
        sa.CheckConstraint(
            "birth_date <= CURRENT_DATE", name=op.f("ck_patients_birth_date_not_future")
        ),
        sa.CheckConstraint(
            "(emergency_contact_name IS NULL AND emergency_contact_relationship IS NULL "
            "AND emergency_contact_phone IS NULL) "
            "OR (emergency_contact_name IS NOT NULL AND emergency_contact_phone IS NOT NULL)",
            name=op.f("ck_patients_emergency_contact"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["app.clinics.id"], name=op.f("fk_patients_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patients")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_patients_clinic_id")),
        schema="app",
    )
    op.create_index(
        "ix_patients_clinic_id_cpf",
        "patients",
        ["clinic_id", "cpf"],
        unique=True,
        schema="app",
        postgresql_where=sa.text("cpf IS NOT NULL"),
    )
    op.create_table(
        "patient_alerts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
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
            "kind IN ('ALLERGY', 'MEDICATION', 'CLINICAL_RISK', 'OTHER')",
            name=op.f("ck_patient_alerts_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'RESOLVED')", name=op.f("ck_patient_alerts_status")
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND resolved_at IS NULL) "
            "OR (status = 'RESOLVED' AND resolved_at IS NOT NULL)",
            name=op.f("ck_patient_alerts_resolved_at"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
            name=op.f("fk_patient_alerts_clinic_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["app.users.id"],
            name=op.f("fk_patient_alerts_created_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_alerts")),
        schema="app",
    )

    _enable_row_security()
    _create_app_policies()

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.professional_profiles TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.patients TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.patient_alerts TO {APP_ROLE}")


def _enable_row_security() -> None:
    for table in (*TENANT_TABLES, *OWNER_TABLES):
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
        op.execute(
            f"CREATE POLICY {table}_tenant_update ON app.{table} "
            f"FOR UPDATE TO {APP_ROLE} USING ({TENANT_SCOPE}) WITH CHECK ({TENANT_SCOPE})"
        )
    op.execute(
        f"CREATE POLICY professional_profiles_owner_select ON app.professional_profiles "
        f"FOR SELECT TO {APP_ROLE} USING ({OWNER_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY professional_profiles_owner_insert ON app.professional_profiles "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({OWNER_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY professional_profiles_owner_update ON app.professional_profiles "
        f"FOR UPDATE TO {APP_ROLE} USING ({OWNER_SCOPE}) WITH CHECK ({OWNER_SCOPE})"
    )


def downgrade() -> None:
    for table, policy in APP_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.{table}")
    for table in (*TENANT_TABLES, *OWNER_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_migrator_all ON app.{table}")
        op.execute(f"ALTER TABLE app.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_patients_clinic_id_cpf", table_name="patients", schema="app")
    op.drop_table("patient_alerts", schema="app")
    op.drop_table("patients", schema="app")
    op.drop_table("professional_profiles", schema="app")
