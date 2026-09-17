from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta

import asyncpg
import httpx
import pytest
from conftest import RecordingEmailSender, make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.action_tokens import (
    EMAIL_VERIFICATION_TTL,
    PASSWORD_RESET_TTL,
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    ActionTokenService,
)
from app.auth.tokens import token_digest
from app.core.database import transaction_scope

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "another correct battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"
TOKEN_IN_LINK = re.compile(r"#token=([A-Za-z0-9_\-]+)")


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


def mutation_headers(csrf: str, session_token: str | None = None) -> dict[str, str]:
    cookies = [f"{CSRF_COOKIE}={csrf}"]
    if session_token is not None:
        cookies.append(f"{SESSION_COOKIE}={session_token}")
    return {"Cookie": "; ".join(cookies), "X-CSRF-Token": csrf, "Origin": ORIGIN}


def auth_headers(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=mutation_headers(csrf),
    )
    client.cookies.clear()
    return response


async def issue_token(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    purpose: str,
    ttl: timedelta,
) -> str:
    async with transaction_scope(session_factory) as session:
        return await ActionTokenService().issue(session, purpose=purpose, user_id=user_id, ttl=ttl)


async def outbox_rows(
    migrator_connection: asyncpg.Connection, recipient: str
) -> list[asyncpg.Record]:
    rows = await migrator_connection.fetch(
        "SELECT idempotency_key, template, status, attempt_count, next_attempt_at, payload "
        "FROM app.email_outbox WHERE recipient = $1 ORDER BY created_at, id",
        recipient,
    )
    return list(rows)


def token_from_body(body: str) -> str:
    match = TOKEN_IN_LINK.search(body)
    assert match is not None
    return match.group(1)


def outbox_payload(row: asyncpg.Record) -> dict[str, str]:
    return json.loads(str(row["payload"]))


@pytest.mark.anyio
async def test_forgot_returns_202_and_enqueues_only_for_known_email(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    email_sender: RecordingEmailSender,
) -> None:
    email = make_test_email("forgot-known")
    await seed_user_with_password(email=email, password=PASSWORD)
    absent = make_test_email("forgot-absent")
    csrf = await anonymous_csrf(api_client)

    known = await api_client.post(
        "/api/v1/auth/password/forgot", json={"email": email}, headers=mutation_headers(csrf)
    )
    clean = await anonymous_csrf(api_client)
    unknown = await api_client.post(
        "/api/v1/auth/password/forgot", json={"email": absent}, headers=mutation_headers(clean)
    )

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.content == unknown.content == b""
    assert known.cookies.get(SESSION_COOKIE) is None

    rows = await outbox_rows(migrator_connection, email)
    assert len(rows) == 1
    assert rows[0]["template"] == "password-reset"
    assert rows[0]["status"] == "SENT"
    body = outbox_payload(rows[0])["body"]
    assert "#token=" in body
    assert await outbox_rows(migrator_connection, absent) == []

    token = token_from_body(body)
    stored = await migrator_connection.fetchrow(
        "SELECT purpose, expires_at, consumed_at FROM app.auth_action_tokens WHERE token_hash = $1",
        token_digest(token),
    )
    assert stored is not None
    assert stored["purpose"] == PURPOSE_PASSWORD_RESET
    assert stored["consumed_at"] is None

    assert len(email_sender.sent) == 1
    recipient, subject, sent_body = email_sender.sent[0]
    assert recipient == email
    assert "senha" in subject.lower()
    assert token in sent_body


@pytest.mark.anyio
async def test_forgot_rate_limits_recipient_with_retry_after(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("forgot-limit")
    await seed_user_with_password(email=email, password=PASSWORD)

    responses = []
    for _ in range(4):
        csrf = await anonymous_csrf(api_client)
        responses.append(
            await api_client.post(
                "/api/v1/auth/password/forgot",
                json={"email": email},
                headers=mutation_headers(csrf),
            )
        )

    assert [response.status_code for response in responses[:3]] == [202, 202, 202]
    blocked = responses[3]
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["title"] == "Muitas tentativas"

    audits = await migrator_connection.fetch(
        "SELECT event_type FROM app.auth_audit_events WHERE user_id IS NULL"
    )
    assert sum(1 for row in audits if row["event_type"] == "rate_limit_triggered") == 1


@pytest.mark.anyio
async def test_resend_requires_authentication(
    api_client: httpx.AsyncClient, clean_auth_state: None
) -> None:
    csrf = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/email-verification/resend", headers=mutation_headers(csrf)
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_resend_sends_verification_email_for_unverified_user(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    email_sender: RecordingEmailSender,
) -> None:
    email = make_test_email("resend")
    await seed_user_with_password(email=email, password=PASSWORD)
    token = (await login(api_client, email)).cookies.get(SESSION_COOKIE)
    assert token
    csrf_response = await api_client.get("/api/v1/auth/csrf", headers=auth_headers(token))
    bound = csrf_response.json()["csrf_token"]

    response = await api_client.post(
        "/api/v1/auth/email-verification/resend",
        headers=mutation_headers(bound, token),
    )

    assert response.status_code == 202

    rows = await outbox_rows(migrator_connection, email)
    assert len(rows) == 1
    assert rows[0]["template"] == "email-verification"
    assert rows[0]["status"] == "SENT"
    token_row = await migrator_connection.fetchrow(
        "SELECT purpose FROM app.auth_action_tokens WHERE token_hash = $1",
        token_digest(token_from_body(outbox_payload(rows[0])["body"])),
    )
    assert token_row["purpose"] == PURPOSE_EMAIL_VERIFICATION

    assert len(email_sender.sent) == 1
    assert "e-mail" in email_sender.sent[0][1].lower()


@pytest.mark.anyio
async def test_resend_skips_delivery_when_email_is_already_verified(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("resend-verified")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    await migrator_connection.execute(
        "UPDATE app.users SET email_verified_at = now() WHERE id = $1", user_id
    )
    token = (await login(api_client, email)).cookies.get(SESSION_COOKIE)
    assert token
    csrf_response = await api_client.get("/api/v1/auth/csrf", headers=auth_headers(token))
    bound = csrf_response.json()["csrf_token"]

    response = await api_client.post(
        "/api/v1/auth/email-verification/resend",
        headers=mutation_headers(bound, token),
    )

    assert response.status_code == 202
    assert await outbox_rows(migrator_connection, email) == []
    count = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.auth_action_tokens WHERE user_id = $1", user_id
    )
    assert count == 0


@pytest.mark.anyio
async def test_confirm_valid_token_verifies_email_once(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = make_test_email("confirm")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    token = await issue_token(
        session_factory,
        user_id=user_id,
        purpose=PURPOSE_EMAIL_VERIFICATION,
        ttl=EMAIL_VERIFICATION_TTL,
    )
    csrf = await anonymous_csrf(api_client)

    confirmed = await api_client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": token},
        headers=mutation_headers(csrf),
    )

    assert confirmed.status_code == 204
    verified_at = await migrator_connection.fetchval(
        "SELECT email_verified_at FROM app.users WHERE id = $1", user_id
    )
    assert verified_at is not None
    audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.auth_audit_events "
        "WHERE event_type = 'email_verified' AND user_id = $1",
        user_id,
    )
    assert audit == 1

    reused = await api_client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": token},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    assert reused.status_code == 400
    assert reused.json()["title"] == "Requisição inválida"


@pytest.mark.anyio
async def test_confirm_rejects_invalid_token_generically(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("confirm-invalid")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/email-verification/confirm",
        json={"token": "definitely-not-a-token"},
        headers=mutation_headers(csrf),
    )

    assert response.status_code == 400
    assert response.json()["title"] == "Requisição inválida"
    assert response.cookies.get(SESSION_COOKIE) is None


@pytest.mark.anyio
async def test_recovery_endpoints_require_csrf(
    api_client: httpx.AsyncClient, clean_auth_state: None
) -> None:
    response = await api_client.post(
        "/api/v1/auth/password/forgot", json={"email": make_test_email("csrf")}
    )

    assert response.status_code == 403
    assert response.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_reset_rejects_invalid_token_generically(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    await seed_user_with_password(email=make_test_email("reset-invalid"), password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": "definitely-not-a-token", "password": NEW_PASSWORD},
        headers=mutation_headers(csrf),
    )

    assert response.status_code == 400
    assert response.json()["title"] == "Requisição inválida"
    assert response.cookies.get(SESSION_COOKIE) is None


@pytest.mark.anyio
async def test_reset_weak_password_is_rejected_without_consuming_token(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = make_test_email("reset-weak")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    token = await issue_token(
        session_factory,
        user_id=user_id,
        purpose=PURPOSE_PASSWORD_RESET,
        ttl=PASSWORD_RESET_TTL,
    )

    rejected = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "password": "too-short"},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "Dados inválidos"

    accepted = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "password": NEW_PASSWORD},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    assert accepted.status_code == 204


@pytest.mark.anyio
async def test_reset_changes_password_revokes_sessions_and_does_not_login(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("reset-flow")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    first = (await login(api_client, email)).cookies.get(SESSION_COOKIE)
    second = (await login(api_client, email)).cookies.get(SESSION_COOKIE)
    assert first and second
    token = await issue_token(
        session_factory,
        user_id=user_id,
        purpose=PURPOSE_PASSWORD_RESET,
        ttl=PASSWORD_RESET_TTL,
    )

    response = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "password": NEW_PASSWORD},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )

    assert response.status_code == 204
    assert response.cookies.get(SESSION_COOKIE) is None
    for stale in (first, second):
        assert (
            await api_client.get("/api/v1/auth/me", headers=auth_headers(stale))
        ).status_code == 401

    assert (await login(api_client, email, PASSWORD)).status_code == 401
    assert (await login(api_client, email, NEW_PASSWORD)).status_code == 200

    reused = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "password": NEW_PASSWORD},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    assert reused.status_code == 400

    audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.auth_audit_events "
        "WHERE event_type = 'password_reset_completed' AND user_id = $1",
        user_id,
    )
    assert audit == 1


@pytest.mark.anyio
async def test_forgot_outbox_row_survives_delivery_failure(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    email_sender: RecordingEmailSender,
) -> None:
    email = make_test_email("forgot-smtp-down")
    await seed_user_with_password(email=email, password=PASSWORD)
    email_sender.fail = True

    response = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": email},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )

    assert response.status_code == 202
    assert email_sender.sent == []
    rows = await outbox_rows(migrator_connection, email)
    assert len(rows) == 1
    assert rows[0]["status"] == "PENDING"
    assert rows[0]["attempt_count"] == 1
    assert rows[0]["next_attempt_at"] is not None
    assert rows[0]["idempotency_key"].startswith("password-reset:")


@pytest.mark.anyio
async def test_forgot_creates_distinct_outbox_rows_per_request(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    email_sender: RecordingEmailSender,
) -> None:
    email = make_test_email("forgot-distinct")
    await seed_user_with_password(email=email, password=PASSWORD)

    for _ in range(2):
        response = await api_client.post(
            "/api/v1/auth/password/forgot",
            json={"email": email},
            headers=mutation_headers(await anonymous_csrf(api_client)),
        )
        assert response.status_code == 202

    rows = await outbox_rows(migrator_connection, email)
    assert len(rows) == 2
    assert rows[0]["idempotency_key"] != rows[1]["idempotency_key"]
    assert {row["status"] for row in rows} == {"SENT"}
    assert len(email_sender.sent) == 2
    bodies = [outbox_payload(row)["body"] for row in rows]
    assert bodies[0] != bodies[1]
