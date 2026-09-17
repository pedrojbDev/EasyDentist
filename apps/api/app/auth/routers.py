from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.action_tokens import (
    EMAIL_VERIFICATION_TTL,
    PASSWORD_RESET_TTL,
    PURPOSE_EMAIL_VERIFICATION,
    PURPOSE_PASSWORD_RESET,
    ActionTokenService,
)
from app.auth.audit import AuthAuditService
from app.auth.authenticator import LocalPasswordAuthenticator
from app.auth.cookies import clear_session_cookie, set_csrf_cookie, set_session_cookie
from app.auth.csrf import ANONYMOUS_BINDING, CsrfService
from app.auth.dependencies import (
    AuthSettingsDep,
    EmailSenderDep,
    PrincipalDep,
    SessionFactoryDep,
    require_csrf,
    resolve_principal,
)
from app.auth.emails import EmailOutboxService
from app.auth.invitations import InvitationService
from app.auth.passwords import PasswordHasher
from app.auth.ratelimit import (
    LOGIN_ACCOUNT_LIMIT,
    LOGIN_ACCOUNT_WINDOW_SECONDS,
    LOGIN_IP_LIMIT,
    LOGIN_IP_WINDOW_SECONDS,
    RateLimiter,
)
from app.auth.repositories.password_credential_repository import PasswordCredentialRepository
from app.auth.repositories.session_repository import SessionRepository
from app.auth.schemas import (
    CsrfTokenResponse,
    EmailVerificationConfirmRequest,
    InvitationAcceptRequest,
    LoginRequest,
    LoginResponse,
    PasswordForgotRequest,
    PasswordResetRequest,
    SessionResponse,
    UserResponse,
)
from app.auth.sessions import SessionService
from app.auth.templates import (
    EMAIL_VERIFICATION_TEMPLATE,
    PASSWORD_RESET_TEMPLATE,
    email_idempotency_key,
    email_verification_message,
    password_reset_message,
)
from app.core.clock import utcnow
from app.core.database import transaction_scope
from app.platform.network import client_ip
from app.platform.rate_limit import enforce_recovery_rate_limit
from app.users.repositories.user_repository import UserRepository

router = APIRouter(prefix="/api/v1/auth", tags=["auth"], dependencies=[Depends(require_csrf)])
invitations_router = APIRouter(
    prefix="/api/v1/invitations", tags=["auth"], dependencies=[Depends(require_csrf)]
)


async def user_response(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> UserResponse:
    async with transaction_scope(session_factory) as session:
        user = await UserRepository(session).get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return UserResponse(
        id=user.id,
        email=user.email,
        email_verified_at=user.email_verified_at,
        status=user.status,
    )


@router.get("/csrf", response_model=CsrfTokenResponse)
async def issue_csrf_token(
    request: Request,
    response: Response,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> CsrfTokenResponse:
    principal = await resolve_principal(request, settings, session_factory)
    binding = str(principal.session_id) if principal is not None else ANONYMOUS_BINDING
    value = CsrfService(settings.auth_secret).issue(binding)
    set_csrf_cookie(response, value, settings)
    return CsrfTokenResponse(csrf_token=value)


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> LoginResponse:
    limiter = RateLimiter(session_factory, settings)
    peer = client_ip(request, settings.trusted_proxies)
    account = payload.email.strip().lower()
    ip_decision = await limiter.consume(
        "login_ip", peer, limit=LOGIN_IP_LIMIT, window_seconds=LOGIN_IP_WINDOW_SECONDS
    )
    account_decision = await limiter.consume(
        "login_account",
        account,
        limit=LOGIN_ACCOUNT_LIMIT,
        window_seconds=LOGIN_ACCOUNT_WINDOW_SECONDS,
    )
    if not ip_decision.allowed or not account_decision.allowed:
        retry_after = max(ip_decision.retry_after_seconds, account_decision.retry_after_seconds)
        async with transaction_scope(session_factory) as session:
            await AuthAuditService(session).record("rate_limit_triggered")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(retry_after)},
        )

    authenticator = LocalPasswordAuthenticator(session_factory, PasswordHasher(settings))
    user_id = await authenticator.authenticate(payload.email, payload.password)
    if user_id is None:
        async with transaction_scope(session_factory) as session:
            await AuthAuditService(session).record("login_failed")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    await limiter.clear("login_account", account)
    session_id, token = await SessionService(session_factory, settings).create(user_id)
    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record("login_succeeded", user_id=user_id)
    set_session_cookie(response, token, settings)
    set_csrf_cookie(response, CsrfService(settings.auth_secret).issue(str(session_id)), settings)
    return LoginResponse(user=await user_response(session_factory, user_id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    principal: PrincipalDep,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    await SessionService(session_factory, settings).revoke(principal.user_id, principal.session_id)
    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record("logout", user_id=principal.user_id)
    clear_session_cookie(response, settings)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    principal: PrincipalDep,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    await SessionService(session_factory, settings).revoke_all(principal.user_id)
    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record("logout_all", user_id=principal.user_id)
    clear_session_cookie(response, settings)


@router.get("/me", response_model=UserResponse)
async def me(
    principal: PrincipalDep,
    session_factory: SessionFactoryDep,
) -> UserResponse:
    return await user_response(session_factory, principal.user_id)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    principal: PrincipalDep,
    session_factory: SessionFactoryDep,
) -> list[SessionResponse]:
    async with transaction_scope(session_factory) as session:
        rows = await SessionRepository(session).list_for_user(principal.user_id)
    return [
        SessionResponse(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.absolute_expires_at,
            current=row.id == principal.session_id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    response: Response,
    principal: PrincipalDep,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    revoked = await SessionService(session_factory, settings).revoke(principal.user_id, session_id)
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record(
            "session_revoked", user_id=principal.user_id, metadata={"session_id": str(session_id)}
        )
    if session_id == principal.session_id:
        clear_session_cookie(response, settings)


@router.post("/email-verification/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_email_verification(
    request: Request,
    principal: PrincipalDep,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
    sender: EmailSenderDep,
) -> Response:
    async with transaction_scope(session_factory) as session:
        user = await UserRepository(session).get(principal.user_id)
    if user is None or user.status != "ACTIVE" or user.email_verified_at is not None:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    await enforce_recovery_rate_limit(request, settings, session_factory, user.email)
    outbox = EmailOutboxService(session_factory, sender)
    async with transaction_scope(session_factory) as session:
        token = await ActionTokenService().issue(
            session,
            purpose=PURPOSE_EMAIL_VERIFICATION,
            user_id=user.id,
            ttl=EMAIL_VERIFICATION_TTL,
        )
        subject, body = email_verification_message(settings, token)
        await outbox.enqueue(
            session,
            idempotency_key=email_idempotency_key(EMAIL_VERIFICATION_TEMPLATE, token),
            recipient=user.email,
            template=EMAIL_VERIFICATION_TEMPLATE,
            subject=subject,
            body=body,
        )
    await outbox.deliver_pending()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/email-verification/confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_email_verification(
    payload: EmailVerificationConfirmRequest,
    session_factory: SessionFactoryDep,
) -> None:
    async with transaction_scope(session_factory) as session:
        user_id = await ActionTokenService().consume(
            session, purpose=PURPOSE_EMAIL_VERIFICATION, token=payload.token
        )
        users = UserRepository(session)
        user = await users.get(user_id) if user_id is not None else None
        if user is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        users.set_email_verified(user, now=utcnow())
        await AuthAuditService(session).record("email_verified", user_id=user.id)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: PasswordForgotRequest,
    request: Request,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
    sender: EmailSenderDep,
) -> Response:
    account = payload.email.strip().lower()
    await enforce_recovery_rate_limit(request, settings, session_factory, account)
    outbox = EmailOutboxService(session_factory, sender)
    enqueued = False
    async with transaction_scope(session_factory) as session:
        user = await UserRepository(session).find_by_email(account)
        if user is not None and user.status == "ACTIVE":
            token = await ActionTokenService().issue(
                session,
                purpose=PURPOSE_PASSWORD_RESET,
                user_id=user.id,
                ttl=PASSWORD_RESET_TTL,
            )
            subject, body = password_reset_message(settings, token)
            await outbox.enqueue(
                session,
                idempotency_key=email_idempotency_key(PASSWORD_RESET_TEMPLATE, token),
                recipient=user.email,
                template=PASSWORD_RESET_TEMPLATE,
                subject=subject,
                body=body,
            )
            enqueued = True
    if enqueued:
        await outbox.deliver_pending()
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRequest,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    async with transaction_scope(session_factory) as session:
        user_id = await ActionTokenService().consume(
            session, purpose=PURPOSE_PASSWORD_RESET, token=payload.token
        )
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
        now = utcnow()
        await PasswordCredentialRepository(session).upsert(
            user_id=user_id,
            password_hash=PasswordHasher(settings).hash(payload.password),
            changed_at=now,
        )
        await SessionRepository(session).revoke_all_for_user(user_id, now=now)
        await AuthAuditService(session).record("password_reset_completed", user_id=user_id)


@invitations_router.post("/accept", status_code=status.HTTP_204_NO_CONTENT)
async def accept_invitation(
    payload: InvitationAcceptRequest,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    accepted = await InvitationService(session_factory, settings).accept(
        token=payload.token, password=payload.password
    )
    if accepted is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST)
