from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta

import pytest

from app.auth.settings import AuthSettings


def test_development_defaults() -> None:
    settings = AuthSettings.from_environment({})

    assert settings.app_env == "development"
    assert settings.cookie_secure is False
    assert settings.session_cookie_name == "easydent_session"
    assert settings.csrf_cookie_name == "easydent_csrf"
    assert settings.session_idle_ttl == timedelta(hours=12)
    assert settings.session_absolute_ttl == timedelta(days=30)
    assert settings.last_seen_throttle == timedelta(minutes=5)
    assert settings.argon2_time_cost == 3
    assert settings.argon2_memory_kib == 65536
    assert settings.argon2_parallelism == 1
    assert settings.allowed_origins == ("http://localhost:3000",)
    assert settings.public_base_url == "http://localhost:3000"
    assert settings.trusted_proxies == ()
    assert len(settings.auth_secret) >= 32


def test_production_requires_auth_secret() -> None:
    with pytest.raises(RuntimeError, match="AUTH_SECRET is required in production"):
        AuthSettings.from_environment({"APP_ENV": "production"})


def test_rejects_short_auth_secret() -> None:
    environment: Mapping[str, str] = {"AUTH_SECRET": "too-short"}

    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        AuthSettings.from_environment(environment)


def test_rejects_unknown_app_environment() -> None:
    with pytest.raises(RuntimeError, match="APP_ENV must be"):
        AuthSettings.from_environment({"APP_ENV": "staging"})


def test_production_cookie_hardening() -> None:
    environment: Mapping[str, str] = {
        "APP_ENV": "production",
        "AUTH_SECRET": "p" * 32,
    }

    settings = AuthSettings.from_environment(environment)

    assert settings.cookie_secure is True
    assert settings.session_cookie_name == "__Host-easydent_session"
    assert settings.csrf_cookie_name == "__Host-easydent_csrf"


def test_parses_comma_separated_lists() -> None:
    environment: Mapping[str, str] = {
        "TRUSTED_PROXIES": "10.0.0.1, 10.0.0.2 ,",
        "ALLOWED_ORIGINS": "https://app.example.com, https://admin.example.com",
    }

    settings = AuthSettings.from_environment(environment)

    assert settings.trusted_proxies == ("10.0.0.1", "10.0.0.2")
    assert settings.allowed_origins == (
        "https://app.example.com",
        "https://admin.example.com",
    )


def test_smtp_and_public_url_overrides() -> None:
    environment: Mapping[str, str] = {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "2525",
        "SMTP_SENDER": "contato@example.com",
        "PUBLIC_BASE_URL": "https://app.example.com",
    }

    settings = AuthSettings.from_environment(environment)

    assert settings.smtp_host == "smtp.example.com"
    assert settings.smtp_port == 2525
    assert settings.smtp_sender == "contato@example.com"
    assert settings.public_base_url == "https://app.example.com"


def test_rejects_invalid_smtp_port() -> None:
    with pytest.raises(RuntimeError, match="SMTP_PORT must be an integer"):
        AuthSettings.from_environment({"SMTP_PORT": "not-a-port"})
