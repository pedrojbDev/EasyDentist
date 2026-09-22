from __future__ import annotations

import os

from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEVELOPMENT = "development"
PRODUCTION = "production"

SECURITY_HEADERS: tuple[tuple[bytes, bytes], ...] = (
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
    (b"cross-origin-resource-policy", b"same-origin"),
    (
        b"content-security-policy",
        b"default-src 'none'; base-uri 'none'; frame-ancestors 'none'",
    ),
)

HSTS_HEADER: tuple[bytes, bytes] = (
    b"strict-transport-security",
    b"max-age=31536000; includeSubDomains",
)


def is_production_environment() -> bool:
    return os.environ.get("APP_ENV", DEVELOPMENT).strip().lower() == PRODUCTION


class SecurityHeadersMiddleware:
    """Adds the API security header contract to every HTTP response.

    HSTS is only emitted in production; development never sends it so a local
    browser cannot pin `127.0.0.1` to HTTPS.
    """

    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        self.app = app
        self._headers = SECURITY_HEADERS + ((HSTS_HEADER,) if production else ())

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {name.lower() for name, _ in headers}
                headers.extend(
                    (name, value) for name, value in self._headers if name not in existing
                )
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
