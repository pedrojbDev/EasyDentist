from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date

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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.anamnesis.models import Anamnesis
from app.core.context import TenantContext, UserContext
from app.core.database import create_session_factory
from app.core.tenancy import tenant_transaction, user_transaction
from app.documents.models import PatientDocument
from app.patients.models import Patient, PatientAlert
from app.users.models import ProfessionalProfile

M2_TABLES = (
    "anamneses",
    "patient_alerts",
    "patient_documents",
    "patients",
    "professional_profiles",
)

M2_TENANT_TABLES = (
    "anamneses",
    "patient_alerts",
    "patient_documents",
    "patients",
)

M2_POLICY_MATRIX = {
    "patients": [
        ("patients_tenant_select", "SELECT", "easydentist_app"),
        ("patients_tenant_insert", "INSERT", "easydentist_app"),
        ("patients_tenant_update", "UPDATE", "easydentist_app"),
        ("patients_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "patient_alerts": [
        ("patient_alerts_tenant_select", "SELECT", "easydentist_app"),
        ("patient_alerts_tenant_insert", "INSERT", "easydentist_app"),
        ("patient_alerts_tenant_update", "UPDATE", "easydentist_app"),
        ("patient_alerts_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "anamneses": [
        ("anamneses_tenant_select", "SELECT", "easydentist_app"),
        ("anamneses_tenant_insert", "INSERT", "easydentist_app"),
        ("anamneses_tenant_update", "UPDATE", "easydentist_app"),
        ("anamneses_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "patient_documents": [
        ("patient_documents_tenant_select", "SELECT", "easydentist_app"),
        ("patient_documents_tenant_insert", "INSERT", "easydentist_app"),
        ("patient_documents_tenant_update", "UPDATE", "easydentist_app"),
        ("patient_documents_migrator_all", "ALL", "easydentist_migrator"),
    ],
    "professional_profiles": [
        ("professional_profiles_owner_select", "SELECT", "easydentist_app"),
        ("professional_profiles_owner_insert", "INSERT", "easydentist_app"),
        ("professional_profiles_owner_update", "UPDATE", "easydentist_app"),
        ("professional_profiles_migrator_all", "ALL", "easydentist_migrator"),
    ],
}


@dataclass(frozen=True, slots=True)
class SeededM2:
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


@pytest.fixture
async def seeded_m2(
    migrator_connection: asyncpg.Connection, seeded_tenants: SeededTenants
) -> AsyncIterator[SeededM2]:
    patient_a = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_a)
    patient_b = await insert_patient(migrator_connection, clinic_id=seeded_tenants.clinic_b)
    alert_a = await insert_patient_alert(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_a,
        patient_id=patient_a,
        created_by_user_id=seeded_tenants.user_a,
    )
    alert_b = await insert_patient_alert(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_b,
        patient_id=patient_b,
        created_by_user_id=seeded_tenants.user_b,
    )
    draft_a = await insert_anamnesis(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_a,
        patient_id=patient_a,
        author_user_id=seeded_tenants.user_a,
    )
    draft_b = await insert_anamnesis(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_b,
        patient_id=patient_b,
        author_user_id=seeded_tenants.user_b,
    )
    document_a = await insert_patient_document(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_a,
        patient_id=patient_a,
        uploaded_by_user_id=seeded_tenants.user_a,
    )
    document_b = await insert_patient_document(
        migrator_connection,
        clinic_id=seeded_tenants.clinic_b,
        patient_id=patient_b,
        uploaded_by_user_id=seeded_tenants.user_b,
    )
    await insert_professional_profile(migrator_connection, user_id=seeded_tenants.user_a)
    await insert_professional_profile(migrator_connection, user_id=seeded_tenants.user_b)

    try:
        yield SeededM2(
            patient_a=patient_a,
            patient_b=patient_b,
            alert_a=alert_a,
            alert_b=alert_b,
            draft_a=draft_a,
            draft_b=draft_b,
            document_a=document_a,
            document_b=document_b,
            profile_a=seeded_tenants.user_a,
            profile_b=seeded_tenants.user_b,
        )
    finally:
        clinic_ids = [seeded_tenants.clinic_a, seeded_tenants.clinic_b]
        await migrator_connection.execute(
            "DELETE FROM app.patient_documents WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.patient_alerts WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.anamneses WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.patients WHERE clinic_id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.professional_profiles WHERE user_id = ANY($1::uuid[])",
            [seeded_tenants.user_a, seeded_tenants.user_b],
        )


async def _set_context(
    connection: asyncpg.Connection, *, user_id: object, clinic_id: object | None = None
) -> None:
    if clinic_id is None:
        await connection.execute("SELECT set_config('app.current_user_id', $1, true)", str(user_id))
    else:
        await connection.execute(
            "SELECT set_config('app.current_user_id', $1, true), "
            "set_config('app.current_clinic_id', $2, true)",
            str(user_id),
            str(clinic_id),
        )


async def _visible_ids(
    connection: asyncpg.Connection,
    *,
    user_id: object,
    clinic_id: object | None,
    table: str,
    key: str = "id",
) -> list[object]:
    transaction = connection.transaction()
    await transaction.start()
    try:
        await _set_context(connection, user_id=user_id, clinic_id=clinic_id)
        rows = await connection.fetch(f"SELECT {key} AS key FROM app.{table}")
        return [row["key"] for row in rows]
    finally:
        await transaction.rollback()


async def _attempt_denied_in_tenant(
    connection: asyncpg.Connection,
    user_id: object,
    clinic_id: object,
    statement: str,
    *args: object,
) -> None:
    transaction = connection.transaction()
    await transaction.start()
    try:
        await _set_context(connection, user_id=user_id, clinic_id=clinic_id)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(statement, *args)
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_m2_policies_catalog_matches_the_matrix(
    admin_connection: asyncpg.Connection,
) -> None:
    records = await admin_connection.fetch(
        "SELECT tablename, policyname, cmd, roles FROM pg_policies "
        "WHERE schemaname = 'app' AND tablename = ANY($1::text[])",
        list(M2_POLICY_MATRIX),
    )
    actual = {
        (record["tablename"], record["policyname"], record["cmd"], tuple(record["roles"]))
        for record in records
    }
    expected = {
        (table, policy, command, (role,))
        for table, policies in M2_POLICY_MATRIX.items()
        for policy, command, role in policies
    }

    assert actual == expected


@pytest.mark.anyio
async def test_m2_tables_force_row_level_security(admin_connection: asyncpg.Connection) -> None:
    rows = await admin_connection.fetch(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'app' AND c.relname = ANY($1::text[])
        """,
        list(M2_TABLES),
    )
    state = {row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"]) for row in rows}

    assert set(state) == set(M2_TABLES)
    for table, (enabled, forced) in state.items():
        assert enabled is True, table
        assert forced is True, table


@pytest.mark.anyio
async def test_m2_tables_return_no_rows_without_context(
    app_connection: asyncpg.Connection, seeded_m2: SeededM2
) -> None:
    for table in M2_TABLES:
        count = await app_connection.fetchval(f"SELECT count(*) FROM app.{table}")

        assert count == 0, table


@pytest.mark.anyio
async def test_m2_tenant_rows_are_isolated_both_directions(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    for table, own_id, foreign_id in (
        ("patients", seeded_m2.patient_a, seeded_m2.patient_b),
        ("patient_alerts", seeded_m2.alert_a, seeded_m2.alert_b),
        ("anamneses", seeded_m2.draft_a, seeded_m2.draft_b),
        ("patient_documents", seeded_m2.document_a, seeded_m2.document_b),
    ):
        visible_a = await _visible_ids(
            app_connection,
            user_id=seeded_tenants.user_a,
            clinic_id=seeded_tenants.clinic_a,
            table=table,
        )
        visible_b = await _visible_ids(
            app_connection,
            user_id=seeded_tenants.user_b,
            clinic_id=seeded_tenants.clinic_b,
            table=table,
        )

        assert visible_a == [own_id], table
        assert visible_b == [foreign_id], table


@pytest.mark.anyio
async def test_m2_context_without_membership_hides_tenant_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    for table in M2_TENANT_TABLES:
        visible = await _visible_ids(
            app_connection,
            user_id=seeded_tenants.user_a,
            clinic_id=seeded_tenants.clinic_b,
            table=table,
        )

        assert visible == [], table


@pytest.mark.anyio
async def test_professional_profiles_are_owner_scoped_in_both_directions(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    visible_a = await _visible_ids(
        app_connection,
        user_id=seeded_tenants.user_a,
        clinic_id=None,
        table="professional_profiles",
        key="user_id",
    )
    visible_b = await _visible_ids(
        app_connection,
        user_id=seeded_tenants.user_b,
        clinic_id=None,
        table="professional_profiles",
        key="user_id",
    )

    assert visible_a == [seeded_m2.profile_a]
    assert visible_b == [seeded_m2.profile_b]


@pytest.mark.anyio
async def test_professional_profile_owner_scope_ignores_the_clinic(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    visible = await _visible_ids(
        app_connection,
        user_id=seeded_tenants.user_a,
        clinic_id=seeded_tenants.clinic_b,
        table="professional_profiles",
        key="user_id",
    )

    assert visible == [seeded_m2.profile_a]


@pytest.mark.anyio
async def test_m2_cross_tenant_updates_affect_no_rows(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a
        )

        for statement, argument in (
            ("UPDATE app.patients SET full_name = 'breach' WHERE id = $1", seeded_m2.patient_b),
            (
                "UPDATE app.patient_alerts SET description = 'breach' WHERE id = $1",
                seeded_m2.alert_b,
            ),
            ("UPDATE app.anamneses SET payload = '{}'::jsonb WHERE id = $1", seeded_m2.draft_b),
            (
                "UPDATE app.patient_documents SET title = 'breach' WHERE id = $1",
                seeded_m2.document_b,
            ),
            (
                "UPDATE app.professional_profiles "
                "SET professional_name = 'breach' WHERE user_id = $1",
                seeded_m2.profile_b,
            ),
        ):
            result = await app_connection.execute(statement, argument)

            assert result == "UPDATE 0", statement
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_m2_runtime_role_cannot_delete_clinical_rows(
    app_connection: asyncpg.Connection, seeded_m2: SeededM2
) -> None:
    for table in M2_TABLES:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await app_connection.execute(f"DELETE FROM app.{table}")


@pytest.mark.anyio
async def test_m2_inserts_for_another_tenant_are_rejected(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    other_clinic = seeded_tenants.clinic_b
    other_user = seeded_tenants.user_b
    statements = (
        (
            "INSERT INTO app.patients (clinic_id, full_name, birth_date, phone) "
            "VALUES ($1, 'Intruso', $2, '11999999999')",
            (other_clinic, date(1990, 1, 1)),
        ),
        (
            "INSERT INTO app.patient_alerts "
            "(clinic_id, patient_id, kind, description, created_by_user_id) "
            "VALUES ($1, $2, 'ALLERGY', 'Intruso', $3)",
            (other_clinic, seeded_m2.patient_b, other_user),
        ),
        (
            "INSERT INTO app.anamneses (clinic_id, patient_id, author_user_id) VALUES ($1, $2, $3)",
            (other_clinic, seeded_m2.patient_b, other_user),
        ),
        (
            "INSERT INTO app.patient_documents "
            "(clinic_id, patient_id, category, title, original_filename, detected_mime, "
            "size_bytes, sha256, storage_key, uploaded_by_user_id) "
            "VALUES ($1, $2, 'CLINICAL', 'Intruso', 'intruso.pdf', 'application/pdf', "
            "10, $3, $4, $5)",
            (other_clinic, seeded_m2.patient_b, "b" * 64, uuid.uuid4().hex, other_user),
        ),
        (
            "INSERT INTO app.professional_profiles "
            "(user_id, professional_name, cro_number, cro_state) "
            "VALUES ($1, 'Intruso', '99999', 'SP')",
            (other_user,),
        ),
    )

    for statement, args in statements:
        await _attempt_denied_in_tenant(
            app_connection, seeded_tenants.user_a, seeded_tenants.clinic_a, statement, *args
        )


@pytest.mark.anyio
async def test_m2_inserts_in_own_tenant_are_allowed(
    app_connection: asyncpg.Connection, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    transaction = app_connection.transaction()
    await transaction.start()
    try:
        await _set_context(
            app_connection, user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a
        )

        patient_id = await insert_patient(
            app_connection,
            clinic_id=seeded_tenants.clinic_a,
            full_name="Paciente Novo",
            birth_date=date(2000, 5, 6),
        )
        alert_id = await insert_patient_alert(
            app_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_id,
            created_by_user_id=seeded_tenants.user_a,
        )
        anamnesis_id = await insert_anamnesis(
            app_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_id,
            author_user_id=seeded_tenants.user_a,
        )
        document_id = await insert_patient_document(
            app_connection,
            clinic_id=seeded_tenants.clinic_a,
            patient_id=patient_id,
            uploaded_by_user_id=seeded_tenants.user_a,
        )
        updated = await app_connection.execute(
            "UPDATE app.professional_profiles SET professional_name = 'Dra. Atualizada' "
            "WHERE user_id = $1",
            seeded_tenants.user_a,
        )
        draft_updated = await app_connection.execute(
            'UPDATE app.anamneses SET payload = \'{"q1": "YES"}\'::jsonb WHERE id = $1',
            seeded_m2.draft_a,
        )

        assert patient_id is not None
        assert alert_id is not None
        assert anamnesis_id is not None
        assert document_id is not None
        assert updated == "UPDATE 1"
        assert draft_updated == "UPDATE 1"
    finally:
        await transaction.rollback()


@pytest.mark.anyio
async def test_orm_sessions_isolate_tenant_rows_both_directions(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    context_b = TenantContext(user_id=seeded_tenants.user_b, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context_a) as session:
        assert [
            patient.id for patient in (await session.execute(select(Patient))).scalars().all()
        ] == [seeded_m2.patient_a]
        assert [
            alert.id for alert in (await session.execute(select(PatientAlert))).scalars().all()
        ] == [seeded_m2.alert_a]
        assert [
            anamnesis.id for anamnesis in (await session.execute(select(Anamnesis))).scalars().all()
        ] == [seeded_m2.draft_a]
        assert [
            document.id
            for document in (await session.execute(select(PatientDocument))).scalars().all()
        ] == [seeded_m2.document_a]
        assert await session.get(Patient, seeded_m2.patient_b) is None
        assert await session.get(Anamnesis, seeded_m2.draft_b) is None

    async with tenant_transaction(session_factory, context_b) as session:
        assert [
            patient.id for patient in (await session.execute(select(Patient))).scalars().all()
        ] == [seeded_m2.patient_b]
        assert [
            alert.id for alert in (await session.execute(select(PatientAlert))).scalars().all()
        ] == [seeded_m2.alert_b]
        assert [
            anamnesis.id for anamnesis in (await session.execute(select(Anamnesis))).scalars().all()
        ] == [seeded_m2.draft_b]
        assert [
            document.id
            for document in (await session.execute(select(PatientDocument))).scalars().all()
        ] == [seeded_m2.document_b]
        assert await session.get(Patient, seeded_m2.patient_a) is None


@pytest.mark.anyio
async def test_orm_sessions_isolate_professional_profiles(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants, seeded_m2: SeededM2
) -> None:
    session_factory = create_session_factory(app_engine)

    async with user_transaction(
        session_factory, UserContext(user_id=seeded_tenants.user_a)
    ) as session:
        assert [
            profile.user_id
            for profile in (await session.execute(select(ProfessionalProfile))).scalars().all()
        ] == [seeded_m2.profile_a]

    async with user_transaction(
        session_factory, UserContext(user_id=seeded_tenants.user_b)
    ) as session:
        assert [
            profile.user_id
            for profile in (await session.execute(select(ProfessionalProfile))).scalars().all()
        ] == [seeded_m2.profile_b]

    async with tenant_transaction(
        session_factory,
        TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b),
    ) as session:
        assert [
            profile.user_id
            for profile in (await session.execute(select(ProfessionalProfile))).scalars().all()
        ] == [seeded_m2.profile_a]
