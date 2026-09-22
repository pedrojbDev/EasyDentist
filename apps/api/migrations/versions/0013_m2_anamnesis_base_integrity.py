"""Database-level integrity for anamnesis revision bases.

Revision ID: 0013_m2_anamnesis_base_integrity
Revises: 0012_m2_patient_indexes
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_m2_anamnesis_base_integrity"
down_revision: str | None = "0012_m2_patient_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
BASE_FK = "fk_anamneses_clinic_id_anamneses"
BASE_UNIQUE = "uq_anamneses_clinic_id_patient_id"


def upgrade() -> None:
    op.create_unique_constraint(
        BASE_UNIQUE,
        "anamneses",
        ["clinic_id", "patient_id", "id"],
        schema="app",
    )
    op.drop_constraint(BASE_FK, "anamneses", schema="app", type_="foreignkey")
    op.create_foreign_key(
        BASE_FK,
        "anamneses",
        "anamneses",
        ["clinic_id", "patient_id", "base_version_id"],
        ["clinic_id", "patient_id", "id"],
        source_schema="app",
        referent_schema="app",
    )

    op.execute(
        """
        CREATE FUNCTION app.require_final_anamnesis_base() RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_status text;
        BEGIN
          IF NEW.base_version_id IS NULL THEN
            RETURN NEW;
          END IF;
          SELECT a.status INTO v_status
            FROM app.anamneses a
            WHERE a.clinic_id = NEW.clinic_id AND a.id = NEW.base_version_id;
          IF v_status IS NOT NULL AND v_status <> 'FINAL' THEN
            RAISE EXCEPTION 'anamnesis_base_not_final'
              USING ERRCODE = 'P0001',
                    HINT = 'Revisions can only be based on a final version';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER anamneses_require_final_base
        BEFORE INSERT OR UPDATE OF base_version_id ON app.anamneses
        FOR EACH ROW EXECUTE FUNCTION app.require_final_anamnesis_base()
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.require_final_anamnesis_base() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.require_final_anamnesis_base() TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS anamneses_require_final_base ON app.anamneses")
    op.execute("DROP FUNCTION IF EXISTS app.require_final_anamnesis_base()")
    op.drop_constraint(BASE_FK, "anamneses", schema="app", type_="foreignkey")
    op.create_foreign_key(
        BASE_FK,
        "anamneses",
        "anamneses",
        ["clinic_id", "base_version_id"],
        ["clinic_id", "id"],
        source_schema="app",
        referent_schema="app",
    )
    op.drop_constraint(BASE_UNIQUE, "anamneses", schema="app", type_="unique")
