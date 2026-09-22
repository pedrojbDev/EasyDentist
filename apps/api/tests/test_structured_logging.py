from __future__ import annotations

import json
import logging
import sys
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.application import create_app
from app.auth.audit import sanitize_event_metadata
from app.platform.logging import JsonLogFormatter, get_logger
from app.platform.middleware import RequestLoggingMiddleware, resolve_request_id

REQUIRED_FIELDS = {"timestamp", "service", "environment", "level", "event"}


def build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/clinics/{clinic_id}")
    async def clinic(clinic_id: str) -> dict[str, str]:
        return {"id": clinic_id}

    @app.get("/api/v1/boom")
    async def boom() -> None:
        raise RuntimeError("request payload must not be logged")

    app.add_middleware(RequestLoggingMiddleware)
    return app


@pytest.fixture
async def logging_client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def http_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    formatter = JsonLogFormatter("development")
    events = []
    for record in caplog.records:
        if record.name != "easydentist.api":
            continue
        if record.getMessage() != "http.request":
            continue
        events.append(json.loads(formatter.format(record)))
    return events


def test_formatter_emits_json_with_allowlisted_context() -> None:
    formatter = JsonLogFormatter("production")
    record = logging.LogRecord(
        name="easydentist.api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http.request",
        args=(),
        exc_info=None,
    )
    record.context = {  # type: ignore[attr-defined]
        "request_id": "req-1",
        "status_code": 200,
        "email": "user@example.com",
        "token": "secret-token",
        "query": "?token=secret-token",
    }

    payload = json.loads(formatter.format(record))

    assert REQUIRED_FIELDS <= payload.keys()
    assert payload["service"] == "api"
    assert payload["environment"] == "production"
    assert payload["request_id"] == "req-1"
    assert payload["status_code"] == 200
    assert "email" not in payload
    assert "token" not in payload
    assert "query" not in payload
    assert "secret-token" not in formatter.format(record)


def test_formatter_never_serialises_exception_messages() -> None:
    formatter = JsonLogFormatter("development")
    try:
        raise RuntimeError("password=super-secret")
    except RuntimeError:
        record = logging.LogRecord(
            name="easydentist.api",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="http.request",
            args=(),
            exc_info=sys.exc_info(),
        )

    line = formatter.format(record)

    assert "super-secret" not in line
    assert json.loads(line)["error_type"] == "RuntimeError"


def test_audit_metadata_is_allowlisted_per_event() -> None:
    assert sanitize_event_metadata(
        "session_revoked", {"session_id": "session-1", "token": "must-not-persist"}
    ) == {"session_id": "session-1"}
    assert sanitize_event_metadata("integration.audit", {"auth_method": "password"}) == {}
    assert sanitize_event_metadata("session_revoked", None) == {}


def test_resolve_request_id_reuses_valid_headers_only() -> None:
    valid = str(uuid.uuid4())
    scope = {"headers": [(b"x-request-id", valid.encode())]}
    assert resolve_request_id(scope) == valid

    invalid_scope = {"headers": [(b"x-request-id", b"not-a-uuid")]}
    generated = resolve_request_id(invalid_scope)
    assert generated != "not-a-uuid"
    assert str(uuid.UUID(generated)) == generated


@pytest.mark.anyio
async def test_middleware_logs_route_status_and_request_id(
    logging_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request_id = str(uuid.uuid4())
    caplog.set_level(logging.INFO, logger=get_logger().name)

    response = await logging_client.get(
        "/api/v1/clinics/abc?token=query-secret",
        headers={"X-Request-Id": request_id},
    )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    events = http_events(caplog)
    assert len(events) == 1
    event = events[0]
    assert event["request_id"] == request_id
    assert event["method"] == "GET"
    assert event["route"] == "/api/v1/clinics/{clinic_id}"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], int)
    assert "query-secret" not in json.dumps(events)
    assert "abc" not in json.dumps(events)


@pytest.mark.anyio
async def test_middleware_logs_error_type_for_unhandled_errors(
    logging_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger=get_logger().name)

    response = await logging_client.get("/api/v1/boom")

    assert response.status_code == 500
    events = http_events(caplog)
    assert len(events) == 1
    assert events[0]["status_code"] == 500
    assert events[0]["error_type"] == "RuntimeError"
    assert "request payload must not be logged" not in json.dumps(events)


@pytest.mark.anyio
async def test_real_app_logs_unhandled_errors_without_leaking(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    caplog.set_level(logging.INFO, logger=get_logger().name)
    app = create_app()

    @app.get("/api/v1/boom-test")
    async def boom() -> None:
        raise RuntimeError("payload=must-not-leak")

    request_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/boom-test", headers={"X-Request-Id": request_id})

    assert response.status_code == 500
    events = http_events(caplog)
    event = next(entry for entry in events if entry.get("request_id") == request_id)
    assert event["status_code"] == 500
    assert event["error_type"] == "RuntimeError"
    assert event["route"] == "/api/v1/boom-test"
    assert "must-not-leak" not in json.dumps(events)
