from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["platform"])
async def health() -> dict[str, str]:
    return {"service": "api", "status": "ok"}
