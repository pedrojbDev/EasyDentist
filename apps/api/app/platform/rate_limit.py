from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.audit import AuthAuditService
from app.auth.ratelimit import (
    RECOVERY_IP_LIMIT,
    RECOVERY_IP_WINDOW_SECONDS,
    RECOVERY_RECIPIENT_LIMIT,
    RECOVERY_RECIPIENT_WINDOW_SECONDS,
    RateLimiter,
)
from app.auth.settings import AuthSettings
from app.core.database import transaction_scope
from app.platform.network import client_ip


async def enforce_recovery_rate_limit(
    request: Request,
    settings: AuthSettings,
    session_factory: async_sessionmaker[AsyncSession],
    identifier: str,
) -> None:
    limiter = RateLimiter(session_factory, settings)
    recipient_decision = await limiter.consume(
        "recovery_recipient",
        identifier,
        limit=RECOVERY_RECIPIENT_LIMIT,
        window_seconds=RECOVERY_RECIPIENT_WINDOW_SECONDS,
    )
    ip_decision = await limiter.consume(
        "recovery_ip",
        client_ip(request, settings.trusted_proxies),
        limit=RECOVERY_IP_LIMIT,
        window_seconds=RECOVERY_IP_WINDOW_SECONDS,
    )
    if recipient_decision.allowed and ip_decision.allowed:
        return
    retry_after = max(recipient_decision.retry_after_seconds, ip_decision.retry_after_seconds)
    async with transaction_scope(session_factory) as session:
        await AuthAuditService(session).record("rate_limit_triggered")
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after)},
    )
