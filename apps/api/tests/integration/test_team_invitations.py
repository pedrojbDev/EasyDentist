from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

import asyncpg
import httpx
import pytest
from conftest import RecordingEmailSender, make_test_email
from helpers import insert_clinic, insert_clinic_settings, insert_membership

PASSWORD = "another correct battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


class InviteScenario:
    def __init__(self) -> None:
        self.clinic_id: uuid.UUID
        self.owner: Teammate
        self.admin: Teammate
        self.dentist: Teammate
        self.assistant: Teammate
        self.receptionist: Teammate


@pytest.fixture
async def invite_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[InviteScenario]:
    built = InviteScenario()
    built.clinic_id = await insert_clinic(migrator_connection, f"invite-{uuid.uuid4().hex[:10]}")
    provisioned_clinics.append(built.clinic_id)
    await insert_clinic_settings(migrator_connection, built.clinic_id)
    for name, role in (
        ("owner", "OWNER"),
        ("admin", "ADMIN"),
        ("dentist", "DENTIST"),
        ("assistant", "ASSISTANT"),
        ("receptionist", "RECEPTIONIST"),
    ):
        email = make_test_email(f"invite-{name}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role,
            status="ACTIVE",
        )
        setattr(built, name, Teammate(email=email, user_id=user_id, membership_id=membership_id))
    yield built


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


async def login(client: httpx.AsyncClient, email: str) -> str:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    client.cookies.clear()
    assert response.status_code == 200
    token = response.cookies.get(SESSION_COOKIE)
    assert token
    return token


async def invite(
    client: httpx.AsyncClient, scenario: InviteScenario, token: str, *, email: str, role: str
) -> httpx.Response:
    csrf_response = await client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    csrf = csrf_response.json()["csrf_token"]
    response = await client.post(
        f"/api/v1/clinics/{scenario.clinic_id}/invitations",
        json={"email": email, "role": role},
        headers={
            "Cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


async def accept_invitation(
    client: httpx.AsyncClient, token: str, password: str | None
) -> httpx.Response:
    payload: dict[str, str] = {"token": token}
    if password is not None:
        payload["password"] = password
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/invitations/accept",
        json=payload,
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    client.cookies.clear()
    return response


def token_from_sender(sender: RecordingEmailSender, recipient: str) -> str:
    body = next(body for to, _, body in reversed(sender.sent) if to == recipient)
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


async def outbox_row(
    migrator_connection: asyncpg.Connection, recipient: str
) -> asyncpg.Record | None:
    row = await migrator_connection.fetchrow(
        "SELECT template, status, idempotency_key, payload FROM app.email_outbox "
        "WHERE recipient = $1",
        recipient,
    )
    return row


@pytest.mark.anyio
async def test_owner_can_invite_any_role(
    api_client: httpx.AsyncClient,
    invite_scenario: InviteScenario,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
) -> None:
    token = await login(api_client, invite_scenario.owner.email)
    invitee = make_test_email("invite-new-owner")

    response = await invite(api_client, invite_scenario, token, email=invitee, role="OWNER")

    assert response.status_code == 202
    body = response.json()
    assert body["membership_id"]
    assert body["invitation_expires_at"]
    membership = await migrator_connection.fetchrow(
        "SELECT role, status FROM app.memberships WHERE id = $1", uuid.UUID(body["membership_id"])
    )
    assert membership["role"] == "OWNER"
    assert membership["status"] == "PENDING"
    invitation = await migrator_connection.fetchrow(
        "SELECT email, expires_at, accepted_at FROM app.membership_invitations "
        "WHERE membership_id = $1",
        uuid.UUID(body["membership_id"]),
    )
    assert invitation["email"] == invitee
    assert invitation["accepted_at"] is None
    assert invitation["expires_at"] == datetime.fromisoformat(body["invitation_expires_at"])
    audit = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type = 'membership.invited'",
        invite_scenario.clinic_id,
    )
    assert audit == 1

    row = await outbox_row(migrator_connection, invitee)
    assert row is not None
    assert row["template"] == "team-invitation"
    assert row["status"] == "SENT"
    assert row["idempotency_key"].startswith("team-invitation:")
    sent_body = json.loads(str(row["payload"]))["body"]
    assert "#token=" in sent_body
    assert "Proprietário" in sent_body
    assert str(invite_scenario.clinic_id) in sent_body
    assert len(email_sender.sent) == 1


@pytest.mark.anyio
async def test_admin_can_invite_non_owner_non_admin(
    api_client: httpx.AsyncClient,
    invite_scenario: InviteScenario,
    email_sender: RecordingEmailSender,
) -> None:
    token = await login(api_client, invite_scenario.admin.email)

    response = await invite(
        api_client,
        invite_scenario,
        token,
        email=make_test_email("invite-by-admin"),
        role="DENTIST",
    )

    assert response.status_code == 202


@pytest.mark.anyio
async def test_admin_cannot_invite_owner_or_admin(
    api_client: httpx.AsyncClient, invite_scenario: InviteScenario
) -> None:
    token = await login(api_client, invite_scenario.admin.email)

    for role in ("OWNER", "ADMIN"):
        response = await invite(
            api_client,
            invite_scenario,
            token,
            email=make_test_email(f"invite-blocked-{role.lower()}"),
            role=role,
        )
        assert response.status_code == 403
        assert response.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_operational_roles_cannot_invite(
    api_client: httpx.AsyncClient, invite_scenario: InviteScenario
) -> None:
    for teammate in (
        invite_scenario.dentist,
        invite_scenario.assistant,
        invite_scenario.receptionist,
    ):
        token = await login(api_client, teammate.email)
        response = await invite(
            api_client,
            invite_scenario,
            token,
            email=make_test_email("invite-denied"),
            role="DENTIST",
        )
        assert response.status_code == 403, teammate.email


@pytest.mark.anyio
async def test_inviting_an_existing_member_returns_409(
    api_client: httpx.AsyncClient, invite_scenario: InviteScenario
) -> None:
    token = await login(api_client, invite_scenario.owner.email)

    response = await invite(
        api_client, invite_scenario, token, email=invite_scenario.dentist.email, role="DENTIST"
    )

    assert response.status_code == 409
    assert response.json()["title"] == "Conflito"


@pytest.mark.anyio
async def test_unknown_role_returns_422(
    api_client: httpx.AsyncClient, invite_scenario: InviteScenario
) -> None:
    token = await login(api_client, invite_scenario.owner.email)

    response = await invite(
        api_client,
        invite_scenario,
        token,
        email=make_test_email("invite-bad-role"),
        role="SUPERADMIN",
    )

    assert response.status_code == 422
    assert response.json()["title"] == "Dados inválidos"


@pytest.mark.anyio
async def test_invite_rate_limit_per_recipient(
    api_client: httpx.AsyncClient,
    invite_scenario: InviteScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    token = await login(api_client, invite_scenario.owner.email)
    invitee = make_test_email("invite-rate")

    responses = [
        await invite(api_client, invite_scenario, token, email=invitee, role="DENTIST")
        for _ in range(4)
    ]

    assert responses[0].status_code == 202
    assert [response.status_code for response in responses[1:3]] == [409, 409]
    blocked = responses[3]
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) >= 1
    assert blocked.json()["title"] == "Muitas tentativas"
    audits = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.auth_audit_events WHERE event_type = 'rate_limit_triggered'"
    )
    assert audits == 1


@pytest.mark.anyio
async def test_invite_requires_csrf(
    api_client: httpx.AsyncClient, invite_scenario: InviteScenario
) -> None:
    token = await login(api_client, invite_scenario.owner.email)

    response = await api_client.post(
        f"/api/v1/clinics/{invite_scenario.clinic_id}/invitations",
        json={"email": make_test_email("invite-csrf"), "role": "DENTIST"},
        headers={"Cookie": f"{SESSION_COOKIE}={token}"},
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_invited_user_accepts_and_gains_access(
    api_client: httpx.AsyncClient,
    invite_scenario: InviteScenario,
    email_sender: RecordingEmailSender,
) -> None:
    owner_token = await login(api_client, invite_scenario.owner.email)
    invitee = make_test_email("invite-accept")
    invited = await invite(api_client, invite_scenario, owner_token, email=invitee, role="DENTIST")
    assert invited.status_code == 202

    accepted = await accept_invitation(
        api_client, token_from_sender(email_sender, invitee), PASSWORD
    )

    assert accepted.status_code == 204
    member_token = await login(api_client, invitee)
    listing = await api_client.get(
        "/api/v1/clinics", headers={"Cookie": f"{SESSION_COOKIE}={member_token}"}
    )
    assert listing.status_code == 200
    entry = next(row for row in listing.json() if row["id"] == str(invite_scenario.clinic_id))
    assert entry["role"] == "DENTIST"


@pytest.mark.anyio
async def test_new_user_cannot_accept_without_password(
    api_client: httpx.AsyncClient,
    invite_scenario: InviteScenario,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
) -> None:
    owner_token = await login(api_client, invite_scenario.owner.email)
    invitee = make_test_email("invite-no-password")
    invited = await invite(
        api_client, invite_scenario, owner_token, email=invitee, role="ASSISTANT"
    )
    assert invited.status_code == 202
    membership_id = uuid.UUID(invited.json()["membership_id"])

    response = await accept_invitation(
        api_client, token_from_sender(email_sender, invitee), password=None
    )

    assert response.status_code == 422
    assert response.json()["title"] == "Dados inválidos"
    status_value = await migrator_connection.fetchval(
        "SELECT status FROM app.memberships WHERE id = $1", membership_id
    )
    assert status_value == "PENDING"
    remaining = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.membership_invitations "
        "WHERE membership_id = $1 AND accepted_at IS NULL",
        membership_id,
    )
    assert remaining == 1
