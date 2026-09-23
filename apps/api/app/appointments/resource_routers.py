from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.appointments.resource_service import AgendaResourceService
from app.appointments.schemas import (
    AgendaProfessionalCreateRequest,
    AgendaProfessionalListParams,
    AgendaProfessionalListResponse,
    AgendaProfessionalResponse,
    AgendaProfessionalUpdateRequest,
    AgendaRoomCreateRequest,
    AgendaRoomListParams,
    AgendaRoomListResponse,
    AgendaRoomResponse,
    AgendaRoomUpdateRequest,
)
from app.auth.dependencies import SessionFactoryDep, require_csrf
from app.clinics.dependencies import MembershipDep
from app.clinics.rbac import Permission, require_permission

router = APIRouter(
    prefix="/api/v1/clinics", tags=["agenda-resources"], dependencies=[Depends(require_csrf)]
)


@router.get("/{clinic_id}/professionals", response_model=AgendaProfessionalListResponse)
async def list_professionals(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[AgendaProfessionalListParams, Query()],
) -> AgendaProfessionalListResponse:
    require_permission(membership.role, Permission.AGENDA_CATALOG_READ)
    page = await AgendaResourceService(session_factory).list_professionals(
        membership.context, params
    )
    return AgendaProfessionalListResponse(
        items=[AgendaProfessionalResponse.model_validate(item) for item in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/professionals",
    response_model=AgendaProfessionalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_professional(
    payload: AgendaProfessionalCreateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> AgendaProfessionalResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    professional = await AgendaResourceService(session_factory).create_professional(
        membership.context, payload
    )
    return AgendaProfessionalResponse.model_validate(professional)


@router.get(
    "/{clinic_id}/professionals/{professional_id}", response_model=AgendaProfessionalResponse
)
async def get_professional(
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaProfessionalResponse:
    require_permission(membership.role, Permission.AGENDA_CATALOG_READ)
    professional = await AgendaResourceService(session_factory).get_professional(
        membership.context, professional_id
    )
    return AgendaProfessionalResponse.model_validate(professional)


@router.patch(
    "/{clinic_id}/professionals/{professional_id}", response_model=AgendaProfessionalResponse
)
async def update_professional(
    payload: AgendaProfessionalUpdateRequest,
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaProfessionalResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    professional = await AgendaResourceService(session_factory).update_professional(
        membership.context, professional_id, payload
    )
    return AgendaProfessionalResponse.model_validate(professional)


@router.post(
    "/{clinic_id}/professionals/{professional_id}/archive",
    response_model=AgendaProfessionalResponse,
)
async def archive_professional(
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaProfessionalResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    professional = await AgendaResourceService(session_factory).archive_professional(
        membership.context, professional_id
    )
    return AgendaProfessionalResponse.model_validate(professional)


@router.post(
    "/{clinic_id}/professionals/{professional_id}/restore",
    response_model=AgendaProfessionalResponse,
)
async def restore_professional(
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaProfessionalResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    professional = await AgendaResourceService(session_factory).restore_professional(
        membership.context, professional_id
    )
    return AgendaProfessionalResponse.model_validate(professional)


@router.get("/{clinic_id}/rooms", response_model=AgendaRoomListResponse)
async def list_rooms(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[AgendaRoomListParams, Query()],
) -> AgendaRoomListResponse:
    require_permission(membership.role, Permission.AGENDA_CATALOG_READ)
    page = await AgendaResourceService(session_factory).list_rooms(membership.context, params)
    return AgendaRoomListResponse(
        items=[AgendaRoomResponse.model_validate(item) for item in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/rooms", response_model=AgendaRoomResponse, status_code=status.HTTP_201_CREATED
)
async def create_room(
    payload: AgendaRoomCreateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> AgendaRoomResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    room = await AgendaResourceService(session_factory).create_room(membership.context, payload)
    return AgendaRoomResponse.model_validate(room)


@router.get("/{clinic_id}/rooms/{room_id}", response_model=AgendaRoomResponse)
async def get_room(
    membership: MembershipDep,
    room_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaRoomResponse:
    require_permission(membership.role, Permission.AGENDA_CATALOG_READ)
    room = await AgendaResourceService(session_factory).get_room(membership.context, room_id)
    return AgendaRoomResponse.model_validate(room)


@router.patch("/{clinic_id}/rooms/{room_id}", response_model=AgendaRoomResponse)
async def update_room(
    payload: AgendaRoomUpdateRequest,
    membership: MembershipDep,
    room_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaRoomResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    room = await AgendaResourceService(session_factory).update_room(
        membership.context, room_id, payload
    )
    return AgendaRoomResponse.model_validate(room)


@router.post("/{clinic_id}/rooms/{room_id}/archive", response_model=AgendaRoomResponse)
async def archive_room(
    membership: MembershipDep,
    room_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaRoomResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    room = await AgendaResourceService(session_factory).archive_room(membership.context, room_id)
    return AgendaRoomResponse.model_validate(room)


@router.post("/{clinic_id}/rooms/{room_id}/restore", response_model=AgendaRoomResponse)
async def restore_room(
    membership: MembershipDep,
    room_id: UUID,
    session_factory: SessionFactoryDep,
) -> AgendaRoomResponse:
    require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    room = await AgendaResourceService(session_factory).restore_room(membership.context, room_id)
    return AgendaRoomResponse.model_validate(room)
