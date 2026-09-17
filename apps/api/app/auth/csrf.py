from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

TOKEN_BYTES = 32
ANONYMOUS_BINDING = "anonymous"


def _signature(secret: bytes, binding: str, token: str) -> str:
    payload = f"csrf:{binding}:{token}".encode()
    digest = hmac.new(secret, payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class CsrfService:
    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def issue(self, binding: str) -> str:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        return f"{token}.{_signature(self._secret, binding, token)}"

    def verify(self, value: str, binding: str) -> bool:
        token, separator, signature = value.partition(".")
        if not separator or not token or not signature:
            return False
        expected = _signature(self._secret, binding, token)
        return hmac.compare_digest(signature, expected)
