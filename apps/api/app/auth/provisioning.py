from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.emails import EmailOutboxService, EmailSender
from app.auth.settings import AuthSettings
from app.auth.templates import INVITATION_TEMPLATE, email_idempotency_key, invitation_message
from app.auth.tokens import generate_token, token_digest
from app.core.clock import utcnow
from app.core.database import transaction_scope
from app.core.errors import translate_integrity_error

DEFAULT_TIMEZONE = "America/Bahia"


@dataclass(frozen=True, slots=True)
class ProvisionedInvitation:
    user_id: UUID
    clinic_id: UUID
    invitation_expires_at: datetime
    recipient: str
    slug: str


class ProvisionService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        settings: AuthSettings,
        sender: EmailSender,
        *,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._sender = sender
        self._clock = clock

    async def provision(
        self,
        *,
        email: str,
        name: str,
        slug: str,
        display_name: str | None = None,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> ProvisionedInvitation:
        token = generate_token()
        outbox = EmailOutboxService(self._session_factory, self._sender, clock=self._clock)
        try:
            async with transaction_scope(self._session_factory) as session:
                row = (
                    await session.execute(
                        text(
                            "SELECT user_id, clinic_id, invitation_expires_at "
                            "FROM app.provision_clinic_owner("
                            ":email, :name, :slug, :timezone, :display_name, :token_hash)"
                        ),
                        {
                            "email": email,
                            "name": name,
                            "slug": slug,
                            "timezone": timezone,
                            "display_name": display_name if display_name is not None else name,
                            "token_hash": token_digest(token),
                        },
                    )
                ).one()
                subject, body = invitation_message(
                    self._settings,
                    token,
                    clinic_name=display_name if display_name is not None else name,
                )
                await outbox.enqueue(
                    session,
                    idempotency_key=email_idempotency_key(INVITATION_TEMPLATE, token),
                    recipient=email,
                    template=INVITATION_TEMPLATE,
                    subject=subject,
                    body=body,
                )
        except IntegrityError as error:
            raise translate_integrity_error(error) from error

        await outbox.deliver_pending()
        return ProvisionedInvitation(
            user_id=row.user_id,
            clinic_id=row.clinic_id,
            invitation_expires_at=row.invitation_expires_at,
            recipient=email,
            slug=slug,
        )
