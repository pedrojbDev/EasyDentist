from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.application import create_app

DATABASE_URL = "postgresql+asyncpg://app:secret@db:5432/easydentist"


@pytest.mark.anyio
async def test_lifespan_wires_engine_and_session_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    app = create_app()

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.engine, AsyncEngine)
        assert isinstance(app.state.session_factory, async_sessionmaker)


@pytest.mark.anyio
async def test_lifespan_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = create_app()

    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        async with app.router.lifespan_context(app):
            pass


def test_app_creation_does_not_require_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app()

    assert app.title == "EasyDentist API"
