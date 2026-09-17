from __future__ import annotations

import uuid
from datetime import UTC, datetime

import argon2
import pytest
from argon2 import PasswordHasher as Argon2PasswordHasher
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.authenticator import Authenticator, LocalPasswordAuthenticator
from app.auth.passwords import PasswordHasher
from app.auth.repositories.password_credential_repository import PasswordCredentialRepository
from app.auth.settings import AuthSettings
from app.core.database import transaction_scope
from app.users.models import User

PASSWORD = "correct horse battery staple"


class FakeAuthenticator:
    def __init__(self, credentials: dict[str, tuple[uuid.UUID, str]]) -> None:
        self._credentials = credentials

    async def authenticate(self, email: str, password: str) -> uuid.UUID | None:
        record = self._credentials.get(email)
        if record is None:
            return None
        user_id, expected = record
        return user_id if password == expected else None


async def assert_authenticator_contract(
    authenticator: Authenticator,
    *,
    known_email: str,
    known_user_id: uuid.UUID,
    unknown_email: str,
) -> None:
    assert await authenticator.authenticate(unknown_email, PASSWORD) is None
    assert await authenticator.authenticate(known_email, "wrong password entirely") is None
    assert await authenticator.authenticate(known_email, PASSWORD) == known_user_id


@pytest.mark.anyio
async def test_local_authenticator_satisfies_contract(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("local-auth")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    authenticator = LocalPasswordAuthenticator(session_factory, PasswordHasher(auth_settings))

    await assert_authenticator_contract(
        authenticator,
        known_email=email,
        known_user_id=user_id,
        unknown_email=make_test_email("absent"),
    )


@pytest.mark.anyio
async def test_fake_authenticator_satisfies_contract() -> None:
    known_email = "fake-known@test.invalid"
    user_id = uuid.uuid4()
    authenticator = FakeAuthenticator({known_email: (user_id, PASSWORD)})

    await assert_authenticator_contract(
        authenticator,
        known_email=known_email,
        known_user_id=user_id,
        unknown_email="fake-absent@test.invalid",
    )


@pytest.mark.anyio
async def test_local_authenticator_rejects_disabled_user(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("disabled")
    user_id = await seed_user_with_password(email=email, password=PASSWORD)
    async with transaction_scope(session_factory) as session:
        user = await session.get(User, user_id)
        assert user is not None
        user.status = "DISABLED"
    authenticator = LocalPasswordAuthenticator(session_factory, PasswordHasher(auth_settings))

    assert await authenticator.authenticate(email, PASSWORD) is None


@pytest.mark.anyio
async def test_local_authenticator_rehashes_outdated_credentials(
    session_factory: async_sessionmaker[AsyncSession],
    auth_settings: AuthSettings,
    clean_auth_state: None,
) -> None:
    email = make_test_email("rehash")
    outdated = Argon2PasswordHasher(
        time_cost=2, memory_cost=8192, parallelism=2, hash_len=32, salt_len=16
    ).hash(PASSWORD)
    async with transaction_scope(session_factory) as session:
        user = User(email=email)
        session.add(user)
        await session.flush()
        await PasswordCredentialRepository(session).upsert(
            user_id=user.id,
            password_hash=outdated,
            changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        user_id = user.id
    authenticator = LocalPasswordAuthenticator(session_factory, PasswordHasher(auth_settings))

    assert await authenticator.authenticate(email, PASSWORD) == user_id

    async with transaction_scope(session_factory) as session:
        credential = await PasswordCredentialRepository(session).get(user_id)

    assert credential is not None
    parameters = argon2.extract_parameters(credential.password_hash)
    assert parameters.time_cost == 3
    assert parameters.memory_cost == 65536
    assert parameters.parallelism == 1
