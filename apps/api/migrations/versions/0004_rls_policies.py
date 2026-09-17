"""Row-level security policies and tenant context helpers.

Revision ID: 0004_rls_policies
Revises: 0003_tenant_structure
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_rls_policies"
down_revision: str | None = "0003_tenant_structure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"
MIGRATOR_ROLE = "easydentist_migrator"

TENANT_TABLES = (
    "clinics",
    "memberships",
    "clinic_settings",
    "clinic_feature_flags",
    "membership_invitations",
    "clinic_audit_events",
)

APP_POLICIES = (
    ("clinics", "clinics_user_select"),
    ("clinics", "clinics_tenant_update"),
    ("memberships", "memberships_user_select"),
    ("memberships", "memberships_tenant_select"),
    ("clinic_settings", "clinic_settings_tenant_select"),
    ("clinic_settings", "clinic_settings_tenant_update"),
    ("clinic_feature_flags", "clinic_feature_flags_tenant_select"),
    ("membership_invitations", "membership_invitations_tenant_select"),
    ("membership_invitations", "membership_invitations_tenant_insert"),
    ("clinic_audit_events", "clinic_audit_events_tenant_select"),
    ("clinic_audit_events", "clinic_audit_events_tenant_insert"),
)

TENANT_SCOPE = (
    "clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

CLINICS_TENANT_SCOPE = (
    "id::text = NULLIF(current_setting('app.current_clinic_id', true), '') "
    "AND app.is_active_member()"
)

USER_SCOPE_USER_ID = "user_id::text = NULLIF(current_setting('app.current_user_id', true), '')"


def _create_membership_function() -> None:
    op.execute(
        """
        CREATE FUNCTION app.is_active_member() RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
          SELECT EXISTS (
            SELECT 1 FROM app.memberships m
            WHERE m.clinic_id::text = NULLIF(current_setting('app.current_clinic_id', true), '')
              AND m.user_id::text   = NULLIF(current_setting('app.current_user_id', true), '')
              AND m.status = 'ACTIVE'
          );
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION app.is_active_member() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.is_active_member() TO {APP_ROLE}")


def _enable_tenant_row_security() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE app.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_migrator_all ON app.{table} "
            f"FOR ALL TO {MIGRATOR_ROLE} USING (true) WITH CHECK (true)"
        )


def _create_app_policies() -> None:
    op.execute(
        f"CREATE POLICY clinics_user_select ON app.clinics FOR SELECT TO {APP_ROLE} "
        "USING (EXISTS ("
        "SELECT 1 FROM app.memberships m "
        "WHERE m.clinic_id = clinics.id "
        "AND m.user_id::text = NULLIF(current_setting('app.current_user_id', true), '') "
        "AND m.status = 'ACTIVE'"
        "))"
    )
    op.execute(
        f"CREATE POLICY clinics_tenant_update ON app.clinics FOR UPDATE TO {APP_ROLE} "
        f"USING ({CLINICS_TENANT_SCOPE}) WITH CHECK ({CLINICS_TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY memberships_user_select ON app.memberships FOR SELECT TO {APP_ROLE} "
        f"USING ({USER_SCOPE_USER_ID})"
    )
    op.execute(
        f"CREATE POLICY memberships_tenant_select ON app.memberships FOR SELECT TO {APP_ROLE} "
        f"USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY clinic_settings_tenant_select ON app.clinic_settings "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY clinic_settings_tenant_update ON app.clinic_settings "
        f"FOR UPDATE TO {APP_ROLE} USING ({TENANT_SCOPE}) WITH CHECK ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY clinic_feature_flags_tenant_select ON app.clinic_feature_flags "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY membership_invitations_tenant_select ON app.membership_invitations "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY membership_invitations_tenant_insert ON app.membership_invitations "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY clinic_audit_events_tenant_select ON app.clinic_audit_events "
        f"FOR SELECT TO {APP_ROLE} USING ({TENANT_SCOPE})"
    )
    op.execute(
        f"CREATE POLICY clinic_audit_events_tenant_insert ON app.clinic_audit_events "
        f"FOR INSERT TO {APP_ROLE} WITH CHECK ({TENANT_SCOPE})"
    )


def upgrade() -> None:
    _create_membership_function()
    _enable_tenant_row_security()
    _create_app_policies()


def downgrade() -> None:
    for table, policy in APP_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {policy} ON app.{table}")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_migrator_all ON app.{table}")
        op.execute(f"ALTER TABLE app.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE app.{table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS app.is_active_member()")
