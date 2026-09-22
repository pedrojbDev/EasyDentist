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
from app.platform.logging import JsonLogFormatter

PASSWORD = "structured logging password"
NEW_PASSWORD = "structured logging new password"
CSRF_COOKIE = "easydent_csrf"
SESSION_COOKIE = "easydent_session"
ORIGIN = "http://testserver"
QUERY_SECRET = "query-secret-should-not-be-logged"


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


async def login(
    client: httpx.AsyncClient, email: str, password: str, **extra: str
) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={**mutation_headers(csrf), **extra},
    )
    client.cookies.clear()
    return response


def token_from_body(body: str) -> str:
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


def structured_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    formatter = JsonLogFormatter("development")
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if record.name == "easydentist.api"
    ]


@pytest.mark.anyio
async def test_json_logs_correlate_events_and_never_leak_secrets(
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
    caplog.set_level(logging.INFO, logger="easydentist.api")
    email = make_test_email("logging")
    await seed_user_with_password(email=email, password=PASSWORD)

    request_id = str(uuid.uuid4())
    login_response = await login(api_client, email, PASSWORD, **{"X-Request-Id": request_id})
    assert login_response.status_code == 200
    session_token = login_response.cookies.get(SESSION_COOKIE)
    assert session_token

    failed_login = await login(api_client, email, "wrong-password-12345")
    assert failed_login.status_code == 401

    bound_csrf = (
        await api_client.get(
            "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={session_token}"}
        )
    ).json()["csrf_token"]
    sessions = await api_client.get(
        "/api/v1/auth/sessions", headers={"Cookie": f"{SESSION_COOKIE}={session_token}"}
    )
    assert sessions.status_code == 200
    current_session_id = next(row["id"] for row in sessions.json() if row["current"])
    revoked = await api_client.delete(
        f"/api/v1/auth/sessions/{current_session_id}",
        headers=mutation_headers(bound_csrf, session_token),
    )
    assert revoked.status_code == 204

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

    invitee = make_test_email("logging-invitee")
    service = ProvisionService(session_factory, auth_settings, email_sender)
    provisioned = await service.provision(
        email=invitee, name="Clínica Logging", slug=f"clinica-{uuid.uuid4().hex[:10]}"
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

    queried = await api_client.get(f"/api/v1/auth/me?token={QUERY_SECRET}")
    assert queried.status_code == 401

    events = structured_events(caplog)
    assert events
    joined = "\n".join(json.dumps(event, ensure_ascii=False) for event in events)
    for event in events:
        assert {"timestamp", "service", "environment", "level", "event"} <= event.keys()
        assert event["service"] == "api"
    request_events = [event for event in events if event["event"] == "http.request"]
    assert request_events
    assert any(event.get("request_id") == request_id for event in request_events)
    routes = {event.get("route") for event in request_events}
    assert "/api/v1/auth/login" in routes

    for name, secret in {
        "password": PASSWORD,
        "new_password": NEW_PASSWORD,
        "session_token": session_token,
        "reset_token": reset_token,
        "invitation_token": invite_token,
        "email": email,
        "query_secret": QUERY_SECRET,
        "raw_ip": "127.0.0.1",
    }.items():
        assert secret not in joined, f"{name} leaked into structured logs"

    event_types = {
        row["event_type"]
        for row in await migrator_connection.fetch("SELECT event_type FROM app.auth_audit_events")
    }
    assert {
        "login_succeeded",
        "password_reset_completed",
        "invitation_accepted",
        "session_revoked",
    } <= event_types

    revoked_rows = await migrator_connection.fetch(
        "SELECT metadata FROM app.auth_audit_events WHERE event_type = 'session_revoked'"
    )
    assert any(
        json.loads(row["metadata"]) == {"session_id": current_session_id} for row in revoked_rows
    )
