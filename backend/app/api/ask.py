from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

router = APIRouter(tags=["ask"])


@router.post("/ask", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def ask() -> JSONResponse:
    return JSONResponse(
        status_code=501,
        content={"detail": "Phase 5: LLM-synthesised answer not yet implemented"},
    )
