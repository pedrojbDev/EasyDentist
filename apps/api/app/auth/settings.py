from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

DEVELOPMENT = "development"
PRODUCTION = "production"
MINIMUM_SECRET_BYTES = 32
DEVELOPMENT_SECRET = "easydentist-development-secret-not-for-production"

SESSION_IDLE_TTL = timedelta(hours=12)
SESSION_ABSOLUTE_TTL = timedelta(days=30)
LAST_SEEN_THROTTLE = timedelta(minutes=5)

ARGON2_TIME_COST = 3
ARGON2_MEMORY_KIB = 65536
ARGON2_PARALLELISM = 1

DEFAULT_SMTP_HOST = "localhost"
DEFAULT_SMTP_PORT = 1025
DEFAULT_SMTP_SENDER = "no-reply@easydentist.local"
DEFAULT_PUBLIC_BASE_URL = "http://localhost:3000"
DEFAULT_DEVELOPMENT_ORIGIN = "http://localhost:3000"


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class AuthSettings:
    app_env: str
    auth_secret: bytes
    session_cookie_name: str
    csrf_cookie_name: str
    cookie_secure: bool
    session_idle_ttl: timedelta
    session_absolute_ttl: timedelta
    last_seen_throttle: timedelta
    argon2_time_cost: int
    argon2_memory_kib: int
    argon2_parallelism: int
    trusted_proxies: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    smtp_host: str
    smtp_port: int
    smtp_sender: str
    public_base_url: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> AuthSettings:
        values = os.environ if environment is None else environment

        app_env = values.get("APP_ENV", DEVELOPMENT).strip().lower()
        if app_env not in (DEVELOPMENT, PRODUCTION):
            raise RuntimeError("APP_ENV must be 'development' or 'production'")
        production = app_env == PRODUCTION

        raw_secret = values.get("AUTH_SECRET", "").strip()
        if not raw_secret:
            if production:
                raise RuntimeError("AUTH_SECRET is required in production")
            raw_secret = DEVELOPMENT_SECRET
        elif production and raw_secret == DEVELOPMENT_SECRET:
            raise RuntimeError("AUTH_SECRET must not use the development default in production")
        auth_secret = raw_secret.encode()
        if len(auth_secret) < MINIMUM_SECRET_BYTES:
            raise RuntimeError(f"AUTH_SECRET must be at least {MINIMUM_SECRET_BYTES} bytes")

        raw_port = values.get("SMTP_PORT", str(DEFAULT_SMTP_PORT)).strip()
        try:
            smtp_port = int(raw_port)
        except ValueError as error:
            raise RuntimeError("SMTP_PORT must be an integer") from error

        raw_origins = values.get("ALLOWED_ORIGINS", "")
        allowed_origins = _csv_tuple(raw_origins)
        if not allowed_origins and not production:
            allowed_origins = (DEFAULT_DEVELOPMENT_ORIGIN,)

        return cls(
            app_env=app_env,
            auth_secret=auth_secret,
            session_cookie_name="__Host-easydent_session" if production else "easydent_session",
            csrf_cookie_name="__Host-easydent_csrf" if production else "easydent_csrf",
            cookie_secure=production,
            session_idle_ttl=SESSION_IDLE_TTL,
            session_absolute_ttl=SESSION_ABSOLUTE_TTL,
            last_seen_throttle=LAST_SEEN_THROTTLE,
            argon2_time_cost=ARGON2_TIME_COST,
            argon2_memory_kib=ARGON2_MEMORY_KIB,
            argon2_parallelism=ARGON2_PARALLELISM,
            trusted_proxies=_csv_tuple(values.get("TRUSTED_PROXIES", "")),
            allowed_origins=allowed_origins,
            smtp_host=values.get("SMTP_HOST", DEFAULT_SMTP_HOST).strip() or DEFAULT_SMTP_HOST,
            smtp_port=smtp_port,
            smtp_sender=values.get("SMTP_SENDER", DEFAULT_SMTP_SENDER).strip()
            or DEFAULT_SMTP_SENDER,
            public_base_url=values.get("PUBLIC_BASE_URL", DEFAULT_PUBLIC_BASE_URL).strip()
            or DEFAULT_PUBLIC_BASE_URL,
        )
