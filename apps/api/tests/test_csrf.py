from __future__ import annotations

from app.auth.csrf import ANONYMOUS_BINDING, CsrfService

SECRET = b"csrf-test-secret-with-enough-bytes"


def test_issue_and_verify_roundtrip() -> None:
    service = CsrfService(SECRET)

    value = service.issue(ANONYMOUS_BINDING)

    assert value.count(".") == 1
    assert service.verify(value, ANONYMOUS_BINDING) is True


def test_verify_rejects_other_binding() -> None:
    service = CsrfService(SECRET)

    value = service.issue("session-one")

    assert service.verify(value, "session-two") is False
    assert service.verify(value, ANONYMOUS_BINDING) is False


def test_verify_rejects_another_secret() -> None:
    value = CsrfService(SECRET).issue(ANONYMOUS_BINDING)

    assert (
        CsrfService(b"another-secret-with-enough-bytes!!").verify(value, ANONYMOUS_BINDING) is False
    )


def test_verify_rejects_tampered_token_and_signature() -> None:
    service = CsrfService(SECRET)
    value = service.issue(ANONYMOUS_BINDING)
    token, _, signature = value.partition(".")

    assert service.verify(f"x{token}.{signature}", ANONYMOUS_BINDING) is False
    assert service.verify(f"{token}.{signature}x", ANONYMOUS_BINDING) is False


def test_verify_rejects_malformed_values() -> None:
    service = CsrfService(SECRET)

    for value in ("", "token", ".", "token.", ".signature"):
        assert service.verify(value, ANONYMOUS_BINDING) is False


def test_issued_values_are_unique() -> None:
    service = CsrfService(SECRET)

    assert service.issue(ANONYMOUS_BINDING) != service.issue(ANONYMOUS_BINDING)
