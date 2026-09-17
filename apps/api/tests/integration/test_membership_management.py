from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_membership

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


@dataclass(frozen=True, slots=True)
class Member:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID
    role: str


class TeamScenario:
    def __init__(self) -> None:
        self.clinic_id: uuid.UUID
        self.foreign_clinic_id: uuid.UUID
        self.members: dict[str, Member]


@pytest.fixture
async def team_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[TeamScenario]:
    built = TeamScenario()
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"team-{suffix}")
    built.foreign_clinic_id = await insert_clinic(migrator_connection, f"team-foreign-{suffix}")
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    built.members = {}
    for key, role in (
        ("owner", "OWNER"),
        ("co_owner", "OWNER"),
        ("admin", "ADMIN"),
        ("dentist", "DENTIST"),
        ("assistant", "ASSISTANT"),
        ("receptionist", "RECEPTIONIST"),
    ):
        email = make_test_email(f"team-{key}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role,
            status="ACTIVE",
        )
        built.members[key] = Member(
            email=email, user_id=user_id, membership_id=membership_id, role=role
        )
    foreign_email = make_test_email("team-foreign-owner")
    foreign_user = await seed_user_with_password(email=foreign_email, password=PASSWORD)
    foreign_membership = await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=foreign_user,
        role="OWNER",
        status="ACTIVE",
    )
    built.members["foreign"] = Member(
        email=foreign_email,
        user_id=foreign_user,
        membership_id=foreign_membership,
        role="OWNER",
    )
    yield built


async def login(client: httpx.AsyncClient, email: str) -> str:
    client.cookies.clear()
    csrf_response = await client.get("/api/v1/auth/csrf")
    csrf = csrf_response.json()["csrf_token"]
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


def memberships_url(scenario: TeamScenario) -> str:
    return f"/api/v1/clinics/{scenario.clinic_id}/memberships"


async def audit_events(migrator_connection: asyncpg.Connection, clinic_id: uuid.UUID) -> list[str]:
    rows = await migrator_connection.fetch(
        "SELECT event_type FROM app.clinic_audit_events WHERE clinic_id = $1", clinic_id
    )
    return [row["event_type"] for row in rows]


@pytest.mark.anyio
async def test_owner_can_change_member_role(
    api_client: httpx.AsyncClient,
    team_scenario: TeamScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    token = await login(api_client, team_scenario.members["owner"].email)
    dentist = team_scenario.members["dentist"]

    response = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{dentist.membership_id}",
        token,
        {"role": "ASSISTANT"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ASSISTANT"
    stored = await migrator_connection.fetchval(
        "SELECT role FROM app.memberships WHERE id = $1", dentist.membership_id
    )
    assert stored == "ASSISTANT"
    assert "membership.role_changed" in await audit_events(
        migrator_connection, team_scenario.clinic_id
    )


@pytest.mark.anyio
async def test_owner_can_remove_member_and_effect_is_immediate(
    api_client: httpx.AsyncClient,
    team_scenario: TeamScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    dentist = team_scenario.members["dentist"]
    dentist_token = await login(api_client, dentist.email)
    owner_token = await login(api_client, team_scenario.members["owner"].email)
    before = await api_client.get(
        f"/api/v1/clinics/{team_scenario.clinic_id}",
        headers={"Cookie": f"{SESSION_COOKIE}={dentist_token}"},
    )
    assert before.status_code == 200

    response = await mutate(
        api_client,
        "DELETE",
        f"{memberships_url(team_scenario)}/{dentist.membership_id}",
        owner_token,
    )

    assert response.status_code == 204
    after = await api_client.get(
        f"/api/v1/clinics/{team_scenario.clinic_id}",
        headers={"Cookie": f"{SESSION_COOKIE}={dentist_token}"},
    )
    assert after.status_code == 404
    remaining = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.memberships WHERE id = $1", dentist.membership_id
    )
    assert remaining == 0
    assert "membership.removed" in await audit_events(migrator_connection, team_scenario.clinic_id)
    reinvited = await insert_membership(
        migrator_connection,
        clinic_id=team_scenario.clinic_id,
        user_id=dentist.user_id,
        role="DENTIST",
        status="PENDING",
    )
    assert reinvited is not None


@pytest.mark.anyio
async def test_admin_cannot_promote_owner_or_touch_admin(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    token = await login(api_client, team_scenario.members["admin"].email)
    dentist = team_scenario.members["dentist"]
    assistant = team_scenario.members["assistant"]
    admin = team_scenario.members["admin"]

    promote_owner = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{dentist.membership_id}",
        token,
        {"role": "OWNER"},
    )
    promote_admin = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{assistant.membership_id}",
        token,
        {"role": "ADMIN"},
    )
    touch_admin = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{admin.membership_id}",
        token,
        {"role": "DENTIST"},
    )

    for response in (promote_owner, promote_admin, touch_admin):
        assert response.status_code == 403
        assert response.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_admin_can_manage_non_owner_non_admin_members(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    token = await login(api_client, team_scenario.members["admin"].email)
    assistant = team_scenario.members["assistant"]
    receptionist = team_scenario.members["receptionist"]

    changed = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{assistant.membership_id}",
        token,
        {"role": "DENTIST"},
    )
    removed = await mutate(
        api_client,
        "DELETE",
        f"{memberships_url(team_scenario)}/{receptionist.membership_id}",
        token,
    )

    assert changed.status_code == 200
    assert removed.status_code == 204


@pytest.mark.anyio
async def test_last_owner_cannot_be_demoted_or_removed(
    api_client: httpx.AsyncClient,
    team_scenario: TeamScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    owner = team_scenario.members["owner"]
    co_owner = team_scenario.members["co_owner"]
    token = await login(api_client, owner.email)
    url = f"{memberships_url(team_scenario)}/{co_owner.membership_id}"
    demoted = await mutate(api_client, "PATCH", url, token, {"role": "DENTIST"})
    assert demoted.status_code == 200

    self_url = f"{memberships_url(team_scenario)}/{owner.membership_id}"
    demote_self = await mutate(api_client, "PATCH", self_url, token, {"role": "DENTIST"})
    remove_self = await mutate(api_client, "DELETE", self_url, token)

    assert demote_self.status_code == 409
    assert remove_self.status_code == 409
    assert demote_self.json()["title"] == "Conflito"
    owners = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.memberships "
        "WHERE clinic_id = $1 AND role = 'OWNER' AND status = 'ACTIVE'",
        team_scenario.clinic_id,
    )
    assert owners == 1


@pytest.mark.anyio
async def test_membership_list_hides_email_without_read_contact(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    dentist_token = await login(api_client, team_scenario.members["dentist"].email)
    admin_token = await login(api_client, team_scenario.members["admin"].email)

    restricted = await api_client.get(
        memberships_url(team_scenario),
        headers={"Cookie": f"{SESSION_COOKIE}={dentist_token}"},
    )
    contact = await api_client.get(
        memberships_url(team_scenario),
        headers={"Cookie": f"{SESSION_COOKIE}={admin_token}"},
    )

    assert restricted.status_code == 200
    assert contact.status_code == 200
    for row in restricted.json():
        assert set(row) == {"id", "user_id", "role", "status", "created_at"}
        assert "email" not in row
    by_id = {row["id"]: row for row in contact.json()}
    owner_row = by_id[str(team_scenario.members["owner"].membership_id)]
    assert owner_row["email"] == team_scenario.members["owner"].email


@pytest.mark.anyio
async def test_membership_management_requires_permission(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    victim = team_scenario.members["assistant"]
    for key in ("dentist", "assistant", "receptionist"):
        token = await login(api_client, team_scenario.members[key].email)
        listing = await api_client.get(
            memberships_url(team_scenario),
            headers={"Cookie": f"{SESSION_COOKIE}={token}"},
        )
        patch_response = await mutate(
            api_client,
            "PATCH",
            f"{memberships_url(team_scenario)}/{victim.membership_id}",
            token,
            {"role": "DENTIST"},
        )
        delete_response = await mutate(
            api_client,
            "DELETE",
            f"{memberships_url(team_scenario)}/{victim.membership_id}",
            token,
        )
        assert listing.status_code == 200, key
        assert patch_response.status_code == 403, key
        assert delete_response.status_code == 403, key


@pytest.mark.anyio
async def test_unknown_or_foreign_membership_returns_404(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    token = await login(api_client, team_scenario.members["owner"].email)
    unknown_url = f"{memberships_url(team_scenario)}/{uuid.uuid4()}"
    foreign_url = (
        f"{memberships_url(team_scenario)}/{team_scenario.members['foreign'].membership_id}"
    )

    responses = [
        await mutate(api_client, "PATCH", unknown_url, token, {"role": "DENTIST"}),
        await mutate(api_client, "DELETE", unknown_url, token),
        await mutate(api_client, "PATCH", foreign_url, token, {"role": "DENTIST"}),
        await mutate(api_client, "DELETE", foreign_url, token),
    ]

    for response in responses:
        assert response.status_code == 404
        assert response.json()["title"] == "Recurso não encontrado"


@pytest.mark.anyio
async def test_unknown_role_in_request_returns_422(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    token = await login(api_client, team_scenario.members["owner"].email)

    response = await mutate(
        api_client,
        "PATCH",
        f"{memberships_url(team_scenario)}/{team_scenario.members['dentist'].membership_id}",
        token,
        {"role": "SUPERADMIN"},
    )

    assert response.status_code == 422
    assert response.json()["title"] == "Dados inválidos"


@pytest.mark.anyio
async def test_concurrent_self_demotions_keep_one_owner(
    api_client: httpx.AsyncClient,
    team_scenario: TeamScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    owner = team_scenario.members["owner"]
    co_owner = team_scenario.members["co_owner"]
    owner_token = await login(api_client, owner.email)
    co_owner_token = await login(api_client, co_owner.email)

    responses = await asyncio.gather(
        mutate(
            api_client,
            "PATCH",
            f"{memberships_url(team_scenario)}/{owner.membership_id}",
            owner_token,
            {"role": "DENTIST"},
        ),
        mutate(
            api_client,
            "PATCH",
            f"{memberships_url(team_scenario)}/{co_owner.membership_id}",
            co_owner_token,
            {"role": "DENTIST"},
        ),
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    owners = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.memberships "
        "WHERE clinic_id = $1 AND role = 'OWNER' AND status = 'ACTIVE'",
        team_scenario.clinic_id,
    )
    assert owners == 1


@pytest.mark.anyio
async def test_concurrent_owner_removals_keep_one_owner(
    api_client: httpx.AsyncClient,
    team_scenario: TeamScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    owner = team_scenario.members["owner"]
    co_owner = team_scenario.members["co_owner"]
    owner_token = await login(api_client, owner.email)
    co_owner_token = await login(api_client, co_owner.email)

    responses = await asyncio.gather(
        mutate(
            api_client,
            "DELETE",
            f"{memberships_url(team_scenario)}/{co_owner.membership_id}",
            owner_token,
        ),
        mutate(
            api_client,
            "DELETE",
            f"{memberships_url(team_scenario)}/{owner.membership_id}",
            co_owner_token,
        ),
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses[0] == 204
    assert statuses[1] in {403, 404}
    owners = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.memberships "
        "WHERE clinic_id = $1 AND role = 'OWNER' AND status = 'ACTIVE'",
        team_scenario.clinic_id,
    )
    assert owners == 1


@pytest.mark.anyio
async def test_concurrent_removal_of_same_member_yields_one_success(
    api_client: httpx.AsyncClient, team_scenario: TeamScenario
) -> None:
    token = await login(api_client, team_scenario.members["owner"].email)
    url = f"{memberships_url(team_scenario)}/{team_scenario.members['dentist'].membership_id}"

    responses = await asyncio.gather(
        mutate(api_client, "DELETE", url, token),
        mutate(api_client, "DELETE", url, token),
    )

    assert sorted(response.status_code for response in responses) == [204, 404]
