from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import (
    build_complete_anamnesis_payload,
    delete_anamneses_for_clinics,
    insert_anamnesis,
    insert_clinic,
    insert_clinic_settings,
    insert_membership,
    insert_patient,
)

from app.clinics.rbac import Role

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"

SECRET_ANSWER = "SEGREDO-CLINICO-INALTERADO"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


@dataclass
class AnamnesisScenario:
    clinic_id: uuid.UUID
    foreign_clinic_id: uuid.UUID
    members: dict[Role, Teammate] = field(default_factory=dict)
    patient_id: uuid.UUID = uuid.UUID(int=0)
    foreign_patient_id: uuid.UUID = uuid.UUID(int=0)


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
    payload: dict[str, object] | None = None,
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
async def anamnesis_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[AnamnesisScenario]:
    built = AnamnesisScenario(clinic_id=uuid.UUID(int=0), foreign_clinic_id=uuid.UUID(int=0))
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"anamnesis-{suffix}")
    built.foreign_clinic_id = await insert_clinic(
        migrator_connection, f"anamnesis-foreign-{suffix}"
    )
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    await insert_clinic_settings(migrator_connection, built.clinic_id)

    for role in Role:
        email = make_test_email(f"anamnesis-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
        built.members[role] = Teammate(email=email, user_id=user_id, membership_id=membership_id)

    foreign_email = make_test_email("anamnesis-foreign-owner")
    foreign_user_id = await seed_user_with_password(email=foreign_email, password=PASSWORD)
    await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=foreign_user_id,
        role="OWNER",
        status="ACTIVE",
    )

    owner_user_id = built.members[Role.OWNER].user_id
    built.patient_id = await insert_patient(
        migrator_connection,
        clinic_id=built.clinic_id,
        full_name="Ana Souza",
        phone="+5571999112222",
    )
    built.foreign_patient_id = await insert_patient(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        full_name="Paciente Externo",
        phone="+5571988887777",
    )
    await insert_anamnesis(
        migrator_connection,
        clinic_id=built.clinic_id,
        patient_id=built.patient_id,
        author_user_id=owner_user_id,
        status="FINAL",
        version_number=1,
        payload=build_complete_anamnesis_payload(text_prefix=SECRET_ANSWER),
        author_professional_name="Dra. Ana",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )

    try:
        yield built
    finally:
        clinic_ids = [built.clinic_id, built.foreign_clinic_id]
        await delete_anamneses_for_clinics(migrator_connection, clinic_ids)
        await migrator_connection.execute(
            "DELETE FROM app.patients WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        user_ids = [member.user_id for member in built.members.values()] + [foreign_user_id]
        await migrator_connection.execute(
            "DELETE FROM app.professional_profiles WHERE user_id = ANY($1::uuid[])", user_ids
        )


def clinic_url(scenario: AnamnesisScenario, clinic_id: uuid.UUID | None = None) -> str:
    return f"/api/v1/clinics/{clinic_id if clinic_id is not None else scenario.clinic_id}"


def patient_url(
    scenario: AnamnesisScenario,
    patient_id: uuid.UUID | None = None,
    clinic_id: uuid.UUID | None = None,
) -> str:
    target = patient_id if patient_id is not None else scenario.patient_id
    return f"{clinic_url(scenario, clinic_id)}/patients/{target}"


def anamneses_url(
    scenario: AnamnesisScenario,
    patient_id: uuid.UUID | None = None,
    clinic_id: uuid.UUID | None = None,
) -> str:
    return f"{patient_url(scenario, patient_id, clinic_id)}/anamneses"


def anamnesis_url(
    scenario: AnamnesisScenario,
    anamnesis_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
) -> str:
    return f"{anamneses_url(scenario, patient_id)}/{anamnesis_id}"


async def owner_token(client: httpx.AsyncClient, scenario: AnamnesisScenario) -> str:
    return await login(client, scenario.members[Role.OWNER].email)


async def put_profile(
    client: httpx.AsyncClient,
    token: str,
    *,
    name: str = "Dra. Ana Souza",
    cro_number: str = "12345",
    cro_state: str = "BA",
) -> httpx.Response:
    return await mutate(
        client,
        "PUT",
        "/api/v1/users/me/professional-profile",
        token,
        {"professional_name": name, "cro_number": cro_number, "cro_state": cro_state},
    )


async def create_draft(
    client: httpx.AsyncClient,
    token: str,
    scenario: AnamnesisScenario,
    patient_id: uuid.UUID | None = None,
    *,
    base_version_id: uuid.UUID | None = None,
) -> httpx.Response:
    payload: dict[str, object] = {}
    if base_version_id is not None:
        payload["base_version_id"] = str(base_version_id)
    return await mutate(client, "POST", anamneses_url(scenario, patient_id), token, payload)


async def seed_draft(
    migrator_connection: asyncpg.Connection,
    scenario: AnamnesisScenario,
    *,
    patient_id: uuid.UUID | None = None,
    payload: dict[str, object] | None = None,
) -> uuid.UUID:
    return await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=patient_id if patient_id is not None else scenario.patient_id,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="DRAFT",
        payload=payload if payload is not None else {},
    )


# ---------------------------------------------------------------------------
# Professional profile
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_get_professional_profile_is_null_when_absent(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    token = await owner_token(api_client, anamnesis_scenario)

    response = await read(api_client, "/api/v1/users/me/professional-profile", token)

    assert response.status_code == 200, response.text
    assert response.json() is None


@pytest.mark.anyio
async def test_put_professional_profile_upserts_and_normalizes(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    token = await owner_token(api_client, anamnesis_scenario)

    created = await put_profile(
        api_client, token, name="  Dra. Ana Souza  ", cro_number="  12345  ", cro_state="ba"
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["professional_name"] == "Dra. Ana Souza"
    assert body["cro_number"] == "12345"
    assert body["cro_state"] == "BA"
    assert body["created_at"] and body["updated_at"]

    updated = await put_profile(api_client, token, name="Dra. Ana S. Lima", cro_state="PE")
    assert updated.status_code == 200, updated.text
    assert updated.json()["professional_name"] == "Dra. Ana S. Lima"
    assert updated.json()["cro_state"] == "PE"

    fetched = await read(api_client, "/api/v1/users/me/professional-profile", token)
    assert fetched.status_code == 200
    assert fetched.json()["professional_name"] == "Dra. Ana S. Lima"


@pytest.mark.anyio
async def test_put_professional_profile_rejects_invalid_fields(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    token = await owner_token(api_client, anamnesis_scenario)
    url = "/api/v1/users/me/professional-profile"

    responses = [
        await mutate(
            api_client,
            "PUT",
            url,
            token,
            {"professional_name": "   ", "cro_number": "1", "cro_state": "BA"},
        ),
        await mutate(
            api_client,
            "PUT",
            url,
            token,
            {"professional_name": "Dra. A", "cro_number": "", "cro_state": "BA"},
        ),
        await mutate(
            api_client,
            "PUT",
            url,
            token,
            {"professional_name": "Dra. A", "cro_number": "1", "cro_state": "Bahia"},
        ),
        await mutate(
            api_client,
            "PUT",
            url,
            token,
            {"professional_name": "Dra. A", "cro_number": "1", "cro_state": "B1"},
        ),
        await mutate(
            api_client, "PUT", url, token, {"professional_name": "Dra. A", "cro_number": "1"}
        ),
        await mutate(
            api_client,
            "PUT",
            url,
            token,
            {"professional_name": "Dra. A", "cro_number": "1", "cro_state": "BA", "extra": 1},
        ),
    ]

    for response in responses:
        assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_professional_profile_is_private_to_its_owner(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    scenario = anamnesis_scenario
    owner = await login(api_client, scenario.members[Role.OWNER].email)
    dentist = await login(api_client, scenario.members[Role.DENTIST].email)

    assert (await put_profile(api_client, owner, name="Dra. Ana")).status_code == 200

    dentist_view = await read(api_client, "/api/v1/users/me/professional-profile", dentist)
    assert dentist_view.status_code == 200
    assert dentist_view.json() is None

    assert (await put_profile(api_client, dentist, name="Dr. Bruno")).status_code == 200
    owner_view = await read(api_client, "/api/v1/users/me/professional-profile", owner)
    assert owner_view.json()["professional_name"] == "Dra. Ana"


@pytest.mark.anyio
async def test_professional_profile_is_available_to_every_role(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    scenario = anamnesis_scenario
    for role in Role:
        token = await login(api_client, scenario.members[role].email)
        fetched = await read(api_client, "/api/v1/users/me/professional-profile", token)
        saved = await put_profile(api_client, token, name=f"Profissional {role.value}")
        assert fetched.status_code == 200, role
        assert saved.status_code == 200, role
        assert saved.json()["professional_name"] == f"Profissional {role.value}"


@pytest.mark.anyio
async def test_professional_profile_requires_authentication(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    csrf = await anonymous_csrf(api_client)
    url = "/api/v1/users/me/professional-profile"

    fetched = await api_client.get(url)
    saved = await api_client.put(
        url,
        json={"professional_name": "Anônimo", "cro_number": "1", "cro_state": "BA"},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )

    assert fetched.status_code == 401
    assert saved.status_code == 401


# ---------------------------------------------------------------------------
# Draft lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_empty_draft_and_list_it(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)

    created = await create_draft(api_client, token, scenario)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "DRAFT"
    assert body["version_number"] is None
    assert body["finalized_at"] is None
    assert body["payload"] == {}
    assert body["template"] == "cfo_2026_v1"
    assert body["base_version_id"] is None
    assert body["author_user_id"] == str(scenario.members[Role.OWNER].user_id)

    listed = await read(api_client, f"{anamneses_url(scenario)}?limit=10", token)
    assert listed.status_code == 200, listed.text
    listing = listed.json()
    assert listing["total"] == 2
    assert listing["limit"] == 10
    assert listing["offset"] == 0
    statuses = [item["status"] for item in listing["items"]]
    assert statuses.count("DRAFT") == 1
    assert statuses.count("FINAL") == 1


@pytest.mark.anyio
async def test_create_draft_copies_the_base_final_version(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    base = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=scenario.patient_id,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=2,
        payload={"allergies": {"known_allergy": {"value": "YES", "details": "Penicilina"}}},
        author_professional_name="Dra. Ana",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )

    created = await create_draft(api_client, token, scenario, base_version_id=base)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["base_version_id"] == str(base)
    assert body["payload"] == {
        "allergies": {"known_allergy": {"value": "YES", "details": "Penicilina"}}
    }
    assert body["version_number"] is None


@pytest.mark.anyio
async def test_create_draft_rejects_a_base_that_is_not_a_final_of_the_patient(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    other_patient = await insert_patient(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        full_name="Outro Paciente",
        phone="+5571900000000",
    )
    draft_base = await seed_draft(migrator_connection, scenario, patient_id=other_patient)
    foreign_final = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.foreign_clinic_id,
        patient_id=scenario.foreign_patient_id,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=1,
        author_professional_name="Dr. Externo",
        author_cro_number="999",
        author_cro_state="SP",
        finalized_at=datetime.now(UTC),
    )
    other_patient_final = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=other_patient,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=1,
        author_professional_name="Dra. Ana",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )

    bases = [draft_base, foreign_final, other_patient_final, uuid.uuid4()]
    responses = [
        await create_draft(api_client, token, scenario, base_version_id=base) for base in bases
    ]

    for response in responses:
        assert response.status_code == 404, response.text

    empty = await create_draft(api_client, token, scenario)
    assert empty.status_code == 201, empty.text


@pytest.mark.anyio
async def test_create_draft_conflicts_when_one_already_exists(
    api_client: httpx.AsyncClient, anamnesis_scenario: AnamnesisScenario
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)

    first = await create_draft(api_client, token, scenario)
    second = await create_draft(api_client, token, scenario)

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["title"] == "Conflito"


@pytest.mark.anyio
async def test_update_draft_merges_partial_payload_and_removes_with_null(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    draft = await seed_draft(
        migrator_connection,
        scenario,
        payload={
            "allergies": {"known_allergy": {"value": "YES", "details": "Penicilina"}},
            "chief_complaint": {"description": {"text": "Dor no dente"}},
        },
    )
    url = anamnesis_url(scenario, draft)

    first = await mutate(
        api_client,
        "PATCH",
        url,
        token,
        {"payload": {"allergies": {"emergency_care": {"value": "NO"}}}},
    )
    assert first.status_code == 200, first.text
    assert first.json()["payload"] == {
        "allergies": {
            "known_allergy": {"value": "YES", "details": "Penicilina"},
            "emergency_care": {"value": "NO"},
        },
        "chief_complaint": {"description": {"text": "Dor no dente"}},
    }

    second = await mutate(
        api_client,
        "PATCH",
        url,
        token,
        {
            "payload": {
                "allergies": {"known_allergy": None},
                "chief_complaint": {"description": {"text": "  Dor intensa  "}},
            }
        },
    )
    assert second.status_code == 200, second.text
    assert second.json()["payload"] == {
        "allergies": {"emergency_care": {"value": "NO"}},
        "chief_complaint": {"description": {"text": "Dor intensa"}},
    }

    untouched = await mutate(api_client, "PATCH", url, token, {"payload": {}})
    assert untouched.status_code == 200
    assert untouched.json()["payload"] == second.json()["payload"]


@pytest.mark.anyio
async def test_update_draft_rejects_unknown_keys_and_invalid_values(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    draft = await seed_draft(migrator_connection, scenario)
    url = anamnesis_url(scenario, draft)

    responses = [
        await mutate(api_client, "PATCH", url, token, {"payload": {"unknown_section": {}}}),
        await mutate(
            api_client,
            "PATCH",
            url,
            token,
            {"payload": {"allergies": {"unknown_question": {"value": "NO"}}}},
        ),
        await mutate(
            api_client,
            "PATCH",
            url,
            token,
            {"payload": {"allergies": {"known_allergy": {"value": "NO", "extra": 1}}}},
        ),
        await mutate(
            api_client,
            "PATCH",
            url,
            token,
            {"payload": {"dental_history": {"last_visit": {"value": "not_an_option"}}}},
        ),
        await mutate(
            api_client,
            "PATCH",
            url,
            token,
            {"payload": {"chief_complaint": {"description": {"value": "NO"}}}},
        ),
        await mutate(api_client, "PATCH", url, token, {"payload": {}, "extra": True}),
    ]

    for response in responses:
        assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_update_final_version_is_a_conflict(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    final = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=scenario.patient_id,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=2,
        author_professional_name="Dra. Ana",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )

    response = await mutate(
        api_client,
        "PATCH",
        anamnesis_url(scenario, final),
        token,
        {"payload": {"allergies": {"known_allergy": {"value": "NO"}}}},
    )

    assert response.status_code == 409, response.text
    stored = await migrator_connection.fetchval(
        "SELECT payload FROM app.anamneses WHERE id = $1", final
    )
    assert json.loads(stored) == {}


@pytest.mark.anyio
async def test_anamnesis_list_filters_by_status_and_paginates(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    await seed_draft(migrator_connection, scenario)

    finals = await read(api_client, f"{anamneses_url(scenario)}?status=FINAL", token)
    drafts = await read(api_client, f"{anamneses_url(scenario)}?status=DRAFT&limit=1", token)
    invalid = await read(api_client, f"{anamneses_url(scenario)}?limit=0", token)

    assert finals.status_code == 200
    assert finals.json()["total"] == 1
    assert finals.json()["items"][0]["status"] == "FINAL"
    assert drafts.status_code == 200
    assert drafts.json()["total"] == 1
    assert drafts.json()["limit"] == 1
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_anamnesis_hides_cross_tenant_and_foreign_patient(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    foreign_final = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.foreign_clinic_id,
        patient_id=scenario.foreign_patient_id,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=1,
        author_professional_name="Dr. Externo",
        author_cro_number="999",
        author_cro_state="SP",
        finalized_at=datetime.now(UTC),
    )

    responses = [
        await read(
            api_client, anamneses_url(scenario, clinic_id=scenario.foreign_clinic_id), token
        ),
        await read(api_client, anamneses_url(scenario, scenario.foreign_patient_id), token),
        await read(api_client, anamnesis_url(scenario, foreign_final), token),
        await create_draft(api_client, token, scenario, scenario.foreign_patient_id),
        await mutate(
            api_client,
            "PATCH",
            anamnesis_url(scenario, foreign_final),
            token,
            {"payload": {"allergies": {"known_allergy": {"value": "NO"}}}},
        ),
        await mutate(
            api_client,
            "POST",
            f"{anamnesis_url(scenario, foreign_final)}/finalize",
            token,
        ),
    ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["title"] == "Recurso não encontrado"


# ---------------------------------------------------------------------------
# Finalization
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_finalize_requires_a_complete_payload(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    assert (await put_profile(api_client, token)).status_code == 200
    draft = await seed_draft(
        migrator_connection,
        scenario,
        payload={"allergies": {"known_allergy": {"value": "NO"}}},
    )

    response = await mutate(api_client, "POST", f"{anamnesis_url(scenario, draft)}/finalize", token)

    assert response.status_code == 422, response.text
    assert response.json()["title"] == "Dados inválidos"
    stored = await migrator_connection.fetchrow(
        "SELECT status, version_number FROM app.anamneses WHERE id = $1", draft
    )
    assert stored["status"] == "DRAFT"
    assert stored["version_number"] is None


@pytest.mark.anyio
async def test_finalize_requires_a_professional_profile(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    draft = await seed_draft(
        migrator_connection,
        scenario,
        payload=build_complete_anamnesis_payload(),
    )
    url = f"{anamnesis_url(scenario, draft)}/finalize"

    missing = await mutate(api_client, "POST", url, token)
    assert missing.status_code == 409, missing.text
    assert missing.json()["title"] == "Conflito"

    assert (await put_profile(api_client, token)).status_code == 200
    finalized = await mutate(api_client, "POST", url, token)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "FINAL"


@pytest.mark.anyio
async def test_finalize_snapshots_the_author_and_keeps_the_snapshot_after_profile_change(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    assert (
        await put_profile(
            api_client, token, name="Dra. Ana Souza", cro_number="CRO-12345", cro_state="BA"
        )
    ).status_code == 200
    draft = await seed_draft(
        migrator_connection,
        scenario,
        payload=build_complete_anamnesis_payload(text_prefix=SECRET_ANSWER),
    )

    finalized = await mutate(
        api_client, "POST", f"{anamnesis_url(scenario, draft)}/finalize", token
    )

    assert finalized.status_code == 200, finalized.text
    body = finalized.json()
    assert body["status"] == "FINAL"
    assert body["version_number"] == 2
    assert body["finalized_at"] is not None
    assert body["author_professional_name"] == "Dra. Ana Souza"
    assert body["author_cro_number"] == "CRO-12345"
    assert body["author_cro_state"] == "BA"
    assert body["payload"]["allergies"]["known_allergy"]["value"] == "NO"

    assert (
        await put_profile(
            api_client, token, name="Dra. Ana Lima", cro_number="CRO-99999", cro_state="PE"
        )
    ).status_code == 200
    fetched = await read(api_client, anamnesis_url(scenario, draft), token)
    assert fetched.json()["author_professional_name"] == "Dra. Ana Souza"
    assert fetched.json()["author_cro_number"] == "CRO-12345"
    assert fetched.json()["author_cro_state"] == "BA"


@pytest.mark.anyio
async def test_finalize_assigns_sequential_versions_across_revisions(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    assert (await put_profile(api_client, token)).status_code == 200
    revision_patient = await insert_patient(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        full_name="Paciente Revisão",
        phone="+5571900000000",
    )
    base = await insert_anamnesis(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=revision_patient,
        author_user_id=scenario.members[Role.OWNER].user_id,
        status="FINAL",
        version_number=1,
        payload=build_complete_anamnesis_payload(),
        author_professional_name="Dra. Ana",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )

    revision = await create_draft(
        api_client, token, scenario, revision_patient, base_version_id=base
    )
    assert revision.status_code == 201, revision.text
    revision_id = revision.json()["id"]

    first_final = await mutate(
        api_client,
        "POST",
        f"{anamnesis_url(scenario, uuid.UUID(revision_id), revision_patient)}/finalize",
        token,
    )
    assert first_final.status_code == 200, first_final.text
    assert first_final.json()["version_number"] == 2

    again = await mutate(
        api_client,
        "POST",
        f"{anamnesis_url(scenario, uuid.UUID(revision_id), revision_patient)}/finalize",
        token,
    )
    assert again.status_code == 409, again.text

    finals = await migrator_connection.fetch(
        "SELECT version_number FROM app.anamneses WHERE patient_id = $1 AND status = 'FINAL' "
        "ORDER BY version_number",
        revision_patient,
    )
    assert [row["version_number"] for row in finals] == [1, 2]


# ---------------------------------------------------------------------------
# RBAC and redaction
# ---------------------------------------------------------------------------


ANAMNESIS_OPERATION_EXPECTATIONS: dict[str, dict[Role, int]] = {
    "list": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 403,
    },
    "get": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 403,
    },
    "create": {
        Role.OWNER: 201,
        Role.ADMIN: 403,
        Role.DENTIST: 201,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "update": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "finalize": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
}


@pytest.mark.anyio
@pytest.mark.parametrize("operation", list(ANAMNESIS_OPERATION_EXPECTATIONS))
async def test_role_matrix_on_anamnesis_endpoints(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
    operation: str,
) -> None:
    scenario = anamnesis_scenario
    for role in Role:
        patient = await insert_patient(
            migrator_connection,
            clinic_id=scenario.clinic_id,
            full_name=f"Paciente {operation} {role.value}",
            phone="+5571900000000",
        )
        target = patient
        if operation in {"get", "update", "finalize"}:
            target = await insert_anamnesis(
                migrator_connection,
                clinic_id=scenario.clinic_id,
                patient_id=patient,
                author_user_id=scenario.members[role].user_id,
                status="DRAFT",
                payload=build_complete_anamnesis_payload(),
            )
        token = await login(api_client, scenario.members[role].email)
        if operation == "list":
            response = await read(api_client, anamneses_url(scenario, patient), token)
        elif operation == "get":
            response = await read(api_client, anamnesis_url(scenario, target, patient), token)
        elif operation == "create":
            response = await create_draft(api_client, token, scenario, patient)
        elif operation == "update":
            response = await mutate(
                api_client,
                "PATCH",
                anamnesis_url(scenario, target, patient),
                token,
                {"payload": {"allergies": {"known_allergy": {"value": "NO"}}}},
            )
        else:
            assert (await put_profile(api_client, token)).status_code == 200
            response = await mutate(
                api_client, "POST", f"{anamnesis_url(scenario, target, patient)}/finalize", token
            )
        assert response.status_code == ANAMNESIS_OPERATION_EXPECTATIONS[operation][role], (
            operation,
            role,
            response.text,
        )


@pytest.mark.anyio
async def test_administrative_roles_receive_no_payload_or_existence_signal(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    draft = await seed_draft(
        migrator_connection,
        scenario,
        payload={"allergies": {"known_allergy": {"value": "YES", "details": SECRET_ANSWER}}},
    )

    for role in (Role.ADMIN, Role.RECEPTIONIST):
        token = await login(api_client, scenario.members[role].email)
        responses = [
            await read(api_client, anamneses_url(scenario), token),
            await read(api_client, anamnesis_url(scenario, draft), token),
            await mutate(
                api_client, "PATCH", anamnesis_url(scenario, draft), token, {"payload": {}}
            ),
            await mutate(api_client, "POST", f"{anamnesis_url(scenario, draft)}/finalize", token),
        ]
        for response in responses:
            assert response.status_code == 403, (role, response.text)
            assert SECRET_ANSWER not in response.text
            assert "payload" not in response.json()


@pytest.mark.anyio
async def test_anamnesis_audit_keeps_only_ids_and_states(
    api_client: httpx.AsyncClient,
    anamnesis_scenario: AnamnesisScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = anamnesis_scenario
    token = await owner_token(api_client, scenario)
    assert (
        await put_profile(
            api_client,
            token,
            name="Dra. SEGREDO-AUDITORIA",
            cro_number="CRO-777-SEGREDO",
            cro_state="BA",
        )
    ).status_code == 200

    created = await create_draft(api_client, token, scenario)
    assert created.status_code == 201, created.text
    anamnesis_id = uuid.UUID(created.json()["id"])
    updated = await mutate(
        api_client,
        "PATCH",
        anamnesis_url(scenario, anamnesis_id),
        token,
        {
            "payload": {
                "allergies": {"known_allergy": {"value": "YES", "details": SECRET_ANSWER}},
                "chief_complaint": {"description": {"text": SECRET_ANSWER}},
            }
        },
    )
    assert updated.status_code == 200, updated.text
    await mutate(
        api_client,
        "PATCH",
        anamnesis_url(scenario, anamnesis_id),
        token,
        {"payload": build_complete_anamnesis_payload(text_prefix=SECRET_ANSWER)},
    )
    finalized = await mutate(
        api_client, "POST", f"{anamnesis_url(scenario, anamnesis_id)}/finalize", token
    )
    assert finalized.status_code == 200, finalized.text

    rows = await migrator_connection.fetch(
        "SELECT event_type, entity_type, entity_id, metadata FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type LIKE 'anamnesis%'",
        scenario.clinic_id,
    )
    event_types = {row["event_type"] for row in rows}
    assert {"anamnesis.created", "anamnesis.updated", "anamnesis.finalized"} <= event_types
    for row in rows:
        assert row["entity_type"] == "anamnesis"
        assert row["entity_id"] == anamnesis_id
        metadata = json.loads(row["metadata"])
        assert set(metadata) <= {"patient_id", "status", "version_number"}

    serialized = json.dumps([dict(row) for row in rows], default=str)
    assert SECRET_ANSWER not in serialized
    assert "Dra. SEGREDO-AUDITORIA" not in serialized
    assert "CRO-777-SEGREDO" not in serialized
