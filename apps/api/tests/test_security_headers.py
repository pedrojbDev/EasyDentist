from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, HTTPException, status

from app.application import create_app
from app.platform.security_headers import HSTS_HEADER, SecurityHeadersMiddleware

EXPECTED_API_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
    "content-security-policy": "default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
}


def build_status_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/unauthorized")
    async def unauthorized() -> None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    @app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @app.get("/invalid")
    async def invalid() -> None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)

    @app.get("/limited")
    async def limited() -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, headers={"Retry-After": "30"}
        )

    app.add_middleware(SecurityHeadersMiddleware, production=False)
    return app


@pytest.fixture
async def status_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_status_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def assert_security_headers(response: httpx.Response, *, hsts: bool = False) -> None:
    for name, value in EXPECTED_API_HEADERS.items():
        assert response.headers.get(name) == value, name
    if hsts:
        assert response.headers.get("strict-transport-security") == HSTS_HEADER[1].decode()
    else:
        assert "strict-transport-security" not in response.headers


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/ok", 200),
        ("/unauthorized", 401),
        ("/missing", 404),
        ("/invalid", 422),
        ("/limited", 429),
    ],
)
async def test_every_status_carries_security_headers(
    status_client: httpx.AsyncClient, path: str, expected_status: int
) -> None:
    response = await status_client.get(path)

    assert response.status_code == expected_status
    assert_security_headers(response)


@pytest.mark.anyio
async def test_development_never_emits_hsts() -> None:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(SecurityHeadersMiddleware, production=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ok")

    assert "strict-transport-security" not in response.headers


@pytest.mark.anyio
async def test_production_emits_hsts() -> None:
    app = FastAPI()

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    app.add_middleware(SecurityHeadersMiddleware, production=True)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/ok")

    assert_security_headers(response, hsts=True)


@pytest.mark.anyio
async def test_real_app_carries_headers_on_health_auth_and_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:secret@db:5432/easydentist")
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://testserver")
    monkeypatch.setenv("APP_ENV", "development")
    app = create_app()

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            health = await client.get("/api/v1/health")
            me = await client.get("/api/v1/auth/me")
            missing = await client.get("/api/v1/does-not-exist")
            csrf = await client.get("/api/v1/auth/csrf")
            invalid = await client.post(
                "/api/v1/auth/login",
                json={},
                headers={
                    "X-CSRF-Token": csrf.json()["csrf_token"],
                    "Origin": "http://testserver",
                },
            )

    assert health.status_code == 200
    assert me.status_code == 401
    assert missing.status_code == 404
    assert invalid.status_code == 422
    for response in (health, me, missing, invalid):
        assert_security_headers(response)


@pytest.mark.anyio
async def test_unhandled_exception_carries_headers_and_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    app = create_app()

    @app.get("/api/v1/boom-test")
    async def boom() -> None:
        raise RuntimeError("payload=must-not-leak")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/boom-test")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert_security_headers(response)
    request_id = response.headers["x-request-id"]
    assert request_id
    assert response.json()["request_id"] == request_id
    assert "must-not-leak" not in response.text


@pytest.mark.anyio
async def test_real_app_emits_hsts_only_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:secret@db:5432/easydentist")
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret-with-enough-bytes-123")
    monkeypatch.setenv("APP_ENV", "production")
    app = create_app()

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/health")

    assert_security_headers(response, hsts=True)
