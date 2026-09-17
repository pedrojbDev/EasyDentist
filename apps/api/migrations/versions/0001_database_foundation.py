"""Establish the database migration baseline.

Revision ID: 0001_database_foundation
Revises:
Create Date: 2026-09-16
"""

from collections.abc import Sequence

revision: str = "0001_database_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create no domain objects; Alembic owns only its version table."""


def downgrade() -> None:
    """Remove no domain objects; this revision is an empty baseline."""
