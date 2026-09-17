from __future__ import annotations

from collections.abc import Mapping

from starlette.responses import Response

from app.auth.cookies import clear_session_cookie, set_csrf_cookie, set_session_cookie
from app.auth.settings import AuthSettings


def dev_settings() -> AuthSettings:
    return AuthSettings.from_environment({})


def prod_settings() -> AuthSettings:
    environment: Mapping[str, str] = {"APP_ENV": "production", "AUTH_SECRET": "p" * 32}
    return AuthSettings.from_environment(environment)


def test_session_cookie_flags_in_development() -> None:
    response = Response()

    set_session_cookie(response, "token-value", dev_settings())

    header = response.headers["set-cookie"]
    assert header.startswith("easydent_session=token-value")
    assert "HttpOnly" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
    assert "Max-Age=2592000" in header
    assert "Secure" not in header


def test_session_cookie_flags_in_production() -> None:
    response = Response()

    set_session_cookie(response, "token-value", prod_settings())

    header = response.headers["set-cookie"]
    assert header.startswith("__Host-easydent_session=token-value")
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "Path=/" in header
    assert "Domain" not in header


def test_clear_session_cookie_expires_it() -> None:
    response = Response()

    clear_session_cookie(response, dev_settings())

    header = response.headers["set-cookie"]
    assert header.startswith("easydent_session=")
    assert "Max-Age=0" in header


def test_csrf_cookie_is_readable_by_the_frontend() -> None:
    response = Response()

    set_csrf_cookie(response, "csrf-value", dev_settings())

    header = response.headers["set-cookie"]
    assert header.startswith("easydent_csrf=csrf-value")
    assert "HttpOnly" not in header
    assert "SameSite=lax" in header
