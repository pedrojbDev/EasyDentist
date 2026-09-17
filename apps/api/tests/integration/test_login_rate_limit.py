from __future__ import annotations

import asyncio

import httpx
import pytest
from conftest import make_test_email

PASSWORD = "correct horse battery staple"
CSRF_COOKIE = "easydent_csrf"
ORIGIN = "http://testserver"


async def anonymous_csrf(client: httpx.AsyncClient) -> str:
    client.cookies.clear()
    response = await client.get("/api/v1/auth/csrf")
    client.cookies.clear()
    return response.json()["csrf_token"]


def login_headers(csrf: str) -> dict[str, str]:
    return {
        "Cookie": f"{CSRF_COOKIE}={csrf}",
        "X-CSRF-Token": csrf,
        "Origin": ORIGIN,
    }


async def login(client: httpx.AsyncClient, email: str, password: str = PASSWORD) -> httpx.Response:
    csrf = await anonymous_csrf(client)
    return await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=login_headers(csrf),
    )


@pytest.mark.anyio
async def test_account_lockout_after_five_failures(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("lockout")
    await seed_user_with_password(email=email, password=PASSWORD)

    for _ in range(5):
        response = await login(api_client, email, "wrong-password-12345")
        assert response.status_code == 401

    blocked = await login(api_client, email, PASSWORD)

    assert blocked.status_code == 429
    assert blocked.json()["title"] == "Muitas tentativas"
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.cookies.get("easydent_session") is None


@pytest.mark.anyio
async def test_successful_login_clears_the_account_bucket(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("clear-bucket")
    await seed_user_with_password(email=email, password=PASSWORD)

    for _ in range(4):
        assert (await login(api_client, email, "wrong-password-12345")).status_code == 401
    assert (await login(api_client, email)).status_code == 200

    for _ in range(4):
        assert (await login(api_client, email, "wrong-password-12345")).status_code == 401
    assert (await login(api_client, email)).status_code == 200


@pytest.mark.anyio
async def test_lockout_isolated_per_account(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    locked = make_test_email("locked")
    healthy = make_test_email("healthy")
    await seed_user_with_password(email=locked, password=PASSWORD)
    await seed_user_with_password(email=healthy, password=PASSWORD)

    for _ in range(5):
        await login(api_client, locked, "wrong-password-12345")
    assert (await login(api_client, locked, PASSWORD)).status_code == 429

    assert (await login(api_client, healthy)).status_code == 200


@pytest.mark.anyio
async def test_concurrent_failures_are_deterministic(
    api_client: httpx.AsyncClient, seed_user_with_password, clean_auth_state: None
) -> None:
    email = make_test_email("concurrent")
    await seed_user_with_password(email=email, password=PASSWORD)
    csrf = await anonymous_csrf(api_client)
    headers = login_headers(csrf)

    responses = await asyncio.gather(
        *(
            api_client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "wrong-password-12345"},
                headers=headers,
            )
            for _ in range(10)
        )
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses.count(401) == 5
    assert statuses.count(429) == 5
