from __future__ import annotations

import base64
import hashlib

from app.auth.tokens import generate_token, token_digest, tokens_match


def test_generate_token_is_url_safe_256_bits() -> None:
    token = generate_token()

    assert len(token) == 43
    decoded = base64.urlsafe_b64decode(token + "=")
    assert len(decoded) == 32


def test_generate_token_is_unique() -> None:
    assert generate_token() != generate_token()


def test_token_digest_is_sha256() -> None:
    digest = token_digest("example-token")

    assert digest == hashlib.sha256(b"example-token").digest()
    assert len(digest) == 32


def test_tokens_match_compares_constant_time() -> None:
    assert tokens_match(token_digest("a"), token_digest("a")) is True
    assert tokens_match(token_digest("a"), token_digest("b")) is False
    assert tokens_match(b"short", b"much-longer-value") is False
