from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import DocChunk, Document


@dataclass(frozen=True)
class ChunkData:
    """Input payload for `insert_chunks_batch` — one row per chunk."""

    text: str
    embedding: list[float]
    page: int | None = None
    heading: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ChunkResult:
    """Output row from `vector_search`."""

    document_id: UUID
    text: str
    page: int | None
    heading: str | None
    metadata: dict[str, Any] | None
    score: float
    """1 - cosine_distance. With L2-normalised embeddings (e.g. bge-m3) the
    score is in [0, 1]; closer to 1 = more relevant."""


async def insert_document(
    session: AsyncSession,
    *,
    filename: str,
    sha256: str | None = None,
    status: str = "pending",
) -> Document:
    doc = Document(filename=filename, sha256=sha256, status=status)
    session.add(doc)
    await session.flush()
    return doc


async def find_by_sha256(session: AsyncSession, sha256: str) -> Document | None:
    """Return the most recent non-failed `Document` with the given sha256, or
    `None`. Used for upload idempotency: a re-upload of the same bytes returns
    the existing in-flight or completed document instead of starting again."""
    stmt = (
        select(Document)
        .where(Document.sha256 == sha256)
        .where(Document.status.in_(("pending", "processing", "ready")))
        .order_by(Document.uploaded_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    doc_id: UUID,
    *,
    status: str,
    page_count: int | None = None,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    doc = await session.get(Document, doc_id)
    if doc is None:
        return
    doc.status = status
    if page_count is not None:
        doc.page_count = page_count
    if chunk_count is not None:
        doc.chunk_count = chunk_count
    if error_message is not None:
        doc.error_message = error_message
    await session.flush()


async def list_documents(session: AsyncSession) -> list[Document]:
    result = await session.execute(select(Document).order_by(Document.uploaded_at.desc()))
    return list(result.scalars().all())


async def delete_document(session: AsyncSession, doc_id: UUID) -> None:
    await session.execute(delete(Document).where(Document.id == doc_id))
    await session.flush()


async def insert_chunks_batch(
    session: AsyncSession,
    doc_id: UUID,
    chunks: Iterable[ChunkData],
) -> int:
    """Bulk-insert chunks via Core `insert(DocChunk)` — ~10× faster than
    `add_all` at the 1000-row scale (`insertmanyvalues` ships them as one
    multi-row INSERT). Note: the dict keys use the SQL column name `metadata`,
    not the ORM attribute `chunk_metadata`."""
    rows = [
        {
            "document_id": doc_id,
            "text": c.text,
            "embedding": c.embedding,
            "page": c.page,
            "heading": c.heading,
            "metadata": c.metadata,
        }
        for c in chunks
    ]
    if not rows:
        return 0
    await session.execute(insert(DocChunk), rows)
    return len(rows)


async def vector_search(
    session: AsyncSession,
    query_vec: list[float],
    *,
    k: int = 5,
    doc_ids: list[UUID] | None = None,
) -> list[ChunkResult]:
    """Cosine-distance search over `doc_chunks.embedding`. Returns top-k rows
    ordered by similarity (highest first)."""
    distance = DocChunk.embedding.cosine_distance(query_vec)
    stmt = select(DocChunk, distance.label("distance")).order_by(distance).limit(k)
    if doc_ids:
        stmt = stmt.where(DocChunk.document_id.in_(doc_ids))

    result = await session.execute(stmt)
    rows = result.all()
    return [
        ChunkResult(
            document_id=chunk.document_id,
            text=chunk.text,
            page=chunk.page,
            heading=chunk.heading,
            metadata=chunk.chunk_metadata,
            score=1.0 - float(distance),
        )
        for chunk, distance in rows
    ]
