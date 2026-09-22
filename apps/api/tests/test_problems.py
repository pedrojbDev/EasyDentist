from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)
from app.platform.middleware import RequestLoggingMiddleware
from app.platform.problems import (
    PROBLEM_CONTENT_TYPE,
    domain_error_handler,
    problem_response,
    register_problem_handlers,
    request_id_from,
)


def fake_request(request_id: str = "test-request-id") -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(request_id=request_id))


def test_problem_response_shape() -> None:
    response = problem_response(status=404, request_id="rid-1")

    assert response.media_type == PROBLEM_CONTENT_TYPE
    assert response.status_code == 404


@pytest.mark.anyio
async def test_problem_response_body() -> None:
    response = problem_response(status=401, request_id="rid-1")
    body = response.body.decode()

    assert '"title":"Não autenticado"' in body
    assert '"status":401' in body
    assert '"request_id":"rid-1"' in body


def test_request_id_from_request_state() -> None:
    assert request_id_from(fake_request("abc")) == "abc"  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_domain_error_handler_maps_not_found_and_conflict() -> None:
    request = fake_request()

    not_found = await domain_error_handler(request, NotFoundError("x"))  # type: ignore[arg-type]
    conflict = await domain_error_handler(request, ConflictError("x"))  # type: ignore[arg-type]
    forbidden = await domain_error_handler(request, PermissionDeniedError("x"))  # type: ignore[arg-type]
    invalid = await domain_error_handler(request, InvalidInputError("x"))  # type: ignore[arg-type]

    assert not_found.status_code == 404
    assert conflict.status_code == 409
    assert forbidden.status_code == 403
    assert invalid.status_code == 422


def build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    register_problem_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise StarletteHTTPException(status_code=404, detail="not here")

    @app.get("/conflict")
    async def conflict() -> None:
        raise ConflictError("already exists")

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise PermissionDeniedError("not permitted")

    @app.get("/validated")
    async def validated(required: int) -> dict[str, int]:
        return {"required": required}

    return app


@pytest.mark.anyio
async def test_http_exception_becomes_problem_details_with_request_id() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.headers["x-request-id"]
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Recurso não encontrado"
    assert body["request_id"] == response.headers["x-request-id"]


@pytest.mark.anyio
async def test_domain_error_becomes_problem_details() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/conflict")

    assert response.status_code == 409
    assert response.json()["title"] == "Conflito"


@pytest.mark.anyio
async def test_permission_denied_becomes_problem_details() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/forbidden")

    assert response.status_code == 403
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.json()["title"] == "Acesso negado"


@pytest.mark.anyio
async def test_validation_error_becomes_problem_details() -> None:
    transport = httpx.ASGITransport(app=build_test_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/validated")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.json()["title"] == "Dados inválidos"
