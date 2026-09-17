from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.action_tokens import (
    EMAIL_VERIFICATION_TTL,
    PASSWORD_RESET_TTL,
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    ActionTokenService,
)
from app.auth.tokens import token_digest
from app.core.database import transaction_scope

PASSWORD = "correct horse battery staple"


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def issuer_clock() -> MutableClock:
    return MutableClock(datetime(2026, 9, 17, 12, 0, tzinfo=UTC))


async def issue(
    session_factory: async_sessionmaker[AsyncSession],
    service: ActionTokenService,
    *,
    user_id,
    purpose: str = PURPOSE_PASSWORD_RESET,
    ttl: timedelta = PASSWORD_RESET_TTL,
) -> str:
    async with transaction_scope(session_factory) as session:
        return await service.issue(session, purpose=purpose, user_id=user_id, ttl=ttl)


async def consume(
    session_factory: async_sessionmaker[AsyncSession],
    service: ActionTokenService,
    *,
    token: str,
    purpose: str = PURPOSE_PASSWORD_RESET,
):
    async with transaction_scope(session_factory) as session:
        return await service.consume(session, purpose=purpose, token=token)


@pytest.mark.anyio
async def test_issue_persists_digest_purpose_and_expiry(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
    issuer_clock: MutableClock,
) -> None:
    user_id = await seed_user_with_password(email=make_test_email("token-issue"), password=PASSWORD)
    service = ActionTokenService(clock=issuer_clock)

    token = await issue(session_factory, service, user_id=user_id)

    row = await migrator_connection.fetchrow(
        "SELECT token_hash, purpose, expires_at, consumed_at "
        "FROM app.auth_action_tokens WHERE user_id = $1",
        user_id,
    )
    assert row is not None
    assert bytes(row["token_hash"]) == token_digest(token)
    assert row["purpose"] == PURPOSE_PASSWORD_RESET
    assert row["expires_at"] == issuer_clock.now + PASSWORD_RESET_TTL
    assert row["consumed_at"] is None
    assert token not in str(row["token_hash"])


@pytest.mark.anyio
async def test_consume_marks_single_use_and_returns_user(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("token-consume"), password=PASSWORD
    )
    service = ActionTokenService()
    token = await issue(session_factory, service, user_id=user_id)

    assert await consume(session_factory, service, token=token) == user_id

    row = await migrator_connection.fetchrow(
        "SELECT consumed_at FROM app.auth_action_tokens WHERE user_id = $1", user_id
    )
    assert row["consumed_at"] is not None

    assert await consume(session_factory, service, token=token) is None


@pytest.mark.anyio
async def test_consume_rejects_expired_token(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
    issuer_clock: MutableClock,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("token-expired"), password=PASSWORD
    )
    service = ActionTokenService(clock=issuer_clock)
    token = await issue(session_factory, service, user_id=user_id, ttl=EMAIL_VERIFICATION_TTL)

    issuer_clock.now += EMAIL_VERIFICATION_TTL + timedelta(seconds=1)

    assert await consume(session_factory, service, token=token) is None


@pytest.mark.anyio
async def test_consume_rejects_unknown_token(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    await seed_user_with_password(email=make_test_email("token-unknown"), password=PASSWORD)
    service = ActionTokenService()

    assert await consume(session_factory, service, token="not-a-stored-token") is None


@pytest.mark.anyio
async def test_consume_rejects_purpose_mismatch(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("token-purpose"), password=PASSWORD
    )
    service = ActionTokenService()
    token = await issue(
        session_factory, service, user_id=user_id, purpose=PURPOSE_EMAIL_VERIFICATION
    )

    assert (
        await consume(session_factory, service, token=token, purpose=PURPOSE_PASSWORD_RESET) is None
    )


@pytest.mark.anyio
async def test_concurrent_consumes_yield_exactly_one_success(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("token-concurrent"), password=PASSWORD
    )
    service = ActionTokenService()
    token = await issue(session_factory, service, user_id=user_id)

    results = await asyncio.gather(
        consume(session_factory, service, token=token),
        consume(session_factory, service, token=token),
    )

    assert list(results).count(user_id) == 1
    assert list(results).count(None) == 1
