"""Tenant-aware structure tables for Marco 1.

Revision ID: 0003_tenant_structure
Revises: 0002_global_identity
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_tenant_structure"
down_revision: str | None = "0002_global_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"


def upgrade() -> None:
    op.create_table(
        "clinics",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", postgresql.CITEXT(), nullable=False),
        sa.Column("legal_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PROVISIONING'"), nullable=False),
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
            "status IN ('PROVISIONING', 'ACTIVE', 'SUSPENDED')", name=op.f("ck_clinics_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinics")),
        sa.UniqueConstraint("slug", name=op.f("uq_clinics_slug")),
        schema="app",
    )
    op.create_table(
        "clinic_settings",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'America/Bahia'"), nullable=False),
        sa.Column("locale", sa.Text(), server_default=sa.text("'pt-BR'"), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default=sa.text("'BRL'"), nullable=False),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
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
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["app.clinics.id"], name=op.f("fk_clinic_settings_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("clinic_id", name=op.f("pk_clinic_settings")),
        schema="app",
    )
    op.create_table(
        "clinic_feature_flags",
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_by_user_id", sa.Uuid(), nullable=True),
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
            ["changed_by_user_id"],
            ["app.users.id"],
            name=op.f("fk_clinic_feature_flags_changed_by_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"],
            ["app.clinics.id"],
            name=op.f("fk_clinic_feature_flags_clinic_id_clinics"),
        ),
        sa.PrimaryKeyConstraint("clinic_id", "key", name=op.f("pk_clinic_feature_flags")),
        schema="app",
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
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
            "role IN ('OWNER', 'ADMIN', 'DENTIST', 'ASSISTANT', 'RECEPTIONIST')",
            name=op.f("ck_memberships_role"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'SUSPENDED')", name=op.f("ck_memberships_status")
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["app.clinics.id"], name=op.f("fk_memberships_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app.users.id"], name=op.f("fk_memberships_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_memberships_clinic_id")),
        sa.UniqueConstraint("user_id", "clinic_id", name=op.f("uq_memberships_user_id")),
        schema="app",
    )
    op.create_table(
        "membership_invitations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
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
            ["clinic_id", "membership_id"],
            ["app.memberships.clinic_id", "app.memberships.id"],
            name=op.f("fk_membership_invitations_clinic_id_memberships"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_invitations")),
        sa.UniqueConstraint("clinic_id", "id", name=op.f("uq_membership_invitations_clinic_id")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_membership_invitations_token_hash")),
        schema="app",
    )
    op.create_table(
        "clinic_audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["app.users.id"],
            name=op.f("fk_clinic_audit_events_actor_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["app.clinics.id"], name=op.f("fk_clinic_audit_events_clinic_id_clinics")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clinic_audit_events")),
        schema="app",
    )

    op.execute(f"GRANT SELECT, UPDATE ON app.clinics TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE ON app.clinic_settings TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON app.clinic_feature_flags TO {APP_ROLE}")
    op.execute(f"GRANT SELECT ON app.memberships TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON app.membership_invitations TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON app.clinic_audit_events TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("clinic_audit_events", schema="app")
    op.drop_table("membership_invitations", schema="app")
    op.drop_table("memberships", schema="app")
    op.drop_table("clinic_feature_flags", schema="app")
    op.drop_table("clinic_settings", schema="app")
    op.drop_table("clinics", schema="app")
