from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from app.auth.dependencies import PrincipalDep, SessionFactoryDep
from app.clinics.rbac import Role
from app.clinics.repositories.membership_repository import MembershipRepository
from app.core.context import TenantContext, UserContext
from app.core.errors import NotFoundError
from app.core.tenancy import user_transaction

MEMBERSHIP_CACHE_KEY = "clinic_memberships"


@dataclass(frozen=True, slots=True)
class ClinicMembership:
    context: TenantContext
    role: Role


async def get_membership(
    request: Request,
    clinic_id: UUID,
    principal: PrincipalDep,
    session_factory: SessionFactoryDep,
) -> ClinicMembership:
    cache: dict[tuple[UUID, UUID], ClinicMembership] | None = getattr(
        request.state, MEMBERSHIP_CACHE_KEY, None
    )
    if cache is None:
        cache = {}
        setattr(request.state, MEMBERSHIP_CACHE_KEY, cache)

    key = (principal.user_id, clinic_id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    context = UserContext(user_id=principal.user_id)
    async with user_transaction(session_factory, context) as session:
        memberships = await MembershipRepository(session).list_for_user(context)
    membership = next(
        (row for row in memberships if row.clinic_id == clinic_id and row.status == "ACTIVE"),
        None,
    )
    if membership is None:
        raise NotFoundError("clinic not found")

    resolved = ClinicMembership(
        context=TenantContext(user_id=principal.user_id, clinic_id=clinic_id),
        role=Role(membership.role),
    )
    cache[key] = resolved
    return resolved


MembershipDep = Annotated[ClinicMembership, Depends(get_membership)]
