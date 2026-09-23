from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.types import ASGIApp

from app import models as _models  # noqa: F401
from app.anamnesis.routers import router as anamnesis_router
from app.appointments.resource_routers import router as agenda_resources_router
from app.appointments.schedule_routers import router as agenda_router
from app.auth.emails import SmtpEmailSender
from app.auth.routers import invitations_router
from app.auth.routers import router as auth_router
from app.auth.settings import AuthSettings
from app.clinics.routers import router as clinics_router
from app.core.database import DatabaseSettings, create_database_engine, create_session_factory
from app.documents.routers import router as documents_router
from app.patients.routers import router as patients_router
from app.platform.body_limit import BodyLimitMiddleware
from app.platform.health import router as platform_router
from app.platform.middleware import RequestLoggingMiddleware
from app.platform.problems import register_problem_handlers
from app.platform.s3_storage import StorageSettings, create_s3_storage
from app.platform.security_headers import SecurityHeadersMiddleware, is_production_environment
from app.users.routers import router as users_router


class HardenedFastAPI(FastAPI):
    """Wraps the whole Starlette stack, including ServerErrorMiddleware.

    Regular middlewares registered with `add_middleware` run inside
    ServerErrorMiddleware, so a 500 produced from an unhandled exception would
    bypass them. Building the hardening middlewares outside the stack keeps the
    security headers, the request ID and the structured access event on every
    response, 500 included.
    """

    def build_middleware_stack(self) -> ASGIApp:
        return RequestLoggingMiddleware(
            SecurityHeadersMiddleware(
                BodyLimitMiddleware(super().build_middleware_stack()),
                production=is_production_environment(),
            )
        )


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = DatabaseSettings.from_environment()
        engine = create_database_engine(settings.database_url)
        auth_settings = AuthSettings.from_environment()
        storage_settings = StorageSettings.from_environment()
        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.auth_settings = auth_settings
        app.state.email_sender = SmtpEmailSender(auth_settings)
        app.state.object_storage = create_s3_storage(storage_settings)
        try:
            yield
        finally:
            await engine.dispose()

    app = HardenedFastAPI(title="EasyDentist API", version="0.1.0", lifespan=lifespan)
    register_problem_handlers(app)
    app.include_router(platform_router)
    app.include_router(auth_router)
    app.include_router(invitations_router)
    app.include_router(clinics_router)
    app.include_router(patients_router)
    app.include_router(users_router)
    app.include_router(anamnesis_router)
    app.include_router(documents_router)
    app.include_router(agenda_resources_router)
    app.include_router(agenda_router)
    return app
