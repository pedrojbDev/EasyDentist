from __future__ import annotations

import asyncio
import uuid

import asyncpg
import httpx
import pytest
from conftest import RecordingEmailSender, make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.provisioning import ProvisionService
from app.auth.settings import AuthSettings

PASSWORD = "another correct battery staple"
EXISTING_PASSWORD = "correct horse battery staple"
CSRF_COOKIE = "easydent_csrf"
SESSION_COOKIE = "easydent_session"
ORIGIN = "http://testserver"


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


def mutation_headers(csrf: str) -> dict[str, str]:
    return {"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN}


async def provision_invitation(
    session_factory: async_sessionmaker[AsyncSession],
    settings: AuthSettings,
    sender: RecordingEmailSender,
    *,
    email: str,
) -> uuid.UUID:
    service = ProvisionService(session_factory, settings, sender)
    result = await service.provision(
        email=email, name="Clínica Convite", slug=f"clinica-{uuid.uuid4().hex[:10]}"
    )
    return result.clinic_id


def invitation_token(sender: RecordingEmailSender, email: str) -> str:
    body = next(body for recipient, _, body in reversed(sender.sent) if recipient == email)
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


async def accept(
    client: httpx.AsyncClient, token: str, password: str | None = PASSWORD
) -> httpx.Response:
    payload: dict[str, str] = {"token": token}
    if password is not None:
        payload["password"] = password
    response = await client.post(
        "/api/v1/invitations/accept",
        json=payload,
        headers=mutation_headers(await anonymous_csrf(client)),
    )
    client.cookies.clear()
    return response


async def login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=mutation_headers(await anonymous_csrf(client)),
    )
    client.cookies.clear()
    return response


@pytest.mark.anyio
async def test_accept_activates_tenant_and_sets_password(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)

    response = await accept(api_client, token)

    assert response.status_code == 204
    membership = await migrator_connection.fetchrow(
        "SELECT status FROM app.memberships WHERE clinic_id = $1", clinic_id
    )
    clinic = await migrator_connection.fetchrow(
        "SELECT status FROM app.clinics WHERE id = $1", clinic_id
    )
    assert membership["status"] == "ACTIVE"
    assert clinic["status"] == "ACTIVE"

    user = await migrator_connection.fetchrow(
        "SELECT id, email_verified_at FROM app.users WHERE email = $1", email
    )
    assert user["email_verified_at"] is not None
    credentials = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.password_credentials WHERE user_id = $1", user["id"]
    )
    assert credentials == 1
    invitation = await migrator_connection.fetchrow(
        "SELECT accepted_at FROM app.membership_invitations WHERE clinic_id = $1", clinic_id
    )
    assert invitation["accepted_at"] is not None

    clinic_audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type = 'invitation.accepted'",
        clinic_id,
    )
    auth_audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.auth_audit_events "
        "WHERE user_id = $1 AND event_type = 'invitation_accepted'",
        user["id"],
    )
    assert clinic_audit == 1
    assert auth_audit == 1

    authenticated = await login(api_client, email, PASSWORD)
    assert authenticated.status_code == 200
    assert authenticated.cookies.get(SESSION_COOKIE) is not None


@pytest.mark.anyio
async def test_accept_expired_invitation_is_generic_and_leaves_state_intact(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-expired")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)
    await migrator_connection.execute(
        "UPDATE app.membership_invitations SET expires_at = now() - interval '1 minute' "
        "WHERE clinic_id = $1",
        clinic_id,
    )

    expired = await accept(api_client, token)
    unknown = await accept(api_client, "definitely-not-a-token")

    assert expired.status_code == 400
    assert expired.json()["title"] == "Requisição inválida"
    assert expired.json()["type"] == unknown.json()["type"]
    assert expired.json()["title"] == unknown.json()["title"]

    membership = await migrator_connection.fetchrow(
        "SELECT status FROM app.memberships WHERE clinic_id = $1", clinic_id
    )
    clinic = await migrator_connection.fetchrow(
        "SELECT status FROM app.clinics WHERE id = $1", clinic_id
    )
    invitation = await migrator_connection.fetchrow(
        "SELECT accepted_at FROM app.membership_invitations WHERE clinic_id = $1", clinic_id
    )
    credentials = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.password_credentials pc "
        "JOIN app.users u ON u.id = pc.user_id WHERE u.email = $1",
        email,
    )
    assert membership["status"] == "PENDING"
    assert clinic["status"] == "PROVISIONING"
    assert invitation["accepted_at"] is None
    assert credentials == 0


@pytest.mark.anyio
async def test_accept_reused_token_is_rejected(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-reuse")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)

    assert (await accept(api_client, token)).status_code == 204
    reused = await accept(api_client, token)

    assert reused.status_code == 400
    assert reused.json()["title"] == "Requisição inválida"
    accepted = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.membership_invitations "
        "WHERE clinic_id = $1 AND accepted_at IS NOT NULL",
        clinic_id,
    )
    assert accepted == 1


@pytest.mark.anyio
async def test_accept_weak_password_is_rejected_before_consuming_invitation(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-weak")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)

    rejected = await accept(api_client, token, password="too-short")
    assert rejected.status_code == 422
    assert rejected.json()["title"] == "Dados inválidos"

    membership = await migrator_connection.fetchval(
        "SELECT status FROM app.memberships WHERE clinic_id = $1", clinic_id
    )
    assert membership == "PENDING"

    assert (await accept(api_client, token)).status_code == 204


@pytest.mark.anyio
async def test_concurrent_accepts_yield_exactly_one_success(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-concurrent")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)
    headers = mutation_headers(await anonymous_csrf(api_client))

    responses = await asyncio.gather(
        api_client.post(
            "/api/v1/invitations/accept",
            json={"token": token, "password": PASSWORD},
            headers=headers,
        ),
        api_client.post(
            "/api/v1/invitations/accept",
            json={"token": token, "password": PASSWORD},
            headers=headers,
        ),
    )

    assert sorted(response.status_code for response in responses) == [204, 400]
    clinic_audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type = 'invitation.accepted'",
        clinic_id,
    )
    accepted = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.membership_invitations "
        "WHERE clinic_id = $1 AND accepted_at IS NOT NULL",
        clinic_id,
    )
    assert clinic_audit == 1
    assert accepted == 1


@pytest.mark.anyio
async def test_accept_requires_csrf(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-csrf")
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)

    response = await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": invitation_token(email_sender, email), "password": PASSWORD},
    )

    assert response.status_code == 403
    assert response.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_accept_for_existing_user_keeps_password_and_sessions(
    api_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender: RecordingEmailSender,
    seed_user_with_password,
    migrator_connection: asyncpg.Connection,
    provisioned_clinics: list[uuid.UUID],
) -> None:
    email = make_test_email("accept-existing")
    user_id = await seed_user_with_password(email=email, password=EXISTING_PASSWORD)
    old_login = await login(api_client, email, EXISTING_PASSWORD)
    assert old_login.status_code == 200
    old_session = old_login.cookies.get(SESSION_COOKIE)
    assert old_session
    clinic_id = await provision_invitation(
        session_factory, auth_settings, email_sender, email=email
    )
    provisioned_clinics.append(clinic_id)
    token = invitation_token(email_sender, email)

    with_password = await accept(api_client, token, password=PASSWORD)

    assert with_password.status_code == 422
    assert with_password.json()["title"] == "Dados inválidos"
    pending = await migrator_connection.fetchval(
        "SELECT status FROM app.memberships WHERE clinic_id = $1", clinic_id
    )
    assert pending == "PENDING"

    accepted = await accept(api_client, token, password=None)

    assert accepted.status_code == 204
    membership = await migrator_connection.fetchval(
        "SELECT status FROM app.memberships WHERE clinic_id = $1", clinic_id
    )
    assert membership == "ACTIVE"
    retained = await api_client.get(
        "/api/v1/auth/me", headers={"Cookie": f"{SESSION_COOKIE}={old_session}"}
    )
    assert retained.status_code == 200
    credential = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.password_credentials WHERE user_id = $1", user_id
    )
    assert credential == 1
    assert (await login(api_client, email, EXISTING_PASSWORD)).status_code == 200
    assert (await login(api_client, email, PASSWORD)).status_code == 401
