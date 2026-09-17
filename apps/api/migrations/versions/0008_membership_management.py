"""Membership management functions.

Revision ID: 0008_membership_management
Revises: 0007_invitation_functions
Create Date: 2026-09-17
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008_membership_management"
down_revision: str | None = "0007_invitation_functions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "easydentist_app"


def upgrade() -> None:
    op.execute("DROP FUNCTION app.consume_invitation(bytea, text)")

    op.execute(
        """
        CREATE FUNCTION app.consume_invitation(p_token_hash bytea, p_password_hash text)
        RETURNS TABLE (user_id uuid, clinic_id uuid)
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

          IF EXISTS (SELECT 1 FROM app.password_credentials pc
                     WHERE pc.user_id = v_membership.user_id) THEN
            IF p_password_hash IS NOT NULL THEN
              RAISE EXCEPTION 'password_not_allowed';
            END IF;
          ELSE
            IF p_password_hash IS NULL THEN
              RAISE EXCEPTION 'password_required';
            END IF;
            INSERT INTO app.password_credentials (user_id, password_hash, changed_at)
              VALUES (v_membership.user_id, p_password_hash, v_now);
            UPDATE app.auth_sessions s SET revoked_at = v_now
              WHERE s.user_id = v_membership.user_id AND s.revoked_at IS NULL;
          END IF;

          UPDATE app.users u SET email_verified_at = v_now WHERE u.id = v_membership.user_id;
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
        """
        CREATE FUNCTION app.create_member_invitation(
          p_clinic_id uuid, p_actor_user_id uuid, p_email public.citext,
          p_role text, p_invitation_token_hash bytea
        ) RETURNS TABLE (membership_id uuid, invitation_id uuid, user_id uuid,
                         invitation_expires_at timestamptz)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_actor_role text;
          v_user_id uuid;
          v_membership_id uuid;
          v_invitation_id uuid;
          v_expires_at timestamptz := now() + interval '72 hours';
        BEGIN
          IF p_clinic_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_clinic_id', true), '')
             OR p_actor_user_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_user_id', true), '') THEN
            RAISE EXCEPTION 'context_mismatch';
          END IF;
          IF p_role NOT IN ('OWNER','ADMIN','DENTIST','ASSISTANT','RECEPTIONIST') THEN
            RAISE EXCEPTION 'invalid_role';
          END IF;
          SELECT m.role INTO v_actor_role FROM app.memberships m
            WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id
              AND m.status = 'ACTIVE';
          IF v_actor_role IS NULL
             OR v_actor_role NOT IN ('OWNER','ADMIN')
             OR (p_role IN ('OWNER','ADMIN') AND v_actor_role <> 'OWNER') THEN
            RAISE EXCEPTION 'not_permitted';
          END IF;
          SELECT u.id INTO v_user_id FROM app.users u WHERE u.email = p_email;
          IF v_user_id IS NULL THEN
            INSERT INTO app.users (email) VALUES (p_email) RETURNING id INTO v_user_id;
          END IF;
          INSERT INTO app.memberships (clinic_id, user_id, role, status)
            VALUES (p_clinic_id, v_user_id, p_role, 'PENDING') RETURNING id INTO v_membership_id;
          INSERT INTO app.membership_invitations
            (clinic_id, membership_id, email, token_hash, expires_at)
            VALUES (p_clinic_id, v_membership_id, p_email, p_invitation_token_hash, v_expires_at)
            RETURNING id INTO v_invitation_id;
          INSERT INTO app.clinic_audit_events
            (clinic_id, actor_user_id, event_type, entity_type, entity_id)
            VALUES (p_clinic_id, p_actor_user_id, 'membership.invited', 'membership',
                    v_membership_id);
          RETURN QUERY SELECT v_membership_id, v_invitation_id, v_user_id, v_expires_at;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION app.change_member_role(
          p_clinic_id uuid, p_actor_user_id uuid, p_membership_id uuid, p_new_role text
        ) RETURNS TABLE (membership_id uuid, old_role text, new_role text)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_target app.memberships%ROWTYPE;
          v_actor_role text;
          v_owner_count int;
        BEGIN
          IF p_clinic_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_clinic_id', true), '')
             OR p_actor_user_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_user_id', true), '') THEN
            RAISE EXCEPTION 'context_mismatch';
          END IF;
          IF p_new_role NOT IN ('OWNER','ADMIN','DENTIST','ASSISTANT','RECEPTIONIST') THEN
            RAISE EXCEPTION 'invalid_role';
          END IF;
          PERFORM 1 FROM app.clinics c WHERE c.id = p_clinic_id FOR UPDATE;
          SELECT * INTO v_target FROM app.memberships m
            WHERE m.id = p_membership_id AND m.clinic_id = p_clinic_id FOR UPDATE;
          IF v_target.id IS NULL THEN
            RAISE EXCEPTION 'membership_not_found';
          END IF;
          SELECT m.role INTO v_actor_role FROM app.memberships m
            WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id
              AND m.status = 'ACTIVE';
          IF v_actor_role IS NULL OR v_target.status <> 'ACTIVE'
             OR v_actor_role NOT IN ('OWNER','ADMIN')
             OR ((v_target.role IN ('OWNER','ADMIN') OR p_new_role IN ('OWNER','ADMIN'))
                 AND v_actor_role <> 'OWNER')
             OR (v_actor_role = 'ADMIN' AND v_target.role = 'ADMIN') THEN
            RAISE EXCEPTION 'not_permitted';
          END IF;
          IF v_target.role = 'OWNER' AND p_new_role <> 'OWNER' THEN
            SELECT count(*) INTO v_owner_count FROM app.memberships m
              WHERE m.clinic_id = p_clinic_id AND m.role = 'OWNER' AND m.status = 'ACTIVE';
            IF v_owner_count <= 1 THEN
              RAISE EXCEPTION 'last_owner';
            END IF;
          END IF;
          UPDATE app.memberships m SET role = p_new_role, updated_at = now()
            WHERE m.id = v_target.id;
          INSERT INTO app.clinic_audit_events
            (clinic_id, actor_user_id, event_type, entity_type, entity_id)
            VALUES (p_clinic_id, p_actor_user_id, 'membership.role_changed', 'membership',
                    v_target.id);
          RETURN QUERY SELECT v_target.id, v_target.role, p_new_role;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION app.remove_membership(
          p_clinic_id uuid, p_actor_user_id uuid, p_membership_id uuid
        ) RETURNS TABLE (membership_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = app, pg_temp
        AS $$
        DECLARE
          v_target app.memberships%ROWTYPE;
          v_actor_role text;
          v_owner_count int;
        BEGIN
          IF p_clinic_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_clinic_id', true), '')
             OR p_actor_user_id::text IS DISTINCT FROM
               NULLIF(current_setting('app.current_user_id', true), '') THEN
            RAISE EXCEPTION 'context_mismatch';
          END IF;
          PERFORM 1 FROM app.clinics c WHERE c.id = p_clinic_id FOR UPDATE;
          SELECT * INTO v_target FROM app.memberships m
            WHERE m.id = p_membership_id AND m.clinic_id = p_clinic_id FOR UPDATE;
          IF v_target.id IS NULL THEN
            RAISE EXCEPTION 'membership_not_found';
          END IF;
          SELECT m.role INTO v_actor_role FROM app.memberships m
            WHERE m.clinic_id = p_clinic_id AND m.user_id = p_actor_user_id
              AND m.status = 'ACTIVE';
          IF v_actor_role IS NULL
             OR v_actor_role NOT IN ('OWNER','ADMIN')
             OR (v_target.role IN ('OWNER','ADMIN') AND v_actor_role <> 'OWNER') THEN
            RAISE EXCEPTION 'not_permitted';
          END IF;
          IF v_target.role = 'OWNER' AND v_target.status = 'ACTIVE' THEN
            SELECT count(*) INTO v_owner_count FROM app.memberships m
              WHERE m.clinic_id = p_clinic_id AND m.role = 'OWNER' AND m.status = 'ACTIVE';
            IF v_owner_count <= 1 THEN
              RAISE EXCEPTION 'last_owner';
            END IF;
          END IF;
          DELETE FROM app.membership_invitations i WHERE i.membership_id = v_target.id;
          DELETE FROM app.memberships m WHERE m.id = v_target.id;
          INSERT INTO app.clinic_audit_events
            (clinic_id, actor_user_id, event_type, entity_type, entity_id)
            VALUES (p_clinic_id, p_actor_user_id, 'membership.removed', 'membership', v_target.id);
          RETURN QUERY SELECT v_target.id;
        END;
        $$
        """
    )

    op.execute("REVOKE ALL ON FUNCTION app.consume_invitation(bytea, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.consume_invitation(bytea, text) TO {APP_ROLE}")
    op.execute(
        "REVOKE ALL ON FUNCTION app.create_member_invitation"
        "(uuid, uuid, public.citext, text, bytea) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app.create_member_invitation"
        f"(uuid, uuid, public.citext, text, bytea) TO {APP_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION app.change_member_role(uuid, uuid, uuid, text) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION app.change_member_role(uuid, uuid, uuid, text) TO {APP_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION app.remove_membership(uuid, uuid, uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.remove_membership(uuid, uuid, uuid) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS app.remove_membership(uuid, uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS app.change_member_role(uuid, uuid, uuid, text)")
    op.execute(
        "DROP FUNCTION IF EXISTS app.create_member_invitation"
        "(uuid, uuid, public.citext, text, bytea)"
    )
    op.execute("DROP FUNCTION IF EXISTS app.consume_invitation(bytea, text)")
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
          UPDATE app.auth_sessions s SET revoked_at = v_now
            WHERE s.user_id = v_membership.user_id AND s.revoked_at IS NULL;
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
    op.execute("REVOKE ALL ON FUNCTION app.consume_invitation(bytea, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION app.consume_invitation(bytea, text) TO {APP_ROLE}")
