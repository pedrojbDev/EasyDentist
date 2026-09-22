from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import BinaryIO

import asyncpg
import boto3
import httpx
import pytest
from conftest import make_test_email
from fastapi import FastAPI
from helpers import (
    insert_clinic,
    insert_clinic_settings,
    insert_membership,
    insert_patient,
    insert_patient_document,
)
from sqlalchemy.exc import IntegrityError

from app.application import create_app
from app.clinics.rbac import Role
from app.core.errors import StorageUnavailableError
from app.documents.repositories import DocumentRepository
from app.documents.routers import get_object_storage
from app.platform.storage import ObjectStorage

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"
BUCKET = "easydentist"
TEN_MEGABYTES = 10 * 1024 * 1024

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"\x00" * 64
TEXT_BYTES = b"conteudo clinico que nao e um documento aceito"

SECRET_TITLE = "TITULO-CONFIDENCIAL"
SECRET_FILENAME = "nome-do-paciente-segredo.pdf"


@dataclass(frozen=True, slots=True)
class Teammate:
    email: str
    user_id: uuid.UUID
    membership_id: uuid.UUID


@dataclass
class DocumentScenario:
    clinic_id: uuid.UUID
    foreign_clinic_id: uuid.UUID
    members: dict[Role, Teammate] = field(default_factory=dict)
    patient_id: uuid.UUID = uuid.UUID(int=0)
    foreign_patient_id: uuid.UUID = uuid.UUID(int=0)


@dataclass
class DocumentHarness:
    client: httpx.AsyncClient
    app: FastAPI
    scenario: DocumentScenario
    prefix: str
    s3: object


def _use_storage(harness: DocumentHarness, storage: ObjectStorage) -> None:
    harness.app.dependency_overrides[get_object_storage] = lambda: storage


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


async def read(client: httpx.AsyncClient, url: str, token: str) -> httpx.Response:
    response = await client.get(url, headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    client.cookies.clear()
    return response


async def upload(
    client: httpx.AsyncClient,
    token: str,
    scenario: DocumentScenario,
    *,
    patient_id: uuid.UUID | None = None,
    category: str = "CLINICAL",
    title: str = "Documento de teste",
    filename: str = SECRET_FILENAME,
    data: bytes = PDF_BYTES,
    media_type: str = "application/octet-stream",
) -> httpx.Response:
    csrf = await csrf_token(client, token)
    response = await client.post(
        documents_url(scenario, patient_id),
        data={"title": title, "category": category},
        files={"file": (filename, data, media_type)},
        headers={
            "Cookie": f"{SESSION_COOKIE}={token}; {CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


def clinic_url(scenario: DocumentScenario, clinic_id: uuid.UUID | None = None) -> str:
    return f"/api/v1/clinics/{clinic_id if clinic_id is not None else scenario.clinic_id}"


def documents_url(
    scenario: DocumentScenario,
    patient_id: uuid.UUID | None = None,
    clinic_id: uuid.UUID | None = None,
) -> str:
    target = patient_id if patient_id is not None else scenario.patient_id
    return f"{clinic_url(scenario, clinic_id)}/patients/{target}/documents"


def document_url(
    scenario: DocumentScenario,
    document_id: uuid.UUID,
    patient_id: uuid.UUID | None = None,
    clinic_id: uuid.UUID | None = None,
) -> str:
    return f"{documents_url(scenario, patient_id, clinic_id)}/{document_id}"


class RecordingStorage:
    """Delegates to the real adapter while recording the calls it receives."""

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


class MemoryStorage:
    """Network-free storage double used to prove compensation and 503 paths."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def put(self, key: str, file_object: BinaryIO, *, content_type: str) -> None:
        self.objects[key] = file_object.read()

    async def stream(self, key: str):
        raise AssertionError("stream must not be called in this scenario")

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.objects.pop(key, None)

    async def verify(self, key: str) -> bool:
        return key in self.objects


class FailingStorage(MemoryStorage):
    async def put(self, key: str, file_object: BinaryIO, *, content_type: str) -> None:
        raise StorageUnavailableError("storage is unavailable")


@pytest.fixture
async def document_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[DocumentScenario]:
    built = DocumentScenario(clinic_id=uuid.UUID(int=0), foreign_clinic_id=uuid.UUID(int=0))
    suffix = uuid.uuid4().hex[:10]
    built.clinic_id = await insert_clinic(migrator_connection, f"documents-{suffix}")
    built.foreign_clinic_id = await insert_clinic(
        migrator_connection, f"documents-foreign-{suffix}"
    )
    provisioned_clinics.extend([built.clinic_id, built.foreign_clinic_id])
    await insert_clinic_settings(migrator_connection, built.clinic_id)

    for role in Role:
        email = make_test_email(f"documents-{role.value.lower()}")
        user_id = await seed_user_with_password(email=email, password=PASSWORD)
        membership_id = await insert_membership(
            migrator_connection,
            clinic_id=built.clinic_id,
            user_id=user_id,
            role=role.value,
            status="ACTIVE",
        )
        built.members[role] = Teammate(email=email, user_id=user_id, membership_id=membership_id)

    foreign_email = make_test_email("documents-foreign-owner")
    foreign_user_id = await seed_user_with_password(email=foreign_email, password=PASSWORD)
    await insert_membership(
        migrator_connection,
        clinic_id=built.foreign_clinic_id,
        user_id=foreign_user_id,
        role="OWNER",
        status="ACTIVE",
    )

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

    try:
        yield built
    finally:
        clinic_ids = [built.clinic_id, built.foreign_clinic_id]
        await migrator_connection.execute(
            "DELETE FROM app.patient_documents WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.patients WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.professional_profiles WHERE user_id = $1",
            built.members[Role.OWNER].user_id,
        )


def required_s3_environment() -> dict[str, str]:
    names = ("S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET")
    values = {name: os.environ.get(name, "") for name in names}
    if not all(values.values()):
        pytest.skip("S3_ENDPOINT_URL/S3_ACCESS_KEY/S3_SECRET_KEY/S3_BUCKET are required")
    return values


@pytest.fixture
async def documents(
    app_async_url: str,
    monkeypatch: pytest.MonkeyPatch,
    email_sender,
    document_scenario: DocumentScenario,
) -> AsyncIterator[DocumentHarness]:
    environment = required_s3_environment()
    prefix = f"test-documents/{uuid.uuid4().hex}/"
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
            try:
                yield DocumentHarness(
                    client=client,
                    app=app,
                    scenario=document_scenario,
                    prefix=prefix,
                    s3=s3,
                )
            finally:
                app.dependency_overrides.clear()
                delete_prefixed(s3, prefix)


async def owner_token(client: httpx.AsyncClient, scenario: DocumentScenario) -> str:
    return await login(client, scenario.members[Role.OWNER].email)


async def stored_storage_key(connection: asyncpg.Connection, document_id: str) -> str | None:
    return await connection.fetchval(
        "SELECT storage_key FROM app.patient_documents WHERE id = $1", uuid.UUID(document_id)
    )


async def document_count(connection: asyncpg.Connection, clinic_id: uuid.UUID) -> int:
    return int(
        await connection.fetchval(
            "SELECT count(*) FROM app.patient_documents WHERE clinic_id = $1", clinic_id
        )
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_upload_pdf_stores_the_private_object_and_returns_metadata(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    response = await upload(
        harness.client,
        token,
        scenario,
        category="CLINICAL",
        title="  Receita controlada  ",
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["clinic_id"] == str(scenario.clinic_id)
    assert body["patient_id"] == str(scenario.patient_id)
    assert body["category"] == "CLINICAL"
    assert body["title"] == "Receita controlada"
    assert body["original_filename"] == SECRET_FILENAME
    assert body["detected_mime"] == "application/pdf"
    assert body["size_bytes"] == len(PDF_BYTES)
    assert body["sha256"] == hashlib.sha256(PDF_BYTES).hexdigest()
    assert body["status"] == "ACTIVE"
    assert body["archived_at"] is None
    assert body["uploaded_by_user_id"] == str(scenario.members[Role.OWNER].user_id)
    assert "storage_key" not in body

    key = await stored_storage_key(migrator_connection, body["id"])
    assert key is not None
    assert key.isalnum()
    assert SECRET_FILENAME not in key
    assert "Ana" not in key
    full_key = f"{harness.prefix}{key}"
    assert list_prefixed(harness.s3, harness.prefix) == [full_key]
    stored = harness.s3.get_object(Bucket=BUCKET, Key=full_key)["Body"].read()
    assert stored == PDF_BYTES


@pytest.mark.anyio
async def test_download_serves_content_as_attachment_with_detected_mime(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    created = await upload(harness.client, token, scenario, filename='laudo "especial".pdf')
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    response = await read(
        harness.client, f"{document_url(scenario, uuid.UUID(document_id))}/content", token
    )

    assert response.status_code == 200, response.text
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["cache-control"] == "private, no-store"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "\r" not in disposition and "\n" not in disposition


@pytest.mark.anyio
async def test_download_encodes_unicode_filename_in_content_disposition(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    created = await upload(harness.client, token, scenario, filename="laudo-çãó.pdf")
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]

    response = await read(
        harness.client, f"{document_url(scenario, uuid.UUID(document_id))}/content", token
    )

    assert response.status_code == 200
    assert "filename*=UTF-8''" in response.headers["content-disposition"]


@pytest.mark.anyio
async def test_download_missing_object_is_not_found(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    created = await upload(harness.client, token, scenario)
    assert created.status_code == 201, created.text
    body = created.json()
    key = await stored_storage_key(migrator_connection, body["id"])
    assert key is not None
    harness.s3.delete_object(Bucket=BUCKET, Key=f"{harness.prefix}{key}")

    response = await read(
        harness.client, f"{document_url(scenario, uuid.UUID(body['id']))}/content", token
    )

    assert response.status_code == 404, response.text
    assert response.json()["title"] == "Recurso não encontrado"
    assert SECRET_FILENAME not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("data", "expected_mime"),
    [(JPEG_BYTES, "image/jpeg"), (PNG_BYTES, "image/png")],
)
async def test_upload_accepts_jpeg_and_png(
    documents: DocumentHarness, data: bytes, expected_mime: str
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    response = await upload(harness.client, token, scenario, data=data, filename="imagem.bin")

    assert response.status_code == 201, response.text
    assert response.json()["detected_mime"] == expected_mime


@pytest.mark.anyio
async def test_upload_ignores_the_client_supplied_content_type(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    response = await upload(
        harness.client, token, scenario, media_type="text/html", filename="pagina.pdf"
    )

    assert response.status_code == 201, response.text
    assert response.json()["detected_mime"] == "application/pdf"


@pytest.mark.anyio
async def test_upload_rejects_forged_magic_bytes_without_persisting(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    response = await upload(harness.client, token, scenario, data=TEXT_BYTES, filename="falso.pdf")

    assert response.status_code == 415, response.text
    assert response.json()["title"] == "Formato não suportado"
    assert TEXT_BYTES.decode() not in response.text
    assert await document_count(migrator_connection, scenario.clinic_id) == 0
    assert list_prefixed(harness.s3, harness.prefix) == []


@pytest.mark.anyio
async def test_upload_rejects_an_empty_file(
    documents: DocumentHarness, migrator_connection: asyncpg.Connection
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    response = await upload(harness.client, token, scenario, data=b"")

    assert response.status_code == 415, response.text
    assert await document_count(migrator_connection, scenario.clinic_id) == 0
    assert list_prefixed(harness.s3, harness.prefix) == []


@pytest.mark.anyio
async def test_upload_accepts_exactly_ten_megabytes(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    payload = b"%PDF-" + b"a" * (TEN_MEGABYTES - 5)

    response = await upload(harness.client, token, scenario, data=payload)

    assert response.status_code == 201, response.text
    assert response.json()["size_bytes"] == TEN_MEGABYTES


@pytest.mark.anyio
async def test_upload_rejects_more_than_ten_megabytes(
    documents: DocumentHarness, migrator_connection: asyncpg.Connection
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    payload = b"%PDF-" + b"a" * (TEN_MEGABYTES - 4)

    response = await upload(harness.client, token, scenario, data=payload)

    assert response.status_code == 413, response.text
    assert response.json()["title"] == "Arquivo muito grande"
    assert await document_count(migrator_connection, scenario.clinic_id) == 0
    assert list_prefixed(harness.s3, harness.prefix) == []


@pytest.mark.anyio
async def test_upload_rejects_blank_title(documents: DocumentHarness) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    blank = await upload(harness.client, token, scenario, title="   ")
    empty = await upload(harness.client, token, scenario, title="")

    assert blank.status_code == 422, blank.text
    assert empty.status_code == 422, empty.text


@pytest.mark.anyio
async def test_upload_unknown_or_foreign_patient_is_not_found(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)

    unknown = await upload(harness.client, token, scenario, patient_id=uuid.uuid4())
    foreign = await upload(
        harness.client,
        token,
        scenario,
        patient_id=scenario.foreign_patient_id,
    )

    assert unknown.status_code == 404, unknown.text
    assert foreign.status_code == 404, foreign.text
    assert list_prefixed(harness.s3, harness.prefix) == []


@pytest.mark.anyio
async def test_s3_failure_returns_503_without_active_metadata(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    _use_storage(harness, FailingStorage())

    response = await upload(harness.client, token, scenario)

    assert response.status_code == 503, response.text
    assert response.json()["title"] == "Serviço indisponível"
    assert await document_count(migrator_connection, scenario.clinic_id) == 0
    assert list_prefixed(harness.s3, harness.prefix) == []


@pytest.mark.anyio
async def test_metadata_failure_compensates_the_uploaded_object(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    memory = MemoryStorage()
    _use_storage(harness, memory)

    async def failing_add(self: object, *args: object, **kwargs: object) -> object:
        raise IntegrityError("INSERT INTO app.patient_documents", {}, Exception("boom"))

    monkeypatch.setattr(DocumentRepository, "add", failing_add)

    response = await upload(harness.client, token, scenario)

    assert response.status_code == 500, response.text
    assert memory.objects == {}
    assert len(memory.deleted) == 1
    assert await document_count(migrator_connection, scenario.clinic_id) == 0


# ---------------------------------------------------------------------------
# Listing, filters and archival
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_filters_by_category_status_and_paginates(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    admin_doc = await upload(harness.client, token, scenario, category="ADMINISTRATIVE")
    clinical_doc = await upload(harness.client, token, scenario, category="CLINICAL")
    assert admin_doc.status_code == 201 and clinical_doc.status_code == 201
    clinical_id = uuid.UUID(clinical_doc.json()["id"])
    assert (
        await mutate(
            harness.client, "POST", f"{document_url(scenario, clinical_id)}/archive", token
        )
    ).status_code == 200

    all_active = await read(harness.client, f"{documents_url(scenario)}?limit=10", token)
    clinical = await read(harness.client, f"{documents_url(scenario)}?category=CLINICAL", token)
    archived = await read(harness.client, f"{documents_url(scenario)}?status=ARCHIVED", token)
    page = await read(harness.client, f"{documents_url(scenario)}?limit=1&offset=0", token)
    invalid = await read(harness.client, f"{documents_url(scenario)}?category=OTHER", token)

    assert all_active.status_code == 200, all_active.text
    assert all_active.json()["total"] == 1
    assert all_active.json()["items"][0]["category"] == "ADMINISTRATIVE"
    assert all_active.json()["limit"] == 10
    assert clinical.status_code == 200
    assert clinical.json()["total"] == 0
    assert archived.status_code == 200
    assert archived.json()["total"] == 1
    assert archived.json()["items"][0]["id"] == str(clinical_id)
    assert page.status_code == 200
    assert page.json()["total"] == 1
    assert len(page.json()["items"]) == 1
    assert invalid.status_code == 422


@pytest.mark.anyio
async def test_archived_document_stays_directly_accessible_and_restorable(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    created = await upload(harness.client, token, scenario)
    document_id = uuid.UUID(created.json()["id"])

    archived = await mutate(
        harness.client, "POST", f"{document_url(scenario, document_id)}/archive", token
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "ARCHIVED"
    assert archived.json()["archived_at"] is not None

    still_there = await read(harness.client, document_url(scenario, document_id), token)
    hidden = await read(harness.client, documents_url(scenario), token)
    content = await read(harness.client, f"{document_url(scenario, document_id)}/content", token)
    assert still_there.status_code == 200
    assert hidden.json()["total"] == 0
    assert content.status_code == 200

    again = await mutate(
        harness.client, "POST", f"{document_url(scenario, document_id)}/archive", token
    )
    assert again.status_code == 200
    assert again.json()["archived_at"] == archived.json()["archived_at"]

    restored = await mutate(
        harness.client, "POST", f"{document_url(scenario, document_id)}/restore", token
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "ACTIVE"
    assert restored.json()["archived_at"] is None
    visible = await read(harness.client, documents_url(scenario), token)
    assert visible.json()["total"] == 1


# ---------------------------------------------------------------------------
# RBAC, isolation and redaction
# ---------------------------------------------------------------------------


DOCUMENT_OPERATION_EXPECTATIONS: dict[str, dict[Role, int]] = {
    "list": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 200,
    },
    "get-administrative": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 200,
    },
    "get-clinical": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 403,
    },
    "content-administrative": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 200,
    },
    "content-clinical": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 200,
        Role.RECEPTIONIST: 403,
    },
    "upload-administrative": {
        Role.OWNER: 201,
        Role.ADMIN: 201,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 201,
    },
    "upload-clinical": {
        Role.OWNER: 201,
        Role.ADMIN: 403,
        Role.DENTIST: 201,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "archive-administrative": {
        Role.OWNER: 200,
        Role.ADMIN: 200,
        Role.DENTIST: 403,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 200,
    },
    "archive-clinical": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
    "restore-clinical": {
        Role.OWNER: 200,
        Role.ADMIN: 403,
        Role.DENTIST: 200,
        Role.ASSISTANT: 403,
        Role.RECEPTIONIST: 403,
    },
}


@pytest.mark.anyio
@pytest.mark.parametrize("operation", list(DOCUMENT_OPERATION_EXPECTATIONS))
async def test_role_matrix_on_document_endpoints(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
    operation: str,
) -> None:
    harness = documents
    scenario = harness.scenario
    for role in Role:
        patient = await insert_patient(
            migrator_connection,
            clinic_id=scenario.clinic_id,
            full_name=f"Paciente {operation} {role.value}",
            phone="+5571900000000",
        )
        administrative_key = uuid.uuid4().hex
        clinical_key = uuid.uuid4().hex
        administrative = await insert_patient_document(
            migrator_connection,
            clinic_id=scenario.clinic_id,
            patient_id=patient,
            uploaded_by_user_id=scenario.members[role].user_id,
            category="ADMINISTRATIVE",
            storage_key=administrative_key,
        )
        clinical = await insert_patient_document(
            migrator_connection,
            clinic_id=scenario.clinic_id,
            patient_id=patient,
            uploaded_by_user_id=scenario.members[role].user_id,
            category="CLINICAL",
            status="ARCHIVED",
            archived_at=datetime.now(UTC),
            storage_key=clinical_key,
        )
        if operation.startswith("content-"):
            for key in (administrative_key, clinical_key):
                harness.s3.put_object(Bucket=BUCKET, Key=f"{harness.prefix}{key}", Body=PDF_BYTES)
        token = await login(harness.client, scenario.members[role].email)
        if operation == "list":
            response = await read(harness.client, documents_url(scenario, patient), token)
        elif operation.startswith("get-"):
            target = administrative if operation.endswith("administrative") else clinical
            response = await read(harness.client, document_url(scenario, target, patient), token)
        elif operation.startswith("content-"):
            target = administrative if operation.endswith("administrative") else clinical
            response = await read(
                harness.client, f"{document_url(scenario, target, patient)}/content", token
            )
        elif operation.startswith("upload-"):
            category = "ADMINISTRATIVE" if operation.endswith("administrative") else "CLINICAL"
            response = await upload(
                harness.client, token, scenario, patient_id=patient, category=category
            )
        elif operation.startswith("archive-"):
            target = administrative if operation.endswith("administrative") else clinical
            response = await mutate(
                harness.client,
                "POST",
                f"{document_url(scenario, target, patient)}/archive",
                token,
            )
        else:
            response = await mutate(
                harness.client,
                "POST",
                f"{document_url(scenario, clinical, patient)}/restore",
                token,
            )
        assert response.status_code == DOCUMENT_OPERATION_EXPECTATIONS[operation][role], (
            operation,
            role,
            response.text,
        )
        if operation.startswith("content-") and response.status_code == 200:
            assert response.content == PDF_BYTES


@pytest.mark.anyio
async def test_administrative_roles_never_receive_clinical_documents(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    clinical = await insert_patient_document(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        patient_id=scenario.patient_id,
        uploaded_by_user_id=scenario.members[Role.OWNER].user_id,
        category="CLINICAL",
        title=SECRET_TITLE,
        original_filename=SECRET_FILENAME,
    )

    for role in (Role.ADMIN, Role.RECEPTIONIST):
        token = await login(harness.client, scenario.members[role].email)
        listing = await read(harness.client, documents_url(scenario), token)
        explicit = await read(harness.client, f"{documents_url(scenario)}?category=CLINICAL", token)
        metadata = await read(harness.client, document_url(scenario, clinical), token)
        content = await read(harness.client, f"{document_url(scenario, clinical)}/content", token)
        archived = await mutate(
            harness.client, "POST", f"{document_url(scenario, clinical)}/archive", token
        )

        assert listing.status_code == 200
        assert listing.json()["total"] == 0
        for response in (explicit, metadata, content, archived):
            assert response.status_code == 403, (role, response.text)
            assert SECRET_TITLE not in response.text
            assert SECRET_FILENAME not in response.text
            assert "Conteúdo" not in response.text


@pytest.mark.anyio
async def test_content_authorization_happens_before_storage_access(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    owner = await owner_token(harness.client, scenario)
    created = await upload(harness.client, owner, scenario, category="CLINICAL")
    assert created.status_code == 201, created.text
    clinical = uuid.UUID(created.json()["id"])
    recording = RecordingStorage(harness.app.state.object_storage)
    _use_storage(harness, recording)

    admin_token = await login(harness.client, scenario.members[Role.ADMIN].email)
    denied = await read(harness.client, f"{document_url(scenario, clinical)}/content", admin_token)
    dentist_token = await login(harness.client, scenario.members[Role.DENTIST].email)
    allowed = await read(
        harness.client, f"{document_url(scenario, clinical)}/content", dentist_token
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert recording.stream_calls == 1


@pytest.mark.anyio
async def test_role_without_storage_access_does_not_reach_the_backend(
    documents: DocumentHarness,
) -> None:
    harness = documents
    scenario = harness.scenario
    recording = RecordingStorage(harness.app.state.object_storage)
    _use_storage(harness, recording)
    admin = await login(harness.client, scenario.members[Role.ADMIN].email)

    response = await upload(harness.client, admin, scenario, category="CLINICAL", data=PDF_BYTES)

    assert response.status_code == 403, response.text
    assert recording.puts == []


@pytest.mark.anyio
async def test_cross_tenant_documents_and_patients_are_not_found(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    foreign = await insert_patient_document(
        migrator_connection,
        clinic_id=scenario.foreign_clinic_id,
        patient_id=scenario.foreign_patient_id,
        uploaded_by_user_id=scenario.members[Role.OWNER].user_id,
        category="ADMINISTRATIVE",
    )

    responses = [
        await read(
            harness.client,
            documents_url(scenario, scenario.foreign_patient_id, scenario.foreign_clinic_id),
            token,
        ),
        await read(harness.client, documents_url(scenario, scenario.foreign_patient_id), token),
        await read(
            harness.client,
            document_url(
                scenario, foreign, scenario.foreign_patient_id, scenario.foreign_clinic_id
            ),
            token,
        ),
        await read(harness.client, f"{document_url(scenario, foreign)}/content", token),
        await mutate(harness.client, "POST", f"{document_url(scenario, foreign)}/archive", token),
        await mutate(harness.client, "POST", f"{document_url(scenario, foreign)}/restore", token),
        await upload(harness.client, token, scenario, patient_id=scenario.foreign_patient_id),
    ]

    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["title"] == "Recurso não encontrado"


@pytest.mark.anyio
async def test_audit_keeps_only_ids_category_and_state(
    documents: DocumentHarness,
    migrator_connection: asyncpg.Connection,
) -> None:
    harness = documents
    scenario = harness.scenario
    token = await owner_token(harness.client, scenario)
    created = await upload(
        harness.client,
        token,
        scenario,
        title=SECRET_TITLE,
        filename=SECRET_FILENAME,
    )
    assert created.status_code == 201, created.text
    document_id = created.json()["id"]
    key = await stored_storage_key(migrator_connection, document_id)
    checksum = created.json()["sha256"]

    assert (
        await mutate(
            harness.client,
            "POST",
            f"{document_url(scenario, uuid.UUID(document_id))}/archive",
            token,
        )
    ).status_code == 200
    assert (
        await mutate(
            harness.client,
            "POST",
            f"{document_url(scenario, uuid.UUID(document_id))}/restore",
            token,
        )
    ).status_code == 200

    rows = await migrator_connection.fetch(
        "SELECT event_type, entity_type, entity_id, metadata FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type LIKE 'document%'",
        scenario.clinic_id,
    )
    event_types = {row["event_type"] for row in rows}
    assert event_types == {"document.created", "document.archived", "document.restored"}
    for row in rows:
        assert row["entity_type"] == "patient_document"
        assert row["entity_id"] == uuid.UUID(document_id)
        metadata = json.loads(row["metadata"])
        assert set(metadata) <= {"patient_id", "category", "status"}

    serialized = json.dumps([dict(row) for row in rows], default=str)
    assert SECRET_TITLE not in serialized
    assert SECRET_FILENAME not in serialized
    assert checksum not in serialized
    assert key is not None and key not in serialized
