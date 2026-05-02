import logging
from dataclasses import replace
from pathlib import Path
from uuid import UUID

from backend.app.config import settings
from backend.app.db.postgres import session_factory
from backend.app.docs.loader import pdf_to_markdown
from backend.app.docs.splitter import split
from backend.app.embeddings import tei_client
from backend.app.repos.docs import ChunkData, insert_chunks_batch, update_status

log = logging.getLogger(__name__)

_ERROR_MESSAGE_MAX_LEN = 1000


async def ingest(doc_id: UUID) -> None:
    staging_path = settings.staging_dir / f'{doc_id}.pdf'

    await _set_status(doc_id, status='processing')
    try:
        chunks, page_count = _load_and_split(staging_path, doc_id)
        embedded = await _embed(chunks)
        await _persist_ready(doc_id, embedded, page_count)
        log.info('ingest done doc=%s pages=%d chunks=%d', doc_id, page_count, len(embedded))
    except Exception as e:
        log.exception('ingest failed doc=%s', doc_id)
        try:
            await _set_status(
                doc_id, status='failed', error_message=str(e)[:_ERROR_MESSAGE_MAX_LEN]
            )
        except Exception:
            log.exception('also failed to mark doc as failed doc=%s', doc_id)
        raise


def _load_and_split(staging_path: Path, doc_id: UUID) -> tuple[list[ChunkData], int]:
    if not staging_path.exists():
        raise FileNotFoundError(f'missing staged file for doc {doc_id}')
    markdown, page_ranges = pdf_to_markdown(staging_path.read_bytes())
    chunks = split(markdown, page_ranges)
    if not chunks:
        raise ValueError('split produced zero chunks')
    return chunks, len(page_ranges)


async def _embed(chunks: list[ChunkData]) -> list[ChunkData]:
    vectors = await tei_client.embed([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise RuntimeError(f'embed returned {len(vectors)} vectors for {len(chunks)} chunks')
    return [replace(chunk, embedding=v) for chunk, v in zip(chunks, vectors, strict=True)]


async def _persist_ready(doc_id: UUID, embedded: list[ChunkData], page_count: int) -> None:
    Session = session_factory()
    async with Session() as session, session.begin():
        await insert_chunks_batch(session, doc_id, embedded)
        await update_status(
            session, doc_id, status='ready', page_count=page_count, chunk_count=len(embedded)
        )


async def _set_status(
    doc_id: UUID, *, status: str, error_message: str | None = None
) -> None:
    Session = session_factory()
    async with Session() as session, session.begin():
        await update_status(session, doc_id, status=status, error_message=error_message)
