from __future__ import annotations

from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.passwords import PasswordHasher
from app.auth.repositories.password_credential_repository import PasswordCredentialRepository
from app.core.clock import utcnow
from app.core.database import transaction_scope
from app.users.repositories.user_repository import UserRepository


class Authenticator(Protocol):
    async def authenticate(self, email: str, password: str) -> UUID | None: ...


class LocalPasswordAuthenticator:
    """Argon2id provider; verifies against a dummy hash when the account is
    unknown so the response time does not reveal account existence."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        password_hasher: PasswordHasher,
    ) -> None:
        self._session_factory = session_factory
        self._password_hasher = password_hasher
        self._dummy_hash = password_hasher.hash("easydentist-dummy-password")

    async def authenticate(self, email: str, password: str) -> UUID | None:
        async with transaction_scope(self._session_factory) as session:
            user = await UserRepository(session).find_by_email(email.strip())
            if user is None or user.status != "ACTIVE":
                self._password_hasher.verify_and_rehash(password, self._dummy_hash)
                return None

            credentials = PasswordCredentialRepository(session)
            credential = await credentials.get(user.id)
            if credential is None:
                self._password_hasher.verify_and_rehash(password, self._dummy_hash)
                return None

            verified, new_hash = self._password_hasher.verify_and_rehash(
                password, credential.password_hash
            )
            if not verified:
                return None
            if new_hash is not None:
                await credentials.upsert(
                    user_id=user.id, password_hash=new_hash, changed_at=utcnow()
                )
            return user.id
