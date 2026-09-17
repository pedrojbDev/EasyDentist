from __future__ import annotations

import uuid

import asyncpg
import httpx
import pytest
from conftest import make_test_email

PASSWORD = "correct horse battery staple"
SESSION_COOKIE = "easydent_session"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


async def csrf_token(client: httpx.AsyncClient, session_token: str | None = None) -> str:
    client.cookies.clear()
    headers = {"Cookie": f"{SESSION_COOKIE}={session_token}"} if session_token else {}
    response = await client.get("/api/v1/auth/csrf", headers=headers)
    assert response.status_code == 200
    client.cookies.clear()
    return response.json()["csrf_token"]


def mutation_headers(csrf: str, session_token: str | None = None) -> dict[str, str]:
    cookies = [f"{CSRF_COOKIE}={csrf}"]
    if session_token is not None:
        cookies.append(f"{SESSION_COOKIE}={session_token}")
    return {"Cookie": "; ".join(cookies), "X-CSRF-Token": csrf, "Origin": ORIGIN}


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    csrf = await csrf_token(client)
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


def auth_headers(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


@pytest.mark.anyio
async def test_login_returns_user_and_sets_cookies(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("login")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)

    response = await login(api_client, email)

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["id"] == str(user_id)
    assert body["user"]["email"] == email
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_header = next(h for h in set_cookie_headers if h.startswith(SESSION_COOKIE))
    assert "HttpOnly" in session_header
    assert "Secure" not in session_header
    assert any(h.startswith(CSRF_COOKIE) for h in set_cookie_headers)


@pytest.mark.anyio
async def test_login_rejects_wrong_password_and_unknown_email_identically(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("enumeration")
    await seed_user_with_password(email=email, password=PASSWORD)

    wrong_password = await login(api_client, email, "wrong-password-12345")
    unknown_email = await login(api_client, make_test_email("absent"), PASSWORD)

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json()["title"] == unknown_email.json()["title"]
    assert wrong_password.json()["type"] == unknown_email.json()["type"]
    assert wrong_password.cookies.get(SESSION_COOKIE) is None
    assert unknown_email.cookies.get(SESSION_COOKIE) is None


@pytest.mark.anyio
async def test_me_requires_a_session(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("me")
    await seed_user_with_password(email=email, password=PASSWORD)

    unauthenticated = await api_client.get("/api/v1/auth/me")
    assert unauthenticated.status_code == 401

    token = session_token(await login(api_client, email))
    authenticated = await api_client.get("/api/v1/auth/me", headers=auth_headers(token))

    assert authenticated.status_code == 200
    assert authenticated.json()["email"] == email
    assert authenticated.json()["email_verified_at"] is None


@pytest.mark.anyio
async def test_logout_revokes_the_session_and_clears_the_cookie(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("logout")
    await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))
    csrf = await csrf_token(api_client, session_token=token)

    logout = await api_client.post("/api/v1/auth/logout", headers=mutation_headers(csrf, token))

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]
    reused = await api_client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert reused.status_code == 401


@pytest.mark.anyio
async def test_logout_all_revokes_every_session(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("logout-all")
    await seed_user_with_password(email=email, password=PASSWORD)
    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))
    csrf = await csrf_token(api_client, session_token=first)

    logout_all = await api_client.post(
        "/api/v1/auth/logout-all", headers=mutation_headers(csrf, first)
    )

    assert logout_all.status_code == 204
    for token in (first, second):
        response = await api_client.get("/api/v1/auth/me", headers=auth_headers(token))
        assert response.status_code == 401


@pytest.mark.anyio
async def test_sessions_list_marks_current_and_hides_tokens(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("sessions")
    await seed_user_with_password(email=email, password=PASSWORD)
    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))

    listing = await api_client.get("/api/v1/auth/sessions", headers=auth_headers(second))

    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 2
    assert sum(1 for row in rows if row["current"]) == 1
    for row in rows:
        assert set(row) == {"id", "created_at", "last_seen_at", "expires_at", "current"}
    assert first not in listing.text
    assert second not in listing.text


@pytest.mark.anyio
async def test_delete_session_revokes_another_device(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("delete-session")
    await seed_user_with_password(email=email, password=PASSWORD)
    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))
    listing = await api_client.get("/api/v1/auth/sessions", headers=auth_headers(first))
    other_id = next(row["id"] for row in listing.json() if not row["current"])
    csrf = await csrf_token(api_client, session_token=first)

    deleted = await api_client.delete(
        f"/api/v1/auth/sessions/{other_id}", headers=mutation_headers(csrf, first)
    )

    assert deleted.status_code == 204
    assert (
        await api_client.get("/api/v1/auth/me", headers=auth_headers(second))
    ).status_code == 401
    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(first))).status_code == 200


@pytest.mark.anyio
async def test_delete_unknown_session_returns_generic_not_found(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("delete-unknown")
    await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))
    csrf = await csrf_token(api_client, session_token=token)

    response = await api_client.delete(
        f"/api/v1/auth/sessions/{uuid.uuid4()}", headers=mutation_headers(csrf, token)
    )

    assert response.status_code == 404
    assert response.json()["title"] == "Recurso não encontrado"


@pytest.mark.anyio
async def test_login_creates_new_session_without_revoking_others(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("rotation")
    await seed_user_with_password(email=email, password=PASSWORD)

    first = session_token(await login(api_client, email))
    second = session_token(await login(api_client, email))

    assert first != second
    assert (await api_client.get("/api/v1/auth/me", headers=auth_headers(first))).status_code == 200
    assert (
        await api_client.get("/api/v1/auth/me", headers=auth_headers(second))
    ).status_code == 200


@pytest.mark.anyio
async def test_audit_events_are_recorded(
    api_client: httpx.AsyncClient,
    seed_user_with_password,
    clean_auth_state: None,
    migrator_connection: asyncpg.Connection,
) -> None:
    email = make_test_email("audit")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    token = session_token(await login(api_client, email))
    await login(api_client, email, "wrong-password-12345")
    csrf = await csrf_token(api_client, session_token=token)
    await api_client.post("/api/v1/auth/logout", headers=mutation_headers(csrf, token))

    rows = await migrator_connection.fetch(
        "SELECT event_type, user_id FROM app.auth_audit_events "
        "WHERE user_id = $1 OR user_id IS NULL",
        user_id,
    )
    events = {(record["event_type"], record["user_id"]) for record in rows}

    assert ("login_succeeded", user_id) in events
    assert ("logout", user_id) in events
    assert ("login_failed", None) in events
