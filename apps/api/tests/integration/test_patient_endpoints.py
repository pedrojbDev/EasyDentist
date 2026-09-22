from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from helpers import (
    insert_clinic,
    insert_clinic_settings,
    insert_membership,
    insert_patient,
    insert_patient_alert,
)

from app.clinics.rbac import Role

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"

VALID_CPF = "52998224725"
OTHER_VALID_CPF = "11144477735"
INVALID_CPF = "52998224724"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


@dataclass
class PatientScenario:
    clinic_id: uuid.UUID
    foreign_clinic_id: uuid.UUID
    members: dict[Role, Teammate] = field(default_factory=dict)
    patient_id: uuid.UUID = uuid.UUID(int=0)
    archived_patient_id: uuid.UUID = uuid.UUID(int=0)
    foreign_patient_id: uuid.UUID = uuid.UUID(int=0)
    alert_id: uuid.UUID = uuid.UUID(int=0)


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
async def patient_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[PatientScenario]:
    built = PatientScenario(clinic_id=uuid.UUID(int=0), foreign_clinic_id=uuid.UUID(int=0))
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"patients-{suffix}")
    built.foreign_clinic_id = await insert_clinic(migrator_connection, f"patients-foreign-{suffix}")
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    await insert_clinic_settings(migrator_connection, built.clinic_id)

    for role in Role:
        email = make_test_email(f"patients-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
        built.members[role] = Teammate(email=email, user_id=user_id, membership_id=membership_id)

    foreign_email = make_test_email("patients-foreign-owner")
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
        cpf=VALID_CPF,
        phone="+5571999112222",
    )
    await insert_patient(
        migrator_connection,
        clinic_id=built.clinic_id,
        full_name="Bruno Lima",
        birth_date=date(1985, 3, 4),
        phone="+5571988887777",
    )
    await insert_patient(
        migrator_connection,
        clinic_id=built.clinic_id,
        full_name="Carla Dias",
        birth_date=date(2001, 7, 9),
        phone="+5571977776666",
        cpf=OTHER_VALID_CPF,
    )
    built.archived_patient_id = await insert_patient(
        migrator_connection,
        clinic_id=built.clinic_id,
        full_name="Zelia Arquivada",
        status="ARCHIVED",
        archived_at=datetime.now(UTC),
    )
    built.foreign_patient_id = await insert_patient(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        full_name="Paciente Externo",
        cpf="12345678909",
    )
    built.alert_id = await insert_patient_alert(
        migrator_connection,
        clinic_id=built.clinic_id,
        patient_id=built.patient_id,
        created_by_user_id=owner_user_id,
        kind="ALLERGY",
        description="Alergia a dipirona",
    )

    try:
        yield built
    finally:
        clinic_ids = [built.clinic_id, built.foreign_clinic_id]
        await migrator_connection.execute(
            "DELETE FROM app.patient_alerts WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.patients WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )


def clinic_url(scenario: PatientScenario, clinic_id: uuid.UUID | None = None) -> str:
    return f"/api/v1/clinics/{clinic_id if clinic_id is not None else scenario.clinic_id}"


def patient_url(scenario: PatientScenario, patient_id: uuid.UUID | None = None) -> str:
    target = patient_id if patient_id is not None else scenario.patient_id
    return f"{clinic_url(scenario)}/patients/{target}"


async def owner_token(client: httpx.AsyncClient, scenario: PatientScenario) -> str:
    return await login(client, scenario.members[Role.OWNER].email)


@pytest.mark.anyio
async def test_create_patient_persists_the_record(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await mutate(
        api_client,
        "POST",
        f"{clinic_url(scenario)}/patients",
        token,
        {
            "full_name": "  Diego Nunes  ",
            "birth_date": "1990-05-06",
            "phone": "+5571911110000",
            "cpf": "123.456.789-09",
            "state": "ba",
            "emergency_contact_name": "Marta Nunes",
            "emergency_contact_phone": "+5571922220000",
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_name"] == "Diego Nunes"
    assert body["cpf"] == "12345678909"
    assert body["state"] == "BA"
    assert body["status"] == "ACTIVE"
    assert body["archived_at"] is None
    assert body["clinic_id"] == str(scenario.clinic_id)
    assert body["created_at"] and body["updated_at"]


@pytest.mark.anyio
async def test_create_patient_accepts_a_minor_with_complete_guardian(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await mutate(
        api_client,
        "POST",
        f"{clinic_url(scenario)}/patients",
        token,
        {
            "full_name": "Enzo Nunes",
            "birth_date": "2016-01-10",
            "phone": "+5571911110000",
            "guardian_name": "Marta Nunes",
            "guardian_relationship": "Mãe",
            "guardian_phone": "+5571922220000",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["guardian_name"] == "Marta Nunes"


@pytest.mark.anyio
async def test_create_patient_rejects_invalid_payloads(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    url = f"{clinic_url(scenario)}/patients"
    base = {"full_name": "Teste", "birth_date": "1990-01-01", "phone": "+5571911110000"}

    future = await mutate(api_client, "POST", url, token, {**base, "birth_date": "2999-01-01"})
    minor = await mutate(api_client, "POST", url, token, {**base, "birth_date": "2016-01-10"})
    invalid_cpf = await mutate(api_client, "POST", url, token, {**base, "cpf": INVALID_CPF})
    missing = await mutate(api_client, "POST", url, token, {"full_name": "Só nome"})
    partial_emergency = await mutate(
        api_client,
        "POST",
        url,
        token,
        {**base, "emergency_contact_relationship": "Irmão"},
    )

    for response in (future, minor, invalid_cpf, missing, partial_emergency):
        assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_create_patient_maps_duplicate_cpf_to_conflict(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await mutate(
        api_client,
        "POST",
        f"{clinic_url(scenario)}/patients",
        token,
        {
            "full_name": "Outra Ana",
            "birth_date": "1990-01-01",
            "phone": "+5571911110000",
            "cpf": VALID_CPF,
        },
    )

    assert response.status_code == 409
    assert response.json()["title"] == "Conflito"


@pytest.mark.anyio
async def test_get_patient_returns_the_full_record(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await read(api_client, patient_url(scenario), token)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(scenario.patient_id)
    assert body["full_name"] == "Ana Souza"
    assert body["cpf"] == VALID_CPF


@pytest.mark.anyio
async def test_patch_patient_updates_only_informed_fields(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await mutate(
        api_client,
        "PATCH",
        patient_url(scenario),
        token,
        {"social_name": "Ana S.", "phone_secondary": "+5571933334444", "cpf": None},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["social_name"] == "Ana S."
    assert body["phone_secondary"] == "+5571933334444"
    assert body["cpf"] is None
    assert body["full_name"] == "Ana Souza"


@pytest.mark.anyio
async def test_patch_patient_rejects_rule_violations(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    future = await mutate(
        api_client, "PATCH", patient_url(scenario), token, {"birth_date": "2999-01-01"}
    )
    conflicting = await mutate(
        api_client, "PATCH", patient_url(scenario), token, {"cpf": OTHER_VALID_CPF}
    )
    invalid = await mutate(api_client, "PATCH", patient_url(scenario), token, {"cpf": INVALID_CPF})

    assert future.status_code == 422
    assert conflicting.status_code == 409
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_patch_patient_rejects_null_and_blank_mandatory_fields(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    url = patient_url(scenario)

    nulls = [
        await mutate(api_client, "PATCH", url, token, {"full_name": None}),
        await mutate(api_client, "PATCH", url, token, {"phone": None}),
        await mutate(api_client, "PATCH", url, token, {"birth_date": None}),
    ]
    blanks = [
        await mutate(api_client, "PATCH", url, token, {"full_name": "   "}),
        await mutate(api_client, "PATCH", url, token, {"phone": ""}),
    ]

    for response in (*nulls, *blanks):
        assert response.status_code == 422, response.text

    unchanged = await read(api_client, url, token)
    assert unchanged.json()["full_name"] == "Ana Souza"
    assert unchanged.json()["phone"] == "+5571999112222"

    valid = await mutate(
        api_client,
        "PATCH",
        url,
        token,
        {"full_name": "Ana Souza Lima", "phone": "+5571900000000"},
    )
    assert valid.status_code == 200, valid.text
    assert valid.json()["full_name"] == "Ana Souza Lima"
    assert valid.json()["phone"] == "+5571900000000"


@pytest.mark.anyio
async def test_archive_hides_the_patient_from_the_default_list_but_keeps_direct_access(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    archived = await mutate(api_client, "POST", f"{patient_url(scenario)}/archive", token)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["archived_at"] is not None

    default_list = await read(api_client, f"{clinic_url(scenario)}/patients", token)
    listing = default_list.json()
    assert listing["total"] == 2
    assert str(scenario.patient_id) not in {item["id"] for item in listing["items"]}

    direct = await read(api_client, patient_url(scenario), token)
    assert direct.status_code == 200
    assert direct.json()["status"] == "ARCHIVED"


@pytest.mark.anyio
async def test_restore_returns_the_patient_to_active(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    restored = await mutate(
        api_client, "POST", f"{patient_url(scenario, scenario.archived_patient_id)}/restore", token
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "ACTIVE"
    assert restored.json()["archived_at"] is None


@pytest.mark.anyio
async def test_archive_and_restore_are_idempotent(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    url = patient_url(scenario)

    first = await mutate(api_client, "POST", f"{url}/archive", token)
    second = await mutate(api_client, "POST", f"{url}/archive", token)
    restored = await mutate(api_client, "POST", f"{url}/restore", token)
    restored_again = await mutate(api_client, "POST", f"{url}/restore", token)

    assert first.status_code == second.status_code == 200
    assert first.json()["archived_at"] == second.json()["archived_at"]
    assert restored.status_code == restored_again.status_code == 200
    assert restored.json()["archived_at"] is None


@pytest.mark.anyio
async def test_list_patients_searches_and_paginates(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    page = await read(api_client, f"{clinic_url(scenario)}/patients?limit=1&offset=0", token)
    second = await read(api_client, f"{clinic_url(scenario)}/patients?limit=1&offset=1", token)
    by_name = await read(api_client, f"{clinic_url(scenario)}/patients?search=souza", token)
    by_cpf = await read(api_client, f"{clinic_url(scenario)}/patients?search=529.982", token)

    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 3
    assert body["limit"] == 1
    assert body["offset"] == 0
    assert len(body["items"]) == 1
    assert body["items"][0]["full_name"] == "Ana Souza"
    assert second.json()["items"][0]["full_name"] == "Bruno Lima"
    assert [item["full_name"] for item in by_name.json()["items"]] == ["Ana Souza"]
    assert by_name.json()["total"] == 1
    assert [item["full_name"] for item in by_cpf.json()["items"]] == ["Ana Souza"]


@pytest.mark.anyio
async def test_list_patients_filters_by_status(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    response = await read(api_client, f"{clinic_url(scenario)}/patients?status=ARCHIVED", token)

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["full_name"] == "Zelia Arquivada"


@pytest.mark.anyio
async def test_list_patients_rejects_invalid_pagination(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    for query in ("limit=0", "limit=101", "offset=-1"):
        response = await read(api_client, f"{clinic_url(scenario)}/patients?{query}", token)
        assert response.status_code == 422, query


@pytest.mark.anyio
async def test_patient_endpoints_require_authentication(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    csrf = await anonymous_csrf(api_client)

    listed = await api_client.get(f"{clinic_url(scenario)}/patients")
    created = await api_client.post(
        f"{clinic_url(scenario)}/patients",
        json={"full_name": "Anônimo", "birth_date": "1990-01-01", "phone": "+5571900000000"},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )

    assert listed.status_code == 401
    assert created.status_code == 401


@pytest.mark.anyio
async def test_patient_endpoints_hide_cross_tenant_resources(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    foreign_clinic = clinic_url(scenario, scenario.foreign_clinic_id)
    foreign_patient = patient_url(scenario, scenario.foreign_patient_id)

    responses = [
        await read(api_client, foreign_patient, token),
        await read(api_client, f"{foreign_patient}/alerts", token),
        await mutate(api_client, "PATCH", foreign_patient, token, {"full_name": "Invasão"}),
        await mutate(api_client, "POST", f"{foreign_patient}/archive", token),
        await mutate(api_client, "POST", f"{foreign_patient}/restore", token),
        await mutate(
            api_client,
            "POST",
            f"{foreign_patient}/alerts",
            token,
            {"kind": "OTHER", "description": "Invasão"},
        ),
        await read(api_client, f"{foreign_clinic}/patients", token),
        await mutate(
            api_client,
            "POST",
            f"{foreign_clinic}/patients",
            token,
            {"full_name": "Invasão", "birth_date": "1990-01-01", "phone": "+5571900000000"},
        ),
    ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["title"] == "Recurso não encontrado"


PATIENT_OPERATION_EXPECTATIONS: dict[str, dict[Role, int]] = {
    "list_patients": {role: 200 for role in Role},
    "get_patient": {role: 200 for role in Role},
    "create_patient": {
        Role.OWNER: 201,
        Role.ADMIN: 201,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 201,
    },
    "update_patient": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 200,
    },
    "archive_patient": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "restore_patient": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "list_alerts": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 403,
    },
    "create_alert": {
        Role.OWNER: 201,
        Role.ADMIN: 403,
        Role.DENTIST: 201,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "update_alert": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
}


@pytest.mark.anyio
@pytest.mark.parametrize("operation", list(PATIENT_OPERATION_EXPECTATIONS))
async def test_role_matrix_on_patient_endpoints(
    api_client: httpx.AsyncClient,
    patient_scenario: PatientScenario,
    operation: str,
) -> None:
    scenario = patient_scenario
    for role in Role:
        token = await login(api_client, scenario.members[role].email)
        if operation == "list_patients":
            response = await read(api_client, f"{clinic_url(scenario)}/patients", token)
        elif operation == "get_patient":
            response = await read(api_client, patient_url(scenario), token)
        elif operation == "create_patient":
            response = await mutate(
                api_client,
                "POST",
                f"{clinic_url(scenario)}/patients",
                token,
                {
                    "full_name": f"Nova Pessoa {role.value}",
                    "birth_date": "1990-01-01",
                    "phone": "+5571900000000",
                },
            )
        elif operation == "update_patient":
            response = await mutate(
                api_client,
                "PATCH",
                patient_url(scenario),
                token,
                {"social_name": f"Apelido {role.value}"},
            )
        elif operation == "archive_patient":
            response = await mutate(api_client, "POST", f"{patient_url(scenario)}/archive", token)
        elif operation == "restore_patient":
            response = await mutate(
                api_client,
                "POST",
                f"{patient_url(scenario, scenario.archived_patient_id)}/restore",
                token,
            )
        elif operation == "list_alerts":
            response = await read(api_client, f"{patient_url(scenario)}/alerts", token)
        elif operation == "create_alert":
            response = await mutate(
                api_client,
                "POST",
                f"{patient_url(scenario)}/alerts",
                token,
                {"kind": "MEDICATION", "description": f"Alerta {role.value}"},
            )
        else:
            response = await mutate(
                api_client,
                "PATCH",
                f"{patient_url(scenario)}/alerts/{scenario.alert_id}",
                token,
                {"status": "RESOLVED"},
            )
        assert response.status_code == PATIENT_OPERATION_EXPECTATIONS[operation][role], (
            operation,
            role,
        )


@pytest.mark.anyio
async def test_alerts_create_list_and_resolve(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    url = f"{patient_url(scenario)}/alerts"

    created = await mutate(
        api_client,
        "POST",
        url,
        token,
        {"kind": "CLINICAL_RISK", "description": "Risco de sangramento"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["kind"] == "CLINICAL_RISK"
    assert body["status"] == "ACTIVE"
    assert body["resolved_at"] is None
    assert body["created_by_user_id"] == str(scenario.members[Role.OWNER].user_id)

    listed = await read(api_client, f"{url}?limit=50", token)
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert {item["id"] for item in listed.json()["items"]} >= {
        str(scenario.alert_id),
        body["id"],
    }

    resolved = await mutate(
        api_client, "PATCH", f"{url}/{scenario.alert_id}", token, {"status": "RESOLVED"}
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "RESOLVED"
    assert resolved.json()["resolved_at"] is not None

    reopened = await mutate(
        api_client, "PATCH", f"{url}/{scenario.alert_id}", token, {"status": "ACTIVE"}
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "ACTIVE"
    assert reopened.json()["resolved_at"] is None


@pytest.mark.anyio
async def test_alert_updates_reject_null_and_empty_payloads(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)
    url = f"{patient_url(scenario)}/alerts/{scenario.alert_id}"

    null_description = await mutate(api_client, "PATCH", url, token, {"description": None})
    null_status = await mutate(api_client, "PATCH", url, token, {"status": None})
    blank_description = await mutate(api_client, "PATCH", url, token, {"description": "   "})

    for response in (null_description, null_status, blank_description):
        assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_alert_endpoints_hide_cross_tenant_resources(
    api_client: httpx.AsyncClient, patient_scenario: PatientScenario
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    listed = await read(
        api_client, f"{patient_url(scenario, scenario.foreign_patient_id)}/alerts", token
    )
    created = await mutate(
        api_client,
        "POST",
        f"{patient_url(scenario, scenario.foreign_patient_id)}/alerts",
        token,
        {"kind": "OTHER", "description": "Invasão"},
    )
    patched = await mutate(
        api_client,
        "PATCH",
        f"{patient_url(scenario, scenario.foreign_patient_id)}/alerts/{uuid.uuid4()}",
        token,
        {"status": "RESOLVED"},
    )

    for response in (listed, created, patched):
        assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_audit_events_keep_only_ids_and_states(
    api_client: httpx.AsyncClient,
    patient_scenario: PatientScenario,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = patient_scenario
    token = await owner_token(api_client, scenario)

    created = await mutate(
        api_client,
        "POST",
        f"{clinic_url(scenario)}/patients",
        token,
        {
            "full_name": "Segredo Nome Unico",
            "birth_date": "1980-02-02",
            "phone": "+5571944445555",
            "cpf": "123.456.789-09",
        },
    )
    assert created.status_code == 201
    await mutate(
        api_client,
        "POST",
        f"{patient_url(scenario)}/alerts",
        token,
        {"kind": "OTHER", "description": "Descrição clínica confidencial"},
    )
    await mutate(api_client, "POST", f"{patient_url(scenario)}/archive", token)

    rows = await migrator_connection.fetch(
        "SELECT event_type, entity_type, entity_id, metadata FROM app.clinic_audit_events "
        "WHERE clinic_id = $1",
        scenario.clinic_id,
    )
    event_types = {row["event_type"] for row in rows}
    assert {
        "patient.created",
        "patient.archived",
        "patient_alert.created",
    } <= event_types

    for row in rows:
        if row["event_type"].startswith("patient"):
            assert row["entity_type"] is not None
            assert row["entity_id"] is not None

    serialized = json.dumps([dict(row) for row in rows], default=str)
    for secret in (
        "Segredo Nome Unico",
        "12345678909",
        "Descrição clínica confidencial",
        "+5571944445555",
    ):
        assert secret not in serialized, secret
