from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from conftest import make_test_email
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.repositories.password_credential_repository import PasswordCredentialRepository
from app.auth.repositories.session_repository import SessionRepository
from app.auth.tokens import token_digest
from app.core.database import transaction_scope
from app.users.repositories.user_repository import UserRepository

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


async def create_session(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, token: str
) -> uuid.UUID:
    async with transaction_scope(session_factory) as session:
        row = SessionRepository(session).add(
            user_id=user_id,
            token_hash=token_digest(token),
            last_seen_at=NOW,
            idle_expires_at=NOW + timedelta(hours=12),
            absolute_expires_at=NOW + timedelta(days=30),
        )
        await session.flush()
        return row.id


@pytest.mark.anyio
async def test_session_repository_roundtrip(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("session"), password="password-12345"
    )
    token = "session-token-value"
    session_id = await create_session(session_factory, user_id, token)

    async with transaction_scope(session_factory) as session:
        repository = SessionRepository(session)
        found = await repository.find_by_token_hash(token_digest(token))
        missing = await repository.find_by_token_hash(token_digest("other-token"))
        owned = await repository.get_for_user(session_id, user_id)
        foreign = await repository.get_for_user(session_id, uuid.uuid4())
        listed = await repository.list_for_user(user_id)

    assert found is not None
    assert found.id == session_id
    assert found.token_hash == token_digest(token)
    assert missing is None
    assert owned is not None
    assert foreign is None
    assert [row.id for row in listed] == [session_id]


@pytest.mark.anyio
async def test_session_repository_revokes_all_for_user(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("revoke"), password="password-12345"
    )
    await create_session(session_factory, user_id, "token-one")
    await create_session(session_factory, user_id, "token-two")

    async with transaction_scope(session_factory) as session:
        revoked = await SessionRepository(session).revoke_all_for_user(user_id, now=NOW)

    assert revoked == 2

    async with transaction_scope(session_factory) as session:
        again = await SessionRepository(session).revoke_all_for_user(user_id, now=NOW)
        listed = await SessionRepository(session).list_for_user(user_id)

    assert again == 0
    assert all(row.revoked_at == NOW for row in listed)


@pytest.mark.anyio
async def test_password_credential_repository_upserts(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("credential"), password="password-12345"
    )

    async with transaction_scope(session_factory) as session:
        repository = PasswordCredentialRepository(session)
        created = await repository.get(user_id)
        assert created is not None
        await repository.upsert(
            user_id=user_id,
            password_hash="new-hash-value",
            changed_at=NOW + timedelta(minutes=1),
        )

    async with transaction_scope(session_factory) as session:
        updated = await PasswordCredentialRepository(session).get(user_id)

    assert updated is not None
    assert updated.password_hash == "new-hash-value"
    assert updated.changed_at == NOW + timedelta(minutes=1)


@pytest.mark.anyio
async def test_user_repository_finds_email_case_insensitively(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    email = make_test_email("CaseCheck")
    user_id = await seed_user_with_password(email=email, password="password-12345")

    async with transaction_scope(session_factory) as session:
        repository = UserRepository(session)
        found = await repository.find_by_email(email.upper())
        missing = await repository.find_by_email(make_test_email("absent"))
        by_id = await repository.get(user_id)

    assert found is not None
    assert found.id == user_id
    assert missing is None
    assert by_id is not None
    assert by_id.id == user_id


@pytest.mark.anyio
async def test_user_repository_marks_email_verified(
    session_factory: async_sessionmaker[AsyncSession],
    seed_user_with_password,
    clean_auth_state: None,
) -> None:
    user_id = await seed_user_with_password(
        email=make_test_email("verify"), password="password-12345"
    )

    async with transaction_scope(session_factory) as session:
        repository = UserRepository(session)
        user = await repository.get(user_id)
        assert user is not None
        assert user.email_verified_at is None
        repository.set_email_verified(user, now=NOW)

    async with transaction_scope(session_factory) as session:
        verified = await UserRepository(session).get(user_id)

    assert verified is not None
    assert verified.email_verified_at == NOW
