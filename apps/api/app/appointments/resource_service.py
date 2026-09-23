from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.appointments.models import AgendaProfessional, AgendaRoom
from app.appointments.repositories.resource_repository import AgendaResourceRepository
from app.appointments.schemas import (
    AgendaProfessionalCreateRequest,
    AgendaProfessionalListParams,
    AgendaProfessionalUpdateRequest,
    AgendaResourceStatus,
    AgendaRoomCreateRequest,
    AgendaRoomListParams,
    AgendaRoomUpdateRequest,
)
from app.clinics.audit import ClinicAuditService
from app.clinics.models import ClinicSettings, Membership
from app.core.clock import utcnow
from app.core.context import TenantContext
from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    translate_integrity_error,
)
from app.core.tenancy import tenant_transaction


@dataclass(frozen=True, slots=True)
class AgendaResourcePage:
    items: list[AgendaProfessional] | list[AgendaRoom]
    total: int


class AgendaResourceService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock

    async def list_professionals(
        self, context: TenantContext, params: AgendaProfessionalListParams
    ) -> AgendaResourcePage:
        async with tenant_transaction(self._session_factory, context) as session:
            items, total = await AgendaResourceRepository(session).list_professionals(
                context, status=params.status, limit=params.limit, offset=params.offset
            )
        return AgendaResourcePage(list(items), total)

    async def get_professional(
        self, context: TenantContext, professional_id: UUID
    ) -> AgendaProfessional:
        async with tenant_transaction(self._session_factory, context) as session:
            professional = await AgendaResourceRepository(session).get_professional(
                context, professional_id
            )
        if professional is None:
            raise NotFoundError("agenda professional not found")
        return professional

    async def create_professional(
        self, context: TenantContext, payload: AgendaProfessionalCreateRequest
    ) -> AgendaProfessional:
        values = payload.model_dump()
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            repository = AgendaResourceRepository(session)
            await self._validate_membership(session, context, values.get("membership_id"))
            try:
                professional = await repository.add_professional(
                    context, **values, updated_at=self._clock()
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            await ClinicAuditService(session).record(
                "agenda.professional.created",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_professional",
                entity_id=professional.id,
                metadata={
                    "status": professional.status,
                    "has_member": professional.membership_id is not None,
                },
            )
        return professional

    async def update_professional(
        self,
        context: TenantContext,
        professional_id: UUID,
        payload: AgendaProfessionalUpdateRequest,
    ) -> AgendaProfessional:
        updates = payload.model_dump(exclude_unset=True)
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            repository = AgendaResourceRepository(session)
            current = await repository.get_professional(context, professional_id)
            if current is None:
                raise NotFoundError("agenda professional not found")
            if "membership_id" in updates:
                await self._validate_membership(session, context, updates["membership_id"])
            if not updates:
                return current
            updates["updated_at"] = self._clock()
            try:
                updated = await repository.update_professional(context, professional_id, **updates)
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            if updated is None:
                raise NotFoundError("agenda professional not found")
            await ClinicAuditService(session).record(
                "agenda.professional.updated",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_professional",
                entity_id=updated.id,
                metadata={
                    "status": updated.status,
                    "has_member": updated.membership_id is not None,
                },
            )
        return updated

    async def archive_professional(
        self, context: TenantContext, professional_id: UUID
    ) -> AgendaProfessional:
        return await self._set_professional_archived(context, professional_id, archived=True)

    async def restore_professional(
        self, context: TenantContext, professional_id: UUID
    ) -> AgendaProfessional:
        return await self._set_professional_archived(context, professional_id, archived=False)

    async def _set_professional_archived(
        self, context: TenantContext, professional_id: UUID, *, archived: bool
    ) -> AgendaProfessional:
        target = AgendaResourceStatus.ARCHIVED if archived else AgendaResourceStatus.ACTIVE
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            repository = AgendaResourceRepository(session)
            current = await repository.get_professional(context, professional_id)
            if current is None:
                raise NotFoundError("agenda professional not found")
            if current.status == target.value:
                return current
            if archived and await repository.has_pending_professional_appointments(
                context, professional_id
            ):
                raise ConflictError(
                    "resolve pending appointments before archiving this professional"
                )
            now = self._clock()
            updated = await repository.update_professional(
                context,
                professional_id,
                status=target.value,
                archived_at=now if archived else None,
                updated_at=now,
            )
            if updated is None:
                raise NotFoundError("agenda professional not found")
            await ClinicAuditService(session).record(
                "agenda.professional.archived" if archived else "agenda.professional.restored",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_professional",
                entity_id=updated.id,
            )
        return updated

    async def list_rooms(
        self, context: TenantContext, params: AgendaRoomListParams
    ) -> AgendaResourcePage:
        async with tenant_transaction(self._session_factory, context) as session:
            items, total = await AgendaResourceRepository(session).list_rooms(
                context, status=params.status, limit=params.limit, offset=params.offset
            )
        return AgendaResourcePage(list(items), total)

    async def get_room(self, context: TenantContext, room_id: UUID) -> AgendaRoom:
        async with tenant_transaction(self._session_factory, context) as session:
            room = await AgendaResourceRepository(session).get_room(context, room_id)
        if room is None:
            raise NotFoundError("agenda room not found")
        return room

    async def create_room(
        self, context: TenantContext, payload: AgendaRoomCreateRequest
    ) -> AgendaRoom:
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            try:
                room = await AgendaResourceRepository(session).add_room(
                    context, name=payload.name, updated_at=self._clock()
                )
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            await ClinicAuditService(session).record(
                "agenda.room.created",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_room",
                entity_id=room.id,
                metadata={"status": room.status},
            )
        return room

    async def update_room(
        self, context: TenantContext, room_id: UUID, payload: AgendaRoomUpdateRequest
    ) -> AgendaRoom:
        updates = payload.model_dump(exclude_unset=True)
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            repository = AgendaResourceRepository(session)
            current = await repository.get_room(context, room_id)
            if current is None:
                raise NotFoundError("agenda room not found")
            if not updates:
                return current
            updates["updated_at"] = self._clock()
            try:
                updated = await repository.update_room(context, room_id, **updates)
            except IntegrityError as error:
                raise translate_integrity_error(error) from error
            if updated is None:
                raise NotFoundError("agenda room not found")
            await ClinicAuditService(session).record(
                "agenda.room.updated",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_room",
                entity_id=updated.id,
                metadata={"status": updated.status},
            )
        return updated

    async def archive_room(self, context: TenantContext, room_id: UUID) -> AgendaRoom:
        return await self._set_room_archived(context, room_id, archived=True)

    async def restore_room(self, context: TenantContext, room_id: UUID) -> AgendaRoom:
        return await self._set_room_archived(context, room_id, archived=False)

    async def _set_room_archived(
        self, context: TenantContext, room_id: UUID, *, archived: bool
    ) -> AgendaRoom:
        target = AgendaResourceStatus.ARCHIVED if archived else AgendaResourceStatus.ACTIVE
        async with tenant_transaction(self._session_factory, context) as session:
            await self._lock_agenda(session, context)
            repository = AgendaResourceRepository(session)
            current = await repository.get_room(context, room_id)
            if current is None:
                raise NotFoundError("agenda room not found")
            if current.status == target.value:
                return current
            if archived and await repository.has_pending_room_appointments(context, room_id):
                raise ConflictError("resolve pending appointments before archiving this room")
            now = self._clock()
            updated = await repository.update_room(
                context,
                room_id,
                status=target.value,
                archived_at=now if archived else None,
                updated_at=now,
            )
            if updated is None:
                raise NotFoundError("agenda room not found")
            await ClinicAuditService(session).record(
                "agenda.room.archived" if archived else "agenda.room.restored",
                clinic_id=context.clinic_id,
                actor_user_id=context.user_id,
                entity_type="agenda_room",
                entity_id=updated.id,
            )
        return updated

    @staticmethod
    async def _lock_agenda(session: AsyncSession, context: TenantContext) -> None:
        settings = await session.scalar(
            select(ClinicSettings)
            .where(ClinicSettings.clinic_id == context.clinic_id)
            .with_for_update()
        )
        if settings is None:
            raise NotFoundError("clinic settings not found")

    @staticmethod
    async def _validate_membership(
        session: AsyncSession, context: TenantContext, membership_id: object
    ) -> None:
        if membership_id is None:
            return
        if not isinstance(membership_id, UUID):
            raise InvalidInputError("membership_id must be a UUID")
        membership = await session.scalar(
            select(Membership)
            .where(Membership.clinic_id == context.clinic_id, Membership.id == membership_id)
            .with_for_update()
        )
        if membership is None:
            raise NotFoundError("clinic member not found")
        if membership.status != "ACTIVE" or membership.role not in {"DENTIST", "OWNER"}:
            raise InvalidInputError("linked member must be an active DENTIST or OWNER")
