from __future__ import annotations

import hashlib
import hmac
import secrets

TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_digest(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def tokens_match(candidate: bytes, stored: bytes) -> bool:
    return hmac.compare_digest(candidate, stored)
