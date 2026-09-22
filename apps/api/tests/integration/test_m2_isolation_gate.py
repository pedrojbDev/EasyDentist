"""M2 isolation and redaction gate.

Proves, with valid IDs taken from the other clinic, that no M2 resource leaks
across the tenant boundary at any layer:

- HTTP API (every new route, including document content);
- repositories under a mismatched tenant context;
- raw SQL under the runtime role, with and without context;
- private object storage keys (authorization before any I/O).

It also proves that CPF, anamnesis answers, file names, file content and S3
keys never reach application logs, Problem Details or audit metadata.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import BinaryIO

import asyncpg
import boto3
import httpx
import pytest
from conftest import SeededTenants
from fastapi import FastAPI
from helpers import (
    build_complete_anamnesis_payload,
    delete_m2_rows_for_clinics,
    delete_professional_profiles_for_users,
    insert_anamnesis,
    insert_patient,
    insert_patient_alert,
    insert_patient_document,
    insert_professional_profile,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.anamnesis.repositories import AnamnesisRepository
from app.application import create_app
from app.auth.sessions import SessionService
from app.auth.settings import AuthSettings
from app.clinics.audit import CLINIC_EVENT_METADATA_ALLOWLIST
from app.core.context import TenantContext
from app.core.errors import ContextMismatchError
from app.core.tenancy import tenant_transaction
from app.documents.repositories import DocumentRepository
from app.documents.routers import get_object_storage
from app.patients.repositories.patient_repository import PatientRepository
from app.platform.logging import JsonLogFormatter
from app.platform.storage import ObjectStorage

BUCKET = "easydentist"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"

M2_TENANT_TABLES = ("patients", "patient_alerts", "anamneses", "patient_documents")

OWN_ROW_FIELDS: dict[str, tuple[str, str]] = {
    "patients": ("patient_a", "patient_b"),
    "patient_alerts": ("alert_a", "alert_b"),
    "anamneses": ("draft_a", "draft_b"),
    "patient_documents": ("document_a", "document_b"),
}

SECRET_CPF = "11144477735"
SECRET_NAME = "Paciente Sigiloso {suffix}"
SECRET_ANSWER = "SEGREDO-CLINICO-{suffix}"
SECRET_FILENAME = "receita-secreta-{suffix}.pdf"
SECRET_CONTENT = b"%PDF-1.7\nCONTEUDO-CONFIDENCIAL-{suffix}\n%%EOF\n"


def secret_values(suffix: str) -> dict[str, str]:
    return {
        "cpf": SECRET_CPF,
        "name": SECRET_NAME.format(suffix=suffix),
        "answer": SECRET_ANSWER.format(suffix=suffix),
        "filename": SECRET_FILENAME.format(suffix=suffix),
        "content": SECRET_CONTENT.decode().format(suffix=suffix),
    }


@dataclass
class IsolatedM2:
    patient_a: uuid.UUID
    patient_b: uuid.UUID
    alert_a: uuid.UUID
    alert_b: uuid.UUID
    draft_a: uuid.UUID
    draft_b: uuid.UUID
    document_a: uuid.UUID
    document_b: uuid.UUID
    profile_a: uuid.UUID
    profile_b: uuid.UUID


@dataclass
class IsolationHarness:
    app: FastAPI
    client: httpx.AsyncClient
    session_factory: async_sessionmaker[AsyncSession]
    auth_settings: AuthSettings
    sessions: SessionService
    tenants: SeededTenants
    token_a: str
    token_b: str
    prefix: str
    s3: object
    storage: RecordingStorage
    uploaded_document_id: uuid.UUID = uuid.UUID(int=0)
    uploaded_storage_key: str = ""


class RecordingStorage:
    """Delegates to the real adapter while counting storage operations."""

    def __init__(self, inner: ObjectStorage) -> None:
        self._inner = inner
        self.puts: list[str] = []
        self.deletes: list[str] = []
        self.stream_calls = 0

    async def put(self, key: str, file_object: BinaryIO, *, content_type: str) -> None:
        self.puts.append(key)
        await self._inner.put(key, file_object, content_type=content_type)

    async def stream(self, key: str):
        self.stream_calls += 1
        return await self._inner.stream(key)

    async def delete(self, key: str) -> None:
        self.deletes.append(key)
        await self._inner.delete(key)

    async def verify(self, key: str) -> bool:
        return await self._inner.verify(key)


def required_s3_environment() -> dict[str, str]:
    names = ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET")
    values = {name: os.environ.get(name, "") for name in names}
    if not all(values.values()):
        pytest.skip("S3_ENDPOINT_URL/S3_ACCESS_KEY/S3_SECRET_KEY/S3_BUCKET are required")
    return values


def delete_prefixed(s3: object, prefix: str) -> None:
    paginator = s3.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        keys = [entry["Key"] for entry in page.get("Contents", [])]
        if keys:
            s3.delete_objects(  # type: ignore[attr-defined]
                Bucket=BUCKET, Delete={"Objects": [{"Key": key} for key in keys]}
            )


def list_prefixed(s3: object, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = s3.get_paginator("list_objects_v2")  # type: ignore[attr-defined]
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        keys.extend(entry["Key"] for entry in page.get("Contents", []))
    return keys


def session_cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


async def csrf_for(client: httpx.AsyncClient, token: str) -> str:
    response = await client.get("/api/v1/auth/csrf", headers=session_cookie(token))
    assert response.status_code == 200
    return response.json()["csrf_token"]


async def mutate(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    token: str,
    payload: dict[str, object] | None = None,
) -> httpx.Response:
    csrf = await csrf_for(client, token)
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


async def upload_content(
    client: httpx.AsyncClient,
    token: str,
    url: str,
    *,
    title: str,
    category: str,
    filename: str,
    data: bytes,
) -> httpx.Response:
    csrf = await csrf_for(client, token)
    response = await client.post(
        url,
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


@pytest.fixture
async def isolated_m2(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> AsyncIterator[IsolatedM2]:
    tenants = seeded_tenants
    patient_a = await insert_patient(
        migrator_connection,
        clinic_id=tenants.clinic_a,
        full_name="Paciente Interno A",
        phone="+5571999112222",
    )
    patient_b = await insert_patient(
        migrator_connection,
        clinic_id=tenants.clinic_b,
        full_name="Paciente Externo B",
        phone="+5571988887777",
    )
    alert_a = await insert_patient_alert(
        migrator_connection,
        clinic_id=tenants.clinic_a,
        patient_id=patient_a,
        created_by_user_id=tenants.user_a,
    )
    alert_b = await insert_patient_alert(
        migrator_connection,
        clinic_id=tenants.clinic_b,
        patient_id=patient_b,
        created_by_user_id=tenants.user_b,
    )
    draft_a = await insert_anamnesis(
        migrator_connection,
        clinic_id=tenants.clinic_a,
        patient_id=patient_a,
        author_user_id=tenants.user_a,
    )
    draft_b = await insert_anamnesis(
        migrator_connection,
        clinic_id=tenants.clinic_b,
        patient_id=patient_b,
        author_user_id=tenants.user_b,
    )
    document_a = await insert_patient_document(
        migrator_connection,
        clinic_id=tenants.clinic_a,
        patient_id=patient_a,
        uploaded_by_user_id=tenants.user_a,
        storage_key=f"gate-a-{uuid.uuid4().hex}",
    )
    document_b = await insert_patient_document(
        migrator_connection,
        clinic_id=tenants.clinic_b,
        patient_id=patient_b,
        uploaded_by_user_id=tenants.user_b,
        storage_key=f"gate-b-{uuid.uuid4().hex}",
    )
    await insert_professional_profile(migrator_connection, user_id=tenants.user_a)
    await insert_professional_profile(migrator_connection, user_id=tenants.user_b)

    clinic_ids = [tenants.clinic_a, tenants.clinic_b]
    try:
        yield IsolatedM2(
            patient_a=patient_a,
            patient_b=patient_b,
            alert_a=alert_a,
            alert_b=alert_b,
            draft_a=draft_a,
            draft_b=draft_b,
            document_a=document_a,
            document_b=document_b,
            profile_a=tenants.user_a,
            profile_b=tenants.user_b,
        )
    finally:
        await delete_m2_rows_for_clinics(migrator_connection, clinic_ids)
        await delete_professional_profiles_for_users(
            migrator_connection, [tenants.user_a, tenants.user_b]
        )


@pytest.fixture
async def isolation_harness(
    seeded_tenants: SeededTenants,
    app_async_url: str,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    email_sender,
    migrator_connection: asyncpg.Connection,
) -> AsyncIterator[IsolationHarness]:
    environment = required_s3_environment()
    prefix = f"test-m26-gate/{uuid.uuid4().hex}/"
    monkeypatch.setenv("DATABASE_URL", app_async_url)
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://testserver")
    monkeypatch.setenv("S3_ENDPOINT_URL", environment["S3_ENDPOINT_URL"])
    monkeypatch.setenv("S3_ACCESS_KEY", environment["S3_ACCESS_KEY"])
    monkeypatch.setenv("S3_SECRET_KEY", environment["S3_SECRET_KEY"])
    monkeypatch.setenv("S3_BUCKET", environment["S3_BUCKET"])
    monkeypatch.setenv("S3_REGION", os.environ.get("S3_REGION", "us-east-1"))
    monkeypatch.setenv("S3_KEY_PREFIX", prefix)

    s3 = boto3.client(
        "s3",
        endpoint_url=environment["S3_ENDPOINT_URL"],
        region_name=os.environ.get("S3_REGION", "us-east-1"),
        aws_access_key_id=environment["S3_ACCESS_KEY"],
        aws_secret_access_key=environment["S3_SECRET_KEY"],
        config=boto3.session.Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    app = create_app()
    sessions = SessionService(session_factory, auth_settings)
    _, token_a = await sessions.create(seeded_tenants.user_a)
    _, token_b = await sessions.create(seeded_tenants.user_b)

    async with app.router.lifespan_context(app):
        app.state.email_sender = email_sender
        storage = RecordingStorage(app.state.object_storage)
        app.dependency_overrides[get_object_storage] = lambda: storage
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            harness = IsolationHarness(
                app=app,
                client=client,
                session_factory=session_factory,
                auth_settings=auth_settings,
                sessions=sessions,
                tenants=seeded_tenants,
                token_a=token_a,
                token_b=token_b,
                prefix=prefix,
                s3=s3,
                storage=storage,
            )
            try:
                yield harness
            finally:
                app.dependency_overrides.clear()
                delete_prefixed(s3, prefix)
                await migrator_connection.execute(
                    "DELETE FROM app.auth_sessions WHERE user_id = ANY($1::uuid[])",
                    [seeded_tenants.user_a, seeded_tenants.user_b],
                )


def m2_paths(clinic_id: uuid.UUID, patient_id: uuid.UUID, *extra: str) -> list[str]:
    base = f"/api/v1/clinics/{clinic_id}/patients/{patient_id}"
    return [f"{base}{suffix}" for suffix in ("", "/alerts", "/anamneses", "/documents", *extra)]


@pytest.mark.anyio
async def test_foreign_clinic_routes_are_not_found_without_leak(
    isolation_harness: IsolationHarness, isolated_m2: IsolatedM2
) -> None:
    harness = isolation_harness
    tenants = harness.tenants
    m2 = isolated_m2
    foreign = tenants.clinic_b
    foreign_paths = [
        f"/api/v1/clinics/{foreign}/patients",
        *m2_paths(foreign, m2.patient_b),
        f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/documents/{m2.document_b}",
        f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/documents/{m2.document_b}/content",
    ]
    for path in foreign_paths:
        response = await harness.client.get(path, headers=session_cookie(harness.token_a))
        assert response.status_code == 404, path
        body = response.text
        assert str(foreign) not in body, path
        assert str(m2.patient_b) not in body, path
        assert "Paciente Externo B" not in body, path

    mutations = [
        ("PATCH", f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}", {"social_name": "x"}),
        ("POST", f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/archive", None),
        ("POST", f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/alerts", {"kind": "OTHER"}),
        ("POST", f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/anamneses", {}),
        ("POST", f"/api/v1/clinics/{foreign}/patients/{m2.patient_b}/archive", None),
    ]
    for method, path, payload in mutations:
        response = await mutate(harness.client, method, path, harness.token_a, payload)
        assert response.status_code == 404, path


@pytest.mark.anyio
async def test_own_clinic_with_foreign_ids_is_not_found(
    isolation_harness: IsolationHarness, isolated_m2: IsolatedM2
) -> None:
    harness = isolation_harness
    tenants = harness.tenants
    m2 = isolated_m2
    own = f"/api/v1/clinics/{tenants.clinic_a}"
    paths = [
        f"{own}/patients/{m2.patient_b}",
        f"{own}/patients/{m2.patient_b}/alerts",
        f"{own}/patients/{m2.patient_b}/anamneses",
        f"{own}/patients/{m2.patient_b}/anamneses/{m2.draft_b}",
        f"{own}/patients/{m2.patient_a}/anamneses/{m2.draft_b}",
        f"{own}/patients/{m2.patient_a}/documents/{m2.document_b}",
        f"{own}/patients/{m2.patient_a}/documents/{m2.document_b}/content",
    ]
    for path in paths:
        response = await harness.client.get(path, headers=session_cookie(harness.token_a))
        assert response.status_code == 404, path
        assert str(m2.patient_b) not in response.text, path
        assert str(m2.draft_b) not in response.text, path
        assert str(m2.document_b) not in response.text, path

    for method, path, payload in (
        ("PATCH", f"{own}/patients/{m2.patient_b}", {"social_name": "x"}),
        ("POST", f"{own}/patients/{m2.patient_b}/archive", None),
        ("POST", f"{own}/patients/{m2.patient_b}/alerts", {"kind": "OTHER", "description": "x"}),
        ("POST", f"{own}/patients/{m2.patient_b}/anamneses", {}),
        ("POST", f"{own}/patients/{m2.patient_a}/anamneses/{m2.draft_b}/finalize", None),
    ):
        response = await mutate(harness.client, method, path, harness.token_a, payload)
        assert response.status_code == 404, path


@pytest.mark.anyio
async def test_repositories_reject_mismatched_context_and_hide_foreign_rows(
    isolation_harness: IsolationHarness, isolated_m2: IsolatedM2
) -> None:
    harness = isolation_harness
    tenants = harness.tenants
    m2 = isolated_m2
    context_a = TenantContext(user_id=tenants.user_a, clinic_id=tenants.clinic_a)
    context_b = TenantContext(user_id=tenants.user_b, clinic_id=tenants.clinic_b)

    async with tenant_transaction(harness.session_factory, context_a) as session:
        assert await PatientRepository(session).get(context_a, m2.patient_b) is None
        assert await PatientRepository(session).get(context_a, m2.patient_a) is not None
        assert await AnamnesisRepository(session).get(context_a, m2.patient_a, m2.draft_b) is None
        assert (
            await AnamnesisRepository(session).get(context_a, m2.patient_a, m2.draft_a) is not None
        )
        assert await DocumentRepository(session).get(context_a, m2.patient_a, m2.document_b) is None
        patients, total = await PatientRepository(session).list(
            context_a, status="ACTIVE", search=None, limit=50, offset=0
        )
        assert {patient.id for patient in patients} == {m2.patient_a}
        assert total == 1

        with pytest.raises(ContextMismatchError):
            await PatientRepository(session).get(context_b, m2.patient_b)

    async with tenant_transaction(harness.session_factory, context_b) as session:
        assert await PatientRepository(session).get(context_b, m2.patient_a) is None
        assert await AnamnesisRepository(session).get(context_b, m2.patient_b, m2.draft_a) is None
        assert await DocumentRepository(session).get(context_b, m2.patient_b, m2.document_a) is None


async def _scoped_ids(
    connection: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    clinic_id: uuid.UUID | None,
    table: str,
    key: str = "id",
) -> list[uuid.UUID]:
    transaction = connection.transaction()
    await transaction.start()
    try:
        if clinic_id is None:
            await connection.execute(
                "SELECT set_config('app.current_user_id', $1, true)", str(user_id)
            )
        else:
            await connection.execute(
                "SELECT set_config('app.current_user_id', $1, true), "
                "set_config('app.current_clinic_id', $2, true)",
                str(user_id),
                str(clinic_id),
            )
        rows = await connection.fetch(f"SELECT {key} AS key FROM app.{table}")
        return [row["key"] for row in rows]
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_raw_sql_under_runtime_role_is_fail_closed_and_scoped(
    app_connection: asyncpg.Connection,
    isolated_m2: IsolatedM2,
    seeded_tenants: SeededTenants,
) -> None:
    m2 = isolated_m2
    tenants = seeded_tenants

    for table in M2_TENANT_TABLES:
        a_field, b_field = OWN_ROW_FIELDS[table]
        assert (
            await _scoped_ids(app_connection, user_id=tenants.user_a, clinic_id=None, table=table)
            == []
        ), table
        assert await _scoped_ids(
            app_connection, user_id=tenants.user_a, clinic_id=tenants.clinic_a, table=table
        ) == [getattr(m2, a_field)], table
        assert await _scoped_ids(
            app_connection, user_id=tenants.user_b, clinic_id=tenants.clinic_b, table=table
        ) == [getattr(m2, b_field)], table
        # Membership of the other clinic does not grant its rows.
        assert (
            await _scoped_ids(
                app_connection, user_id=tenants.user_a, clinic_id=tenants.clinic_b, table=table
            )
            == []
        ), table

    profiles = await _scoped_ids(
        app_connection,
        user_id=tenants.user_a,
        clinic_id=None,
        table="professional_profiles",
        key="user_id",
    )
    assert set(profiles) == {m2.profile_a}

    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(tenants.user_a),
            str(tenants.clinic_a),
        )
        updated = await app_connection.execute(
            "UPDATE app.patients SET full_name = 'invasao' WHERE id = $1 RETURNING id",
            m2.patient_b,
        )
        assert updated == "UPDATE 0"
    finally:
        await transaction.rollback()

    # The runtime role has no DELETE grant on any M2 table (defence in depth);
    # each attempt runs in its own transaction because the first denial aborts it.
    for table in M2_TENANT_TABLES:
        transaction = app_connection.transaction()
        await transaction.start()
        try:
            await app_connection.execute(
                "SELECT set_config('app.current_user_id', $1, true), "
                "set_config('app.current_clinic_id', $2, true)",
                str(tenants.user_a),
                str(tenants.clinic_a),
            )
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await app_connection.execute(f"DELETE FROM app.{table}")
        finally:
            await transaction.rollback()

    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await app_connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(tenants.user_a),
            str(tenants.clinic_a),
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_patient_document(
                app_connection,
                clinic_id=tenants.clinic_a,
                patient_id=m2.patient_b,
                uploaded_by_user_id=tenants.user_a,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_document_storage_is_authorized_before_any_io(
    isolation_harness: IsolationHarness, isolated_m2: IsolatedM2
) -> None:
    harness = isolation_harness
    tenants = harness.tenants
    suffix = uuid.uuid4().hex[:10]
    secrets = secret_values(suffix)
    b_url = f"/api/v1/clinics/{tenants.clinic_b}/patients/{isolated_m2.patient_b}/documents"

    uploaded = await upload_content(
        harness.client,
        harness.token_b,
        b_url,
        title=f"Documento {suffix}",
        category="CLINICAL",
        filename=secrets["filename"],
        data=secrets["content"].encode(),
    )
    assert uploaded.status_code == 201, uploaded.text
    document_id = uuid.UUID(uploaded.json()["id"])
    storage_key = await _storage_key(
        harness.session_factory,
        user_id=tenants.user_b,
        clinic_id=tenants.clinic_b,
        document_id=document_id,
    )
    assert storage_key is not None
    assert harness.prefix + storage_key in list_prefixed(harness.s3, harness.prefix)
    assert secrets["filename"] not in storage_key
    assert "gate-b" not in storage_key

    stream_calls_before = harness.storage.stream_calls

    own = await harness.client.get(
        f"{b_url}/{document_id}/content", headers=session_cookie(harness.token_b)
    )
    assert own.status_code == 200
    assert own.content == secrets["content"].encode()
    assert harness.storage.stream_calls == stream_calls_before + 1

    foreign_reads = [
        f"/api/v1/clinics/{tenants.clinic_b}/patients/{isolated_m2.patient_b}/documents/{document_id}",
        f"{b_url}/{document_id}/content",
        f"/api/v1/clinics/{tenants.clinic_a}/patients/{isolated_m2.patient_a}/documents/{document_id}",
        f"/api/v1/clinics/{tenants.clinic_a}/patients/{isolated_m2.patient_a}/documents/{document_id}/content",
    ]
    for path in foreign_reads:
        response = await harness.client.get(path, headers=session_cookie(harness.token_a))
        assert response.status_code == 404, path
        assert secrets["content"] not in response.text, path
        assert storage_key not in response.text, path
        assert secrets["filename"] not in response.text, path

    # Authorization must fail before touching the private object.
    assert harness.storage.stream_calls == stream_calls_before + 1

    listing = await harness.client.get(
        f"/api/v1/clinics/{tenants.clinic_a}/patients/{isolated_m2.patient_a}/documents",
        headers=session_cookie(harness.token_a),
    )
    assert listing.status_code == 200
    text = listing.text
    assert str(document_id) not in text
    assert secrets["filename"] not in text
    assert storage_key not in text

    single = await harness.client.get(
        f"/api/v1/clinics/{tenants.clinic_a}/patients/{isolated_m2.patient_a}/documents/{isolated_m2.document_b}",
        headers=session_cookie(harness.token_a),
    )
    assert single.status_code == 404
    assert str(isolated_m2.document_b) not in single.text


async def _storage_key(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: uuid.UUID,
    clinic_id: uuid.UUID,
    document_id: uuid.UUID,
) -> str | None:
    async with tenant_transaction(
        session_factory, TenantContext(user_id=user_id, clinic_id=clinic_id)
    ) as session:
        key = await session.scalar(
            text("SELECT storage_key FROM app.patient_documents WHERE id = :id"),
            {"id": document_id},
        )
    return str(key) if key is not None else None


@pytest.mark.anyio
async def test_sensitive_values_never_reach_logs_or_problem_details(
    isolation_harness: IsolationHarness,
    isolated_m2: IsolatedM2,
    migrator_connection: asyncpg.Connection,
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness = isolation_harness
    tenants = harness.tenants
    suffix = uuid.uuid4().hex[:10]
    secrets = secret_values(suffix)

    caplog.set_level(logging.DEBUG, logger="easydentist.api")

    created = await mutate(
        harness.client,
        "POST",
        f"/api/v1/clinics/{tenants.clinic_a}/patients",
        harness.token_a,
        {
            "full_name": secrets["name"],
            "birth_date": "1990-05-06",
            "phone": "+5571900000000",
            "cpf": secrets["cpf"],
        },
    )
    assert created.status_code == 201, created.text
    created_patient = uuid.UUID(created.json()["id"])
    created_url = f"/api/v1/clinics/{tenants.clinic_a}/patients/{created_patient}"

    updated = await mutate(
        harness.client, "PATCH", created_url, harness.token_a, {"social_name": secrets["name"]}
    )
    assert updated.status_code == 200, updated.text

    draft = await mutate(
        harness.client,
        "POST",
        f"{created_url}/anamneses",
        harness.token_a,
        {"base_version_id": None},
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["id"]
    payload = build_complete_anamnesis_payload(text_prefix=secrets["answer"])
    saved = await mutate(
        harness.client,
        "PATCH",
        f"{created_url}/anamneses/{draft_id}",
        harness.token_a,
        {"payload": payload},
    )
    assert saved.status_code == 200, saved.text
    finalized = await mutate(
        harness.client, "POST", f"{created_url}/anamneses/{draft_id}/finalize", harness.token_a
    )
    assert finalized.status_code == 200, finalized.text

    uploaded = await upload_content(
        harness.client,
        harness.token_a,
        f"{created_url}/documents",
        title="Documento sigiloso",
        category="CLINICAL",
        filename=secrets["filename"],
        data=secrets["content"].encode(),
    )
    assert uploaded.status_code == 201, uploaded.text
    uploaded_id = uuid.UUID(uploaded.json()["id"])
    storage_key = await _storage_key(
        harness.session_factory,
        user_id=tenants.user_a,
        clinic_id=tenants.clinic_a,
        document_id=uploaded_id,
    )
    assert storage_key is not None

    # Cross-tenant mutation carrying the secrets must answer 404 without echo.
    foreign = await mutate(
        harness.client,
        "PATCH",
        f"/api/v1/clinics/{tenants.clinic_b}/patients/{isolated_m2.patient_b}",
        harness.token_a,
        {"full_name": secrets["name"], "cpf": secrets["cpf"]},
    )
    assert foreign.status_code == 404
    assert secrets["name"] not in foreign.text
    assert secrets["cpf"] not in foreign.text

    # Local validation failure must not echo the submitted values either.
    problem = await mutate(
        harness.client,
        "PATCH",
        created_url,
        harness.token_a,
        {"full_name": secrets["name"], "birth_date": "2999-01-01"},
    )
    assert problem.status_code == 422
    assert secrets["name"] not in problem.text
    assert problem.json()["title"] == "Dados inválidos"

    app_logs = "\n".join(
        # Only the application JSONL contract is under test; the test client's
        # own httpx INFO lines are harness output, not product logs.
        JsonLogFormatter("development").format(record)
        for record in caplog.records
        if record.name == "easydentist.api"
    )
    assert app_logs, "the exercised requests must produce access log events"
    for name, secret in {
        **secrets,
        "storage_key": storage_key,
        "patient_id": str(created_patient),
    }.items():
        assert secret not in app_logs, f"{name} leaked into application logs"

    audit_rows = await migrator_connection.fetch(
        "SELECT event_type, metadata FROM app.clinic_audit_events "
        "WHERE clinic_id = ANY($1::uuid[])",
        [tenants.clinic_a, tenants.clinic_b],
    )
    audit_text = json.dumps([dict(row) for row in audit_rows], default=str)
    for name, secret in {**secrets, "storage_key": storage_key}.items():
        assert secret not in audit_text, f"{name} leaked into clinic audit"

    assert {"anamnesis.created", "anamnesis.finalized", "document.created"} <= {
        row["event_type"] for row in audit_rows
    }
    for row in audit_rows:
        metadata = json.loads(row["metadata"])
        allowed = CLINIC_EVENT_METADATA_ALLOWLIST.get(row["event_type"], frozenset())
        assert set(metadata) <= allowed, row["event_type"]
        for forbidden in ("cpf", "payload", "title", "original_filename", "sha256", "storage_key"):
            assert forbidden not in metadata, row["event_type"]
