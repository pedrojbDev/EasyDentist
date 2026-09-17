from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from conftest import RecordingEmailSender, make_test_email
from helpers import insert_user
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.provisioning import ProvisionService
from app.auth.settings import AuthSettings
from app.auth.tokens import token_digest
from app.core.errors import ConflictError

NAME = "Clínica Sorriso"
SLUG_PREFIX = "clinica-sorriso"


def make_slug() -> str:
    return f"{SLUG_PREFIX}-{uuid.uuid4().hex[:10]}"


async def provision(
    session_factory: async_sessionmaker[AsyncSession],
    settings: AuthSettings,
    sender: RecordingEmailSender,
    *,
    email: str,
    slug: str,
    name: str = NAME,
    display_name: str | None = None,
):
    service = ProvisionService(session_factory, settings, sender)
    return await service.provision(email=email, name=name, slug=slug, display_name=display_name)


def token_from_body(body: str) -> str:
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


@pytest.mark.anyio
async def test_provision_creates_pending_owner_and_invitation(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("provision")
    slug = make_slug()

    result = await provision(session_factory, auth_settings, email_sender, email=email, slug=slug)
    provisioned_clinics.append(result.clinic_id)

    user = await migrator_connection.fetchrow(
        "SELECT email, email_verified_at FROM app.users WHERE id = $1", result.user_id
    )
    assert user["email"] == email
    assert user["email_verified_at"] is None
    credentials = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.password_credentials WHERE user_id = $1", result.user_id
    )
    assert credentials == 0

    clinic = await migrator_connection.fetchrow(
        "SELECT slug, legal_name, status FROM app.clinics WHERE id = $1", result.clinic_id
    )
    assert clinic["slug"] == slug
    assert clinic["legal_name"] == NAME
    assert clinic["status"] == "PROVISIONING"

    settings_row = await migrator_connection.fetchrow(
        "SELECT display_name, timezone FROM app.clinic_settings WHERE clinic_id = $1",
        result.clinic_id,
    )
    assert settings_row["display_name"] == NAME
    assert settings_row["timezone"] == "America/Bahia"

    membership = await migrator_connection.fetchrow(
        "SELECT role, status FROM app.memberships WHERE clinic_id = $1", result.clinic_id
    )
    assert membership["role"] == "OWNER"
    assert membership["status"] == "PENDING"

    outbox = await migrator_connection.fetchrow(
        "SELECT idempotency_key, template, status, payload FROM app.email_outbox "
        "WHERE recipient = $1",
        email,
    )
    assert outbox is not None
    assert outbox["template"] == "invitation"
    assert outbox["status"] == "SENT"
    assert outbox["idempotency_key"].startswith("invitation:")
    token = token_from_body(json.loads(str(outbox["payload"]))["body"])

    invitation = await migrator_connection.fetchrow(
        "SELECT email, token_hash, expires_at, accepted_at "
        "FROM app.membership_invitations WHERE clinic_id = $1",
        result.clinic_id,
    )
    assert invitation["email"] == email
    assert bytes(invitation["token_hash"]) == token_digest(token)
    assert invitation["accepted_at"] is None
    expected_expiry = datetime.now(UTC) + timedelta(hours=72)
    assert abs((invitation["expires_at"] - expected_expiry).total_seconds()) < 60

    audit = await migrator_connection.fetchrow(
        "SELECT event_type, entity_type, entity_id FROM app.clinic_audit_events "
        "WHERE clinic_id = $1",
        result.clinic_id,
    )
    assert audit["event_type"] == "clinic.provisioned"
    assert audit["entity_type"] == "clinic"
    assert audit["entity_id"] == result.clinic_id

    assert len(email_sender.sent) == 1
    recipient, subject, body = email_sender.sent[0]
    assert recipient == email
    assert NAME in subject or NAME in body
    assert "#token=" in body


@pytest.mark.anyio
async def test_provision_reuses_existing_user(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("provision-reuse")
    existing_user_id = await insert_user(migrator_connection, email)

    result = await provision(
        session_factory, auth_settings, email_sender, email=email, slug=make_slug()
    )
    provisioned_clinics.append(result.clinic_id)

    assert result.user_id == existing_user_id
    count = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.users WHERE email = $1", email
    )
    assert count == 1


@pytest.mark.anyio
async def test_provision_uses_optional_display_name_and_timezone(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("provision-display")
    service = ProvisionService(session_factory, auth_settings, email_sender)

    result = await service.provision(
        email=email,
        name="Razão Social Ltda",
        slug=make_slug(),
        display_name="Sorriso Odontologia",
        timezone="America/Sao_Paulo",
    )
    provisioned_clinics.append(result.clinic_id)

    clinic = await migrator_connection.fetchrow(
        "SELECT legal_name FROM app.clinics WHERE id = $1", result.clinic_id
    )
    settings_row = await migrator_connection.fetchrow(
        "SELECT display_name, timezone FROM app.clinic_settings WHERE clinic_id = $1",
        result.clinic_id,
    )
    assert clinic["legal_name"] == "Razão Social Ltda"
    assert settings_row["display_name"] == "Sorriso Odontologia"
    assert settings_row["timezone"] == "America/Sao_Paulo"


@pytest.mark.anyio
async def test_provision_rejects_duplicate_slug(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    slug = make_slug()
    first = await provision(
        session_factory, auth_settings, email_sender, email=make_test_email("slug-a"), slug=slug
    )
    provisioned_clinics.append(first.clinic_id)

    with pytest.raises(ConflictError):
        await provision(
            session_factory,
            auth_settings,
            email_sender,
            email=make_test_email("slug-b"),
            slug=slug,
        )

    count = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.clinics WHERE slug = $1", slug
    )
    assert count == 1
    second_user = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.users WHERE email = $1", make_test_email("slug-b")
    )
    assert second_user == 0


@pytest.mark.anyio
async def test_cli_prints_only_metadata_never_the_token(
    email_sender: RecordingEmailSender,
    app_async_url: str,
    monkeypatch: pytest.MonkeyPatch,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.auth.provision import parse_args, run

    email = make_test_email("provision-cli")
    slug = make_slug()
    monkeypatch.setenv("DATABASE_URL", app_async_url)
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    args = parse_args(
        ["--email", email, "--name", NAME, "--slug", slug, "--timezone", "America/Bahia"]
    )

    exit_code = await run(args, sender=email_sender)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "user_id=" in captured.out
    assert "clinic_id=" in captured.out
    assert slug in captured.out

    outbox = await migrator_connection.fetchrow(
        "SELECT payload FROM app.email_outbox WHERE recipient = $1", email
    )
    token = token_from_body(json.loads(str(outbox["payload"]))["body"])
    clinic_id = await migrator_connection.fetchval(
        "SELECT id FROM app.clinics WHERE slug = $1", slug
    )
    provisioned_clinics.append(clinic_id)
    assert token not in captured.out
    assert token not in captured.err


@pytest.mark.anyio
async def test_cli_reports_conflict_without_creating_tenant(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    app_async_url: str,
    monkeypatch: pytest.MonkeyPatch,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.auth.provision import parse_args, run

    slug = make_slug()
    first = await provision(
        session_factory, auth_settings, email_sender, email=make_test_email("cli-first"), slug=slug
    )
    provisioned_clinics.append(first.clinic_id)
    monkeypatch.setenv("DATABASE_URL", app_async_url)
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    args = parse_args(["--email", make_test_email("cli-conflict"), "--name", NAME, "--slug", slug])

    exit_code = await run(args, sender=email_sender)

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "conflito" in captured.err.lower() or "existe" in captured.err.lower()
