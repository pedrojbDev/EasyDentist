from __future__ import annotations

import pytest
from conftest import SeededTenants
from sqlalchemy.ext.asyncio import AsyncEngine

from app.clinics.repositories.membership_repository import MembershipRepository
from app.core.context import TenantContext, UserContext
from app.core.database import create_session_factory
from app.core.tenancy import tenant_transaction, user_transaction


@pytest.mark.anyio
async def test_list_for_user_returns_only_own_memberships(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = UserContext(user_id=seeded_tenants.user_a)

    async with user_transaction(session_factory, context) as session:
        memberships = await MembershipRepository(session).list_for_user(context)

    assert [membership.id for membership in memberships] == [seeded_tenants.membership_a]


@pytest.mark.anyio
async def test_list_for_clinic_returns_only_clinic_members(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        memberships = await MembershipRepository(session).list_for_clinic(context)

    assert [membership.id for membership in memberships] == [seeded_tenants.membership_a]


@pytest.mark.anyio
async def test_list_for_clinic_returns_nothing_for_cross_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_b)

    async with tenant_transaction(session_factory, context) as session:
        memberships = await MembershipRepository(session).list_for_clinic(context)

    assert list(memberships) == []


@pytest.mark.anyio
async def test_get_returns_membership_within_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        membership = await MembershipRepository(session).get(context, seeded_tenants.membership_a)

    assert membership is not None
    assert membership.id == seeded_tenants.membership_a


@pytest.mark.anyio
async def test_get_returns_none_for_membership_of_another_tenant(
    app_engine: AsyncEngine, seeded_tenants: SeededTenants
) -> None:
    session_factory = create_session_factory(app_engine)
    context = TenantContext(user_id=seeded_tenants.user_a, clinic_id=seeded_tenants.clinic_a)

    async with tenant_transaction(session_factory, context) as session:
        membership = await MembershipRepository(session).get(context, seeded_tenants.membership_b)

    assert membership is None
