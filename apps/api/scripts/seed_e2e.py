"""Deterministic E2E fixtures created through the migration connection.

The seed never uses the runtime role: clinic and membership writes are reserved
to the migration role by the RLS design, so the migration DSN is the only
credential that can build tenants directly. Every row is namespaced with the
run identifier and removed by ``--cleanup`` (or ``global-teardown.ts``).

Documents written by the E2E API live under ``e2e/{run_id}/`` in the private
bucket (see the Compose ``S3_KEY_PREFIX``). Cleanup removes exactly that prefix
and verifies that no object survives before deleting the run rows; final
anamneses are immutable, so the maintenance connection disables the user
triggers only for the cleanup statement and restores them afterwards.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.auth.passwords import PasswordHasher
from app.auth.settings import AuthSettings
from app.platform.s3_storage import StorageSettings

MANIFEST_PREFIX = "E2E_MANIFEST "
DEFAULT_TIMEZONE = "America/Bahia"
DEFAULT_LOCALE = "pt-BR"
DEFAULT_CURRENCY = "BRL"
E2E_STORAGE_ROOT = "e2e"
DELETE_BATCH_SIZE = 1000
RUN_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")

PATIENT_A_CPF = "52998224725"
PROFESSIONAL_PROFILE = {
    "professional_name": "Dra. E2E Profissional",
    "cro_number": "12345",
    "cro_state": "BA",
}


def _new_password() -> str:
    return secrets.token_urlsafe(18)


def _new_run_id() -> str:
    return secrets.token_hex(6)


def _new_id() -> uuid.UUID:
    return uuid.uuid4()


def _sentinel(run_id: str, label: str) -> str:
    return f"SENTINELA-{label}-{run_id.upper()}"


def _email(run_id: str, name: str) -> str:
    return f"e2e-{run_id}-{name}@example.com"


async def _insert_clinic(
    connection: AsyncConnection,
    *,
    clinic_id: uuid.UUID,
    slug: str,
    legal_name: str,
    display_name: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO app.clinics (id, slug, legal_name, status) "
            "VALUES (:id, :slug, :legal_name, 'ACTIVE')"
        ),
        {"id": clinic_id, "slug": slug, "legal_name": legal_name},
    )
    await connection.execute(
        text(
            "INSERT INTO app.clinic_settings "
            "(clinic_id, display_name, timezone, locale, currency) "
            "VALUES (:clinic_id, :display_name, :timezone, :locale, :currency)"
        ),
        {
            "clinic_id": clinic_id,
            "display_name": display_name,
            "timezone": DEFAULT_TIMEZONE,
            "locale": DEFAULT_LOCALE,
            "currency": DEFAULT_CURRENCY,
        },
    )


async def _insert_user(
    connection: AsyncConnection,
    *,
    user_id: uuid.UUID,
    email: str,
    password_hash: str,
    verified: bool,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO app.users (id, email, status, email_verified_at) "
            "VALUES (:id, :email, 'ACTIVE', :email_verified_at)"
        ),
        {
            "id": user_id,
            "email": email,
            "email_verified_at": datetime.now(UTC) if verified else None,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO app.password_credentials (user_id, password_hash, changed_at) "
            "VALUES (:user_id, :password_hash, now())"
        ),
        {"user_id": user_id, "password_hash": password_hash},
    )


async def _insert_membership(
    connection: AsyncConnection,
    *,
    clinic_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
) -> str:
    membership_id = _new_id()
    await connection.execute(
        text(
            "INSERT INTO app.memberships (id, clinic_id, user_id, role, status) "
            "VALUES (:id, :clinic_id, :user_id, :role, 'ACTIVE')"
        ),
        {
            "id": membership_id,
            "clinic_id": clinic_id,
            "user_id": user_id,
            "role": role,
        },
    )
    return str(membership_id)


async def _insert_patient(
    connection: AsyncConnection,
    *,
    clinic_id: uuid.UUID,
    full_name: str,
    birth_date: date,
    phone: str,
    cpf: str | None = None,
) -> uuid.UUID:
    patient_id: uuid.UUID = await connection.scalar(
        text(
            "INSERT INTO app.patients (clinic_id, full_name, birth_date, phone, cpf) "
            "VALUES (:clinic_id, :full_name, :birth_date, :phone, :cpf) RETURNING id"
        ),
        {
            "clinic_id": clinic_id,
            "full_name": full_name,
            "birth_date": birth_date,
            "phone": phone,
            "cpf": cpf,
        },
    )
    return patient_id


async def _insert_professional_profile(
    connection: AsyncConnection,
    *,
    user_id: uuid.UUID,
    professional_name: str,
    cro_number: str,
    cro_state: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO app.professional_profiles "
            "(user_id, professional_name, cro_number, cro_state) "
            "VALUES (:user_id, :professional_name, :cro_number, :cro_state)"
        ),
        {
            "user_id": user_id,
            "professional_name": professional_name,
            "cro_number": cro_number,
            "cro_state": cro_state,
        },
    )


async def _seed(connection: AsyncConnection, run_id: str) -> dict[str, Any]:
    password = _new_password()
    password_hash = PasswordHasher(AuthSettings.from_environment()).hash(password)

    clinic_a_id = _new_id()
    clinic_b_id = _new_id()
    clinic_a_slug = f"e2e-{run_id}-clinica-a"
    clinic_b_slug = f"e2e-{run_id}-clinica-b"
    clinic_a_sentinel = _sentinel(run_id, "A")
    clinic_b_sentinel = _sentinel(run_id, "B")
    clinic_a_name = f"Clínica A {clinic_a_sentinel}"
    clinic_b_name = f"Clínica B {clinic_b_sentinel}"
    await _insert_clinic(
        connection,
        clinic_id=clinic_a_id,
        slug=clinic_a_slug,
        legal_name=clinic_a_name,
        display_name=clinic_a_name,
    )
    await _insert_clinic(
        connection,
        clinic_id=clinic_b_id,
        slug=clinic_b_slug,
        legal_name=clinic_b_name,
        display_name=clinic_b_name,
    )

    users: dict[str, dict[str, Any]] = {}
    definitions = (
        ("multi", True),
        ("clinic-a", True),
        ("clinic-b", True),
        ("unverified", False),
        ("recovery", True),
        # Administrative role without clinical read: proves the restricted
        # panels and the forbidden clinical document category in the E2E specs.
        ("admin", True),
    )
    for name, verified in definitions:
        user_id = _new_id()
        email = _email(run_id, name)
        await _insert_user(
            connection,
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            verified=verified,
        )
        users[name] = {"id": str(user_id), "email": email, "password": password}

    memberships = {
        "multi_clinic_a": await _insert_membership(
            connection,
            clinic_id=clinic_a_id,
            user_id=uuid.UUID(users["multi"]["id"]),
            role="OWNER",
        ),
        "multi_clinic_b": await _insert_membership(
            connection,
            clinic_id=clinic_b_id,
            user_id=uuid.UUID(users["multi"]["id"]),
            role="DENTIST",
        ),
        "clinic_a": await _insert_membership(
            connection,
            clinic_id=clinic_a_id,
            user_id=uuid.UUID(users["clinic-a"]["id"]),
            role="DENTIST",
        ),
        "clinic_b": await _insert_membership(
            connection,
            clinic_id=clinic_b_id,
            user_id=uuid.UUID(users["clinic-b"]["id"]),
            role="DENTIST",
        ),
        "unverified": await _insert_membership(
            connection,
            clinic_id=clinic_a_id,
            user_id=uuid.UUID(users["unverified"]["id"]),
            role="ASSISTANT",
        ),
        "recovery": await _insert_membership(
            connection,
            clinic_id=clinic_a_id,
            user_id=uuid.UUID(users["recovery"]["id"]),
            role="RECEPTIONIST",
        ),
        "admin": await _insert_membership(
            connection,
            clinic_id=clinic_a_id,
            user_id=uuid.UUID(users["admin"]["id"]),
            role="ADMIN",
        ),
    }

    # Rate limit buckets are keyed by HMAC and cannot be attributed to a run;
    # the E2E environment starts with a clean throttle so repeated executions
    # are deterministic. This is local/test-only tooling.
    await connection.execute(text("DELETE FROM app.auth_rate_limit_buckets"))

    patient_a_sentinel = _sentinel(run_id, "PACIENTE-A")
    patient_b_sentinel = _sentinel(run_id, "PACIENTE-B")
    patient_a_name = f"Paciente A {patient_a_sentinel}"
    patient_b_name = f"Paciente B {patient_b_sentinel}"
    patient_a_id = await _insert_patient(
        connection,
        clinic_id=clinic_a_id,
        full_name=patient_a_name,
        birth_date=date(1990, 5, 6),
        phone="+5571999112222",
        cpf=PATIENT_A_CPF,
    )
    patient_b_id = await _insert_patient(
        connection,
        clinic_id=clinic_b_id,
        full_name=patient_b_name,
        birth_date=date(1985, 3, 4),
        phone="+5571988887777",
    )
    # The multi user is OWNER of clinic A and DENTIST of clinic B; the global
    # professional profile lets the anamnesis spec finalize in either clinic.
    await _insert_professional_profile(
        connection,
        user_id=uuid.UUID(users["multi"]["id"]),
        **PROFESSIONAL_PROFILE,
    )

    return {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "clinics": {
            "a": {
                "id": str(clinic_a_id),
                "slug": clinic_a_slug,
                "legal_name": clinic_a_name,
                "display_name": clinic_a_name,
                "sentinel": clinic_a_sentinel,
            },
            "b": {
                "id": str(clinic_b_id),
                "slug": clinic_b_slug,
                "legal_name": clinic_b_name,
                "display_name": clinic_b_name,
                "sentinel": clinic_b_sentinel,
            },
        },
        "users": users,
        "memberships": memberships,
        "patients": {
            "a": {
                "id": str(patient_a_id),
                "full_name": patient_a_name,
                "sentinel": patient_a_sentinel,
                "cpf": PATIENT_A_CPF,
            },
            "b": {
                "id": str(patient_b_id),
                "full_name": patient_b_name,
                "sentinel": patient_b_sentinel,
                "cpf": None,
            },
        },
        "professional_profile": dict(PROFESSIONAL_PROFILE),
    }


def _run_storage_prefix(run_id: str) -> str:
    return f"{E2E_STORAGE_ROOT}/{run_id}/"


def _create_s3_client(settings: StorageSettings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.endpoint_url,
        region_name=settings.region,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def _list_object_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        keys.extend(entry["Key"] for entry in page.get("Contents", []))
    return keys


def _delete_run_objects(run_id: str) -> None:
    """Delete every object under ``e2e/{run_id}/`` and verify the prefix is empty.

    Any failure propagates: the run must not report a successful teardown while
    an object of that run could still be reached. The database rows are only
    removed after this verification, so metadata never points at deleted
    objects after a partial cleanup.
    """

    settings = StorageSettings.from_environment()
    prefix = _run_storage_prefix(run_id)
    client = _create_s3_client(settings)
    keys = _list_object_keys(client, settings.bucket, prefix)
    for start in range(0, len(keys), DELETE_BATCH_SIZE):
        batch = keys[start : start + DELETE_BATCH_SIZE]
        client.delete_objects(
            Bucket=settings.bucket,
            Delete={"Objects": [{"Key": key} for key in batch]},
        )
    remaining = _list_object_keys(client, settings.bucket, prefix)
    if remaining:
        raise RuntimeError(f"storage cleanup left {len(remaining)} object(s) under {prefix}")
    print(f"E2E_STORAGE_CLEANUP prefix={prefix} objects={len(keys)}")


async def _cleanup(connection: AsyncConnection, run_id: str) -> None:
    clinic_prefix = f"e2e-{run_id}-%"
    email_prefix = f"e2e-{run_id}-%"
    clinic_scope = "SELECT id FROM app.clinics WHERE slug LIKE :clinic_prefix"
    user_scope = "SELECT id FROM app.users WHERE email LIKE :email_prefix"
    parameters = {"clinic_prefix": clinic_prefix, "email_prefix": email_prefix}

    agenda_triggers = (
        ("app.appointment_history", "appointment_history_immutable"),
        ("app.schedule_blocks", "schedule_blocks_no_delete"),
        ("app.agenda_professionals", "agenda_professionals_no_delete"),
        ("app.agenda_rooms", "agenda_rooms_no_delete"),
    )
    for table, trigger in agenda_triggers:
        await connection.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}"))
    try:
        for statement in (
            f"DELETE FROM app.appointment_history WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.schedule_blocks WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.appointments WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.schedule_events WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.professional_availabilities WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.agenda_professionals WHERE clinic_id IN ({clinic_scope})",
            f"DELETE FROM app.agenda_rooms WHERE clinic_id IN ({clinic_scope})",
        ):
            await connection.execute(text(statement), parameters)
    finally:
        for table, trigger in reversed(agenda_triggers):
            await connection.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}"))

    # Final anamneses are immutable by trigger, so the maintenance connection
    # disables the user triggers only for the cleanup statement and always
    # restores them, even when a test failed before the teardown.
    await connection.execute(text("ALTER TABLE app.anamneses DISABLE TRIGGER USER"))
    try:
        await connection.execute(
            text(f"DELETE FROM app.anamneses WHERE clinic_id IN ({clinic_scope})"),
            parameters,
        )
    finally:
        await connection.execute(text("ALTER TABLE app.anamneses ENABLE TRIGGER USER"))

    statements = (
        f"DELETE FROM app.patient_documents WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.patient_alerts WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.patients WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.professional_profiles WHERE user_id IN ({user_scope})",
        f"DELETE FROM app.clinic_audit_events WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.membership_invitations WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.memberships WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.clinic_settings WHERE clinic_id IN ({clinic_scope})",
        f"DELETE FROM app.clinic_feature_flags WHERE clinic_id IN ({clinic_scope})",
        "DELETE FROM app.clinics WHERE slug LIKE :clinic_prefix",
        f"UPDATE app.auth_sessions SET replaced_by_session_id = NULL "
        f"WHERE user_id IN ({user_scope})",
        f"DELETE FROM app.auth_sessions WHERE user_id IN ({user_scope})",
        f"DELETE FROM app.auth_action_tokens WHERE user_id IN ({user_scope})",
        f"DELETE FROM app.auth_audit_events WHERE user_id IN ({user_scope})",
        "DELETE FROM app.email_outbox WHERE recipient LIKE :email_prefix",
        f"DELETE FROM app.password_credentials WHERE user_id IN ({user_scope})",
        f"DELETE FROM app.external_identities WHERE user_id IN ({user_scope})",
        "DELETE FROM app.users WHERE email LIKE :email_prefix",
        "DELETE FROM app.auth_rate_limit_buckets",
    )
    for statement in statements:
        await connection.execute(text(statement), parameters)


def _validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise SystemExit("invalid run id: expected 12 lowercase hexadecimal characters")
    return run_id


def _resolve_run_id(run_id: str, manifest_path: Path | None) -> str:
    if run_id:
        return _validate_run_id(run_id)
    if manifest_path is not None and manifest_path.exists():
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return _validate_run_id(str(manifest["run_id"]))
    raise SystemExit("--run-id is required when the manifest file does not exist")


async def _run(args: argparse.Namespace) -> int:
    database_url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("MIGRATION_DATABASE_URL is required for the E2E seed")

    manifest_path: Path | None = args.manifest
    if args.cleanup:
        run_id = _resolve_run_id(args.run_id, manifest_path)
    else:
        run_id = _validate_run_id(args.run_id or _new_run_id())

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        if args.cleanup:
            await asyncio.to_thread(_delete_run_objects, run_id)
            async with engine.begin() as connection:
                await _cleanup(connection, run_id)
            print(f"E2E_CLEANUP fixtures removed for run {run_id}")
            return 0

        async with engine.begin() as connection:
            manifest = await _seed(connection, run_id)
        if manifest_path is not None:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"E2E_MANIFEST_FILE {manifest_path}")
        print(f"{MANIFEST_PREFIX}{json.dumps(manifest, ensure_ascii=False)}")
    finally:
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_e2e")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(os.environ["E2E_MANIFEST_PATH"])
        if os.environ.get("E2E_MANIFEST_PATH")
        else None,
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
