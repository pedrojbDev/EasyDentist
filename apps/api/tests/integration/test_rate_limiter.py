from __future__ import annotations

import asyncio

import asyncpg
import pytest
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.ratelimit import RateLimiter
from app.auth.settings import AuthSettings

KIND = "test-limit"


@pytest.fixture
def limiter(
    session_factory: async_sessionmaker[AsyncSession], auth_settings: AuthSettings
) -> RateLimiter:
    return RateLimiter(session_factory, auth_settings)


@pytest.mark.anyio
async def test_allows_up_to_limit_then_blocks(limiter: RateLimiter, clean_auth_state: None) -> None:
    identifier = make_test_email("limit")

    for _ in range(5):
        decision = await limiter.consume(KIND, identifier, limit=5, window_seconds=900)
        assert decision.allowed is True

    blocked = await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    assert blocked.allowed is False
    assert blocked.retry_after_seconds > 0


@pytest.mark.anyio
async def test_backoff_grows_with_repeated_attempts(
    limiter: RateLimiter, clean_auth_state: None
) -> None:
    identifier = make_test_email("backoff")
    for _ in range(5):
        await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    first = await limiter.consume(KIND, identifier, limit=5, window_seconds=900)
    second = await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    assert first.allowed is False
    assert second.allowed is False
    assert second.retry_after_seconds > first.retry_after_seconds


@pytest.mark.anyio
async def test_window_reset_starts_a_fresh_count(
    limiter: RateLimiter, migrator_connection: asyncpg.Connection, clean_auth_state: None
) -> None:
    identifier = make_test_email("window")
    for _ in range(6):
        await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    await migrator_connection.execute(
        "UPDATE app.auth_rate_limit_buckets "
        "SET window_started_at = now() - interval '2 hours', blocked_until = NULL "
        "WHERE bucket_key = $1",
        limiter.bucket_key(KIND, identifier),
    )

    decision = await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    assert decision.allowed is True


@pytest.mark.anyio
async def test_clear_removes_the_block(limiter: RateLimiter, clean_auth_state: None) -> None:
    identifier = make_test_email("clear")
    for _ in range(6):
        await limiter.consume(KIND, identifier, limit=5, window_seconds=900)
    assert (await limiter.consume(KIND, identifier, limit=5, window_seconds=900)).allowed is False

    await limiter.clear(KIND, identifier)

    assert (await limiter.consume(KIND, identifier, limit=5, window_seconds=900)).allowed is True


@pytest.mark.anyio
async def test_concurrent_consumes_are_atomic(limiter: RateLimiter, clean_auth_state: None) -> None:
    identifier = make_test_email("concurrency")

    decisions = await asyncio.gather(
        *(limiter.consume(KIND, identifier, limit=5, window_seconds=900) for _ in range(10))
    )

    assert sum(1 for decision in decisions if decision.allowed) == 5
    assert sum(1 for decision in decisions if not decision.allowed) == 5


@pytest.mark.anyio
async def test_bucket_keys_are_hmac_protected(
    limiter: RateLimiter, migrator_connection: asyncpg.Connection, clean_auth_state: None
) -> None:
    identifier = make_test_email("hmac")
    await limiter.consume(KIND, identifier, limit=5, window_seconds=900)

    rows = await migrator_connection.fetch("SELECT bucket_key FROM app.auth_rate_limit_buckets")

    assert rows
    for row in rows:
        stored = bytes(row["bucket_key"])
        assert len(stored) == 32
        assert identifier.encode() not in stored
