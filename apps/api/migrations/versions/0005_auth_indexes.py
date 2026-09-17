"""Authentication indexes.

Revision ID: 0005_auth_indexes
Revises: 0004_rls_policies
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_auth_indexes"
down_revision: str | None = "0004_rls_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], schema="app")
    op.create_index(
        "ix_auth_action_tokens_user_id", "auth_action_tokens", ["user_id"], schema="app"
    )
    op.create_index(
        "ix_email_outbox_delivery", "email_outbox", ["status", "next_attempt_at"], schema="app"
    )


def downgrade() -> None:
    op.drop_index("ix_email_outbox_delivery", table_name="email_outbox", schema="app")
    op.drop_index("ix_auth_action_tokens_user_id", table_name="auth_action_tokens", schema="app")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions", schema="app")
