from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import asyncpg


async def insert_user(connection: asyncpg.Connection, email: str) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.users (email) VALUES ($1) RETURNING id",
        email,
    )


async def insert_clinic(
    connection: asyncpg.Connection,
    slug: str,
    *,
    legal_name: str | None = None,
    status: str = "ACTIVE",
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.clinics (slug, legal_name, status) VALUES ($1, $2, $3) RETURNING id",
        slug,
        legal_name if legal_name is not None else slug,
        status,
    )


async def insert_clinic_settings(connection: asyncpg.Connection, clinic_id: uuid.UUID) -> None:
    await connection.execute(
        "INSERT INTO app.clinic_settings (clinic_id, display_name) VALUES ($1, $2)",
        clinic_id,
        f"Clinic {clinic_id}",
    )


async def insert_membership(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "OWNER",
    status: str = "ACTIVE",
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.memberships (clinic_id, user_id, role, status) "
        "VALUES ($1, $2, $3, $4) RETURNING id",
        clinic_id,
        user_id,
        role,
        status,
    )


async def insert_invitation(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    membership_id: uuid.UUID,
    email: str,
    token_hash: bytes = b"invitation-token-hash",
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.membership_invitations "
        "(clinic_id, membership_id, email, token_hash, expires_at) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id",
        clinic_id,
        membership_id,
        email,
        token_hash,
        datetime.now(UTC) + timedelta(hours=72),
    )


async def insert_professional_profile(
    connection: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    professional_name: str = "Dra. Teste",
    cro_number: str = "12345",
    cro_state: str = "BA",
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.professional_profiles "
        "(user_id, professional_name, cro_number, cro_state) "
        "VALUES ($1, $2, $3, $4) RETURNING user_id",
        user_id,
        professional_name,
        cro_number,
        cro_state,
    )


async def insert_patient(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    full_name: str = "Paciente de Teste",
    birth_date: date = date(1990, 1, 1),
    phone: str = "+5571900000000",
    cpf: str | None = None,
    emergency_contact_name: str | None = None,
    emergency_contact_relationship: str | None = None,
    emergency_contact_phone: str | None = None,
    status: str = "ACTIVE",
    archived_at: datetime | None = None,
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.patients "
        "(clinic_id, full_name, birth_date, phone, cpf, emergency_contact_name, "
        "emergency_contact_relationship, emergency_contact_phone, status, archived_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id",
        clinic_id,
        full_name,
        birth_date,
        phone,
        cpf,
        emergency_contact_name,
        emergency_contact_relationship,
        emergency_contact_phone,
        status,
        archived_at,
    )


async def insert_patient_alert(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    kind: str = "ALLERGY",
    description: str = "Alergia a dipirona",
    status: str = "ACTIVE",
    resolved_at: datetime | None = None,
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.patient_alerts "
        "(clinic_id, patient_id, kind, description, status, resolved_at, created_by_user_id) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id",
        clinic_id,
        patient_id,
        kind,
        description,
        status,
        resolved_at,
        created_by_user_id,
    )


async def insert_anamnesis(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    author_user_id: uuid.UUID,
    status: str = "DRAFT",
    version_number: int | None = None,
    template: str = "cfo_2026_v1",
    payload: dict[str, object] | None = None,
    base_version_id: uuid.UUID | None = None,
    author_professional_name: str | None = None,
    author_cro_number: str | None = None,
    author_cro_state: str | None = None,
    finalized_at: datetime | None = None,
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.anamneses "
        "(clinic_id, patient_id, status, version_number, template, payload, base_version_id, "
        "author_user_id, author_professional_name, author_cro_number, author_cro_state, "
        "finalized_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id",
        clinic_id,
        patient_id,
        status,
        version_number,
        template,
        json.dumps(payload if payload is not None else {}),
        base_version_id,
        author_user_id,
        author_professional_name,
        author_cro_number,
        author_cro_state,
        finalized_at,
    )


async def insert_patient_document(
    connection: asyncpg.Connection,
    *,
    clinic_id: uuid.UUID,
    patient_id: uuid.UUID,
    uploaded_by_user_id: uuid.UUID,
    category: str = "CLINICAL",
    title: str = "Documento de Teste",
    original_filename: str = "documento.pdf",
    detected_mime: str = "application/pdf",
    size_bytes: int = 1024,
    sha256: str = "a" * 64,
    storage_key: str | None = None,
    status: str = "ACTIVE",
    archived_at: datetime | None = None,
) -> uuid.UUID:
    return await connection.fetchval(
        "INSERT INTO app.patient_documents "
        "(clinic_id, patient_id, category, title, original_filename, detected_mime, "
        "size_bytes, sha256, storage_key, uploaded_by_user_id, status, archived_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) RETURNING id",
        clinic_id,
        patient_id,
        category,
        title,
        original_filename,
        detected_mime,
        size_bytes,
        sha256,
        storage_key if storage_key is not None else uuid.uuid4().hex,
        uploaded_by_user_id,
        status,
        archived_at,
    )
