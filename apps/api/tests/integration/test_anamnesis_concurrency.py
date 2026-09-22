from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg
import pytest
from helpers import (
    build_complete_anamnesis_payload,
    delete_anamneses_for_clinics,
    insert_anamnesis,
    insert_clinic,
    insert_clinic_settings,
    insert_membership,
    insert_patient,
    insert_professional_profile,
)
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.anamnesis.schemas import AnamnesisCreateRequest, AnamnesisStatus
from app.anamnesis.services import AnamnesisService
from app.core.context import TenantContext
from app.core.database import create_database_engine, create_session_factory
from app.core.errors import ConflictError

PASSWORD = "correct horse battery staple"


@dataclass
class ConcurrencyScenario:
    clinic_id: uuid.UUID
    user_id: uuid.UUID
    patient_id: uuid.UUID
    draft_id: uuid.UUID

    @property
    def context(self) -> TenantContext:
        return TenantContext(user_id=self.user_id, clinic_id=self.clinic_id)


@pytest.fixture
async def concurrency_scenario(
    migrator_connection: asyncpg.Connection,
    seed_user_with_password,
    clean_auth_state: None,
    provisioned_clinics: list[uuid.UUID],
) -> AsyncIterator[ConcurrencyScenario]:
    suffix = uuid.uuid4().hex[:10]
    clinic_id = await insert_clinic(migrator_connection, f"concurrency-{suffix}")
    provisioned_clinics.append(clinic_id)
    await insert_clinic_settings(migrator_connection, clinic_id)
    user_id = await seed_user_with_password(
        email=f"concurrency-owner-{suffix}@test.invalid", password=PASSWORD
    )
    await insert_membership(migrator_connection, clinic_id=clinic_id, user_id=user_id, role="OWNER")
    patient_id = await insert_patient(
        migrator_connection,
        clinic_id=clinic_id,
        full_name="Paciente Concorrente",
        phone="+5571900000000",
    )
    await insert_professional_profile(migrator_connection, user_id=user_id)
    draft_id = await insert_anamnesis(
        migrator_connection,
        clinic_id=clinic_id,
        patient_id=patient_id,
        author_user_id=user_id,
        status="DRAFT",
        payload=build_complete_anamnesis_payload(),
    )

    try:
        yield ConcurrencyScenario(
            clinic_id=clinic_id,
            user_id=user_id,
            patient_id=patient_id,
            draft_id=draft_id,
        )
    finally:
        await delete_anamneses_for_clinics(migrator_connection, [clinic_id])
        await migrator_connection.execute(
            "DELETE FROM app.patients WHERE clinic_id = $1", clinic_id
        )
        await migrator_connection.execute(
            "DELETE FROM app.professional_profiles WHERE user_id = $1", user_id
        )


@dataclass(frozen=True, slots=True)
class IndependentSessions:
    first: async_sessionmaker[AsyncSession]
    second: async_sessionmaker[AsyncSession]


@pytest.fixture
async def independent_sessions(app_async_url: str) -> AsyncIterator[IndependentSessions]:
    engines: list[AsyncEngine] = [
        create_database_engine(app_async_url),
        create_database_engine(app_async_url),
    ]
    try:
        yield IndependentSessions(
            first=create_session_factory(engines[0]),
            second=create_session_factory(engines[1]),
        )
    finally:
        for engine in engines:
            await engine.dispose()


@pytest.mark.anyio
async def test_two_simultaneous_drafts_produce_one_success_and_one_conflict(
    concurrency_scenario: ConcurrencyScenario,
    independent_sessions: IndependentSessions,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = concurrency_scenario
    first = AnamnesisService(independent_sessions.first)
    second = AnamnesisService(independent_sessions.second)
    patient_id = await insert_patient(
        migrator_connection,
        clinic_id=scenario.clinic_id,
        full_name="Paciente Sem Rascunho",
        phone="+5571900000000",
    )

    results = await asyncio.gather(
        first.create_draft(scenario.context, patient_id, AnamnesisCreateRequest()),
        second.create_draft(scenario.context, patient_id, AnamnesisCreateRequest()),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, ConflictError)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results
    assert successes[0].status == AnamnesisStatus.DRAFT.value

    drafts = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.anamneses WHERE patient_id = $1 AND status = 'DRAFT'",
        patient_id,
    )
    assert drafts == 1


@pytest.mark.anyio
async def test_two_simultaneous_finalizations_create_exactly_one_final_version(
    concurrency_scenario: ConcurrencyScenario,
    independent_sessions: IndependentSessions,
    migrator_connection: asyncpg.Connection,
) -> None:
    scenario = concurrency_scenario
    first = AnamnesisService(independent_sessions.first)
    second = AnamnesisService(independent_sessions.second)

    results = await asyncio.gather(
        first.finalize_anamnesis(scenario.context, scenario.patient_id, scenario.draft_id),
        second.finalize_anamnesis(scenario.context, scenario.patient_id, scenario.draft_id),
        return_exceptions=True,
    )

    successes = [result for result in results if not isinstance(result, BaseException)]
    conflicts = [result for result in results if isinstance(result, ConflictError)]
    assert len(successes) == 1, results
    assert len(conflicts) == 1, results
    assert successes[0].status == AnamnesisStatus.FINAL.value
    assert successes[0].version_number == 1

    finals = await migrator_connection.fetch(
        "SELECT version_number FROM app.anamneses WHERE patient_id = $1 AND status = 'FINAL'",
        scenario.patient_id,
    )
    assert [row["version_number"] for row in finals] == [1]
    audits = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.clinic_audit_events "
        "WHERE clinic_id = $1 AND event_type = 'anamnesis.finalized'",
        scenario.clinic_id,
    )
    assert audits == 1
