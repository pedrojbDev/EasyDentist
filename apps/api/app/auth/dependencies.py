from __future__ import annotations

import hmac
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.csrf import ANONYMOUS_BINDING, CsrfService
from app.auth.emails import EmailSender
from app.auth.principal import Principal
from app.auth.sessions import SessionService
from app.auth.settings import AuthSettings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_auth_settings(request: Request) -> AuthSettings:
    settings: AuthSettings = request.app.state.auth_settings
    return settings


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


AuthSettingsDep = Annotated[AuthSettings, Depends(get_auth_settings)]
SessionFactoryDep = Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


async def resolve_principal(
    request: Request,
    settings: AuthSettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> Principal | None:
    cached: Principal | None = getattr(request.state, "principal", None)
    if cached is not None:
        return cached
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    principal = await SessionService(session_factory, settings).resolve(token)
    if principal is not None:
        request.state.principal = principal
    return principal


async def get_principal(
    request: Request,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> Principal:
    principal = await resolve_principal(request, settings, session_factory)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return principal


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/")
    referer = request.headers.get("referer")
    if referer:
        parsed = urlparse(referer)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


async def require_csrf(
    request: Request,
    settings: AuthSettingsDep,
    session_factory: SessionFactoryDep,
) -> None:
    if request.method in SAFE_METHODS:
        return

    origin = request_origin(request)
    allowed_origins = {allowed.rstrip("/") for allowed in settings.allowed_origins}
    if origin is None or origin not in allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    cookie_value = request.cookies.get(settings.csrf_cookie_name)
    header_value = request.headers.get("x-csrf-token")
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    principal = await resolve_principal(request, settings, session_factory)
    binding = str(principal.session_id) if principal is not None else ANONYMOUS_BINDING
    if not CsrfService(settings.auth_secret).verify(cookie_value, binding):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
