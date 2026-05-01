"""Document upload + listing + delete endpoints."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import postgres
from backend.app.db.postgres import get_session
from backend.app.queue.tasks import ingest_document
from backend.app.repos.docs import (
    delete_document,
    find_by_sha256,
    insert_document,
    list_documents,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/docs", tags=["docs"])

ALLOWED_EXTENSIONS = {".pdf"}


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    status: str
    page_count: int | None
    chunk_count: int | None
    error_message: str | None
    uploaded_at: datetime


class UploadResponse(BaseModel):
    doc_id: UUID
    status: str


@router.get("/health")
async def health() -> dict[str, str]:
    return {"postgres": postgres.status()}


@router.get("", response_model=list[DocumentOut])
async def list_docs(session: AsyncSession = Depends(get_session)) -> list[DocumentOut]:
    docs = await list_documents(session)
    return [
        DocumentOut(
            id=d.id,
            filename=d.filename,
            status=d.status,
            page_count=d.page_count,
            chunk_count=d.chunk_count,
            error_message=d.error_message,
            uploaded_at=d.uploaded_at,
        )
        for d in docs
    ]


@router.post("", response_model=UploadResponse, status_code=201)
async def upload(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> UploadResponse:
    filename = file.filename or "upload.pdf"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {ext}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="Empty file")

    sha = hashlib.sha256(body).hexdigest()

    existing = await find_by_sha256(session, sha)
    if existing is not None:
        log.info("upload idempotent doc=%s status=%s", existing.id, existing.status)
        return UploadResponse(doc_id=existing.id, status=existing.status)

    doc = await insert_document(session, filename=filename, sha256=sha, status="pending")
    await session.commit()

    settings.staging_dir.mkdir(parents=True, exist_ok=True)
    (settings.staging_dir / f"{doc.id}.pdf").write_bytes(body)

    await ingest_document.defer_async(doc_id=str(doc.id))
    log.info("upload accepted doc=%s sha=%s", doc.id, sha[:12])
    return UploadResponse(doc_id=doc.id, status=doc.status)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_doc(
    doc_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    from backend.app.db.models import Document

    doc = await session.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        status=doc.status,
        page_count=doc.page_count,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        uploaded_at=doc.uploaded_at,
    )


@router.delete("/{doc_id}", status_code=204)
async def delete_doc(
    doc_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_document(session, doc_id)
    await session.commit()
    staging_file = settings.staging_dir / f"{doc_id}.pdf"
    staging_file.unlink(missing_ok=True)
