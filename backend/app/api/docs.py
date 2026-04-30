from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.app.db import postgres

router = APIRouter(prefix="/docs", tags=["docs"])


@router.post("", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def upload() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "Phase 2: PDF upload + ingest not yet implemented"},
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"postgres": "ok" if postgres.is_healthy() else "down"}
