from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

from app.platform.problems import problem_response

BODY_LIMIT_BYTES = 11 * 1024 * 1024


def declared_length_exceeds(scope: Scope, max_bytes: int) -> bool:
    """Reads only the Content-Length header; an absent or invalid one passes."""

    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value) > max_bytes
            except ValueError:
                return False
    return False


class BodyLimitMiddleware:
    """Rejects oversized declared bodies before the application reads them.

    FastAPI solves dependencies and parses `request.form()` before any endpoint
    runs, so without this an anonymous client could make the server spool an
    unbounded multipart body to disk. The Content-Length is checked up front and
    the body is never read. Chunked uploads carry no length and must be capped
    by the ingress/proxy in front of the API (see docs/operations.md).
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = BODY_LIMIT_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not declared_length_exceeds(scope, self.max_bytes):
            await self.app(scope, receive, send)
            return

        request_id = str(scope.get("state", {}).get("request_id", ""))
        response = problem_response(status=413, request_id=request_id)
        await response(scope, receive, send)
