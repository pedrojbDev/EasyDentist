import importlib

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.application import create_app

app = main.app


@pytest.mark.anyio
async def test_health_returns_api_service_contract() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "ok"}


@pytest.mark.anyio
async def test_application_factory_registers_the_health_contract() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "ok"}


def test_main_exposes_the_application_created_by_the_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.application as application

    instance = object()
    monkeypatch.setattr(application, "create_app", lambda: instance)
    try:
        reloaded_main = importlib.reload(main)
        assert reloaded_main.app is instance
    finally:
        monkeypatch.undo()
        importlib.reload(main)
