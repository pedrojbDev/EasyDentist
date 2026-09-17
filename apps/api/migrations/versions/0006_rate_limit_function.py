"""Atomic rate limit consumption function.

Revision ID: 0006_rate_limit_function
Revises: 0005_auth_indexes
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_rate_limit_function"
down_revision: str | None = "0005_auth_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.consume_rate_limit(
          p_bucket_key bytea, p_max_attempts int, p_window_seconds int
        ) RETURNS TABLE (allowed boolean, retry_after_seconds int)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_row app.auth_rate_limit_buckets%ROWTYPE;
          v_now timestamptz := now();
        BEGIN
          INSERT INTO app.auth_rate_limit_buckets AS b
            (bucket_key, attempt_count, window_started_at, blocked_until)
          VALUES (p_bucket_key, 1, v_now, NULL)
          ON CONFLICT (bucket_key) DO UPDATE SET
            attempt_count = CASE
              WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds)
                THEN 1
              ELSE b.attempt_count + 1
            END,
            window_started_at = CASE
              WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds)
                THEN v_now
              ELSE b.window_started_at
            END,
            blocked_until = CASE
              WHEN (CASE
                     WHEN b.window_started_at < v_now - make_interval(secs => p_window_seconds)
                       THEN 1
                     ELSE b.attempt_count + 1
                   END) > p_max_attempts
              THEN v_now + least(
                     make_interval(secs => 30 * power(2, b.attempt_count - p_max_attempts)),
                     interval '15 minutes')
              ELSE b.blocked_until
            END
          RETURNING * INTO v_row;

          IF v_row.blocked_until IS NOT NULL AND v_row.blocked_until > v_now THEN
            RETURN QUERY SELECT false,
              ceil(extract(epoch FROM (v_row.blocked_until - v_now)))::int;
            RETURN;
          END IF;
          RETURN QUERY SELECT true, 0;
        END;
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.consume_rate_limit(bytea, int, int) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.consume_rate_limit(bytea, int, int) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.consume_rate_limit(bytea, int, int)")
