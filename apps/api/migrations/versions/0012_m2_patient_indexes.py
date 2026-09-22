"""Supporting indexes for patient listing and clinical alerts.

Revision ID: 0012_m2_patient_indexes
Revises: 0011_m2_documents
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_m2_patient_indexes"
down_revision: str | None = "0011_m2_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_patients_clinic_id_status_full_name",
        "patients",
        ["clinic_id", "status", "full_name"],
        schema="app",
    )
    op.create_index(
        "ix_patient_alerts_clinic_id_patient_id_created_at",
        "patient_alerts",
        ["clinic_id", "patient_id", "created_at"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_patient_alerts_clinic_id_patient_id_created_at",
        table_name="patient_alerts",
        schema="app",
    )
    op.drop_index(
        "ix_patients_clinic_id_status_full_name",
        table_name="patients",
        schema="app",
    )
