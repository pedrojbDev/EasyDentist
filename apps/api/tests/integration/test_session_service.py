from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.principal import Principal
from app.auth.repositories.session_repository import SessionRepository
from app.auth.sessions import SessionService
from app.auth.settings import AuthSettings
from app.auth.tokens import token_digest
from app.core.database import transaction_scope

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
PASSWORD = "correct horse battery staple"


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(NOW)


@pytest.fixture
def session_service(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    clock: MutableClock,
) -> SessionService:
    return SessionService(session_factory, auth_settings, clock=clock)


async def read_session(session_factory: async_sessionmaker[AsyncSession], token: str):
    async with transaction_scope(session_factory) as session:
        return await SessionRepository(session).find_by_token_hash(token_digest(token))


@pytest.mark.anyio
async def test_create_stores_only_the_digest(
    session_factory: async_sessionmaker[AsyncSession],
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-create"), password=PASSWORD
    )

    session_id, token = await session_service.create(user_id)

    assert len(token) == 43
    row = await read_session(session_factory, token)
    assert row is not None
    assert row.id == session_id
    assert row.user_id == user_id
    assert row.token_hash == token_digest(token)
    assert row.last_seen_at == NOW
    assert row.idle_expires_at == NOW + timedelta(hours=12)
    assert row.absolute_expires_at == NOW + timedelta(days=30)
    assert row.revoked_at is None


@pytest.mark.anyio
async def test_resolve_returns_principal(
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-resolve"), password=PASSWORD
    )
    session_id, token = await session_service.create(user_id)

    principal = await session_service.resolve(token)

    assert principal == Principal(user_id=user_id, session_id=session_id, auth_method="password")


@pytest.mark.anyio
async def test_resolve_returns_none_for_unknown_or_revoked_token(
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-revoke"), password=PASSWORD
    )
    session_id, token = await session_service.create(user_id)

    assert await session_service.resolve("unknown-token-value") is None
    assert await session_service.revoke(user_id, session_id) is True
    assert await session_service.resolve(token) is None
    assert await session_service.revoke(user_id, session_id) is True


@pytest.mark.anyio
async def test_revoke_returns_false_for_foreign_session(
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    owner_id = await seed_user_with_password(
        email=make_test_email("session-owner"), password=PASSWORD
    )
    other_id = await seed_user_with_password(
        email=make_test_email("session-other"), password=PASSWORD
    )
    session_id, _ = await session_service.create(owner_id)

    assert await session_service.revoke(other_id, session_id) is False


@pytest.mark.anyio
async def test_resolve_enforces_idle_expiry(
    clock: MutableClock,
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-idle"), password=PASSWORD
    )
    _, token = await session_service.create(user_id)

    clock.now = NOW + timedelta(hours=12, seconds=1)

    assert await session_service.resolve(token) is None


@pytest.mark.anyio
async def test_resolve_enforces_absolute_expiry(
    session_factory: async_sessionmaker[AsyncSession],
    clock: MutableClock,
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-absolute"), password=PASSWORD
    )
    _, token = await session_service.create(user_id)
    async with transaction_scope(session_factory) as session:
        row = await SessionRepository(session).find_by_token_hash(token_digest(token))
        assert row is not None
        row.absolute_expires_at = NOW - timedelta(seconds=1)
        row.idle_expires_at = NOW + timedelta(hours=1)

    assert await session_service.resolve(token) is None


@pytest.mark.anyio
async def test_resolve_touches_with_throttle(
    session_factory: async_sessionmaker[AsyncSession],
    clock: MutableClock,
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session-touch"), password=PASSWORD
    )
    _, token = await session_service.create(user_id)

    clock.now = NOW + timedelta(minutes=1)
    assert await session_service.resolve(token) is not None
    row = await read_session(session_factory, token)
    assert row is not None
    assert row.last_seen_at == NOW

    clock.now = NOW + timedelta(minutes=6)
    assert await session_service.resolve(token) is not None
    row = await read_session(session_factory, token)
    assert row is not None
    assert row.last_seen_at == clock.now
    assert row.idle_expires_at == clock.now + timedelta(hours=12)


@pytest.mark.anyio
async def test_revoke_all_only_affects_the_user(
    session_service: SessionService,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_a = await seed_user_with_password(email=make_test_email("revoke-a"), password=PASSWORD)
    user_b = await seed_user_with_password(email=make_test_email("revoke-b"), password=PASSWORD)
    _, token_a = await session_service.create(user_a)
    _, token_b = await session_service.create(user_b)

    revoked = await session_service.revoke_all(user_a)

    assert revoked == 1
    assert await session_service.resolve(token_a) is None
    assert await session_service.resolve(token_b) is not None
