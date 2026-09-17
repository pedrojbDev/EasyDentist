from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg
import pytest
from conftest import SeededTenants
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.models import MembershipInvitation
from app.core.context import TenantContext
from app.core.database import create_session_factory
from app.core.errors import NotFoundError, translate_integrity_error
from app.core.tenancy import tenant_transaction


@pytest.mark.anyio
async def test_cross_tenant_reference_is_translated_to_not_found(
    app_engine: AsyncEngine,
    seeded_tenants: SeededTenants,
    migrator_connection: asyncpg.Connection,
) -> None:
    session_factory = create_session_factory(app_engine)
    context_a = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)
    invitation = MembershipInvitation(
        clinic_id=seeded_tenants.clinic_a,
        membership_id=seeded_tenants.membership_b,
        email="invitee@example.com",
        token_hash=uuid4().bytes,
        expires_at=datetime.now(UTC) + timedelta(hours=72),
    )

    with pytest.raises(IntegrityError) as excinfo:
        async with tenant_transaction(session_factory, context_a) as session:
            session.add(invitation)
            await session.flush()

    translated = translate_integrity_error(excinfo.value)

    assert isinstance(translated, NotFoundError)
    persisted = await migrator_connection.fetchval(
        "SELECT count(*) FROM app.membership_invitations "
        "WHERE clinic_id = $1 AND membership_id = $2",
        seeded_tenants.clinic_a,
        seeded_tenants.membership_b,
    )
    assert persisted == 0
