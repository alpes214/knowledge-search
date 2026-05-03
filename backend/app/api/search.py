import logging
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db.postgres import get_session
from backend.app.embeddings import tei_client
from backend.app.embeddings.tei_client import TeiUnavailable
from backend.app.repos.docs import ChunkResult, vector_search

log = logging.getLogger(__name__)

router = APIRouter(tags=['search'])


class SearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: int
    document_id: UUID
    filename: str
    page: int | None
    heading: str | None
    text: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]


# TODO(phase-5): extract embed + vector_search + min_score filter into a shared
# search service function so /ask can apply the same quality threshold.
@router.get('/search', response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=2000)],
    k: Annotated[int, Query(ge=1, le=100)] = settings.docs_top_k,
    doc_id: Annotated[list[UUID] | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    start = time.monotonic()
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail='q must not be whitespace')

    try:
        [query_vec] = await tei_client.embed([query])
    except TeiUnavailable as e:
        raise HTTPException(
            status_code=503, detail=f'embedding service unavailable: {e}'
        ) from e

    raw = await vector_search(session, query_vec, k=k, doc_ids=doc_id)
    kept, dropped_count, top_dropped = _apply_threshold(raw, settings.search_min_score)

    doc_filter = [str(d) for d in (doc_id or [])]
    latency_ms = int((time.monotonic() - start) * 1000)
    log.info(
        'search q=%r k=%d filter=%s returned=%d dropped=%d top_dropped=%.3f latency_ms=%d',
        query, k, doc_filter, len(kept), dropped_count, top_dropped, latency_ms,
    )

    return SearchResponse(
        query=query,
        results=[SearchResult.model_validate(r) for r in kept],
    )


def _apply_threshold(
    results: list[ChunkResult], threshold: float
) -> tuple[list[ChunkResult], int, float]:
    kept = [r for r in results if r.score >= threshold]
    dropped = [r for r in results if r.score < threshold]
    top_dropped = max((r.score for r in dropped), default=0.0)
    return kept, len(dropped), top_dropped
