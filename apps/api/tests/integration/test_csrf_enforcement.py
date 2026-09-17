from __future__ import annotations

import httpx
import pytest
from conftest import make_test_email

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={
            "Cookie": f"{CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Origin": ORIGIN,
        },
    )
    client.cookies.clear()
    return response


def csrf_headers(
    csrf: str | None,
    *,
    origin: str | None = ORIGIN,
    referer: str | None = None,
    session: str | None = None,
    send_cookie: bool = True,
    send_header: bool = True,
    header_value: str | None = None,
) -> dict[str, str]:
    cookies = []
    if csrf is not None and send_cookie:
        cookies.append(f"{CSRF_COOKIE}={csrf}")
    if session is not None:
        cookies.append(f"{SESSION_COOKIE}={session}")
    headers: dict[str, str] = {}
    if cookies:
        headers["Cookie"] = "; ".join(cookies)
    if csrf is not None and send_header:
        headers["X-CSRF-Token"] = header_value if header_value is not None else csrf
    if origin is not None:
        headers["Origin"] = origin
    if referer is not None:
        headers["Referer"] = referer
    return headers


@pytest.mark.anyio
async def test_get_csrf_sets_a_readable_cookie_and_returns_the_token(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/auth/csrf")

    assert response.status_code == 200
    token = response.json()["csrf_token"]
    header = response.headers["set-cookie"]
    assert header.startswith(f"{CSRF_COOKIE}={token}")
    assert "HttpOnly" not in header
    assert "SameSite=lax" in header


@pytest.mark.anyio
async def test_mutation_without_csrf_is_rejected(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-missing")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    no_header = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(csrf, send_header=False),
    )
    no_cookie = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(csrf, send_cookie=False),
    )

    assert no_header.status_code == 403
    assert no_cookie.status_code == 403
    assert no_header.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_mutation_with_mismatched_values_is_rejected(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-mismatch")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)
    other = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(csrf, header_value=other),
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_mutation_with_tampered_signature_is_rejected(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-tamper")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(f"{csrf}x"),
    )

    assert response.status_code == 403


@pytest.mark.anyio
async def test_mutation_from_foreign_origin_is_rejected(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-origin")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    foreign = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(csrf, origin="http://evil.example"),
    )
    missing = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(csrf, origin=None),
    )

    assert foreign.status_code == 403
    assert missing.status_code == 403


@pytest.mark.anyio
async def test_referer_is_accepted_when_origin_is_absent(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-referer")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong-password-12345"},
        headers=csrf_headers(csrf, origin=None, referer=f"{ORIGIN}/login"),
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_safe_methods_are_exempt_from_csrf(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_session_bound_token_is_required_after_login(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("csrf-binding")
    await seed_user_with_password(email=email, password=PASSWORD)
    anonymous = await anonymous_csrf(api_client)
    login_response = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=csrf_headers(anonymous),
    )
    assert login_response.status_code == 200
    session = login_response.cookies.get(SESSION_COOKIE)
    assert session
    api_client.cookies.clear()

    stale = await api_client.post(
        "/api/v1/auth/logout", headers=csrf_headers(anonymous, session=session)
    )
    assert stale.status_code == 403

    api_client.cookies.clear()
    bound_response = await api_client.get(
        "/api/v1/auth/csrf", headers={"Cookie": f"{SESSION_COOKIE}={session}"}
    )
    bound = bound_response.json()["csrf_token"]
    api_client.cookies.clear()

    fresh = await api_client.post(
        "/api/v1/auth/logout", headers=csrf_headers(bound, session=session)
    )

    assert fresh.status_code == 204
