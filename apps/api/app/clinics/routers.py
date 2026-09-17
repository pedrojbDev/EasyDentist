from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import DBAPIError

from app.auth.dependencies import (
    AuthSettingsDep,
    EmailSenderDep,
    PrincipalDep,
    SessionFactoryDep,
    require_csrf,
)
from app.auth.emails import EmailOutboxService
from app.auth.templates import (
    TEAM_INVITATION_TEMPLATE,
    email_idempotency_key,
    role_label,
    team_invitation_message,
)
from app.auth.tokens import generate_token
from app.clinics.dependencies import MembershipDep
from app.clinics.rbac import Permission, Role, require_permission, role_allows
from app.clinics.repositories.clinic_repository import ClinicRepository
from app.clinics.repositories.clinic_settings_repository import ClinicSettingsRepository
from app.clinics.repositories.membership_repository import MembershipRepository
from app.clinics.schemas import (
    ClinicResponse,
    ClinicSettingsResponse,
    ClinicSettingsUpdateRequest,
    ClinicUpdateRequest,
    MembershipInvitationRequest,
    MembershipInvitationResponse,
    MembershipResponse,
    MembershipRoleUpdateRequest,
)
from app.clinics.services import MembershipService, translate_membership_error
from app.core.context import UserContext
from app.core.errors import NotFoundError
from app.core.tenancy import tenant_transaction, user_transaction
from app.platform.rate_limit import enforce_recovery_rate_limit
from app.users.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api/v1/clinics", tags=["clinics"], dependencies=[Depends(require_csrf)])


@router.get("", response_model=list[ClinicResponse])
async def list_clinics(
    principal: PrincipalDep, session_factory: SessionFactoryDep
) -> list[ClinicResponse]:
    context = UserContext(user_id=principal.user_id)
    async with user_transaction(session_factory, context) as session:
        memberships = await MembershipRepository(session).list_for_user(context)
        clinics = await ClinicRepository(session).list_for_user(context)

    roles = {
        membership.clinic_id: membership.role
        for membership in memberships
        if membership.status == "ACTIVE"
    }
    responses: list[ClinicResponse] = []
    for clinic in clinics:
        role = roles.get(clinic.id)
        if role is None:
            continue
        responses.append(
            ClinicResponse(
                id=clinic.id,
                slug=clinic.slug,
                legal_name=clinic.legal_name,
                status=clinic.status,
                role=Role(role),
            )
        )
    return responses


@router.get("/{clinic_id}", response_model=ClinicResponse)
async def get_clinic(
    membership: MembershipDep, session_factory: SessionFactoryDep
) -> ClinicResponse:
    async with tenant_transaction(session_factory, membership.context) as session:
        clinic = await ClinicRepository(session).get(membership.context)
    if clinic is None:
        raise NotFoundError("clinic not found")
    return ClinicResponse(
        id=clinic.id,
        slug=clinic.slug,
        legal_name=clinic.legal_name,
        status=clinic.status,
        role=membership.role,
    )


@router.patch("/{clinic_id}", response_model=ClinicResponse)
async def update_clinic(
    payload: ClinicUpdateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> ClinicResponse:
    require_permission(membership.role, Permission.CLINIC_UPDATE_LEGAL_NAME)
    async with tenant_transaction(session_factory, membership.context) as session:
        clinic = await ClinicRepository(session).update_legal_name(
            membership.context, payload.legal_name
        )
    if clinic is None:
        raise NotFoundError("clinic not found")
    return ClinicResponse(
        id=clinic.id,
        slug=clinic.slug,
        legal_name=clinic.legal_name,
        status=clinic.status,
        role=membership.role,
    )


@router.get("/{clinic_id}/settings", response_model=ClinicSettingsResponse)
async def get_clinic_settings(
    membership: MembershipDep, session_factory: SessionFactoryDep
) -> ClinicSettingsResponse:
    require_permission(membership.role, Permission.SETTINGS_READ)
    async with tenant_transaction(session_factory, membership.context) as session:
        settings = await ClinicSettingsRepository(session).get(membership.context)
    if settings is None:
        raise NotFoundError("clinic settings not found")
    return ClinicSettingsResponse(
        clinic_id=settings.clinic_id,
        display_name=settings.display_name,
        timezone=settings.timezone,
        locale=settings.locale,
        currency=settings.currency,
    )


@router.patch("/{clinic_id}/settings", response_model=ClinicSettingsResponse)
async def update_clinic_settings(
    payload: ClinicSettingsUpdateRequest,
    membership: MembershipDep,
    session_factory: SessionFactoryDep,
) -> ClinicSettingsResponse:
    require_permission(membership.role, Permission.SETTINGS_UPDATE)
    async with tenant_transaction(session_factory, membership.context) as session:
        settings = await ClinicSettingsRepository(session).update(
            membership.context,
            display_name=payload.display_name,
            timezone=payload.timezone,
            locale=payload.locale,
            currency=payload.currency,
        )
    if settings is None:
        raise NotFoundError("clinic settings not found")
    return ClinicSettingsResponse(
        clinic_id=settings.clinic_id,
        display_name=settings.display_name,
        timezone=settings.timezone,
        locale=settings.locale,
        currency=settings.currency,
    )


@router.get(
    "/{clinic_id}/memberships",
    response_model=list[MembershipResponse],
    response_model_exclude_none=True,
)
async def list_memberships(
    membership: MembershipDep, session_factory: SessionFactoryDep
) -> list[MembershipResponse]:
    require_permission(membership.role, Permission.MEMBERSHIPS_READ)
    show_contact = role_allows(membership.role, Permission.MEMBERSHIPS_READ_CONTACT)
    async with tenant_transaction(session_factory, membership.context) as session:
        rows = await MembershipRepository(session).list_for_clinic(membership.context)
        emails: dict[UUID, str] = {}
        if show_contact:
            users = await UserRepository(session).list_by_ids([row.user_id for row in rows])
            emails = {user.id: user.email for user in users}
    return [
        MembershipResponse(
            id=row.id,
            user_id=row.user_id,
            role=Role(row.role),
            status=row.status,
            created_at=row.created_at,
            email=emails.get(row.user_id) if show_contact else None,
        )
        for row in rows
    ]


@router.patch(
    "/{clinic_id}/memberships/{membership_id}",
    response_model=MembershipResponse,
    response_model_exclude_none=True,
)
async def update_membership_role(
    payload: MembershipRoleUpdateRequest,
    membership: MembershipDep,
    membership_id: UUID,
    session_factory: SessionFactoryDep,
) -> MembershipResponse:
    require_permission(membership.role, Permission.MEMBERSHIPS_MANAGE_ROLE)
    await MembershipService(session_factory).change_role(
        membership.context, membership_id=membership_id, new_role=payload.role.value
    )
    show_contact = role_allows(membership.role, Permission.MEMBERSHIPS_READ_CONTACT)
    async with tenant_transaction(session_factory, membership.context) as session:
        row = await MembershipRepository(session).get(membership.context, membership_id)
        email: str | None = None
        if row is not None and show_contact:
            user = await UserRepository(session).get(row.user_id)
            email = user.email if user is not None else None
    if row is None:
        raise NotFoundError("membership not found")
    return MembershipResponse(
        id=row.id,
        user_id=row.user_id,
        role=Role(row.role),
        status=row.status,
        created_at=row.created_at,
        email=email,
    )


@router.delete("/{clinic_id}/memberships/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_membership(
    membership: MembershipDep,
    membership_id: UUID,
    session_factory: SessionFactoryDep,
) -> None:
    require_permission(membership.role, Permission.MEMBERSHIPS_REMOVE)
    await MembershipService(session_factory).remove(membership.context, membership_id=membership_id)


@router.post(
    "/{clinic_id}/invitations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=MembershipInvitationResponse,
)
async def invite_member(
    payload: MembershipInvitationRequest,
    request: Request,
    membership: MembershipDep,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
    sender: EmailSenderDep,
) -> MembershipInvitationResponse:
    require_permission(membership.role, Permission.INVITATIONS_CREATE)
    account = payload.email.strip().lower()
    await enforce_recovery_rate_limit(request, settings, session_factory, account)

    token = generate_token()
    outbox = EmailOutboxService(session_factory, sender)
    try:
        async with tenant_transaction(session_factory, membership.context) as session:
            clinic = await ClinicRepository(session).get(membership.context)
            clinic_settings = await ClinicSettingsRepository(session).get(membership.context)
            if clinic_settings is not None:
                clinic_name = clinic_settings.display_name
            elif clinic is not None:
                clinic_name = clinic.legal_name
            else:
                clinic_name = "sua clínica"

            invited = await MembershipService(session_factory).invite(
                session,
                membership.context,
                email=account,
                role=payload.role.value,
                token=token,
            )
            subject, body = team_invitation_message(
                settings,
                token,
                clinic_name=clinic_name,
                role_label=role_label(payload.role.value),
            )
            await outbox.enqueue(
                session,
                idempotency_key=email_idempotency_key(TEAM_INVITATION_TEMPLATE, token),
                recipient=account,
                template=TEAM_INVITATION_TEMPLATE,
                subject=subject,
                body=body,
            )
    except DBAPIError as error:
        translated = translate_membership_error(error)
        if translated is not None:
            raise translated from error
        raise

    await outbox.deliver_pending()
    return MembershipInvitationResponse(
        membership_id=invited.membership_id,
        invitation_expires_at=invited.invitation_expires_at,
    )
