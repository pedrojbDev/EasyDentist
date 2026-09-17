"""Invitation provisioning and acceptance functions.

Revision ID: 0007_invitation_functions
Revises: 0006_rate_limit_function
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_invitation_functions"
down_revision: str | None = "0006_rate_limit_function"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION app.provision_clinic_owner(
          p_email public.citext, p_name text, p_slug public.citext,
          p_timezone text, p_display_name text, p_invitation_token_hash bytea
        ) RETURNS TABLE (user_id uuid, clinic_id uuid, invitation_expires_at timestamptz)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_user_id uuid;
          v_clinic_id uuid;
          v_membership_id uuid;
          v_expires_at timestamptz := now() + interval '72 hours';
        BEGIN
          SELECT u.id INTO v_user_id FROM app.users u WHERE u.email = p_email;
          IF v_user_id IS NULL THEN
            INSERT INTO app.users (email) VALUES (p_email) RETURNING id INTO v_user_id;
          END IF;
          INSERT INTO app.clinics (slug, legal_name, status)
            VALUES (p_slug, p_name, 'PROVISIONING') RETURNING id INTO v_clinic_id;
          INSERT INTO app.clinic_settings (clinic_id, display_name, timezone)
            VALUES (v_clinic_id, p_display_name, p_timezone);
          INSERT INTO app.memberships (clinic_id, user_id, role, status)
            VALUES (v_clinic_id, v_user_id, 'OWNER', 'PENDING') RETURNING id INTO v_membership_id;
          INSERT INTO app.membership_invitations
            (clinic_id, membership_id, email, token_hash, expires_at)
            VALUES (v_clinic_id, v_membership_id, p_email, p_invitation_token_hash, v_expires_at);
          INSERT INTO app.clinic_audit_events
            (clinic_id, actor_user_id, event_type, entity_type, entity_id)
            VALUES (v_clinic_id, v_user_id, 'clinic.provisioned', 'clinic', v_clinic_id);
          RETURN QUERY SELECT v_user_id, v_clinic_id, v_expires_at;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION app.consume_invitation(
          p_token_hash bytea, p_password_hash text
        ) RETURNS TABLE (user_id uuid, clinic_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_invitation app.membership_invitations%ROWTYPE;
          v_membership app.memberships%ROWTYPE;
          v_now timestamptz := now();
        BEGIN
          SELECT * INTO v_invitation FROM app.membership_invitations i
            WHERE i.token_hash = p_token_hash FOR UPDATE;
          IF v_invitation.id IS NULL OR v_invitation.accepted_at IS NOT NULL
             OR v_invitation.expires_at <= v_now THEN
            RAISE EXCEPTION 'invitation_unusable';
          END IF;
          SELECT * INTO v_membership FROM app.memberships m
            WHERE m.id = v_invitation.membership_id;
          UPDATE app.users u SET email_verified_at = v_now WHERE u.id = v_membership.user_id;
          INSERT INTO app.password_credentials (user_id, password_hash, changed_at)
            VALUES (v_membership.user_id, p_password_hash, v_now)
            ON CONFLICT ON CONSTRAINT pk_password_credentials DO UPDATE
              SET password_hash = EXCLUDED.password_hash,
                  changed_at = EXCLUDED.changed_at;
          UPDATE app.memberships m SET status = 'ACTIVE', updated_at = v_now
            WHERE m.id = v_membership.id;
          UPDATE app.clinics c SET status = 'ACTIVE', updated_at = v_now
            WHERE c.id = v_invitation.clinic_id AND c.status = 'PROVISIONING';
          UPDATE app.membership_invitations i SET accepted_at = v_now, updated_at = v_now
            WHERE i.id = v_invitation.id;
          INSERT INTO app.clinic_audit_events
            (clinic_id, actor_user_id, event_type, entity_type, entity_id)
            VALUES (v_invitation.clinic_id, v_membership.user_id, 'invitation.accepted',
                    'membership', v_membership.id);
          RETURN QUERY SELECT v_membership.user_id, v_invitation.clinic_id;
        END;
        $$
        """
    )

    op.execute(
        "REVOKE ALL ON FUNCTION app.provision_clinic_owner"
        "(public.citext, text, public.citext, text, text, bytea) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app.provision_clinic_owner"
        f"(public.citext, text, public.citext, text, text, bytea) TO {APP_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION app.consume_invitation(bytea, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.consume_invitation(bytea, text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.consume_invitation(bytea, text)")
    op.execute(
        "DROP FUNCTION IF EXISTS app.provision_clinic_owner"
        "(public.citext, text, public.citext, text, text, bytea)"
    )
