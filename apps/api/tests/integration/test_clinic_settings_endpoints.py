from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import insert_clinic, insert_clinic_settings, insert_membership

from app.clinics.rbac import Role

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


async def patch(
    client: httpx.AsyncClient, url: str, token: str, payload: dict[str, str]
) -> httpx.Response:
    csrf_response = await client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    csrf = csrf_response.json()["csrf_token"]
    response = await client.patch(
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


class RoleScenario:
    def __init__(self) -> None:
        self.clinic_id: uuid.UUID
        self.foreign_clinic_id: uuid.UUID
        self.emails: dict[Role, str]


@pytest.fixture
async def role_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[RoleScenario]:
    built = RoleScenario()
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"roles-{suffix}")
    built.foreign_clinic_id = await insert_clinic(migrator_connection, f"foreign-{suffix}")
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    await insert_clinic_settings(migrator_connection, built.clinic_id)
    await insert_clinic_settings(migrator_connection, built.foreign_clinic_id)
    built.emails = {}
    for role in Role:
        email = make_test_email(f"m143-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        built.emails[role] = email
        await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
    foreign_user = await seed_user_with_password(
        email=make_test_email("m143-foreign"), password=PASSWORD
    )
    await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=foreign_user,
        role="OWNER",
        status="ACTIVE",
    )
    yield built


@pytest.mark.anyio
async def test_patch_clinic_legal_name_as_owner_persists(
    api_client: httpx.AsyncClient,
    role_scenario: RoleScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    token = await login(api_client, role_scenario.emails[Role.OWNER])

    response = await patch(
        api_client,
        f"/api/v1/clinics/{role_scenario.clinic_id}",
        token,
        {"legal_name": "Razão Social Atualizada Ltda"},
    )

    assert response.status_code == 200
    assert response.json()["legal_name"] == "Razão Social Atualizada Ltda"
    stored = await migrator_connection.fetchval(
        "SELECT legal_name FROM app.clinics WHERE id = $1", role_scenario.clinic_id
    )
    assert stored == "Razão Social Atualizada Ltda"


@pytest.mark.anyio
async def test_patch_clinic_rejects_invalid_legal_name(
    api_client: httpx.AsyncClient, role_scenario: RoleScenario
) -> None:
    token = await login(api_client, role_scenario.emails[Role.OWNER])

    empty = await patch(
        api_client, f"/api/v1/clinics/{role_scenario.clinic_id}", token, {"legal_name": ""}
    )
    too_long = await patch(
        api_client,
        f"/api/v1/clinics/{role_scenario.clinic_id}",
        token,
        {"legal_name": "x" * 201},
    )

    assert empty.status_code == 422
    assert too_long.status_code == 422
    assert empty.json()["title"] == "Dados inválidos"


@pytest.mark.anyio
async def test_get_settings_returns_current_values_for_any_member(
    api_client: httpx.AsyncClient, role_scenario: RoleScenario
) -> None:
    token = await login(api_client, role_scenario.emails[Role.RECEPTIONIST])

    response = await api_client.get(
        f"/api/v1/clinics/{role_scenario.clinic_id}/settings",
        headers={"Cookie": f"{SESSION_COOKIE}={token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["clinic_id"] == str(role_scenario.clinic_id)
    assert body["display_name"] == f"Clinic {role_scenario.clinic_id}"
    assert body["timezone"] == "America/Bahia"
    assert body["locale"] == "pt-BR"
    assert body["currency"] == "BRL"


@pytest.mark.anyio
async def test_patch_settings_as_owner_and_admin_persists(
    api_client: httpx.AsyncClient,
    role_scenario: RoleScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    owner = await login(api_client, role_scenario.emails[Role.OWNER])
    owner_response = await patch(
        api_client,
        f"/api/v1/clinics/{role_scenario.clinic_id}/settings",
        owner,
        {"display_name": "Sorriso Odontologia", "timezone": "America/Sao_Paulo"},
    )
    admin = await login(api_client, role_scenario.emails[Role.ADMIN])
    admin_response = await patch(
        api_client,
        f"/api/v1/clinics/{role_scenario.clinic_id}/settings",
        admin,
        {"locale": "en-US", "currency": "USD"},
    )

    assert owner_response.status_code == 200
    assert admin_response.status_code == 200
    stored = await migrator_connection.fetchrow(
        "SELECT display_name, timezone, locale, currency FROM app.clinic_settings "
        "WHERE clinic_id = $1",
        role_scenario.clinic_id,
    )
    assert stored["display_name"] == "Sorriso Odontologia"
    assert stored["timezone"] == "America/Sao_Paulo"
    assert stored["locale"] == "en-US"
    assert stored["currency"] == "USD"


@pytest.mark.anyio
async def test_patch_settings_rejects_invalid_timezone_and_currency(
    api_client: httpx.AsyncClient, role_scenario: RoleScenario
) -> None:
    token = await login(api_client, role_scenario.emails[Role.OWNER])
    url = f"/api/v1/clinics/{role_scenario.clinic_id}/settings"

    bad_timezone = await patch(api_client, url, token, {"timezone": "Mars/Olympus"})
    lowercase_currency = await patch(api_client, url, token, {"currency": "usd"})
    short_currency = await patch(api_client, url, token, {"currency": "US"})

    for response in (bad_timezone, lowercase_currency, short_currency):
        assert response.status_code == 422
        assert response.json()["title"] == "Dados inválidos"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        (
            "get_clinic",
            {
                Role.OWNER: 200,
                Role.ADMIN: 200,
                Role.DENTIST: 200,
                Role.ASSISTANT: 200,
                Role.RECEPTIONIST: 200,
            },
        ),
        (
            "patch_clinic",
            {
                Role.OWNER: 200,
                Role.ADMIN: 403,
                Role.DENTIST: 403,
                Role.ASSISTANT: 403,
                Role.RECEPTIONIST: 403,
            },
        ),
        (
            "get_settings",
            {
                Role.OWNER: 200,
                Role.ADMIN: 200,
                Role.DENTIST: 200,
                Role.ASSISTANT: 200,
                Role.RECEPTIONIST: 200,
            },
        ),
        (
            "patch_settings",
            {
                Role.OWNER: 200,
                Role.ADMIN: 200,
                Role.DENTIST: 403,
                Role.ASSISTANT: 403,
                Role.RECEPTIONIST: 403,
            },
        ),
    ],
)
async def test_role_matrix_on_clinic_endpoints(
    api_client: httpx.AsyncClient,
    role_scenario: RoleScenario,
    operation: str,
    expected: dict[Role, int],
) -> None:
    for role in Role:
        token = await login(api_client, role_scenario.emails[role])
        clinic_url = f"/api/v1/clinics/{role_scenario.clinic_id}"
        settings_url = f"{clinic_url}/settings"
        if operation == "get_clinic":
            response = await api_client.get(
                clinic_url, headers={"Cookie": f"{SESSION_COOKIE}={token}"}
            )
        elif operation == "patch_clinic":
            response = await patch(
                api_client, clinic_url, token, {"legal_name": f"Razão {role.value}"}
            )
        elif operation == "get_settings":
            response = await api_client.get(
                settings_url, headers={"Cookie": f"{SESSION_COOKIE}={token}"}
            )
        else:
            response = await patch(
                api_client, settings_url, token, {"display_name": f"Nome {role.value}"}
            )
        assert response.status_code == expected[role], (operation, role)


@pytest.mark.anyio
async def test_cross_tenant_access_returns_404_for_every_role(
    api_client: httpx.AsyncClient,
    role_scenario: RoleScenario,
) -> None:
    clinic_url = f"/api/v1/clinics/{role_scenario.foreign_clinic_id}"
    settings_url = f"{clinic_url}/settings"
    for role in Role:
        token = await login(api_client, role_scenario.emails[role])
        headers = {"Cookie": f"{SESSION_COOKIE}={token}"}
        responses = [
            await api_client.get(clinic_url, headers=headers),
            await api_client.get(settings_url, headers=headers),
            await patch(api_client, clinic_url, token, {"legal_name": "Inválido"}),
            await patch(api_client, settings_url, token, {"display_name": "Inválido"}),
        ]
        for response in responses:
            assert response.status_code == 404, role
            assert response.json()["title"] == "Recurso não encontrado"
