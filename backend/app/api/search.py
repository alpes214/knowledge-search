from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(tags=["search"])


@router.get("/search", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def search(q: str = "") -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "Phase 4: vector search not yet implemented"},
    )
