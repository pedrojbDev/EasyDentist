from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

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
