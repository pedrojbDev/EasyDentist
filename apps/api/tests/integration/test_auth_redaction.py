from __future__ import annotations

import json
import logging
import uuid

import asyncpg
import httpx
import pytest
from conftest import RecordingEmailSender, make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.provisioning import ProvisionService
from app.auth.settings import AuthSettings

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "another correct battery staple"
CSRF_COOKIE = "easydent_csrf"
SESSION_COOKIE = "easydent_session"
ORIGIN = "http://testserver"


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


def mutation_headers(csrf: str, session: str | None = None) -> dict[str, str]:
    cookies = [f"{CSRF_COOKIE}={csrf}"]
    if session is not None:
        cookies.append(f"{SESSION_COOKIE}={session}")
    return {"Cookie": "; ".join(cookies), "X-CSRF-Token": csrf, "Origin": ORIGIN}


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=mutation_headers(csrf),
    )
    client.cookies.clear()
    return response


def token_from_body(body: str) -> str:
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


@pytest.mark.anyio
async def test_logs_audit_and_buckets_never_contain_secrets(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
    migrator_connection: asyncpg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    email = make_test_email("redaction")
    await seed_user_with_password(email=email, password=PASSWORD)

    login_response = await login(api_client, email, PASSWORD)
    assert login_response.status_code == 200
    session_token = login_response.cookies.get(SESSION_COOKIE)
    assert session_token
    anonymous_csrf_token = await anonymous_csrf(api_client)
    bound = (
        await api_client.get(
            "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={session_token}"}
        )
    ).json()["csrf_token"]
    await login(api_client, email, "wrong-password-12345")

    forgot_csrf = await anonymous_csrf(api_client)
    forgot = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": email},
        headers=mutation_headers(forgot_csrf),
    )
    assert forgot.status_code == 202
    outbox = await migrator_connection.fetchrow(
        "SELECT payload FROM app.email_outbox WHERE recipient = $1 AND template = 'password-reset'",
        email,
    )
    reset_token = token_from_body(json.loads(str(outbox["payload"]))["body"])
    reset_csrf = await anonymous_csrf(api_client)
    reset = await api_client.post(
        "/api/v1/auth/password/reset",
        json={"token": reset_token, "password": NEW_PASSWORD},
        headers=mutation_headers(reset_csrf),
    )
    assert reset.status_code == 204

    invitee = make_test_email("redaction-invitee")
    service = ProvisionService(session_factory, auth_settings, email_sender)
    provisioned = await service.provision(
        email=invitee, name="Clínica Redaction", slug=f"clinica-{uuid.uuid4().hex[:10]}"
    )
    provisioned_clinics.append(provisioned.clinic_id)
    invite_token = token_from_body(
        next(body for recipient, _, body in reversed(email_sender.sent) if recipient == invitee)
    )
    accept_csrf = await anonymous_csrf(api_client)
    accept = await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": invite_token, "password": NEW_PASSWORD},
        headers=mutation_headers(accept_csrf),
    )
    assert accept.status_code == 204

    secrets = {
        "password": PASSWORD,
        "new_password": NEW_PASSWORD,
        "session_token": session_token,
        "bound_csrf": bound,
        "anonymous_csrf": anonymous_csrf_token,
        "reset_token": reset_token,
        "forgot_csrf": forgot_csrf,
        "reset_csrf": reset_csrf,
        "invitation_token": invite_token,
        "accept_csrf": accept_csrf,
        "cookie_header": f"{SESSION_COOKIE}={session_token}",
        "raw_ip": "127.0.0.1",
        "peer": "testclient",
    }
    for name, secret in secrets.items():
        assert secret not in caplog.text, f"{name} leaked into logs"

    audit_rows = await migrator_connection.fetch(
        "SELECT event_type, metadata FROM app.auth_audit_events"
    )
    audit_text = json.dumps([dict(row) for row in audit_rows], default=str)
    for name, secret in secrets.items():
        assert secret not in audit_text, f"{name} leaked into auth audit"

    clinic_audit = await migrator_connection.fetch(
        "SELECT event_type, metadata FROM app.clinic_audit_events"
    )
    clinic_text = json.dumps([dict(row) for row in clinic_audit], default=str)
    for name, secret in secrets.items():
        assert secret not in clinic_text, f"{name} leaked into clinic audit"

    buckets = await migrator_connection.fetch("SELECT bucket_key FROM app.auth_rate_limit_buckets")
    for bucket in buckets:
        key = bytes(bucket["bucket_key"])
        assert email.encode() not in key
        assert b"127.0.0.1" not in key
        assert b"testclient" not in key

    event_types = {
        row["event_type"]
        for row in await migrator_connection.fetch("SELECT event_type FROM app.auth_audit_events")
    }
    assert {"login_succeeded", "password_reset_completed", "invitation_accepted"} <= event_types
