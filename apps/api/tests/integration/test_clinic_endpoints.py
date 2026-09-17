from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_membership
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


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


def auth_headers(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


class Scenario:
    def __init__(self) -> None:
        self.member_email: str
        self.owner_clinic: uuid.UUID
        self.dentist_clinic: uuid.UUID
        self.pending_clinic: uuid.UUID
        self.suspended_clinic: uuid.UUID
        self.foreign_clinic: uuid.UUID


@pytest.fixture
async def scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    session_factory: async_sessionmaker[AsyncSession],
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[Scenario]:
    built = Scenario()
    built.member_email = make_test_email("clinic-endpoints")
    member_id = await seed_user_with_password(email=built.member_email, password=PASSWORD)
    foreign_id = await seed_user_with_password(
        email=make_test_email("clinic-endpoints-foreign"), password=PASSWORD
    )
    suffix = uuid.uuid4().hex[:10]
    clinics = {
        "owner": await insert_clinic(migrator_connection, f"owner-{suffix}"),
        "dentist": await insert_clinic(migrator_connection, f"dentist-{suffix}"),
        "pending": await insert_clinic(migrator_connection, f"pending-{suffix}"),
        "suspended": await insert_clinic(migrator_connection, f"suspended-{suffix}"),
        "foreign": await insert_clinic(migrator_connection, f"foreign-{suffix}"),
    }
    provisioned_clinics.extend(clinics.values())
    await insert_membership(
        migrator_connection,
        clinic_id=clinics["owner"],
        user_id=member_id,
        role="OWNER",
        status="ACTIVE",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=clinics["dentist"],
        user_id=member_id,
        role="DENTIST",
        status="ACTIVE",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=clinics["pending"],
        user_id=member_id,
        role="ASSISTANT",
        status="PENDING",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=clinics["suspended"],
        user_id=member_id,
        role="RECEPTIONIST",
        status="SUSPENDED",
    )
    await insert_membership(
        migrator_connection,
        clinic_id=clinics["foreign"],
        user_id=foreign_id,
        role="OWNER",
        status="ACTIVE",
    )
    built.owner_clinic = clinics["owner"]
    built.dentist_clinic = clinics["dentist"]
    built.pending_clinic = clinics["pending"]
    built.suspended_clinic = clinics["suspended"]
    built.foreign_clinic = clinics["foreign"]
    yield built


@pytest.mark.anyio
async def test_clinic_routes_require_session(api_client: httpx.AsyncClient) -> None:
    listing = await api_client.get("/api/v1/clinics")
    detail = await api_client.get(f"/api/v1/clinics/{uuid.uuid4()}")

    assert listing.status_code == 401
    assert detail.status_code == 401


@pytest.mark.anyio
async def test_list_returns_only_active_memberships_with_roles(
    api_client: httpx.AsyncClient, scenario: Scenario
) -> None:
    token = await login(api_client, scenario.member_email)

    response = await api_client.get("/api/v1/clinics", headers=auth_headers(token))

    assert response.status_code == 200
    rows = response.json()
    assert {row["id"] for row in rows} == {
        str(scenario.owner_clinic),
        str(scenario.dentist_clinic),
    }
    by_id = {row["id"]: row for row in rows}
    assert by_id[str(scenario.owner_clinic)]["role"] == "OWNER"
    assert by_id[str(scenario.dentist_clinic)]["role"] == "DENTIST"
    for row in rows:
        assert set(row) == {"id", "slug", "legal_name", "status", "role"}
        assert row["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_detail_returns_clinic_and_role_for_active_member(
    api_client: httpx.AsyncClient, scenario: Scenario
) -> None:
    token = await login(api_client, scenario.member_email)

    response = await api_client.get(
        f"/api/v1/clinics/{scenario.owner_clinic}", headers=auth_headers(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(scenario.owner_clinic)
    assert body["role"] == "OWNER"
    assert body["status"] == "ACTIVE"
    assert body["slug"].startswith("owner-")


@pytest.mark.anyio
async def test_hidden_clinics_are_indistinguishable_from_unknown(
    api_client: httpx.AsyncClient, scenario: Scenario
) -> None:
    token = await login(api_client, scenario.member_email)

    responses = [
        await api_client.get(f"/api/v1/clinics/{clinic_id}", headers=auth_headers(token))
        for clinic_id in (
            scenario.foreign_clinic,
            scenario.pending_clinic,
            scenario.suspended_clinic,
            uuid.uuid4(),
        )
    ]

    for response in responses:
        assert response.status_code == 404
    bodies = [response.json() for response in responses]
    assert len({(body["type"], body["title"]) for body in bodies}) == 1
    assert bodies[0]["title"] == "Recurso não encontrado"


@pytest.mark.anyio
async def test_membership_revocation_takes_effect_immediately(
    api_client: httpx.AsyncClient,
    scenario: Scenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    token = await login(api_client, scenario.member_email)
    before = await api_client.get(
        f"/api/v1/clinics/{scenario.dentist_clinic}", headers=auth_headers(token)
    )
    assert before.status_code == 200

    await migrator_connection.execute(
        "UPDATE app.memberships SET status = 'SUSPENDED' "
        "WHERE clinic_id = $1 AND user_id = (SELECT id FROM app.users WHERE email = $2)",
        scenario.dentist_clinic,
        scenario.member_email,
    )

    after = await api_client.get(
        f"/api/v1/clinics/{scenario.dentist_clinic}", headers=auth_headers(token)
    )
    listing = await api_client.get("/api/v1/clinics", headers=auth_headers(token))
    assert after.status_code == 404
    assert str(scenario.dentist_clinic) not in listing.text
