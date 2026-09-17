from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Callable
from datetime import datetime
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.models import EmailOutbox
from app.auth.repositories.outbox_repository import EmailOutboxRepository
from app.auth.settings import AuthSettings
from app.core.clock import utcnow
from app.core.database import transaction_scope


class EmailSender(Protocol):
    async def send(self, recipient: str, subject: str, body: str) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: AuthSettings) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._sender = settings.smtp_sender

    async def send(self, recipient: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_sync, recipient, subject, body)

    def _send_sync(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=10) as client:
            client.send_message(message)


class EmailOutboxService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sender: EmailSender,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._sender = sender
        self._clock = clock

    async def enqueue(
        self,
        session: AsyncSession,
        *,
        idempotency_key: str,
        recipient: str,
        template: str,
        subject: str,
        body: str,
    ) -> EmailOutbox:
        repository = EmailOutboxRepository(session)
        outbox = repository.add(
            idempotency_key=idempotency_key,
            recipient=recipient,
            template=template,
            subject=subject,
            body=body,
        )
        await repository.flush()
        return outbox

    async def deliver_pending(self, *, limit: int = 10) -> None:
        now = self._clock()
        async with transaction_scope(self._session_factory) as session:
            repository = EmailOutboxRepository(session)
            for outbox in await repository.list_due(limit=limit, now=now):
                await self._attempt(repository, outbox, now)

    async def _attempt(
        self, repository: EmailOutboxRepository, outbox: EmailOutbox, now: datetime
    ) -> None:
        subject = str(outbox.payload.get("subject", ""))
        body = str(outbox.payload.get("body", ""))
        try:
            await self._sender.send(outbox.recipient, subject, body)
        except Exception:
            repository.mark_attempt_failed(outbox, now=now)
        else:
            repository.mark_sent(outbox, now=now)
        await repository.flush()
