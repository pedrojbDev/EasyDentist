from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import EmailOutbox

MAX_DELIVERY_ATTEMPTS = 5
BASE_BACKOFF = timedelta(seconds=30)
MAX_BACKOFF = timedelta(hours=1)


def next_attempt_at(attempts: int, now: datetime) -> datetime:
    delay: timedelta = BASE_BACKOFF * (2 ** max(attempts - 1, 0))
    capped: timedelta = min(delay, MAX_BACKOFF)
    return now + capped


class EmailOutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(
        self,
        *,
        idempotency_key: str,
        recipient: str,
        template: str,
        subject: str,
        body: str,
    ) -> EmailOutbox:
        outbox = EmailOutbox(
            idempotency_key=idempotency_key,
            recipient=recipient,
            template=template,
            payload={"subject": subject, "body": body},
        )
        self._session.add(outbox)
        return outbox

    async def list_due(self, *, limit: int, now: datetime) -> Sequence[EmailOutbox]:
        statement = (
            select(EmailOutbox)
            .where(
                EmailOutbox.status == "PENDING",
                or_(
                    EmailOutbox.next_attempt_at.is_(None),
                    EmailOutbox.next_attempt_at <= now,
                ),
            )
            .order_by(EmailOutbox.created_at, EmailOutbox.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(statement)
        return result.scalars().all()

    def mark_sent(self, outbox: EmailOutbox, *, now: datetime) -> None:
        outbox.status = "SENT"
        outbox.sent_at = now
        outbox.next_attempt_at = None
        outbox.updated_at = now

    def mark_attempt_failed(self, outbox: EmailOutbox, *, now: datetime) -> None:
        outbox.attempt_count += 1
        outbox.updated_at = now
        if outbox.attempt_count >= MAX_DELIVERY_ATTEMPTS:
            outbox.status = "FAILED"
            outbox.next_attempt_at = None
        else:
            outbox.next_attempt_at = next_attempt_at(outbox.attempt_count, now)

    async def flush(self) -> None:
        await self._session.flush()
