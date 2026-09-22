"""Consolidated M2 RBAC matrix: every role against every new endpoint.

The expected status of each operation is derived from the declared permission
matrix (``app.clinics.rbac``), so the suite proves both directions at once:

- a role holding the permission gets the positive status (200/201);
- a role without it gets 403 (``default deny``), never 404 or a partial effect.

The independent declaration table is asserted in ``tests/test_rbac.py``; here
the same permissions are exercised through the HTTP layer of all M2 modules.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import asyncpg
import boto3
import httpx
import pytest
from conftest import make_test_email
from fastapi import FastAPI
from helpers import (
    build_complete_anamnesis_payload,
    insert_anamnesis,
    insert_clinic,
    insert_clinic_settings,
    insert_membership,
    insert_patient,
    insert_patient_alert,
    insert_professional_profile,
)

from app.application import create_app
from app.clinics.rbac import Permission, Role, role_allows

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"
BUCKET = "easydentist"

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64

SECRET_CPF = "52998224725"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


@dataclass
class M2Scenario:
    clinic_id: uuid.UUID
    foreign_clinic_id: uuid.UUID
    members: dict[Role, Teammate] = field(default_factory=dict)
    foreign_user_id: uuid.UUID = uuid.UUID(int=0)
    patient_id: uuid.UUID = uuid.UUID(int=0)
    archived_patient_id: uuid.UUID = uuid.UUID(int=0)
    foreign_patient_id: uuid.UUID = uuid.UUID(int=0)
    alert_id: uuid.UUID = uuid.UUID(int=0)
    final_anamnesis_id: uuid.UUID = uuid.UUID(int=0)


@dataclass
class M2Harness:
    client: httpx.AsyncClient
    app: FastAPI
    scenario: M2Scenario
    prefix: str
    s3: object
    administrative_document_id: uuid.UUID = uuid.UUID(int=0)
    clinical_document_id: uuid.UUID = uuid.UUID(int=0)


# Operation → permission required. ``None`` means the endpoint is scoped by the
# authenticated principal itself (professional profile) or readable by every
# role (document listing without a category).
OPERATION_PERMISSIONS: dict[str, Permission | None] = {
    "get_professional_profile": None,
    "put_professional_profile": None,
    "list_patients": Permission.PATIENTS_READ,
    "get_patient": Permission.PATIENTS_READ,
    "create_patient": Permission.PATIENTS_CREATE,
    "update_patient": Permission.PATIENTS_UPDATE,
    "archive_patient": Permission.PATIENTS_ARCHIVE,
    "restore_patient": Permission.PATIENTS_ARCHIVE,
    "list_alerts": Permission.PATIENT_ALERTS_READ,
    "create_alert": Permission.PATIENT_ALERTS_MANAGE,
    "update_alert": Permission.PATIENT_ALERTS_MANAGE,
    "list_anamneses": Permission.ANAMNESIS_READ,
    "get_anamnesis": Permission.ANAMNESIS_READ,
    "create_anamnesis": Permission.ANAMNESIS_CREATE,
    "update_anamnesis": Permission.ANAMNESIS_UPDATE,
    "finalize_anamnesis": Permission.ANAMNESIS_FINALIZE,
    "list_documents": None,
    "get_administrative_document": Permission.DOCUMENTS_ADMINISTRATIVE_READ,
    "download_administrative_document": Permission.DOCUMENTS_ADMINISTRATIVE_READ,
    "upload_administrative_document": Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE,
    "archive_administrative_document": Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE,
    "restore_administrative_document": Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE,
    "get_clinical_document": Permission.DOCUMENTS_CLINICAL_READ,
    "download_clinical_document": Permission.DOCUMENTS_CLINICAL_READ,
    "upload_clinical_document": Permission.DOCUMENTS_CLINICAL_MANAGE,
    "archive_clinical_document": Permission.DOCUMENTS_CLINICAL_MANAGE,
    "restore_clinical_document": Permission.DOCUMENTS_CLINICAL_MANAGE,
}

M2_PERMISSIONS = {
    Permission.PATIENTS_READ,
    Permission.PATIENTS_CREATE,
    Permission.PATIENTS_UPDATE,
    Permission.PATIENTS_ARCHIVE,
    Permission.PATIENT_ALERTS_READ,
    Permission.PATIENT_ALERTS_MANAGE,
    Permission.ANAMNESIS_READ,
    Permission.ANAMNESIS_CREATE,
    Permission.ANAMNESIS_UPDATE,
    Permission.ANAMNESIS_FINALIZE,
    Permission.DOCUMENTS_ADMINISTRATIVE_READ,
    Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE,
    Permission.DOCUMENTS_CLINICAL_READ,
    Permission.DOCUMENTS_CLINICAL_MANAGE,
}

MUTATION_METHODS = {
    "put_professional_profile",
    "create_patient",
    "update_patient",
    "archive_patient",
    "restore_patient",
    "create_alert",
    "update_alert",
    "create_anamnesis",
    "update_anamnesis",
    "finalize_anamnesis",
    "upload_administrative_document",
    "upload_clinical_document",
    "archive_administrative_document",
    "restore_administrative_document",
    "archive_clinical_document",
    "restore_clinical_document",
}


def delete_prefixed(s3: object, prefix: str) -> None:
    paginator = s3.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        keys = [entry["Key"] for entry in page.get("Contents", [])]
        if keys:
            s3.delete_objects(  # type: ignore[attr-defined]
                Bucket=BUCKET, Delete={"Objects": [{"Key": key} for key in keys]}
            )


def required_s3_environment() -> dict[str, str]:
    names = ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET")
    values = {name: os.environ.get(name, "") for name in names}
    if not all(values.values()):
        pytest.skip("S3_ENDPOINT_URL/S3_ACCESS_KEY/S3_SECRET_KEY/S3_BUCKET are required")
    return values


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


async def csrf_token(client: httpx.AsyncClient, token: str) -> str:
    response = await client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={token}"}
    )
    client.cookies.clear()
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def read(client: httpx.AsyncClient, url: str, token: str) -> httpx.Response:
    response = await client.get(url, headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    client.cookies.clear()
    return response


async def mutate(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> httpx.Response:
    csrf = await csrf_token(client, token)
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


async def upload(
    client: httpx.AsyncClient,
    token: str,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    *,
    category: str,
    title: str,
    filename: str = "rbac.pdf",
    data: bytes = PDF_BYTES,
) -> httpx.Response:
    csrf = await csrf_token(client, token)
    response = await client.post(
        f"/api/v1/clinics/{clinic_id}/patients/{patient_id}/documents",
        data={"title": title, "category": category},
        files={"file": (filename, data, "application/octet-stream")},
        headers={
            "Cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


def clinic_url(scenario: M2Scenario, clinic_id: uuid.UUID | None = None) -> str:
    target = clinic_id if clinic_id is not None else scenario.clinic_id
    return f"/api/v1/clinics/{target}"


def patient_url(
    scenario: M2Scenario,
    patient_id: uuid.UUID | None = None,
    clinic_id: uuid.UUID | None = None,
) -> str:
    target = patient_id if patient_id is not None else scenario.patient_id
    return f"{clinic_url(scenario, clinic_id)}/patients/{target}"


def document_url(
    scenario: M2Scenario,
    document_id: uuid.UUID,
    *,
    patient_id: uuid.UUID | None = None,
    suffix: str = "",
) -> str:
    return f"{patient_url(scenario, patient_id)}/documents/{document_id}{suffix}"


async def document_count(
    connection: asyncpg.Connection, clinic_id: uuid.UUID, category: str
) -> int:
    return int(
        await connection.fetchval(
            "SELECT count(*) FROM app.patient_documents WHERE clinic_id = $1 AND category = $2",
            clinic_id,
            category,
        )
    )


async def _build_scenario(
    connection: asyncpg.Connection,
    seed_user_with_password,
) -> M2Scenario:
    built = M2Scenario(clinic_id=uuid.uuid4(), foreign_clinic_id=uuid.uuid4())
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(connection, f"m26-rbac-{suffix}")
    built.foreign_clinic_id = await insert_clinic(connection, f"m26-rbac-foreign-{suffix}")
    await insert_clinic_settings(connection, built.clinic_id)

    for role in Role:
        email = make_test_email(f"m26-rbac-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
        # Every role has a profile so a negative finalize is always a RBAC
        # refusal, never a missing-profile conflict.
        await insert_professional_profile(connection, user_id=user_id)
        built.members[role] = Teammate(email=email, user_id=user_id, membership_id=membership_id)

    built.foreign_user_id = await seed_user_with_password(
        email=make_test_email("m26-rbac-foreign-owner"), password=PASSWORD
    )
    await insert_membership(
        connection,
        clinic_id=built.foreign_clinic_id,
        user_id=built.foreign_user_id,
        role="OWNER",
        status="ACTIVE",
    )

    owner_user_id = built.members[Role.OWNER].user_id
    built.patient_id = await insert_patient(
        connection,
        clinic_id=built.clinic_id,
        full_name="Paciente da Matriz M2",
        cpf=SECRET_CPF,
        phone="+5571999112222",
    )
    built.archived_patient_id = await insert_patient(
        connection,
        clinic_id=built.clinic_id,
        full_name="Paciente Arquivado M2",
        phone="+5571988887777",
        status="ARCHIVED",
        archived_at=datetime.now(UTC),
    )
    built.foreign_patient_id = await insert_patient(
        connection,
        clinic_id=built.foreign_clinic_id,
        full_name="Paciente Externo M2",
        phone="+5571977776666",
    )
    built.alert_id = await insert_patient_alert(
        connection,
        clinic_id=built.clinic_id,
        patient_id=built.patient_id,
        created_by_user_id=owner_user_id,
        kind="ALLERGY",
        description="Alergia a dipirona",
    )
    built.final_anamnesis_id = await insert_anamnesis(
        connection,
        clinic_id=built.clinic_id,
        patient_id=built.patient_id,
        author_user_id=owner_user_id,
        status="FINAL",
        version_number=1,
        payload=build_complete_anamnesis_payload(text_prefix="Resposta da matriz"),
        author_professional_name="Dra. Matriz",
        author_cro_number="12345",
        author_cro_state="BA",
        finalized_at=datetime.now(UTC),
    )
    return built


@pytest.fixture
async def m2_harness(
    migrator_connection: asyncpg.Connection,
    app_async_url: str,
    monkeypatch: pytest.MonkeyPatch,
    email_sender,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[M2Harness]:
    scenario = await _build_scenario(migrator_connection, seed_user_with_password)
    provisioned_clinics.extend([scenario.clinic_id, scenario.foreign_clinic_id])

    environment = required_s3_environment()
    prefix = f"test-m26-rbac/{uuid.uuid4().hex}/"
    monkeypatch.setenv("DATABASE_URL", app_async_url)
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://testserver")
    monkeypatch.setenv("S3_ENDPOINT_URL", environment["S3_ENDPOINT_URL"])
    monkeypatch.setenv("S3_ACCESS_KEY", environment["S3_ACCESS_KEY"])
    monkeypatch.setenv("S3_SECRET_KEY", environment["S3_SECRET_KEY"])
    monkeypatch.setenv("S3_BUCKET", environment["S3_BUCKET"])
    monkeypatch.setenv("S3_REGION", os.environ.get("S3_REGION", "us-east-1"))
    monkeypatch.setenv("S3_KEY_PREFIX", prefix)

    app = create_app()
    s3 = boto3.client(
        "s3",
        endpoint_url=environment["S3_ENDPOINT_URL"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        aws_access_key_id=environment["S3_ACCESS_KEY"],
        aws_secret_access_key=environment["S3_SECRET_KEY"],
        config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    async with app.router.lifespan_context(app):
        app.state.email_sender = email_sender
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            harness = M2Harness(client=client, app=app, scenario=scenario, prefix=prefix, s3=s3)
            owner = await login(client, scenario.members[Role.OWNER].email)
            administrative = await upload(
                client,
                owner,
                scenario.clinic_id,
                scenario.patient_id,
                category="ADMINISTRATIVE",
                title="Contrato administrativo",
            )
            assert administrative.status_code == 201, administrative.text
            harness.administrative_document_id = uuid.UUID(administrative.json()["id"])
            clinical = await upload(
                client,
                owner,
                scenario.clinic_id,
                scenario.patient_id,
                category="CLINICAL",
                title="Laudo clínico",
                data=PDF_BYTES,
            )
            assert clinical.status_code == 201, clinical.text
            harness.clinical_document_id = uuid.UUID(clinical.json()["id"])
            try:
                yield harness
            finally:
                app.dependency_overrides.clear()
                delete_prefixed(s3, prefix)


def expected_status(role: Role, operation: str) -> int:
    permission = OPERATION_PERMISSIONS[operation]
    if permission is None:
        return 200
    if not role_allows(role, permission):
        return 403
    if operation in {
        "create_patient",
        "create_alert",
        "create_anamnesis",
        "upload_administrative_document",
        "upload_clinical_document",
    }:
        return 201
    return 200


async def _run_operation(
    harness: M2Harness,
    token: str,
    operation: str,
    state: dict[str, uuid.UUID],
) -> httpx.Response:
    client = harness.client
    scenario = harness.scenario
    if operation == "get_professional_profile":
        return await read(client, "/api/v1/users/me/professional-profile", token)
    if operation == "put_professional_profile":
        return await mutate(
            client,
            "PUT",
            "/api/v1/users/me/professional-profile",
            token,
            {"professional_name": "Dr. Matriz", "cro_number": "54321", "cro_state": "BA"},
        )
    if operation == "list_patients":
        return await read(client, f"{clinic_url(scenario)}/patients", token)
    if operation == "get_patient":
        return await read(client, patient_url(scenario), token)
    if operation == "create_patient":
        return await mutate(
            client,
            "POST",
            f"{clinic_url(scenario)}/patients",
            token,
            {
                "full_name": "Pessoa Criada na Matriz",
                "birth_date": "1992-02-03",
                "phone": "+5571911110000",
            },
        )
    if operation == "update_patient":
        return await mutate(
            client, "PATCH", patient_url(scenario), token, {"social_name": "Apelido Matriz"}
        )
    if operation == "archive_patient":
        return await mutate(client, "POST", f"{patient_url(scenario)}/archive", token)
    if operation == "restore_patient":
        return await mutate(
            client,
            "POST",
            f"{patient_url(scenario, scenario.archived_patient_id)}/restore",
            token,
        )
    if operation == "list_alerts":
        return await read(client, f"{patient_url(scenario)}/alerts", token)
    if operation == "create_alert":
        return await mutate(
            client,
            "POST",
            f"{patient_url(scenario)}/alerts",
            token,
            {"kind": "MEDICATION", "description": "Alerta da matriz"},
        )
    if operation == "update_alert":
        return await mutate(
            client,
            "PATCH",
            f"{patient_url(scenario)}/alerts/{scenario.alert_id}",
            token,
            {"status": "RESOLVED"},
        )
    if operation == "list_anamneses":
        return await read(client, f"{patient_url(scenario)}/anamneses", token)
    if operation == "get_anamnesis":
        return await read(
            client, f"{patient_url(scenario)}/anamneses/{scenario.final_anamnesis_id}", token
        )
    if operation == "create_anamnesis":
        response = await mutate(client, "POST", f"{patient_url(scenario)}/anamneses", token, {})
        if response.status_code == 201:
            state["draft_id"] = uuid.UUID(response.json()["id"])
        return response
    if operation == "update_anamnesis":
        target = state.get("draft_id", scenario.final_anamnesis_id)
        return await mutate(
            client,
            "PATCH",
            f"{patient_url(scenario)}/anamneses/{target}",
            token,
            {"payload": build_complete_anamnesis_payload(text_prefix="Resposta da matriz")},
        )
    if operation == "finalize_anamnesis":
        target = state.get("draft_id", scenario.final_anamnesis_id)
        return await mutate(
            client,
            "POST",
            f"{patient_url(scenario)}/anamneses/{target}/finalize",
            token,
        )
    if operation == "list_documents":
        return await read(client, f"{patient_url(scenario)}/documents", token)
    if operation == "get_administrative_document":
        return await read(client, document_url(scenario, harness.administrative_document_id), token)
    if operation == "download_administrative_document":
        return await read(
            client,
            document_url(scenario, harness.administrative_document_id, suffix="/content"),
            token,
        )
    if operation == "upload_administrative_document":
        return await upload(
            client,
            token,
            scenario.clinic_id,
            scenario.patient_id,
            category="ADMINISTRATIVE",
            title="Upload administrativo da matriz",
        )
    if operation == "archive_administrative_document":
        return await mutate(
            client,
            "POST",
            document_url(scenario, harness.administrative_document_id, suffix="/archive"),
            token,
        )
    if operation == "restore_administrative_document":
        return await mutate(
            client,
            "POST",
            document_url(scenario, harness.administrative_document_id, suffix="/restore"),
            token,
        )
    if operation == "get_clinical_document":
        return await read(client, document_url(scenario, harness.clinical_document_id), token)
    if operation == "download_clinical_document":
        return await read(
            client,
            document_url(scenario, harness.clinical_document_id, suffix="/content"),
            token,
        )
    if operation == "upload_clinical_document":
        return await upload(
            client,
            token,
            scenario.clinic_id,
            scenario.patient_id,
            category="CLINICAL",
            title="Upload clínico da matriz",
            filename="rbac-clinico.pdf",
        )
    if operation == "archive_clinical_document":
        return await mutate(
            client,
            "POST",
            document_url(scenario, harness.clinical_document_id, suffix="/archive"),
            token,
        )
    if operation == "restore_clinical_document":
        return await mutate(
            client,
            "POST",
            document_url(scenario, harness.clinical_document_id, suffix="/restore"),
            token,
        )
    raise AssertionError(f"unknown operation {operation}")


@pytest.mark.anyio
@pytest.mark.parametrize("role", list(Role))
async def test_role_matrix_on_m2_endpoints(
    m2_harness: M2Harness,
    migrator_connection: asyncpg.Connection,
    role: Role,
) -> None:
    harness = m2_harness
    scenario = harness.scenario
    token = await login(harness.client, scenario.members[role].email)
    administrative_before = await document_count(
        migrator_connection, scenario.clinic_id, "ADMINISTRATIVE"
    )
    clinical_before = await document_count(migrator_connection, scenario.clinic_id, "CLINICAL")
    state: dict[str, uuid.UUID] = {}

    for operation in OPERATION_PERMISSIONS:
        response = await _run_operation(harness, token, operation, state)
        assert response.status_code == expected_status(role, operation), (
            role.value,
            operation,
            response.status_code,
            response.text,
        )

    administrative_after = await document_count(
        migrator_connection, scenario.clinic_id, "ADMINISTRATIVE"
    )
    clinical_after = await document_count(migrator_connection, scenario.clinic_id, "CLINICAL")
    expected_admin = administrative_before + (
        1 if role_allows(role, Permission.DOCUMENTS_ADMINISTRATIVE_MANAGE) else 0
    )
    expected_clinical = clinical_before + (
        1 if role_allows(role, Permission.DOCUMENTS_CLINICAL_MANAGE) else 0
    )
    assert administrative_after == expected_admin, role
    assert clinical_after == expected_clinical, role


@pytest.mark.anyio
async def test_denied_operations_never_touch_the_database(
    m2_harness: M2Harness,
    migrator_connection: asyncpg.Connection,
) -> None:
    """A 403 must be a pure refusal: no patient row survives it."""

    harness = m2_harness
    scenario = harness.scenario
    for role in Role:
        if role_allows(role, Permission.PATIENTS_CREATE):
            continue
        token = await login(harness.client, scenario.members[role].email)
        before = int(
            await migrator_connection.fetchval(
                "SELECT count(*) FROM app.patients WHERE clinic_id = $1", scenario.clinic_id
            )
        )
        response = await mutate(
            harness.client,
            "POST",
            f"{clinic_url(scenario)}/patients",
            token,
            {
                "full_name": "Nao deve existir",
                "birth_date": "1990-01-01",
                "phone": "+5571900000000",
            },
        )
        after = int(
            await migrator_connection.fetchval(
                "SELECT count(*) FROM app.patients WHERE clinic_id = $1", scenario.clinic_id
            )
        )
        assert response.status_code == 403, role
        assert after == before, role


def test_operation_matrix_covers_every_m2_permission() -> None:
    covered = {
        permission for permission in OPERATION_PERMISSIONS.values() if permission is not None
    }
    assert covered == M2_PERMISSIONS


@pytest.mark.anyio
async def test_anonymous_requests_are_rejected(m2_harness: M2Harness) -> None:
    harness = m2_harness
    scenario = harness.scenario
    client = harness.client
    client.cookies.clear()

    reads = (
        "/api/v1/users/me/professional-profile",
        f"{clinic_url(scenario)}/patients",
        patient_url(scenario),
        f"{patient_url(scenario)}/alerts",
        f"{patient_url(scenario)}/anamneses",
        f"{patient_url(scenario)}/documents",
        document_url(scenario, harness.administrative_document_id, suffix="/content"),
    )
    for path in reads:
        response = await client.get(path)
        assert response.status_code == 401, path

    csrf = await anonymous_csrf(client)
    client.cookies.clear()
    mutations = (
        ("POST", f"{clinic_url(scenario)}/patients", {"full_name": "x"}),
        ("PATCH", patient_url(scenario), {"social_name": "x"}),
        ("POST", f"{patient_url(scenario)}/anamneses", {}),
    )
    for method, path, payload in mutations:
        response = await client.request(
            method,
            path,
            json=payload,
            headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
        )
        assert response.status_code == 401, path

    anonymous_upload = await client.post(
        f"{patient_url(scenario)}/documents",
        data={"title": "Sem sessão", "category": "CLINICAL"},
        files={"file": ("anonimo.pdf", PDF_BYTES, "application/octet-stream")},
        headers={"Cookie": f"{CSRF_COOKIE}={csrf}", "X-CSRF-Token": csrf, "Origin": ORIGIN},
    )
    assert anonymous_upload.status_code == 401


@pytest.mark.anyio
async def test_response_bodies_are_problem_details_without_tenant_data(
    m2_harness: M2Harness,
) -> None:
    """403/404/422 responses never echo payload, IDs or clinical content."""

    harness = m2_harness
    scenario = harness.scenario
    assistant = await login(harness.client, scenario.members[Role.ASSISTANT].email)

    forbidden = await mutate(
        harness.client,
        "POST",
        f"{clinic_url(scenario)}/patients",
        assistant,
        {"full_name": "Pessoa Sigilosa", "birth_date": "1990-01-01", "phone": "+5571900000000"},
    )
    assert forbidden.status_code == 403
    body = forbidden.json()
    assert set(body) <= {"type", "title", "status", "request_id", "detail"}
    assert "Pessoa Sigilosa" not in json.dumps(body)
    assert "+5571900000000" not in json.dumps(body)

    missing_id = uuid.uuid4()
    not_found = await read(
        harness.client,
        document_url(scenario, missing_id, suffix="/content"),
        assistant,
    )
    assert not_found.status_code == 404
    assert str(missing_id) not in not_found.text
    assert "Laudo clínico" not in not_found.text

    clinical = await read(
        harness.client, document_url(scenario, harness.clinical_document_id), assistant
    )
    assert clinical.status_code == 200

    admin_role = await login(harness.client, scenario.members[Role.ADMIN].email)
    denied = await read(
        harness.client, document_url(scenario, harness.clinical_document_id), admin_role
    )
    assert denied.status_code == 403
    assert "Laudo clínico" not in denied.text
    assert str(harness.clinical_document_id) not in denied.text


def test_expected_status_helper_is_default_deny() -> None:
    """No operation is silently allowed: the only possible statuses are the
    positive one (200/201) for permission holders and 403 for everyone else."""

    for role in Role:
        for operation, permission in OPERATION_PERMISSIONS.items():
            status = expected_status(role, operation)
            if permission is None:
                assert status == 200
                continue
            assert status in {200, 201, 403}
            if role_allows(role, permission):
                assert status != 403
            else:
                assert status == 403
