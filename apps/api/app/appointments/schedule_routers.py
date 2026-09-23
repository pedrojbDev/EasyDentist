from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.appointments.schedule_service import AgendaService
from app.appointments.schemas import (
    AgendaListParams,
    AppointmentCreateRequest,
    AppointmentHistoryListResponse,
    AppointmentListResponse,
    AppointmentRescheduleRequest,
    AppointmentResponse,
    AppointmentStatusRequest,
    AppointmentUpdateRequest,
    AvailabilityRequest,
    AvailabilityResponse,
    ScheduleBlockCancelRequest,
    ScheduleBlockCreateRequest,
    ScheduleBlockListParams,
    ScheduleBlockListResponse,
    ScheduleBlockResponse,
    ScheduleBlockUpdateRequest,
    WorkingHoursReplaceRequest,
    WorkingHoursResponse,
)
from app.auth.dependencies import SessionFactoryDep, require_csrf
from app.clinics.dependencies import MembershipDep
from app.clinics.rbac import Permission, Role, require_permission

router = APIRouter(prefix="/api/v1/clinics", tags=["agenda"], dependencies=[Depends(require_csrf)])


@router.get(
    "/{clinic_id}/professionals/{professional_id}/working-hours",
    response_model=WorkingHoursResponse,
)
async def get_working_hours(
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> WorkingHoursResponse:
    require_permission(membership.role, Permission.AGENDA_CATALOG_READ)
    return await AgendaService(session_factory).working_hours(membership.context, professional_id)


@router.put(
    "/{clinic_id}/professionals/{professional_id}/working-hours",
    response_model=WorkingHoursResponse,
)
async def replace_working_hours(
    payload: WorkingHoursReplaceRequest,
    membership: MembershipDep,
    professional_id: UUID,
    session_factory: SessionFactoryDep,
) -> WorkingHoursResponse:
    if membership.role not in {Role.OWNER, Role.ADMIN, Role.DENTIST}:
        require_permission(membership.role, Permission.AGENDA_RESOURCES_MANAGE)
    return await AgendaService(session_factory).replace_working_hours(
        membership.context, membership.role, professional_id, payload
    )


@router.get("/{clinic_id}/availability", response_model=AvailabilityResponse)
async def find_availability(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[AvailabilityRequest, Query()],
) -> AvailabilityResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).find_availability(membership.context, params)


@router.get("/{clinic_id}/schedule-blocks", response_model=ScheduleBlockListResponse)
async def list_schedule_blocks(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[ScheduleBlockListParams, Query()],
) -> ScheduleBlockListResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).list_schedule_blocks(membership.context, params)


@router.post(
    "/{clinic_id}/schedule-blocks",
    response_model=ScheduleBlockResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule_block(
    payload: ScheduleBlockCreateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> ScheduleBlockResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).create_schedule_block(
        membership.context, membership.role, payload
    )


@router.patch("/{clinic_id}/schedule-blocks/{block_id}", response_model=ScheduleBlockResponse)
async def update_schedule_block(
    payload: ScheduleBlockUpdateRequest,
    membership: MembershipDep,
    block_id: UUID,
    session_factory: SessionFactoryDep,
) -> ScheduleBlockResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).update_schedule_block(
        membership.context, membership.role, block_id, payload
    )


@router.post(
    "/{clinic_id}/schedule-blocks/{block_id}/cancel",
    response_model=ScheduleBlockResponse,
)
async def cancel_schedule_block(
    payload: ScheduleBlockCancelRequest,
    membership: MembershipDep,
    block_id: UUID,
    session_factory: SessionFactoryDep,
) -> ScheduleBlockResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).cancel_schedule_block(
        membership.context, membership.role, block_id, payload
    )


@router.get("/{clinic_id}/appointments", response_model=AppointmentListResponse)
async def list_appointments(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[AgendaListParams, Query()],
) -> AppointmentListResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).list_appointments(membership.context, params)


@router.post(
    "/{clinic_id}/appointments",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_appointment(
    payload: AppointmentCreateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> AppointmentResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).create_appointment(
        membership.context, membership.role, payload
    )


@router.get("/{clinic_id}/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    membership: MembershipDep,
    appointment_id: UUID,
    session_factory: SessionFactoryDep,
) -> AppointmentResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).get_appointment(membership.context, appointment_id)


@router.patch("/{clinic_id}/appointments/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    payload: AppointmentUpdateRequest,
    membership: MembershipDep,
    appointment_id: UUID,
    session_factory: SessionFactoryDep,
) -> AppointmentResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).update_appointment(
        membership.context, membership.role, appointment_id, payload
    )


@router.post(
    "/{clinic_id}/appointments/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
)
async def reschedule_appointment(
    payload: AppointmentRescheduleRequest,
    membership: MembershipDep,
    appointment_id: UUID,
    session_factory: SessionFactoryDep,
) -> AppointmentResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).reschedule_appointment(
        membership.context, membership.role, appointment_id, payload
    )


@router.post(
    "/{clinic_id}/appointments/{appointment_id}/status",
    response_model=AppointmentResponse,
)
async def change_appointment_status(
    payload: AppointmentStatusRequest,
    membership: MembershipDep,
    appointment_id: UUID,
    session_factory: SessionFactoryDep,
) -> AppointmentResponse:
    require_permission(membership.role, Permission.AGENDA_APPOINTMENTS_MANAGE)
    return await AgendaService(session_factory).change_appointment_status(
        membership.context, membership.role, appointment_id, payload
    )


@router.get(
    "/{clinic_id}/appointments/{appointment_id}/history",
    response_model=AppointmentHistoryListResponse,
)
async def appointment_history(
    membership: MembershipDep,
    appointment_id: UUID,
    session_factory: SessionFactoryDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AppointmentHistoryListResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).appointment_history(
        membership.context, appointment_id, limit=limit, offset=offset
    )


@router.get(
    "/{clinic_id}/patients/{patient_id}/appointments",
    response_model=AppointmentListResponse,
)
async def patient_appointments(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AppointmentListResponse:
    require_permission(membership.role, Permission.AGENDA_READ)
    return await AgendaService(session_factory).patient_appointments(
        membership.context, patient_id, limit=limit, offset=offset
    )
