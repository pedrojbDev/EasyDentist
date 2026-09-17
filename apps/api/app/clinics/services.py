from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.tokens import token_digest
from app.core.context import TenantContext
from app.core.database import transaction_scope
from app.core.errors import (
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
    translate_integrity_error,
)

FUNCTION_RAISE_SQLSTATE = "P0001"


@dataclass(frozen=True, slots=True)
class InvitedMember:
    membership_id: UUID
    invitation_id: UUID
    user_id: UUID
    invitation_expires_at: datetime


def translate_membership_error(error: DBAPIError) -> DomainError | None:
    if isinstance(error, IntegrityError):
        return translate_integrity_error(error)
    if getattr(error.orig, "sqlstate", None) != FUNCTION_RAISE_SQLSTATE:
        return None
    message = str(error.orig)
    if "not_permitted" in message:
        return PermissionDeniedError("role does not allow this operation")
    if "last_owner" in message:
        return ConflictError("the last active owner cannot be removed or demoted")
    if "invalid_role" in message:
        return InvalidInputError("unknown role")
    if "membership_not_found" in message:
        return NotFoundError("membership not found")
    return None


class MembershipService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def invite(
        self,
        session: AsyncSession,
        context: TenantContext,
        *,
        email: str,
        role: str,
        token: str,
    ) -> InvitedMember:
        row = (
            await session.execute(
                text(
                    "SELECT membership_id, invitation_id, user_id, invitation_expires_at "
                    "FROM app.create_member_invitation("
                    ":clinic_id, :actor_user_id, :email, :role, :token_hash)"
                ),
                {
                    "clinic_id": context.clinic_id,
                    "actor_user_id": context.user_id,
                    "email": email,
                    "role": role,
                    "token_hash": token_digest(token),
                },
            )
        ).one()
        return InvitedMember(
            membership_id=row.membership_id,
            invitation_id=row.invitation_id,
            user_id=row.user_id,
            invitation_expires_at=row.invitation_expires_at,
        )

    async def change_role(
        self, context: TenantContext, *, membership_id: UUID, new_role: str
    ) -> None:
        await self._call(
            "SELECT membership_id, old_role, new_role "
            "FROM app.change_member_role(:clinic_id, :actor_user_id, :membership_id, :new_role)",
            {
                "clinic_id": context.clinic_id,
                "actor_user_id": context.user_id,
                "membership_id": membership_id,
                "new_role": new_role,
            },
        )

    async def remove(self, context: TenantContext, *, membership_id: UUID) -> None:
        await self._call(
            "SELECT membership_id "
            "FROM app.remove_membership(:clinic_id, :actor_user_id, :membership_id)",
            {
                "clinic_id": context.clinic_id,
                "actor_user_id": context.user_id,
                "membership_id": membership_id,
            },
        )

    async def _call(self, statement: str, parameters: dict[str, object]) -> None:
        try:
            async with transaction_scope(self._session_factory) as session:
                await session.execute(text(statement), parameters)
        except DBAPIError as error:
            translated = translate_membership_error(error)
            if translated is not None:
                raise translated from error
            raise
