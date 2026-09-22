from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import SessionFactoryDep, require_csrf
from app.clinics.dependencies import MembershipDep
from app.clinics.rbac import Permission, require_permission
from app.patients.schemas import (
    PatientAlertCreateRequest,
    PatientAlertListParams,
    PatientAlertListResponse,
    PatientAlertResponse,
    PatientAlertUpdateRequest,
    PatientCreateRequest,
    PatientListParams,
    PatientListResponse,
    PatientResponse,
    PatientUpdateRequest,
)
from app.patients.services import PatientService

router = APIRouter(
    prefix="/api/v1/clinics", tags=["patients"], dependencies=[Depends(require_csrf)]
)


@router.get("/{clinic_id}/patients", response_model=PatientListResponse)
async def list_patients(
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
    params: Annotated[PatientListParams, Query()],
) -> PatientListResponse:
    require_permission(membership.role, Permission.PATIENTS_READ)
    page = await PatientService(session_factory).list_patients(membership.context, params)
    return PatientListResponse(
        items=[PatientResponse.model_validate(patient) for patient in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/patients",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient(
    payload: PatientCreateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> PatientResponse:
    require_permission(membership.role, Permission.PATIENTS_CREATE)
    patient = await PatientService(session_factory).create_patient(membership.context, payload)
    return PatientResponse.model_validate(patient)


@router.get("/{clinic_id}/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientResponse:
    require_permission(membership.role, Permission.PATIENTS_READ)
    patient = await PatientService(session_factory).get_patient(membership.context, patient_id)
    return PatientResponse.model_validate(patient)


@router.patch("/{clinic_id}/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
    payload: PatientUpdateRequest,
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientResponse:
    require_permission(membership.role, Permission.PATIENTS_UPDATE)
    patient = await PatientService(session_factory).update_patient(
        membership.context, patient_id, payload
    )
    return PatientResponse.model_validate(patient)


@router.post("/{clinic_id}/patients/{patient_id}/archive", response_model=PatientResponse)
async def archive_patient(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientResponse:
    require_permission(membership.role, Permission.PATIENTS_ARCHIVE)
    patient = await PatientService(session_factory).archive_patient(membership.context, patient_id)
    return PatientResponse.model_validate(patient)


@router.post("/{clinic_id}/patients/{patient_id}/restore", response_model=PatientResponse)
async def restore_patient(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientResponse:
    require_permission(membership.role, Permission.PATIENTS_ARCHIVE)
    patient = await PatientService(session_factory).restore_patient(membership.context, patient_id)
    return PatientResponse.model_validate(patient)


@router.get(
    "/{clinic_id}/patients/{patient_id}/alerts",
    response_model=PatientAlertListResponse,
)
async def list_patient_alerts(
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
    params: Annotated[PatientAlertListParams, Query()],
) -> PatientAlertListResponse:
    require_permission(membership.role, Permission.PATIENT_ALERTS_READ)
    page = await PatientService(session_factory).list_alerts(membership.context, patient_id, params)
    return PatientAlertListResponse(
        items=[PatientAlertResponse.model_validate(alert) for alert in page.items],
        total=page.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/{clinic_id}/patients/{patient_id}/alerts",
    response_model=PatientAlertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_alert(
    payload: PatientAlertCreateRequest,
    membership: MembershipDep,
    patient_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientAlertResponse:
    require_permission(membership.role, Permission.PATIENT_ALERTS_MANAGE)
    alert = await PatientService(session_factory).create_alert(
        membership.context, patient_id, payload
    )
    return PatientAlertResponse.model_validate(alert)


@router.patch(
    "/{clinic_id}/patients/{patient_id}/alerts/{alert_id}",
    response_model=PatientAlertResponse,
)
async def update_patient_alert(
    payload: PatientAlertUpdateRequest,
    membership: MembershipDep,
    patient_id: UUID,
    alert_id: UUID,
    session_factory: SessionFactoryDep,
) -> PatientAlertResponse:
    require_permission(membership.role, Permission.PATIENT_ALERTS_MANAGE)
    alert = await PatientService(session_factory).update_alert(
        membership.context, patient_id, alert_id, payload
    )
    return PatientAlertResponse.model_validate(alert)
