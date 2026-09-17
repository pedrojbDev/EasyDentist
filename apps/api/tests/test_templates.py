from __future__ import annotations

from app.auth.settings import AuthSettings
from app.auth.templates import (
    EMAIL_VERIFICATION_TEMPLATE,
    PASSWORD_RESET_TEMPLATE,
    email_idempotency_key,
    email_verification_message,
    invitation_message,
    password_reset_message,
)

TOKEN = "token-with-256-bits-of-entropy"


def test_email_verification_message_uses_fragment_link() -> None:
    settings = AuthSettings.from_environment({})

    subject, body = email_verification_message(settings, TOKEN)

    assert f"{settings.public_base_url}/verify-email#token={TOKEN}" in body
    assert TOKEN not in subject
    assert "e-mail" in subject.lower()
    assert "24 horas" in body


def test_password_reset_message_uses_fragment_link() -> None:
    settings = AuthSettings.from_environment({})

    subject, body = password_reset_message(settings, TOKEN)

    assert f"{settings.public_base_url}/reset-password#token={TOKEN}" in body
    assert TOKEN not in subject
    assert "senha" in subject.lower()
    assert "30 minutos" in body


def test_messages_respect_public_base_url_with_trailing_slash() -> None:
    settings = AuthSettings.from_environment({"PUBLIC_BASE_URL": "https://app.example.com/"})

    _, body = password_reset_message(settings, TOKEN)

    assert "https://app.example.com/reset-password#token=" in body
    assert "example.com//reset-password" not in body


def test_invitation_message_uses_fragment_link_and_clinic_name() -> None:
    settings = AuthSettings.from_environment({})

    subject, body = invitation_message(settings, TOKEN, clinic_name="Clínica Sorriso")

    assert f"{settings.public_base_url}/accept-invitation#token={TOKEN}" in body
    assert "Clínica Sorriso" in subject
    assert "Clínica Sorriso" in body
    assert "72 horas" in body
    assert TOKEN not in subject


def test_idempotency_key_is_semantic_and_hides_the_raw_token() -> None:
    key = email_idempotency_key(EMAIL_VERIFICATION_TEMPLATE, TOKEN)

    assert key.startswith(f"{EMAIL_VERIFICATION_TEMPLATE}:")
    assert TOKEN not in key
    assert key == email_idempotency_key(EMAIL_VERIFICATION_TEMPLATE, TOKEN)
    assert key != email_idempotency_key(EMAIL_VERIFICATION_TEMPLATE, f"{TOKEN}-other")
    assert email_idempotency_key(PASSWORD_RESET_TEMPLATE, TOKEN) != key
