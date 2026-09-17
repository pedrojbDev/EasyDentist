from __future__ import annotations

from collections.abc import Mapping

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    Base,
    DatabaseSettings,
    create_database_engine,
    create_session_factory,
    transaction_scope,
)


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSession:
        return self.session


def test_database_settings_require_database_url() -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        DatabaseSettings.from_environment({})


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@db/easydentist",
        "sqlite+aiosqlite:///easydentist.db",
        "not-a-database-url",
    ],
)
def test_database_settings_require_asyncpg(database_url: str) -> None:
    environment: Mapping[str, str] = {"DATABASE_URL": database_url}

    with pytest.raises(RuntimeError, match=r"postgresql\+asyncpg"):
        DatabaseSettings.from_environment(environment)


def test_database_settings_accept_asyncpg_url() -> None:
    settings = DatabaseSettings.from_environment(
        {"DATABASE_URL": "postgresql+asyncpg://app:secret@db:5432/easydentist"}
    )

    assert settings.database_url == "postgresql+asyncpg://app:secret@db:5432/easydentist"


def test_base_uses_app_schema_and_deterministic_constraint_names() -> None:
    assert Base.metadata.schema == "app"
    assert Base.metadata.naming_convention == {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


@pytest.mark.anyio
async def test_session_factory_disables_expiration_and_autoflush() -> None:
    engine = create_database_engine("postgresql+asyncpg://app:secret@db/easydentist")
    factory = create_session_factory(engine)

    assert factory.kw["expire_on_commit"] is False
    assert factory.kw["autoflush"] is False
    assert factory.class_ is AsyncSession
    await engine.dispose()


@pytest.mark.anyio
async def test_transaction_scope_commits_and_closes_on_success() -> None:
    session = FakeSession()

    async with transaction_scope(FakeSessionFactory(session)):  # type: ignore[arg-type]
        pass

    assert session.committed is True
    assert session.rolled_back is False
    assert session.closed is True


@pytest.mark.anyio
async def test_transaction_scope_rolls_back_and_closes_on_error() -> None:
    session = FakeSession()

    with pytest.raises(ValueError, match="boom"):
        async with transaction_scope(FakeSessionFactory(session)):  # type: ignore[arg-type]
            raise ValueError("boom")

    assert session.committed is False
    assert session.rolled_back is True
    assert session.closed is True
