from __future__ import annotations

import json
import uuid

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.auth.audit import AuthAuditService
from app.core.database import create_session_factory, transaction_scope


@pytest.mark.anyio
async def test_record_persists_only_allowlisted_metadata(
    app_engine: AsyncEngine,
    migrator_connection: asyncpg.Connection,
) -> None:
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(app_engine)
    session_id = str(uuid.uuid4())
    unknown_event = f"integration.audit.{uuid.uuid4().hex}"

    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record(
            "session_revoked",
            user_id=None,
            metadata={"session_id": session_id, "token": "must-not-persist"},
        )
        await AuthAuditService(session).record(
            unknown_event,
            user_id=None,
            metadata={"auth_method": "password", "marker": session_id},
        )

    row = await migrator_connection.fetchrow(
        "SELECT user_id, metadata FROM app.auth_audit_events WHERE event_type = 'session_revoked' "
        "AND metadata->>'session_id' = $1",
        session_id,
    )
    assert row is not None
    assert row["user_id"] is None
    assert json.loads(row["metadata"]) == {"session_id": session_id}

    unknown = await migrator_connection.fetchrow(
        "SELECT metadata FROM app.auth_audit_events WHERE event_type = $1", unknown_event
    )
    assert unknown is not None
    assert json.loads(unknown["metadata"]) == {}

    await migrator_connection.execute(
        "DELETE FROM app.auth_audit_events WHERE metadata->>'session_id' = $1 OR event_type = $2",
        session_id,
        unknown_event,
    )
