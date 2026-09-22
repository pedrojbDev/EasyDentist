from __future__ import annotations

import importlib.util
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType

import asyncpg
import pytest
from conftest import SeededTenants
from helpers import (
    insert_anamnesis,
    insert_patient,
    insert_patient_alert,
    insert_patient_document,
    insert_professional_profile,
)

M2_TABLES = (
    "anamneses",
    "patient_alerts",
    "patient_documents",
    "patients",
    "professional_profiles",
)

APP_ROLE = "easydentist_app"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"
FINAL_SNAPSHOT = {
    "author_professional_name": "Dra. Teste",
    "author_cro_number": "12345",
    "author_cro_state": "BA",
}


async def _start_transaction(connection: asyncpg.Connection) -> asyncpg.Transaction:
    transaction = connection.transaction()
    await transaction.start()
    return transaction


async def _insert_final_anamnesis(
    connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> uuid.UUID:
    patient_id = await insert_patient(connection, clinic_id=seeded_tenants.clinic_a)
    return await insert_anamnesis(
        connection,
        clinic_id=seeded_tenants.clinic_a,
        patient_id=patient_id,
        author_user_id=seeded_tenants.user_a,
        status="FINAL",
        version_number=1,
        finalized_at=datetime.now(UTC),
        **FINAL_SNAPSHOT,
    )


@pytest.mark.anyio
async def test_m2_tables_exist(admin_connection: asyncpg.Connection) -> None:
    records = await admin_connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'app'"
    )

    assert {record["tablename"] for record in records} >= set(M2_TABLES)


@pytest.mark.anyio
async def test_partial_unique_indexes_are_defined(admin_connection: asyncpg.Connection) -> None:
    names = ["ix_patients_clinic_id_cpf", "uq_anamneses_draft_per_patient"]
    records = await admin_connection.fetch(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = 'app' AND indexname = ANY($1::text[])",
        names,
    )
    definitions = {record["indexname"]: record["indexdef"] for record in records}

    assert set(definitions) == set(names)
    assert "UNIQUE" in definitions["ix_patients_clinic_id_cpf"]
    assert "cpf IS NOT NULL" in definitions["ix_patients_clinic_id_cpf"]
    assert "UNIQUE" in definitions["uq_anamneses_draft_per_patient"]
    assert "status = 'DRAFT'" in definitions["uq_anamneses_draft_per_patient"]


@pytest.mark.anyio
async def test_patient_supporting_indexes_are_defined(admin_connection: asyncpg.Connection) -> None:
    names = [
        "ix_patients_clinic_id_status_full_name",
        "ix_patient_alerts_clinic_id_patient_id_created_at",
    ]
    records = await admin_connection.fetch(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'app' AND indexname = ANY($1::text[])",
        names,
    )

    assert {record["indexname"] for record in records} == set(names)


@pytest.mark.anyio
async def test_app_role_grants_are_minimal(admin_connection: asyncpg.Connection) -> None:
    for table in M2_TABLES:
        for privilege in ("SELECT", "INSERT", "UPDATE"):
            granted = await admin_connection.fetchval(
                "SELECT has_table_privilege($1, $2, $3)",
                APP_ROLE,
                f"app.{table}",
                privilege,
            )
            assert granted is True, (table, privilege)

        denied = await admin_connection.fetchval(
            "SELECT has_table_privilege($1, $2, 'DELETE')",
            APP_ROLE,
            f"app.{table}",
        )
        assert denied is False, table


def _load_migration(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        filename.removesuffix(".py"), MIGRATIONS_DIR / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_m2_migration_chain_links_to_0008_and_declares_downgrades() -> None:
    modules = [
        _load_migration(filename)
        for filename in (
            "0009_m2_patient_foundation.py",
            "0010_m2_anamnesis.py",
            "0011_m2_documents.py",
            "0012_m2_patient_indexes.py",
            "0013_m2_anamnesis_base_integrity.py",
        )
    ]

    assert [module.revision for module in modules] == [
        "0009_m2_patient_foundation",
        "0010_m2_anamnesis",
        "0011_m2_documents",
        "0012_m2_patient_indexes",
        "0013_m2_anamnesis_base_integrity",
    ]
    assert [module.down_revision for module in modules] == [
        "0008_membership_management",
        "0009_m2_patient_foundation",
        "0010_m2_anamnesis",
        "0011_m2_documents",
        "0012_m2_patient_indexes",
    ]
    for module in modules:
        assert callable(module.downgrade)


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["full_name", "birth_date", "phone"])
async def test_patients_require_core_fields(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    missing: str,
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        with pytest.raises(asyncpg.NotNullViolationError):
            await insert_patient(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                **{missing: None},
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_cpf_is_unique_within_the_clinic(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        await insert_patient(
            migrator_connection, clinic_id=seeded_tenants.clinic_a, cpf="12345678901"
        )
        await insert_patient(
            migrator_connection, clinic_id=seeded_tenants.clinic_b, cpf="12345678901"
        )
        await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a, cpf=None)
        await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a, cpf=None)

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_patient(
                migrator_connection, clinic_id=seeded_tenants.clinic_a, cpf="12345678901"
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_birth_date_cannot_be_in_the_future(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        today = await migrator_connection.fetchval("SELECT CURRENT_DATE")
        patient_id = await insert_patient(
            migrator_connection, clinic_id=seeded_tenants.clinic_a, birth_date=today
        )
        assert patient_id is not None

        with pytest.raises(asyncpg.CheckViolationError):
            await insert_patient(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                birth_date=today + timedelta(days=1),
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "contact",
    [
        {"emergency_contact_name": "Maria da Silva"},
        {"emergency_contact_relationship": "Mãe"},
        {"emergency_contact_phone": "+5571988887777"},
        {"emergency_contact_name": "Maria da Silva", "emergency_contact_relationship": "Mãe"},
    ],
)
async def test_patient_emergency_contact_requires_name_and_phone(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    contact: dict[str, str],
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        with pytest.raises(asyncpg.CheckViolationError):
            await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a, **contact)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_complete_emergency_contact_is_accepted(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_id = await insert_patient(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            emergency_contact_name="Maria da Silva",
            emergency_contact_relationship="Mãe",
            emergency_contact_phone="+5571988887777",
        )

        assert patient_id is not None
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "archived_at"),
    [
        ("DELETED", None),
        ("ARCHIVED", None),
        ("ACTIVE", datetime.now(UTC)),
    ],
)
async def test_patient_status_and_archived_at_are_coherent(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    status: str,
    archived_at: datetime | None,
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        await insert_patient(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            status="ARCHIVED",
            archived_at=datetime.now(UTC),
        )

        with pytest.raises(asyncpg.CheckViolationError):
            await insert_patient(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                status=status,
                archived_at=archived_at,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_alerts_reject_cross_tenant_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_b)

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_patient_alert(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_b,
                created_by_user_id=seeded_tenants.user_a,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_alerts_accept_same_tenant_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        alert_id = await insert_patient_alert(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            created_by_user_id=seeded_tenants.user_a,
        )

        assert alert_id is not None
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("kind", "status", "resolved_at"),
    [
        ("INVALID", "ACTIVE", None),
        ("ALLERGY", "INVALID", None),
        ("ALLERGY", "RESOLVED", None),
        ("ALLERGY", "ACTIVE", datetime.now(UTC)),
    ],
)
async def test_patient_alert_kind_status_and_resolved_at_are_coherent(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    kind: str,
    status: str,
    resolved_at: datetime | None,
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)

        with pytest.raises(asyncpg.CheckViolationError):
            await insert_patient_alert(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                created_by_user_id=seeded_tenants.user_a,
                kind=kind,
                status=status,
                resolved_at=resolved_at,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamneses_reject_cross_tenant_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_b)

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_b,
                author_user_id=seeded_tenants.user_a,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_base_version_rejects_another_tenant(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_b)
        base_b = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_b,
            patient_id=patient_b,
            author_user_id=seeded_tenants.user_b,
            status="FINAL",
            version_number=1,
            finalized_at=datetime.now(UTC),
            **FINAL_SNAPSHOT,
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                base_version_id=base_b,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_base_version_rejects_another_patient_of_the_same_clinic(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        base_b = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_b,
            author_user_id=seeded_tenants.user_a,
            status="FINAL",
            version_number=1,
            finalized_at=datetime.now(UTC),
            **FINAL_SNAPSHOT,
        )

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                base_version_id=base_b,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_base_version_must_be_final(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        draft_base = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
        )

        with pytest.raises(asyncpg.RaiseError, match="anamnesis_base_not_final"):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                base_version_id=draft_base,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_base_integrity_constraints_are_defined(
    admin_connection: asyncpg.Connection,
) -> None:
    constraints = await admin_connection.fetch(
        "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint "
        "WHERE conrelid = 'app.anamneses'::regclass "
        "AND conname = ANY($1::text[])",
        [
            "fk_anamneses_clinic_id_anamneses",
            "uq_anamneses_clinic_id_patient_id",
        ],
    )
    definitions = {record["conname"]: record["definition"] for record in constraints}

    assert set(definitions) == {
        "fk_anamneses_clinic_id_anamneses",
        "uq_anamneses_clinic_id_patient_id",
    }
    assert (
        definitions["fk_anamneses_clinic_id_anamneses"]
        == "FOREIGN KEY (clinic_id, patient_id, base_version_id) "
        "REFERENCES app.anamneses(clinic_id, patient_id, id)"
    )
    assert definitions["uq_anamneses_clinic_id_patient_id"] == "UNIQUE (clinic_id, patient_id, id)"
    trigger = await admin_connection.fetchval(
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'app.anamneses'::regclass "
        "AND tgname = 'anamneses_require_final_base'"
    )
    assert trigger == "anamneses_require_final_base"


@pytest.mark.anyio
async def test_anamnesis_base_trigger_function_is_restricted(
    admin_connection: asyncpg.Connection,
) -> None:
    search_path, acl = await admin_connection.fetchrow(
        "SELECT proconfig, proacl FROM pg_proc WHERE proname = 'require_final_anamnesis_base'"
    )

    assert "search_path=app, pg_temp" in search_path
    assert all(not entry.startswith("=") for entry in acl)
    assert await admin_connection.fetchval(
        "SELECT has_function_privilege($1, 'app.require_final_anamnesis_base()', 'EXECUTE')",
        APP_ROLE,
    )


@pytest.mark.anyio
async def test_anamnesis_allows_only_one_draft_per_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
        )
        await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
            status="FINAL",
            version_number=1,
            finalized_at=datetime.now(UTC),
            **FINAL_SNAPSHOT,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_version_number_is_unique_per_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        for version_number in (1, 2):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                status="FINAL",
                version_number=version_number,
                finalized_at=datetime.now(UTC),
                **FINAL_SNAPSHOT,
            )

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                status="FINAL",
                version_number=2,
                finalized_at=datetime.now(UTC),
                **FINAL_SNAPSHOT,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "DRAFT", "version_number": 1},
        {"status": "FINAL", "version_number": None, "finalized_at": datetime.now(UTC)},
        {
            "status": "FINAL",
            "version_number": 1,
            "finalized_at": None,
        },
        {
            "status": "FINAL",
            "version_number": 1,
            "finalized_at": datetime.now(UTC),
            "author_professional_name": None,
        },
    ],
)
async def test_anamnesis_status_requires_consistent_version_and_snapshot(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    overrides: dict[str, object],
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        values: dict[str, object] = {
            "status": "DRAFT",
            "version_number": None,
            "finalized_at": None,
            "author_professional_name": None,
            "author_cro_number": None,
            "author_cro_state": None,
        }
        values.update(overrides)

        with pytest.raises(asyncpg.CheckViolationError):
            await insert_anamnesis(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                author_user_id=seeded_tenants.user_a,
                **values,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_final_anamnesis_cannot_be_updated(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        final_id = await _insert_final_anamnesis(migrator_connection, seeded_tenants)

        with pytest.raises(asyncpg.RaiseError, match="anamnesis_final_immutable"):
            await migrator_connection.execute(
                "UPDATE app.anamneses SET payload = '{}'::jsonb WHERE id = $1", final_id
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_final_anamnesis_cannot_be_deleted(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        final_id = await _insert_final_anamnesis(migrator_connection, seeded_tenants)

        with pytest.raises(asyncpg.RaiseError, match="anamnesis_final_immutable"):
            await migrator_connection.execute("DELETE FROM app.anamneses WHERE id = $1", final_id)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_draft_anamnesis_can_be_updated_and_deleted(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        draft_id = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
        )

        updated = await migrator_connection.execute(
            "UPDATE app.anamneses SET payload = '{\"answer\": true}'::jsonb WHERE id = $1",
            draft_id,
        )
        deleted = await migrator_connection.execute(
            "DELETE FROM app.anamneses WHERE id = $1", draft_id
        )

        assert updated == "UPDATE 1"
        assert deleted == "DELETE 1"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_documents_reject_cross_tenant_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_b)

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_patient_document(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_b,
                uploaded_by_user_id=seeded_tenants.user_a,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "INVALID"},
        {"status": "INVALID"},
        {"status": "ARCHIVED", "archived_at": None},
        {"status": "ACTIVE", "archived_at": datetime.now(UTC)},
        {"sha256": "not-a-sha256"},
        {"size_bytes": 0},
    ],
)
async def test_patient_document_constraints(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    overrides: dict[str, object],
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)

        with pytest.raises(asyncpg.CheckViolationError):
            await insert_patient_document(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                uploaded_by_user_id=seeded_tenants.user_a,
                **overrides,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_document_storage_key_is_unique(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        storage_key = uuid.uuid4().hex
        await insert_patient_document(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            uploaded_by_user_id=seeded_tenants.user_a,
            storage_key=storage_key,
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_patient_document(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                uploaded_by_user_id=seeded_tenants.user_a,
                storage_key=storage_key,
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["professional_name", "cro_number", "cro_state"])
async def test_professional_profiles_require_cro_identity(
    migrator_connection: asyncpg.Connection,
    seeded_tenants: SeededTenants,
    missing: str,
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        with pytest.raises(asyncpg.NotNullViolationError):
            await insert_professional_profile(
                migrator_connection,
                user_id=seeded_tenants.user_a,
                **{missing: None},
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_professional_profiles_are_one_per_user(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        profile_id = await insert_professional_profile(
            migrator_connection, user_id=seeded_tenants.user_a
        )

        assert profile_id == seeded_tenants.user_a

        with pytest.raises(asyncpg.UniqueViolationError):
            await insert_professional_profile(migrator_connection, user_id=seeded_tenants.user_a)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_anamnesis_accepts_base_version_of_the_same_patient(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
        base = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
            status="FINAL",
            version_number=1,
            finalized_at=datetime.now(UTC),
            **FINAL_SNAPSHOT,
        )

        revision = await insert_anamnesis(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_a,
            author_user_id=seeded_tenants.user_a,
            base_version_id=base,
            payload={"copied": True},
        )

        assert revision is not None
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_alert_created_by_must_be_a_user(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)

        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await insert_patient_alert(
                migrator_connection,
                clinic_id=seeded_tenants.clinic_a,
                patient_id=patient_a,
                created_by_user_id=uuid.uuid4(),
            )
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_patient_birth_date_round_trips_as_a_date(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> None:
    transaction = await _start_transaction(migrator_connection)
    try:
        patient_id = await insert_patient(
            migrator_connection,
            clinic_id=seeded_tenants.clinic_a,
            birth_date=date(2001, 2, 3),
        )

        stored = await migrator_connection.fetchval(
            "SELECT birth_date FROM app.patients WHERE id = $1", patient_id
        )

        assert stored == date(2001, 2, 3)
    finally:
        await transaction.rollback()
