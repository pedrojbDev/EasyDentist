from fastapi import FastAPI

from app.platform.health import router as platform_router


def create_app() -> FastAPI:
    app = FastAPI(title="EasyDentist API", version="0.1.0")
    app.include_router(platform_router)
    return app
