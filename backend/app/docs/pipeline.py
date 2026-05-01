"""Ingest pipeline: load → split → embed → bulk insert.

Owns its own AsyncSession (the request session is closed by the time a
Procrastinate task fires). Re-raises on failure so Procrastinate can retry;
the user-visible `documents.status` is set to `failed` only on every attempt
(it persists if Procrastinate exhausts retries)."""
from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from backend.app.config import settings
from backend.app.db.postgres import session_factory
from backend.app.docs.loader import pdf_to_markdown
from backend.app.docs.splitter import split
from backend.app.embeddings import tei_client
from backend.app.repos.docs import insert_chunks_batch, update_status

log = logging.getLogger(__name__)


async def ingest(doc_id: UUID) -> None:
    """Read `staging_dir/<doc_id>.pdf`, run the full pipeline, persist results.

    On success: status `processing → ready`; `page_count` and `chunk_count` set.
    On failure: status set to `failed` with `error_message`; the exception is
    re-raised so Procrastinate can retry.
    """
    staging_path = settings.staging_dir / f"{doc_id}.pdf"
    sm = session_factory()

    # Mark processing.
    async with sm() as session, session.begin():
        await update_status(session, doc_id, status="processing")

    try:
        if not staging_path.exists():
            raise FileNotFoundError(f"missing staged file for doc {doc_id}")

        file_bytes = staging_path.read_bytes()
        markdown, page_ranges = pdf_to_markdown(file_bytes)
        chunks = split(markdown, page_ranges)
        if not chunks:
            raise ValueError("split produced zero chunks")

        embeddings = await tei_client.embed([c.text for c in chunks])
        if len(embeddings) != len(chunks):
            raise RuntimeError(
                f"embed returned {len(embeddings)} vectors for {len(chunks)} chunks"
            )

        embedded = [replace(c, embedding=v) for c, v in zip(chunks, embeddings, strict=True)]

        async with sm() as session, session.begin():
            await insert_chunks_batch(session, doc_id, embedded)
            await update_status(
                session,
                doc_id,
                status="ready",
                page_count=len(page_ranges),
                chunk_count=len(embedded),
            )
        log.info("ingest done doc=%s pages=%d chunks=%d", doc_id, len(page_ranges), len(embedded))
    except Exception as e:
        log.exception("ingest failed doc=%s", doc_id)
        async with sm() as session, session.begin():
            await update_status(
                session,
                doc_id,
                status="failed",
                error_message=str(e)[:1000],
            )
        raise
