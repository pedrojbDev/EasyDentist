from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.appointments.models import AgendaProfessional, AgendaRoom, Appointment, ScheduleEvent
from app.appointments.schemas import AgendaResourceStatus
from app.core.context import TenantContext
from app.core.tenancy import ensure_context_matches


class AgendaResourceRepository:
    """All resource operations are tenant-scoped and require a tenant transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_professionals(
        self,
        context: TenantContext,
        *,
        status: AgendaResourceStatus,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AgendaProfessional], int]:
        ensure_context_matches(self._session, context)
        filters = [
            AgendaProfessional.clinic_id == context.clinic_id,
            AgendaProfessional.status == status.value,
        ]
        statement: Select[tuple[AgendaProfessional]] = (
            select(AgendaProfessional)
            .where(*filters)
            .order_by(AgendaProfessional.name, AgendaProfessional.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(AgendaProfessional).where(*filters)
        )
        return rows, int(total or 0)

    async def get_professional(
        self, context: TenantContext, professional_id: UUID
    ) -> AgendaProfessional | None:
        ensure_context_matches(self._session, context)
        result = await self._session.execute(
            select(AgendaProfessional).where(
                AgendaProfessional.id == professional_id,
                AgendaProfessional.clinic_id == context.clinic_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_professional(
        self, context: TenantContext, **fields: object
    ) -> AgendaProfessional:
        ensure_context_matches(self._session, context)
        resource = AgendaProfessional(clinic_id=context.clinic_id, **fields)
        self._session.add(resource)
        await self._session.flush()
        return resource

    async def update_professional(
        self, context: TenantContext, professional_id: UUID, **fields: object
    ) -> AgendaProfessional | None:
        ensure_context_matches(self._session, context)
        if not fields:
            return await self.get_professional(context, professional_id)
        result = await self._session.execute(
            update(AgendaProfessional)
            .where(
                AgendaProfessional.id == professional_id,
                AgendaProfessional.clinic_id == context.clinic_id,
            )
            .values(**fields)
            .returning(AgendaProfessional)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def list_rooms(
        self,
        context: TenantContext,
        *,
        status: AgendaResourceStatus,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[AgendaRoom], int]:
        ensure_context_matches(self._session, context)
        filters = [AgendaRoom.clinic_id == context.clinic_id, AgendaRoom.status == status.value]
        statement: Select[tuple[AgendaRoom]] = (
            select(AgendaRoom)
            .where(*filters)
            .order_by(AgendaRoom.name, AgendaRoom.id)
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(statement)).scalars().all()
        total = await self._session.scalar(
            select(func.count()).select_from(AgendaRoom).where(*filters)
        )
        return rows, int(total or 0)

    async def get_room(self, context: TenantContext, room_id: UUID) -> AgendaRoom | None:
        ensure_context_matches(self._session, context)
        result = await self._session.execute(
            select(AgendaRoom).where(
                AgendaRoom.id == room_id,
                AgendaRoom.clinic_id == context.clinic_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_room(self, context: TenantContext, **fields: object) -> AgendaRoom:
        ensure_context_matches(self._session, context)
        resource = AgendaRoom(clinic_id=context.clinic_id, **fields)
        self._session.add(resource)
        await self._session.flush()
        return resource

    async def update_room(
        self, context: TenantContext, room_id: UUID, **fields: object
    ) -> AgendaRoom | None:
        ensure_context_matches(self._session, context)
        if not fields:
            return await self.get_room(context, room_id)
        result = await self._session.execute(
            update(AgendaRoom)
            .where(AgendaRoom.id == room_id, AgendaRoom.clinic_id == context.clinic_id)
            .values(**fields)
            .returning(AgendaRoom)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def has_pending_professional_appointments(
        self, context: TenantContext, professional_id: UUID
    ) -> bool:
        return await self._has_pending_appointments(
            context, ScheduleEvent.professional_id == professional_id
        )

    async def has_pending_room_appointments(self, context: TenantContext, room_id: UUID) -> bool:
        return await self._has_pending_appointments(context, ScheduleEvent.room_id == room_id)

    async def _has_pending_appointments(
        self, context: TenantContext, resource_filter: ColumnElement[bool]
    ) -> bool:
        ensure_context_matches(self._session, context)
        pending_statuses = ("SCHEDULED", "CONFIRMED", "CHECKED_IN", "IN_PROGRESS")
        statement = (
            select(Appointment.id)
            .join(
                ScheduleEvent,
                (Appointment.clinic_id == ScheduleEvent.clinic_id)
                & (Appointment.schedule_event_id == ScheduleEvent.id),
            )
            .where(
                Appointment.clinic_id == context.clinic_id,
                Appointment.status.in_(pending_statuses),
                resource_filter,
            )
            .limit(1)
        )
        return await self._session.scalar(statement) is not None
