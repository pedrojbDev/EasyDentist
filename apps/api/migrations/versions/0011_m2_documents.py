"""Private patient document metadata with tenant isolation.

Revision ID: 0011_m2_documents
Revises: 0010_m2_anamnesis
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_m2_documents"
down_revision: str | None = "0010_m2_anamnesis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"

TENANT_SCOPE = (
    "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

APP_POLICIES = (
    ("patient_documents", "patient_documents_tenant_select"),
    ("patient_documents", "patient_documents_tenant_insert"),
    ("patient_documents", "patient_documents_tenant_update"),
)


def upgrade() -> None:
    op.create_table(
        "patient_documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("detected_mime", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
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
            "category IN ('ADMINISTRATIVE', 'CLINICAL')",
            name=op.f("ck_patient_documents_category"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')", name=op.f("ck_patient_documents_status")
        ),
        sa.CheckConstraint(
            "(status = 'ACTIVE' AND archived_at IS NULL) "
            "OR (status = 'ARCHIVED' AND archived_at IS NOT NULL)",
            name=op.f("ck_patient_documents_archived_at"),
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_patient_documents_size_bytes")),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_patient_documents_sha256")),
        sa.ForeignKeyConstraint(
            ["clinic_id", "patient_id"],
            ["app.patients.clinic_id", "app.patients.id"],
            name=op.f("fk_patient_documents_clinic_id_patients"),
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["app.users.id"],
            name=op.f("fk_patient_documents_uploaded_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient_documents")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_patient_documents_storage_key")),
        schema="app",
    )

    op.execute("ALTER TABLE app.patient_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.patient_documents FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY patient_documents_migrator_all ON app.patient_documents "
        f"FOR ALL TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)"
    )
    op.execute(
        f"CREATE POLICY patient_documents_tenant_select ON app.patient_documents "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY patient_documents_tenant_insert ON app.patient_documents "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY patient_documents_tenant_update ON app.patient_documents "
        f"FOR UPDATE TO {APP_ROLE} USING ({TENANT_SCOPE}) WITH CHECK ({TENANT_SCOPE})"
    )

    op.execute(f"GRANT SELECT, INSERT, UPDATE ON app.patient_documents TO {APP_ROLE}")


def downgrade() -> None:
    for table, policy in APP_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.{table}")
    op.execute("DROP POLICY IF EXISTS patient_documents_migrator_all ON app.patient_documents")
    op.execute("ALTER TABLE app.patient_documents NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE app.patient_documents DISABLE ROW LEVEL SECURITY")
    op.drop_table("patient_documents", schema="app")
