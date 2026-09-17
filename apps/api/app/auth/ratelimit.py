from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.settings import AuthSettings
from app.core.database import transaction_scope

LOGIN_ACCOUNT_LIMIT = 5
LOGIN_ACCOUNT_WINDOW_SECONDS = 900
LOGIN_IP_LIMIT = 20
LOGIN_IP_WINDOW_SECONDS = 900
RECOVERY_RECIPIENT_LIMIT = 3
RECOVERY_RECIPIENT_WINDOW_SECONDS = 3600
RECOVERY_IP_LIMIT = 20
RECOVERY_IP_WINDOW_SECONDS = 3600


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    retry_after_seconds: int


class RateLimiter:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: AuthSettings,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings

    def bucket_key(self, kind: str, identifier: str) -> bytes:
        return hmac.new(
            self._settings.auth_secret,
            f"{kind}:{identifier}".encode(),
            hashlib.sha256,
        ).digest()

    async def consume(
        self, kind: str, identifier: str, *, limit: int, window_seconds: int
    ) -> RateDecision:
        async with transaction_scope(self._session_factory) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT allowed, retry_after_seconds "
                        "FROM app.consume_rate_limit(:bucket_key, :limit, :window_seconds)"
                    ),
                    {
                        "bucket_key": self.bucket_key(kind, identifier),
                        "limit": limit,
                        "window_seconds": window_seconds,
                    },
                )
            ).one()
        return RateDecision(
            allowed=bool(row.allowed),
            retry_after_seconds=int(row.retry_after_seconds),
        )

    async def clear(self, kind: str, identifier: str) -> None:
        async with transaction_scope(self._session_factory) as session:
            await session.execute(
                text("DELETE FROM app.auth_rate_limit_buckets WHERE bucket_key = :bucket_key"),
                {"bucket_key": self.bucket_key(kind, identifier)},
            )
