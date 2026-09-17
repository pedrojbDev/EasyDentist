"""Global identity tables for Marco 1.

Revision ID: 0002_global_identity
Revises: 0001_database_foundation
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_global_identity"
down_revision: str | None = "0001_database_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name=op.f("ck_users_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        schema="app",
    )
    op.create_table(
        "password_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app.users.id"],
            name=op.f("fk_password_credentials_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_password_credentials")),
        schema="app",
    )
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app.users.id"], name=op.f("fk_external_identities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_identities")),
        sa.UniqueConstraint("provider", "subject", name=op.f("uq_external_identities_provider")),
        schema="app",
    )
    op.create_table(
        "auth_rate_limit_buckets",
        sa.Column("bucket_key", sa.LargeBinary(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("bucket_key", name=op.f("pk_auth_rate_limit_buckets")),
        schema="app",
    )
    op.create_table(
        "auth_action_tokens",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')",
            name=op.f("ck_auth_action_tokens_purpose"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app.users.id"], name=op.f("fk_auth_action_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_action_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_action_tokens_token_hash")),
        schema="app",
    )
    op.create_table(
        "auth_audit_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
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
            ["user_id"], ["app.users.id"], name=op.f("fk_auth_audit_events_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_audit_events")),
        schema="app",
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_session_id"],
            ["app.auth_sessions.id"],
            name=op.f("fk_auth_sessions_replaced_by_session_id_auth_sessions"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app.users.id"], name=op.f("fk_auth_sessions_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_sessions_token_hash")),
        schema="app",
    )
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("recipient", postgresql.CITEXT(), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
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
            "status IN ('PENDING', 'SENT', 'FAILED')", name=op.f("ck_email_outbox_status")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_email_outbox_idempotency_key")),
        schema="app",
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE ON app.users, app.password_credentials, "
        "app.external_identities, app.auth_sessions, app.auth_action_tokens, "
        f"app.email_outbox TO {APP_ROLE}"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON app.auth_rate_limit_buckets TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON app.auth_audit_events TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("email_outbox", schema="app")
    op.drop_table("auth_sessions", schema="app")
    op.drop_table("auth_audit_events", schema="app")
    op.drop_table("auth_action_tokens", schema="app")
    op.drop_table("auth_rate_limit_buckets", schema="app")
    op.drop_table("external_identities", schema="app")
    op.drop_table("password_credentials", schema="app")
    op.drop_table("users", schema="app")
