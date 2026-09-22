from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.application import create_app
from app.platform.body_limit import BODY_LIMIT_BYTES
from app.platform.problems import PROBLEM_CONTENT_TYPE
from app.platform.security_headers import SECURITY_HEADERS

PROBE_PATH = "/api/v1/body-limit-probe"


def build_probe_app() -> tuple[FastAPI, list[str]]:
    app = create_app()
    calls: list[str] = []

    @app.post(PROBE_PATH)
    async def probe() -> dict[str, str]:
        calls.append("called")
        return {"status": "ok"}

    return app, calls


async def body_stream() -> AsyncIterator[bytes]:
    yield b"%PDF-"


@pytest.mark.anyio
async def test_content_length_over_cap_is_rejected_without_calling_the_handler() -> None:
    app, calls = build_probe_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            PROBE_PATH,
            content=b"%PDF-",
            headers={"Content-Length": str(BODY_LIMIT_BYTES + 1)},
        )

    assert response.status_code == 413
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    body = response.json()
    assert body["title"] == "Arquivo muito grande"
    assert body["status"] == 413
    assert body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]
    for name, value in SECURITY_HEADERS:
        assert response.headers[name.decode()] == value.decode()
    assert calls == []


@pytest.mark.anyio
async def test_content_length_under_cap_reaches_the_handler() -> None:
    app, calls = build_probe_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(PROBE_PATH, content=b"%PDF-")

    assert response.status_code == 200
    assert calls == ["called"]


@pytest.mark.anyio
async def test_request_without_content_length_reaches_the_handler() -> None:
    app, calls = build_probe_app()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(PROBE_PATH, content=body_stream())

    assert response.status_code == 200
    assert calls == ["called"]
