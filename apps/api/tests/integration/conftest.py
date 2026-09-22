from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
import httpx
import pytest
from helpers import (
    delete_m2_rows_for_clinics,
    delete_professional_profiles_for_users,
    insert_clinic,
    insert_clinic_settings,
    insert_invitation,
    insert_membership,
    insert_user,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app import models as _models  # noqa: F401
from app.application import create_app
from app.auth.passwords import PasswordHasher
from app.auth.repositories.password_credential_repository import PasswordCredentialRepository
from app.auth.settings import AuthSettings
from app.core.database import create_database_engine, create_session_factory, transaction_scope
from app.users.models import User

TEST_EMAIL_SUFFIX = "@test.invalid"


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = False

    async def send(self, recipient: str, subject: str, body: str) -> None:
        if self.fail:
            raise RuntimeError("smtp is down")
        self.sent.append((recipient, subject, body))


@dataclass(frozen=True, slots=True)
class SeededTenants:
    user_a: uuid.UUID
    user_b: uuid.UUID
    clinic_a: uuid.UUID
    clinic_b: uuid.UUID
    membership_a: uuid.UUID
    membership_b: uuid.UUID


def required_url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required for PostgreSQL integration tests")
    return value


@pytest.fixture
def app_async_url() -> str:
    url = make_url(required_url("TEST_APP_DATABASE_URL")).set(drivername="postgresql+asyncpg")
    return url.render_as_string(hide_password=False)


@pytest.fixture
async def app_engine(app_async_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_database_engine(app_async_url)
    try:
        yield engine
    finally:
        await engine.dispose()


async def _connect(variable: str) -> asyncpg.Connection:
    return await asyncpg.connect(required_url(variable))


@pytest.fixture
async def admin_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_ADMIN_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def app_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_APP_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def migrator_connection() -> AsyncIterator[asyncpg.Connection]:
    connection = await _connect("TEST_MIGRATION_DATABASE_URL")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
async def seeded_tenants(
    migrator_connection: asyncpg.Connection,
) -> AsyncIterator[SeededTenants]:
    suffix = uuid.uuid4().hex
    user_a = await insert_user(migrator_connection, f"tenant-a-{suffix}@example.com")
    user_b = await insert_user(migrator_connection, f"tenant-b-{suffix}@example.com")
    clinic_a = await insert_clinic(migrator_connection, f"clinic-a-{suffix}")
    clinic_b = await insert_clinic(migrator_connection, f"clinic-b-{suffix}")
    membership_a = await insert_membership(migrator_connection, clinic_id=clinic_a, user_id=user_a)
    membership_b = await insert_membership(migrator_connection, clinic_id=clinic_b, user_id=user_b)
    await insert_clinic_settings(migrator_connection, clinic_a)
    await insert_clinic_settings(migrator_connection, clinic_b)
    await insert_invitation(
        migrator_connection,
        clinic_id=clinic_a,
        membership_id=membership_a,
        email=f"invitee-a-{suffix}@example.com",
        token_hash=uuid.uuid4().bytes,
    )
    await migrator_connection.execute(
        "INSERT INTO app.clinic_feature_flags (clinic_id, key, enabled) "
        "VALUES ($1, 'odontogram', true)",
        clinic_a,
    )
    await migrator_connection.execute(
        "INSERT INTO app.clinic_audit_events (clinic_id, actor_user_id, event_type) "
        "VALUES ($1, $2, 'membership.created')",
        clinic_a,
        user_a,
    )

    try:
        yield SeededTenants(
            user_a=user_a,
            user_b=user_b,
            clinic_a=clinic_a,
            clinic_b=clinic_b,
            membership_a=membership_a,
            membership_b=membership_b,
        )
    finally:
        clinic_ids = [clinic_a, clinic_b]
        # M2 children first: clinics cannot be deleted while patients,
        # anamneses, alerts or documents still point at them.
        await delete_m2_rows_for_clinics(migrator_connection, clinic_ids)
        await delete_professional_profiles_for_users(migrator_connection, [user_a, user_b])
        await migrator_connection.execute(
            "DELETE FROM app.membership_invitations WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_audit_events WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_feature_flags WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinic_settings WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.memberships WHERE clinic_id = ANY($1::uuid[])",
            clinic_ids,
        )
        await migrator_connection.execute(
            "DELETE FROM app.clinics WHERE id = ANY($1::uuid[])", clinic_ids
        )
        await migrator_connection.execute(
            "DELETE FROM app.users WHERE id = ANY($1::uuid[])", [user_a, user_b]
        )


def make_test_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}{TEST_EMAIL_SUFFIX}"


@pytest.fixture
def auth_settings() -> AuthSettings:
    return AuthSettings.from_environment({})


@pytest.fixture
async def session_factory(app_async_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(app_async_url, pool_size=2, max_overflow=0)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
async def clean_auth_state(migrator_connection: asyncpg.Connection) -> AsyncIterator[None]:
    yield
    pattern = f"%{TEST_EMAIL_SUFFIX}"
    # Profiles are owner-scoped and reference the user, so they must go before
    # the users; a failed delete here used to leave synthetic users behind.
    await migrator_connection.execute(
        "DELETE FROM app.professional_profiles WHERE user_id IN "
        "(SELECT id FROM app.users WHERE email LIKE $1)",
        pattern,
    )
    for statement in (
        "DELETE FROM app.auth_sessions WHERE user_id IN "
        "(SELECT id FROM app.users WHERE email LIKE $1)",
        "DELETE FROM app.auth_action_tokens WHERE user_id IN "
        "(SELECT id FROM app.users WHERE email LIKE $1)",
        "DELETE FROM app.password_credentials WHERE user_id IN "
        "(SELECT id FROM app.users WHERE email LIKE $1)",
        "DELETE FROM app.auth_audit_events WHERE user_id IN "
        "(SELECT id FROM app.users WHERE email LIKE $1)",
        "DELETE FROM app.email_outbox WHERE recipient LIKE $1",
        "DELETE FROM app.users WHERE email LIKE $1",
    ):
        await migrator_connection.execute(statement, pattern)
    await migrator_connection.execute("DELETE FROM app.auth_audit_events WHERE user_id IS NULL")
    await migrator_connection.execute("DELETE FROM app.auth_rate_limit_buckets")


@pytest.fixture
def email_sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture
async def provisioned_clinics(
    migrator_connection: asyncpg.Connection, clean_auth_state: None
) -> AsyncIterator[list[uuid.UUID]]:
    clinic_ids: list[uuid.UUID] = []
    try:
        yield clinic_ids
    finally:
        if clinic_ids:
            member_rows = await migrator_connection.fetch(
                "SELECT user_id FROM app.memberships WHERE clinic_id = ANY($1::uuid[])",
                clinic_ids,
            )
            await delete_m2_rows_for_clinics(migrator_connection, clinic_ids)
            await delete_professional_profiles_for_users(
                migrator_connection, [row["user_id"] for row in member_rows]
            )
            await migrator_connection.execute(
                "DELETE FROM app.membership_invitations WHERE clinic_id = ANY($1::uuid[])",
                clinic_ids,
            )
            await migrator_connection.execute(
                "DELETE FROM app.clinic_audit_events WHERE clinic_id = ANY($1::uuid[])",
                clinic_ids,
            )
            await migrator_connection.execute(
                "DELETE FROM app.memberships WHERE clinic_id = ANY($1::uuid[])", clinic_ids
            )
            await migrator_connection.execute(
                "DELETE FROM app.clinic_settings WHERE clinic_id = ANY($1::uuid[])",
                clinic_ids,
            )
            await migrator_connection.execute(
                "DELETE FROM app.clinics WHERE id = ANY($1::uuid[])", clinic_ids
            )


@pytest.fixture
async def api_client(
    app_async_url: str, monkeypatch: pytest.MonkeyPatch, email_sender: RecordingEmailSender
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", app_async_url)
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://testserver")
    app = create_app()
    async with app.router.lifespan_context(app):
        app.state.email_sender = email_sender
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def seed_user_with_password(
    session_factory: async_sessionmaker[AsyncSession], auth_settings: AuthSettings
):
    async def _seed(*, email: str, password: str) -> uuid.UUID:
        hasher = PasswordHasher(auth_settings)
        async with transaction_scope(session_factory) as session:
            user = User(email=email)
            session.add(user)
            await session.flush()
            repository = PasswordCredentialRepository(session)
            await repository.upsert(
                user_id=user.id,
                password_hash=hasher.hash(password),
                changed_at=datetime.now(UTC),
            )
            return user.id

    return _seed
