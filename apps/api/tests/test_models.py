from __future__ import annotations

import pytest
from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    LargeBinary,
    UniqueConstraint,
    inspect,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB

from app.auth.models import (
    AuthActionToken,
    AuthAuditEvent,
    AuthRateLimitBucket,
    AuthSession,
    EmailOutbox,
    ExternalIdentity,
    PasswordCredential,
)
from app.clinics.models import (
    Clinic,
    ClinicAuditEvent,
    ClinicFeatureFlag,
    ClinicSettings,
    Membership,
    MembershipInvitation,
)
from app.users.models import User


def foreign_key_targets(model: type) -> set[str]:
    return {foreign_key.target_fullname for foreign_key in model.__table__.foreign_keys}


def unique_column_sets(model: type) -> list[list[str]]:
    return [
        [column.name for column in constraint.columns]
        for constraint in model.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]


def test_user_table_lives_in_app_schema() -> None:
    table = User.__table__

    assert table.schema == "app"
    assert table.name == "users"


def test_user_columns_and_nullability() -> None:
    columns = User.__table__.c

    assert set(columns.keys()) == {
        "id",
        "email",
        "status",
        "email_verified_at",
        "created_at",
        "updated_at",
    }
    assert columns.id.primary_key is True
    assert columns.email.nullable is False
    assert isinstance(columns.email.type, CITEXT)
    assert columns.status.nullable is False
    assert columns.email_verified_at.nullable is True
    assert columns.created_at.nullable is False
    assert columns.updated_at.nullable is False


def test_user_email_is_unique() -> None:
    unique_constraints = [
        constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert [
        [column.name for column in constraint.columns] for constraint in unique_constraints
    ] == [["email"]]


def test_user_status_is_restricted_by_check_constraint() -> None:
    check = next(
        constraint
        for constraint in User.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_users_status"
    )

    assert str(check.sqltext) == "status IN ('ACTIVE', 'DISABLED')"


def test_user_defaults_come_from_the_database() -> None:
    columns = User.__table__.c

    assert str(columns.id.server_default.arg) == "gen_random_uuid()"
    assert str(columns.status.server_default.arg) == "'ACTIVE'"
    assert str(columns.created_at.server_default.arg) == "now()"
    assert str(columns.updated_at.server_default.arg) == "now()"


AUTH_MODELS = [
    PasswordCredential,
    ExternalIdentity,
    AuthSession,
    AuthActionToken,
    AuthRateLimitBucket,
    AuthAuditEvent,
    EmailOutbox,
]


@pytest.mark.parametrize("model", AUTH_MODELS)
def test_auth_tables_live_in_app_schema(model: type) -> None:
    assert model.__table__.schema == "app"


def test_password_credentials_metadata() -> None:
    columns = PasswordCredential.__table__.c

    assert set(columns.keys()) == {"user_id", "password_hash", "changed_at"}
    assert columns.user_id.primary_key is True
    assert columns.password_hash.nullable is False
    assert columns.changed_at.nullable is False
    assert foreign_key_targets(PasswordCredential) == {"app.users.id"}


def test_external_identities_metadata() -> None:
    columns = ExternalIdentity.__table__.c

    assert set(columns.keys()) == {"id", "user_id", "provider", "subject", "created_at"}
    assert columns.user_id.nullable is False
    assert foreign_key_targets(ExternalIdentity) == {"app.users.id"}
    assert ["provider", "subject"] in unique_column_sets(ExternalIdentity)


def test_auth_sessions_metadata() -> None:
    columns = AuthSession.__table__.c

    assert set(columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "last_seen_at",
        "idle_expires_at",
        "absolute_expires_at",
        "revoked_at",
        "replaced_by_session_id",
        "created_at",
    }
    assert isinstance(columns.token_hash.type, LargeBinary)
    assert columns.revoked_at.nullable is True
    assert columns.replaced_by_session_id.nullable is True
    assert foreign_key_targets(AuthSession) == {"app.users.id", "app.auth_sessions.id"}
    assert ["token_hash"] in unique_column_sets(AuthSession)


def test_auth_action_tokens_metadata() -> None:
    columns = AuthActionToken.__table__.c

    assert set(columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "purpose",
        "expires_at",
        "consumed_at",
        "created_at",
    }
    assert columns.consumed_at.nullable is True
    assert foreign_key_targets(AuthActionToken) == {"app.users.id"}
    assert ["token_hash"] in unique_column_sets(AuthActionToken)
    check = next(
        constraint
        for constraint in AuthActionToken.__table__.constraints
        if isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_auth_action_tokens_purpose"
    )
    assert str(check.sqltext) == "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')"


def test_auth_rate_limit_buckets_metadata() -> None:
    columns = AuthRateLimitBucket.__table__.c

    assert set(columns.keys()) == {
        "bucket_key",
        "attempt_count",
        "window_started_at",
        "blocked_until",
    }
    assert columns.bucket_key.primary_key is True
    assert isinstance(columns.bucket_key.type, LargeBinary)
    assert str(columns.attempt_count.server_default.arg) == "0"
    assert columns.blocked_until.nullable is True


def test_auth_audit_events_metadata() -> None:
    columns = AuthAuditEvent.__table__.c

    assert set(columns.keys()) == {"id", "event_type", "user_id", "occurred_at", "metadata"}
    assert columns.user_id.nullable is True
    assert foreign_key_targets(AuthAuditEvent) == {"app.users.id"}
    assert isinstance(columns["metadata"].type, JSONB)
    assert str(columns["metadata"].server_default.arg) == "'{}'"
    assert str(columns.occurred_at.server_default.arg) == "now()"
    assert inspect(AuthAuditEvent).attrs["event_metadata"].columns[0].name == "metadata"


def test_email_outbox_metadata() -> None:
    columns = EmailOutbox.__table__.c

    assert set(columns.keys()) == {
        "id",
        "idempotency_key",
        "recipient",
        "template",
        "payload",
        "status",
        "attempt_count",
        "next_attempt_at",
        "sent_at",
        "created_at",
        "updated_at",
    }
    assert isinstance(columns.recipient.type, CITEXT)
    assert isinstance(columns.payload.type, JSONB)
    assert str(columns.payload.server_default.arg) == "'{}'"
    assert str(columns.status.server_default.arg) == "'PENDING'"
    assert str(columns.attempt_count.server_default.arg) == "0"
    assert columns.next_attempt_at.nullable is True
    assert columns.sent_at.nullable is True
    assert ["idempotency_key"] in unique_column_sets(EmailOutbox)
    check = next(
        constraint
        for constraint in EmailOutbox.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_email_outbox_status"
    )
    assert str(check.sqltext) == "status IN ('PENDING', 'SENT', 'FAILED')"


TENANT_MODELS = [
    Clinic,
    ClinicSettings,
    ClinicFeatureFlag,
    Membership,
    MembershipInvitation,
    ClinicAuditEvent,
]


@pytest.mark.parametrize("model", TENANT_MODELS)
def test_tenant_tables_live_in_app_schema(model: type) -> None:
    assert model.__table__.schema == "app"


def test_clinics_metadata() -> None:
    columns = Clinic.__table__.c

    assert set(columns.keys()) == {"id", "slug", "legal_name", "status", "created_at", "updated_at"}
    assert isinstance(columns.slug.type, CITEXT)
    assert ["slug"] in unique_column_sets(Clinic)
    assert str(columns.status.server_default.arg) == "'PROVISIONING'"
    check = next(
        constraint
        for constraint in Clinic.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_clinics_status"
    )
    assert str(check.sqltext) == "status IN ('PROVISIONING', 'ACTIVE', 'SUSPENDED')"


def test_clinic_settings_metadata() -> None:
    columns = ClinicSettings.__table__.c

    assert set(columns.keys()) == {
        "clinic_id",
        "display_name",
        "timezone",
        "locale",
        "currency",
        "preferences",
        "created_at",
        "updated_at",
    }
    assert [column.name for column in ClinicSettings.__table__.primary_key.columns] == ["clinic_id"]
    assert foreign_key_targets(ClinicSettings) == {"app.clinics.id"}
    assert isinstance(columns.currency.type, CHAR)
    assert columns.currency.type.length == 3
    assert isinstance(columns.preferences.type, JSONB)
    assert str(columns.preferences.server_default.arg) == "'{}'"
    assert str(columns.timezone.server_default.arg) == "'America/Bahia'"
    assert str(columns.locale.server_default.arg) == "'pt-BR'"
    assert str(columns.currency.server_default.arg) == "'BRL'"


def test_clinic_feature_flags_metadata() -> None:
    columns = ClinicFeatureFlag.__table__.c

    assert set(columns.keys()) == {
        "clinic_id",
        "key",
        "enabled",
        "config",
        "changed_by_user_id",
        "created_at",
        "updated_at",
    }
    assert [column.name for column in ClinicFeatureFlag.__table__.primary_key.columns] == [
        "clinic_id",
        "key",
    ]
    assert foreign_key_targets(ClinicFeatureFlag) == {"app.clinics.id", "app.users.id"}
    assert isinstance(columns.enabled.type, Boolean)
    assert str(columns.enabled.server_default.arg) == "false"
    assert columns.config.nullable is True
    assert columns.changed_by_user_id.nullable is True


def test_memberships_metadata() -> None:
    columns = Membership.__table__.c

    assert set(columns.keys()) == {
        "id",
        "clinic_id",
        "user_id",
        "role",
        "status",
        "created_at",
        "updated_at",
    }
    assert foreign_key_targets(Membership) == {"app.clinics.id", "app.users.id"}
    unique_sets = unique_column_sets(Membership)
    assert ["user_id", "clinic_id"] in unique_sets
    assert ["clinic_id", "id"] in unique_sets
    assert str(columns.status.server_default.arg) == "'PENDING'"
    role_check = next(
        constraint
        for constraint in Membership.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_memberships_role"
    )
    assert (
        str(role_check.sqltext)
        == "role IN ('OWNER', 'ADMIN', 'DENTIST', 'ASSISTANT', 'RECEPTIONIST')"
    )
    status_check = next(
        constraint
        for constraint in Membership.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name == "ck_memberships_status"
    )
    assert str(status_check.sqltext) == "status IN ('PENDING', 'ACTIVE', 'SUSPENDED')"


def test_membership_invitations_metadata() -> None:
    columns = MembershipInvitation.__table__.c

    assert set(columns.keys()) == {
        "id",
        "clinic_id",
        "membership_id",
        "email",
        "token_hash",
        "expires_at",
        "accepted_at",
        "created_at",
        "updated_at",
    }
    assert isinstance(columns.email.type, CITEXT)
    assert isinstance(columns.token_hash.type, LargeBinary)
    assert columns.accepted_at.nullable is True
    assert ["token_hash"] in unique_column_sets(MembershipInvitation)
    assert ["clinic_id", "id"] in unique_column_sets(MembershipInvitation)


def test_membership_invitations_reference_memberships_compositely() -> None:
    constraint = next(
        constraint
        for constraint in MembershipInvitation.__table__.constraints
        if isinstance(constraint, ForeignKeyConstraint)
        and {column.name for column in constraint.columns} == {"clinic_id", "membership_id"}
    )

    assert [element.target_fullname for element in constraint.elements] == [
        "app.memberships.clinic_id",
        "app.memberships.id",
    ]


def test_clinic_audit_events_metadata() -> None:
    columns = ClinicAuditEvent.__table__.c

    assert set(columns.keys()) == {
        "id",
        "clinic_id",
        "actor_user_id",
        "event_type",
        "entity_type",
        "entity_id",
        "occurred_at",
        "metadata",
    }
    assert columns.actor_user_id.nullable is True
    assert columns.entity_type.nullable is True
    assert columns.entity_id.nullable is True
    assert foreign_key_targets(ClinicAuditEvent) == {"app.clinics.id", "app.users.id"}
    assert isinstance(columns["metadata"].type, JSONB)
    assert str(columns["metadata"].server_default.arg) == "'{}'"
    assert str(columns.occurred_at.server_default.arg) == "now()"
    assert inspect(ClinicAuditEvent).attrs["event_metadata"].columns[0].name == "metadata"
