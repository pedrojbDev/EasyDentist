from __future__ import annotations

import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.platform.logging import get_logger

DEFAULT_STATUS_CODE = 500


def resolve_request_id(scope: Scope) -> str:
    """Reuses a valid upstream request ID so web/API logs correlate."""

    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1").strip()
            try:
                return str(uuid.UUID(candidate))
            except ValueError:
                break
    return str(uuid.uuid4())


def route_path(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return str(scope.get("path", ""))


class RequestLoggingMiddleware:
    """Assigns the request ID and emits one structured access event per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(scope)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        started = time.perf_counter()
        status_code = DEFAULT_STATUS_CODE
        error_type: str | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = message.setdefault("headers", [])
                headers.append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except BaseException as error:
            error_type = type(error).__name__
            raise
        finally:
            context: dict[str, object] = {
                "request_id": request_id,
                "method": str(scope.get("method", "")),
                "route": route_path(scope),
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            }
            if error_type is not None:
                context["error_type"] = error_type
            get_logger().info("http.request", extra={"context": context})
