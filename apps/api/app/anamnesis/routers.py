from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.anamnesis.schemas import (
    AnamnesisCreateRequest,
    AnamnesisListParams,
    AnamnesisListResponse,
    AnamnesisResponse,
    AnamnesisUpdateRequest,
)
from app.anamnesis.services import AnamnesisService
from app.auth.dependencies import SessionFactoryDep, require_csrf
from app.clinics.dependencies import MembershipDep
from app.clinics.rbac import Permission, require_permission

router = APIRouter(
    prefix="/api/v1/clinics", tags=["anamnesis"], dependencies=[Depends(require_csrf)]
)


@router.get(
    "/{clinic_id}/patients/{patient_id}/anamneses",
    response_model=AnamnesisListResponse,
)
async def list_anamneses(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    params: Annotated[AnamnesisListParams, Query()],
) -> AnamnesisListResponse:
    require_permission(membership.role, Permission.ANAMNESIS_READ)
    page = await AnamnesisService(session_factory).list_anamneses(
        membership.context, patient_id, params
    )
    return AnamnesisListResponse(
        items=[AnamnesisResponse.model_validate(anamnesis) for anamnesis in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/patients/{patient_id}/anamneses",
    response_model=AnamnesisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_anamnesis(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    payload: AnamnesisCreateRequest | None = None,
) -> AnamnesisResponse:
    require_permission(membership.role, Permission.ANAMNESIS_CREATE)
    request = payload if payload is not None else AnamnesisCreateRequest()
    anamnesis = await AnamnesisService(session_factory).create_draft(
        membership.context, patient_id, request
    )
    return AnamnesisResponse.model_validate(anamnesis)


@router.get(
    "/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}",
    response_model=AnamnesisResponse,
)
async def get_anamnesis(
    membership: MembershipDep,
    patient_id: UUID,
    anamnesis_id: UUID,
    session_factory: SessionFactoryDep,
) -> AnamnesisResponse:
    require_permission(membership.role, Permission.ANAMNESIS_READ)
    anamnesis = await AnamnesisService(session_factory).get_anamnesis(
        membership.context, patient_id, anamnesis_id
    )
    return AnamnesisResponse.model_validate(anamnesis)


@router.patch(
    "/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}",
    response_model=AnamnesisResponse,
)
async def update_anamnesis(
    payload: AnamnesisUpdateRequest,
    membership: MembershipDep,
    patient_id: UUID,
    anamnesis_id: UUID,
    session_factory: SessionFactoryDep,
) -> AnamnesisResponse:
    require_permission(membership.role, Permission.ANAMNESIS_UPDATE)
    anamnesis = await AnamnesisService(session_factory).update_draft(
        membership.context, patient_id, anamnesis_id, payload
    )
    return AnamnesisResponse.model_validate(anamnesis)


@router.post(
    "/{clinic_id}/patients/{patient_id}/anamneses/{anamnesis_id}/finalize",
    response_model=AnamnesisResponse,
)
async def finalize_anamnesis(
    membership: MembershipDep,
    patient_id: UUID,
    anamnesis_id: UUID,
    session_factory: SessionFactoryDep,
) -> AnamnesisResponse:
    require_permission(membership.role, Permission.ANAMNESIS_FINALIZE)
    anamnesis = await AnamnesisService(session_factory).finalize_anamnesis(
        membership.context, patient_id, anamnesis_id
    )
    return AnamnesisResponse.model_validate(anamnesis)
