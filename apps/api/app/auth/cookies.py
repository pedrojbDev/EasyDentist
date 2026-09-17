from __future__ import annotations

from starlette.responses import Response

from app.auth.settings import AuthSettings


def set_session_cookie(response: Response, token: str, settings: AuthSettings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=int(settings.session_absolute_ttl.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def set_csrf_cookie(response: Response, value: str, settings: AuthSettings) -> None:
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=value,
        max_age=int(settings.session_absolute_ttl.total_seconds()),
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )
