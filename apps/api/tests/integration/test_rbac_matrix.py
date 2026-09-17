from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import httpx
import pytest
from conftest import RecordingEmailSender, make_test_email
from helpers import insert_clinic, insert_clinic_settings, insert_membership

from app.clinics.rbac import Role

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


class MatrixScenario:
    def __init__(self) -> None:
        self.clinic_id: uuid.UUID
        self.foreign_clinic_id: uuid.UUID
        self.foreign_membership_id: uuid.UUID
        self.victims: dict[str, uuid.UUID]
        self.members: dict[Role, Teammate]


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


async def mutate(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    payload: dict[str, str] | None = None,
) -> httpx.Response:
    csrf_response = await client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    csrf = csrf_response.json()["csrf_token"]
    response = await client.request(
        method,
        url,
        json=payload,
        headers={
            "Cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


async def read(client: httpx.AsyncClient, url: str, token: str) -> httpx.Response:
    response = await client.get(url, headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    client.cookies.clear()
    return response


@pytest.fixture
async def matrix_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[MatrixScenario]:
    built = MatrixScenario()
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"matrix-{suffix}")
    built.foreign_clinic_id = await insert_clinic(migrator_connection, f"matrix-foreign-{suffix}")
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    await insert_clinic_settings(migrator_connection, built.clinic_id)
    built.members = {}
    for role in Role:
        email = make_test_email(f"matrix-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
        built.members[role] = Teammate(email=email, user_id=user_id, membership_id=membership_id)
    foreign_user = await seed_user_with_password(
        email=make_test_email("matrix-foreign-owner"), password=PASSWORD
    )
    built.foreign_membership_id = await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=foreign_user,
        role="OWNER",
        status="ACTIVE",
    )
    built.victims = {}
    for name in ("owner", "admin", "restricted"):
        victim_id = await seed_user_with_password(
            email=make_test_email(f"matrix-victim-{name}"), password=PASSWORD
        )
        built.victims[name] = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=victim_id,
            role="DENTIST",
            status="ACTIVE",
        )
    yield built


def clinic_url(scenario: MatrixScenario, clinic_id: uuid.UUID | None = None) -> str:
    return f"/api/v1/clinics/{clinic_id if clinic_id is not None else scenario.clinic_id}"


EXPECTED: dict[str, dict[Role, int]] = {
    "get_clinics": {role: 200 for role in Role},
    "get_clinic": {role: 200 for role in Role},
    "patch_clinic": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "get_settings": {role: 200 for role in Role},
    "patch_settings": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "get_memberships": {role: 200 for role in Role},
    "patch_membership": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "delete_membership": {
        Role.OWNER: 204,
        Role.ADMIN: 204,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "invite": {
        Role.OWNER: 202,
        Role.ADMIN: 202,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
}

PATCH_TARGETS = {
    Role.OWNER: Role.DENTIST,
    Role.ADMIN: Role.ASSISTANT,
    Role.DENTIST: Role.RECEPTIONIST,
    Role.ASSISTANT: Role.RECEPTIONIST,
    Role.RECEPTIONIST: Role.RECEPTIONIST,
}

DELETE_TARGETS = {
    Role.OWNER: "owner",
    Role.ADMIN: "admin",
    Role.DENTIST: "restricted",
    Role.ASSISTANT: "restricted",
    Role.RECEPTIONIST: "restricted",
}


@pytest.mark.anyio
@pytest.mark.parametrize("operation", list(EXPECTED))
async def test_role_matrix_on_tenancy_endpoints(
    api_client: httpx.AsyncClient,
    matrix_scenario: MatrixScenario,
    email_sender: RecordingEmailSender,
    operation: str,
) -> None:
    scenario = matrix_scenario
    for role in Role:
        token = await login(api_client, scenario.members[role].email)
        if operation == "get_clinics":
            response = await read(api_client, "/api/v1/clinics", token)
        elif operation == "get_clinic":
            response = await read(api_client, clinic_url(scenario), token)
        elif operation == "patch_clinic":
            response = await mutate(
                api_client,
                "PATCH",
                clinic_url(scenario),
                token,
                {"legal_name": f"Razão {role.value}"},
            )
        elif operation == "get_settings":
            response = await read(api_client, f"{clinic_url(scenario)}/settings", token)
        elif operation == "patch_settings":
            response = await mutate(
                api_client,
                "PATCH",
                f"{clinic_url(scenario)}/settings",
                token,
                {"display_name": f"Clínica {role.value}"},
            )
        elif operation == "get_memberships":
            response = await read(api_client, f"{clinic_url(scenario)}/memberships", token)
        elif operation == "patch_membership":
            target = scenario.members[PATCH_TARGETS[role]]
            response = await mutate(
                api_client,
                "PATCH",
                f"{clinic_url(scenario)}/memberships/{target.membership_id}",
                token,
                {"role": "DENTIST"},
            )
        elif operation == "delete_membership":
            target = scenario.victims[DELETE_TARGETS[role]]
            response = await mutate(
                api_client,
                "DELETE",
                f"{clinic_url(scenario)}/memberships/{target}",
                token,
            )
        else:
            response = await mutate(
                api_client,
                "POST",
                f"{clinic_url(scenario)}/invitations",
                token,
                {
                    "email": make_test_email(f"matrix-invite-{role.value.lower()}"),
                    "role": "DENTIST",
                },
            )
        assert response.status_code == EXPECTED[operation][role], (operation, role)


@pytest.mark.anyio
async def test_cross_tenant_endpoints_return_404_for_every_role(
    api_client: httpx.AsyncClient, matrix_scenario: MatrixScenario
) -> None:
    scenario = matrix_scenario
    foreign = clinic_url(scenario, scenario.foreign_clinic_id)
    for role in Role:
        token = await login(api_client, scenario.members[role].email)
        responses = [
            await read(api_client, foreign, token),
            await read(api_client, f"{foreign}/settings", token),
            await read(api_client, f"{foreign}/memberships", token),
            await mutate(api_client, "PATCH", foreign, token, {"legal_name": "Inválido"}),
            await mutate(
                api_client, "PATCH", f"{foreign}/settings", token, {"display_name": "Inválido"}
            ),
            await mutate(
                api_client,
                "PATCH",
                f"{foreign}/memberships/{scenario.foreign_membership_id}",
                token,
                {"role": "DENTIST"},
            ),
            await mutate(
                api_client,
                "DELETE",
                f"{foreign}/memberships/{scenario.foreign_membership_id}",
                token,
            ),
            await mutate(
                api_client,
                "POST",
                f"{foreign}/invitations",
                token,
                {"email": make_test_email("matrix-foreign-invite"), "role": "DENTIST"},
            ),
        ]
        for response in responses:
            assert response.status_code == 404, (role, response.request.url)
            assert response.json()["title"] == "Recurso não encontrado"


@pytest.mark.anyio
async def test_contact_visibility_follows_read_contact_permission(
    api_client: httpx.AsyncClient, matrix_scenario: MatrixScenario
) -> None:
    scenario = matrix_scenario
    for role in Role:
        token = await login(api_client, scenario.members[role].email)
        response = await read(api_client, f"{clinic_url(scenario)}/memberships", token)
        assert response.status_code == 200
        rows = response.json()
        if role in {Role.OWNER, Role.ADMIN}:
            for row in rows:
                assert row["email"]
        else:
            for row in rows:
                assert "email" not in row


@pytest.mark.anyio
async def test_demotion_takes_effect_immediately(
    api_client: httpx.AsyncClient, matrix_scenario: MatrixScenario
) -> None:
    scenario = matrix_scenario
    admin = scenario.members[Role.ADMIN]
    admin_token = await login(api_client, admin.email)
    owner_token = await login(api_client, scenario.members[Role.OWNER].email)
    settings_url = f"{clinic_url(scenario)}/settings"
    before = await mutate(api_client, "PATCH", settings_url, admin_token, {"display_name": "Antes"})
    assert before.status_code == 200

    demoted = await mutate(
        api_client,
        "PATCH",
        f"{clinic_url(scenario)}/memberships/{admin.membership_id}",
        owner_token,
        {"role": "RECEPTIONIST"},
    )
    assert demoted.status_code == 200

    after = await mutate(api_client, "PATCH", settings_url, admin_token, {"display_name": "Depois"})
    still_reads = await read(api_client, settings_url, admin_token)
    assert after.status_code == 403
    assert still_reads.status_code == 200


@pytest.mark.anyio
async def test_last_owner_and_admin_promotion_guards_hold(
    api_client: httpx.AsyncClient, matrix_scenario: MatrixScenario
) -> None:
    scenario = matrix_scenario
    owner = scenario.members[Role.OWNER]
    owner_token = await login(api_client, owner.email)
    admin_token = await login(api_client, scenario.members[Role.ADMIN].email)

    self_demote = await mutate(
        api_client,
        "PATCH",
        f"{clinic_url(scenario)}/memberships/{owner.membership_id}",
        owner_token,
        {"role": "DENTIST"},
    )
    self_remove = await mutate(
        api_client,
        "DELETE",
        f"{clinic_url(scenario)}/memberships/{owner.membership_id}",
        owner_token,
    )
    admin_promotes = await mutate(
        api_client,
        "PATCH",
        f"{clinic_url(scenario)}/memberships/{scenario.members[Role.DENTIST].membership_id}",
        admin_token,
        {"role": "OWNER"},
    )

    assert self_demote.status_code == 409
    assert self_remove.status_code == 409
    assert admin_promotes.status_code == 403


@pytest.mark.anyio
async def test_clinic_audit_metadata_has_no_secrets(
    api_client: httpx.AsyncClient,
    matrix_scenario: MatrixScenario,
    email_sender: RecordingEmailSender,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = matrix_scenario
    owner_token = await login(api_client, scenario.members[Role.OWNER].email)
    invitee = make_test_email("matrix-redaction")
    invited = await mutate(
        api_client,
        "POST",
        f"{clinic_url(scenario)}/invitations",
        owner_token,
        {"email": invitee, "role": "DENTIST"},
    )
    assert invited.status_code == 202
    invite_body = next(body for to, _, body in email_sender.sent if to == invitee)
    invite_token = invite_body.split("#token=")[1].splitlines()[0].strip()

    csrf = await anonymous_csrf(api_client)
    accepted = await api_client.post(
        "/api/v1/invitations/accept",
        json={"token": invite_token, "password": PASSWORD},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    assert accepted.status_code == 204

    rows = await migrator_connection.fetch(
        "SELECT event_type, metadata FROM app.clinic_audit_events WHERE clinic_id = $1",
        scenario.clinic_id,
    )
    metadata = json.dumps([dict(row) for row in rows], default=str)
    secrets = {
        "invite_token": invite_token,
        "password": PASSWORD,
        "csrf": csrf,
        "raw_ip": "127.0.0.1",
        "peer": "testclient",
    }
    for name, secret in secrets.items():
        assert secret not in metadata, name
    event_types = {row["event_type"] for row in rows}
    assert {"membership.invited", "invitation.accepted"} <= event_types
