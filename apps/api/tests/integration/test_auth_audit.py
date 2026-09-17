from __future__ import annotations

import json
import uuid

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.audit import AuthAuditService
from app.core.database import create_session_factory, transaction_scope

EVENT = "integration.audit"


@pytest.mark.anyio
async def test_record_persists_audit_event(
    app_engine: AsyncEngine,
    migrator_connection: asyncpg.Connection,
) -> None:
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(app_engine)
    metadata = {"auth_method": "password", "marker": uuid.uuid4().hex}

    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record(EVENT, user_id=None, metadata=metadata)

    row = await migrator_connection.fetchrow(
        "SELECT event_type, user_id, metadata FROM app.auth_audit_events "
        "WHERE event_type = $1 AND metadata->>'marker' = $2",
        EVENT,
        metadata["marker"],
    )

    assert row is not None
    assert row["user_id"] is None
    assert json.loads(row["metadata"]) == metadata

    await migrator_connection.execute(
        "DELETE FROM app.auth_audit_events WHERE event_type = $1 AND metadata->>'marker' = $2",
        EVENT,
        metadata["marker"],
    )
