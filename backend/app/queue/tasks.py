"""Procrastinate tasks. One task: `ingest_document`. Configured with
exponential-backoff retry — on final failure the user-visible status stays
`failed` (set inside `pipeline.ingest`)."""
from __future__ import annotations

from uuid import UUID

from procrastinate import RetryStrategy

from backend.app.docs.pipeline import ingest
from backend.app.queue.app import app


@app.task(
    name="ingest_document",
    queue="ingest",
    retry=RetryStrategy(max_attempts=3, exponential_wait=30),
)
async def ingest_document(doc_id: str) -> None:
    await ingest(UUID(doc_id))
