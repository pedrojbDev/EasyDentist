from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.emails import EmailOutboxService
from app.core.clock import utcnow
from app.core.database import create_session_factory, transaction_scope

TEMPLATE = "integration-test"


class FakeSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = False

    async def send(self, recipient: str, subject: str, body: str) -> None:
        if self.fail:
            raise RuntimeError("smtp is down")
        self.sent.append((recipient, subject, body))


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
async def session_factory(app_async_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(app_async_url, pool_size=2, max_overflow=0)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


@pytest.fixture
async def cleanup_outbox(
    migrator_connection: asyncpg.Connection,
) -> AsyncIterator[list[str]]:
    keys: list[str] = []
    try:
        yield keys
    finally:
        if keys:
            await migrator_connection.execute(
                "DELETE FROM app.email_outbox WHERE idempotency_key = ANY($1::text[])", keys
            )


async def enqueue(
    session_factory: async_sessionmaker[AsyncSession],
    sender: FakeSender,
    *,
    key: str,
    clock: MutableClock | None = None,
) -> EmailOutboxService:
    service = EmailOutboxService(session_factory, sender, clock=clock or utcnow)
    async with transaction_scope(session_factory) as session:
        await service.enqueue(
            session,
            idempotency_key=key,
            recipient="owner@example.com",
            template=TEMPLATE,
            subject="Assunto",
            body="Corpo",
        )
    return service


@pytest.mark.anyio
async def test_enqueue_creates_pending_row(
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
    cleanup_outbox: list[str],
) -> None:
    key = f"{TEMPLATE}:{uuid.uuid4().hex}"
    cleanup_outbox.append(key)
    sender = FakeSender()

    await enqueue(session_factory, sender, key=key)

    row = await migrator_connection.fetchrow(
        "SELECT status, attempt_count, payload FROM app.email_outbox WHERE idempotency_key = $1",
        key,
    )
    assert row is not None
    assert row["status"] == "PENDING"
    assert row["attempt_count"] == 0
    assert row["payload"] == '{"body": "Corpo", "subject": "Assunto"}'


@pytest.mark.anyio
async def test_deliver_marks_sent(
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
    cleanup_outbox: list[str],
) -> None:
    key = f"{TEMPLATE}:{uuid.uuid4().hex}"
    cleanup_outbox.append(key)
    sender = FakeSender()
    service = await enqueue(session_factory, sender, key=key)

    await service.deliver_pending()

    assert sender.sent == [("owner@example.com", "Assunto", "Corpo")]
    row = await migrator_connection.fetchrow(
        "SELECT status, sent_at FROM app.email_outbox WHERE idempotency_key = $1", key
    )
    assert row["status"] == "SENT"
    assert row["sent_at"] is not None


@pytest.mark.anyio
async def test_deliver_retries_with_backoff(
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
    cleanup_outbox: list[str],
) -> None:
    key = f"{TEMPLATE}:{uuid.uuid4().hex}"
    cleanup_outbox.append(key)
    sender = FakeSender()
    sender.fail = True
    clock = MutableClock(datetime(2026, 9, 17, 12, 0, tzinfo=UTC))
    service = await enqueue(session_factory, sender, key=key, clock=clock)

    await service.deliver_pending()
    row = await migrator_connection.fetchrow(
        "SELECT status, attempt_count, next_attempt_at FROM app.email_outbox "
        "WHERE idempotency_key = $1",
        key,
    )
    assert row["status"] == "PENDING"
    assert row["attempt_count"] == 1
    assert row["next_attempt_at"] == clock.now + timedelta(seconds=30)

    await service.deliver_pending()
    row = await migrator_connection.fetchrow(
        "SELECT attempt_count FROM app.email_outbox WHERE idempotency_key = $1", key
    )
    assert row["attempt_count"] == 1

    clock.now += timedelta(seconds=31)
    sender.fail = False
    await service.deliver_pending()

    row = await migrator_connection.fetchrow(
        "SELECT status, attempt_count FROM app.email_outbox WHERE idempotency_key = $1", key
    )
    assert row["status"] == "SENT"
    assert row["attempt_count"] == 1


@pytest.mark.anyio
async def test_deliver_gives_up_after_max_attempts(
    session_factory: async_sessionmaker[AsyncSession],
    migrator_connection: asyncpg.Connection,
    cleanup_outbox: list[str],
) -> None:
    key = f"{TEMPLATE}:{uuid.uuid4().hex}"
    cleanup_outbox.append(key)
    sender = FakeSender()
    sender.fail = True
    clock = MutableClock(datetime(2026, 9, 17, 12, 0, tzinfo=UTC))
    service = await enqueue(session_factory, sender, key=key, clock=clock)

    for _ in range(5):
        await service.deliver_pending()
        clock.now += timedelta(hours=1)

    row = await migrator_connection.fetchrow(
        "SELECT status, attempt_count, next_attempt_at FROM app.email_outbox "
        "WHERE idempotency_key = $1",
        key,
    )
    assert row["status"] == "FAILED"
    assert row["attempt_count"] == 5
    assert row["next_attempt_at"] is None
