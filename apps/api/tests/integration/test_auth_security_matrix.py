from __future__ import annotations

import asyncio
import json

import asyncpg
import httpx
import pytest
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.responses import Response

from app.auth.action_tokens import (
    PASSWORD_RESET_TTL,
    PURPOSE_PASSWORD_RESET,
    ActionTokenService,
)
from app.auth.cookies import set_csrf_cookie, set_session_cookie
from app.auth.settings import AuthSettings
from app.auth.tokens import token_digest
from app.core.database import transaction_scope

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


def mutation_headers(
    csrf: str,
    *,
    session: str | None = None,
    origin: str | None = ORIGIN,
    send_cookie: bool = True,
    send_header: bool = True,
    header_value: str | None = None,
) -> dict[str, str]:
    cookies: list[str] = []
    if send_cookie:
        cookies.append(f"{CSRF_COOKIE}={csrf}")
    if session is not None:
        cookies.append(f"{SESSION_COOKIE}={session}")
    headers: dict[str, str] = {}
    if cookies:
        headers["Cookie"] = "; ".join(cookies)
    if send_header:
        headers["X-CSRF-Token"] = header_value if header_value is not None else csrf
    if origin is not None:
        headers["Origin"] = origin
    return headers


def auth_headers(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=mutation_headers(csrf),
    )
    client.cookies.clear()
    return response


def session_token(response: httpx.Response) -> str:
    token = response.cookies.get(SESSION_COOKIE)
    assert token
    return token


def token_from_body(body: str) -> str:
    marker = "#token="
    index = body.index(marker) + len(marker)
    return body[index:].splitlines()[0].strip()


@pytest.mark.anyio
async def test_database_stores_only_hashes(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("matrix-hashes")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))

    session_row = await migrator_connection.fetchrow(
        "SELECT * FROM app.auth_sessions WHERE user_id = $1", user_id
    )
    assert bytes(session_row["token_hash"]) == token_digest(token)
    assert token.encode() not in bytes(session_row["token_hash"])
    assert token not in str(dict(session_row))

    credential = await migrator_connection.fetchrow(
        "SELECT password_hash FROM app.password_credentials WHERE user_id = $1", user_id
    )
    assert credential["password_hash"].startswith("$argon2id$v=19$m=65536,t=3,p=1$")
    assert PASSWORD not in credential["password_hash"]

    csrf = await anonymous_csrf(api_client)
    await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": email},
        headers=mutation_headers(csrf),
    )
    outbox = await migrator_connection.fetchrow(
        "SELECT payload FROM app.email_outbox WHERE recipient = $1", email
    )
    reset_token = token_from_body(json.loads(str(outbox["payload"]))["body"])
    action_row = await migrator_connection.fetchrow(
        "SELECT * FROM app.auth_action_tokens WHERE user_id = $1", user_id
    )
    assert bytes(action_row["token_hash"]) == token_digest(reset_token)
    assert reset_token not in str(dict(action_row))


def test_cookie_flags_by_environment() -> None:
    development = AuthSettings.from_environment({})
    production = AuthSettings.from_environment({"APP_ENV": "production", "AUTH_SECRET": "p" * 32})

    dev_response = Response()
    set_session_cookie(dev_response, "dev-token", development)
    set_csrf_cookie(dev_response, "dev-csrf", development)
    dev_headers = dev_response.headers.getlist("set-cookie")
    dev_session = next(header for header in dev_headers if header.startswith(SESSION_COOKIE))
    dev_csrf = next(header for header in dev_headers if header.startswith(CSRF_COOKIE))
    assert "Secure" not in dev_session
    assert "HttpOnly" in dev_session
    assert "SameSite=lax" in dev_session
    assert "Path=/" in dev_session
    assert "HttpOnly" not in dev_csrf

    prod_response = Response()
    set_session_cookie(prod_response, "prod-token", production)
    prod_headers = prod_response.headers.getlist("set-cookie")
    prod_session = next(
        header for header in prod_headers if header.startswith("__Host-easydent_session")
    )
    assert "Secure" in prod_session
    assert "HttpOnly" in prod_session
    assert "Domain" not in prod_session
    assert "Path=/" in prod_session


@pytest.mark.anyio
async def test_idle_expiration_rejects_session(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("matrix-idle")
    await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))
    await migrator_connection.execute(
        "UPDATE app.auth_sessions SET idle_expires_at = now() - interval '1 second' "
        "WHERE token_hash = $1",
        token_digest(token),
    )

    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(token))).status_code == 401


@pytest.mark.anyio
async def test_absolute_expiration_rejects_session_even_with_fresh_idle(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("matrix-absolute")
    await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))
    await migrator_connection.execute(
        "UPDATE app.auth_sessions SET absolute_expires_at = now() - interval '1 second', "
        "idle_expires_at = now() + interval '1 hour' WHERE token_hash = $1",
        token_digest(token),
    )

    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(token))).status_code == 401


@pytest.mark.anyio
async def test_revoked_and_reused_tokens_are_rejected(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-revoke")
    await seed_user_with_password(email=email, password=PASSWORD)
    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))
    bound_response = await api_client.get("/api/v1/auth/csrf", headers=auth_headers(first))
    bound = bound_response.json()["csrf_token"]

    logout = await api_client.post(
        "/api/v1/auth/logout", headers=mutation_headers(bound, session=first)
    )
    assert logout.status_code == 204
    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(first))).status_code == 401

    logout_all_response = await api_client.get("/api/v1/auth/csrf", headers=auth_headers(second))
    bound_second = logout_all_response.json()["csrf_token"]
    logout_all = await api_client.post(
        "/api/v1/auth/logout-all", headers=mutation_headers(bound_second, session=second)
    )
    assert logout_all.status_code == 204
    assert (
        await api_client.get("/api/v1/auth/me", headers=auth_headers(second))
    ).status_code == 401


@pytest.mark.anyio
async def test_two_device_sessions_coexist_concurrently(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-devices")
    await seed_user_with_password(email=email, password=PASSWORD)
    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))
    assert first != second

    responses = await asyncio.gather(
        api_client.get("/api/v1/auth/me", headers=auth_headers(first)),
        api_client.get("/api/v1/auth/me", headers=auth_headers(second)),
    )

    assert [response.status_code for response in responses] == [200, 200]


@pytest.mark.anyio
async def test_login_rotates_session_keeping_previous_device(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-rotation")
    await seed_user_with_password(email=email, password=PASSWORD)

    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))

    assert first != second
    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(first))).status_code == 200
    assert (
        await api_client.get("/api/v1/auth/me", headers=auth_headers(second))
    ).status_code == 200


@pytest.mark.anyio
async def test_login_and_forgot_do_not_reveal_account_existence(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-enum")
    await seed_user_with_password(email=email, password=PASSWORD)

    wrong_password = await login(api_client, email, "wrong-password-12345")
    unknown_email = await login(api_client, make_test_email("matrix-absent"))
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["title"] == unknown_email.json()["title"]
    assert wrong_password.json()["type"] == unknown_email.json()["type"]

    known_forgot = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": email},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    unknown_forgot = await api_client.post(
        "/api/v1/auth/password/forgot",
        json={"email": make_test_email("matrix-absent-forgot")},
        headers=mutation_headers(await anonymous_csrf(api_client)),
    )
    assert known_forgot.status_code == unknown_forgot.status_code == 202
    assert known_forgot.content == unknown_forgot.content


@pytest.mark.anyio
async def test_csrf_rejection_matrix(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-csrf")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)

    cases = {
        "missing header": mutation_headers(csrf, send_header=False),
        "missing cookie": mutation_headers(csrf, send_cookie=False),
        "mismatched header": mutation_headers(csrf, header_value=f"{csrf}-other"),
        "tampered signature": mutation_headers(f"{csrf}x"),
        "foreign origin": mutation_headers(csrf, origin="http://evil.example"),
        "no origin or referer": mutation_headers(csrf, origin=None),
    }
    for name, headers in cases.items():
        response = await api_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": PASSWORD},
            headers=headers,
        )
        assert response.status_code == 403, name
        assert response.json()["title"] == "Acesso negado", name

    referer_only = await api_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={
            "Cookie": f"{CSRF_COOKIE}={csrf}",
            "X-CSRF-Token": csrf,
            "Referer": f"{ORIGIN}/login",
        },
    )
    assert referer_only.status_code == 200

    api_client.cookies.clear()
    safe = await api_client.get("/api/v1/auth/me")
    assert safe.status_code == 401


@pytest.mark.anyio
async def test_rate_limit_is_atomic_under_concurrency(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("matrix-ratelimit")
    await seed_user_with_password(email=email, password=PASSWORD)
    headers = mutation_headers(await anonymous_csrf(api_client))

    responses = await asyncio.gather(
        *(
            api_client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password-12345"},
                headers=headers,
            )
            for _ in range(7)
        )
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses.count(401) == 5
    assert statuses.count(429) == 2
    blocked = next(response for response in responses if response.status_code == 429)
    assert int(blocked.headers["Retry-After"]) > 0


@pytest.mark.anyio
async def test_token_services_single_use_under_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("matrix-token-concurrency"), password=PASSWORD
    )
    service = ActionTokenService()
    async with transaction_scope(session_factory) as session:
        token = await service.issue(
            session, purpose=PURPOSE_PASSWORD_RESET, user_id=user_id, ttl=PASSWORD_RESET_TTL
        )

    async def consume() -> object:
        async with transaction_scope(session_factory) as session:
            return await service.consume(session, purpose=PURPOSE_PASSWORD_RESET, token=token)

    results = await asyncio.gather(consume(), consume())

    assert list(results).count(user_id) == 1
    assert list(results).count(None) == 1
