from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models as _models  # noqa: F401
from app.auth.emails import SmtpEmailSender
from app.auth.routers import invitations_router
from app.auth.routers import router as auth_router
from app.auth.settings import AuthSettings
from app.clinics.routers import router as clinics_router
from app.core.database import DatabaseSettings, create_database_engine, create_session_factory
from app.platform.health import router as platform_router
from app.platform.middleware import RequestIdMiddleware
from app.platform.problems import register_problem_handlers
from app.platform.security_headers import SecurityHeadersMiddleware, is_production_environment


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = DatabaseSettings.from_environment()
        engine = create_database_engine(settings.database_url)
        auth_settings = AuthSettings.from_environment()
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.auth_settings = auth_settings
        app.state.email_sender = SmtpEmailSender(auth_settings)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title="EasyDentist API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, production=is_production_environment())
    register_problem_handlers(app)
    app.include_router(platform_router)
    app.include_router(auth_router)
    app.include_router(invitations_router)
    app.include_router(clinics_router)
    return app
