import random
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.models import DocChunk, Document
from backend.app.repos.docs import (
    ChunkData,
    delete_document,
    insert_chunks_batch,
    insert_document,
    list_documents,
    update_status,
    vector_search,
)

pytestmark = pytest.mark.postgres


def _vec(seed: int, dim: int = 1024) -> list[float]:
    """Deterministic L2-normalised random vector for a given seed."""
    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in raw) ** 0.5
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_insert_list_and_status(postgres_session: AsyncSession) -> None:
    doc = await insert_document(postgres_session, filename="visa-rules.pdf")
    assert doc.status == "pending"

    docs = await list_documents(postgres_session)
    assert [d.filename for d in docs] == ["visa-rules.pdf"]

    await update_status(postgres_session, doc.id, status="ready", page_count=120, chunk_count=300)
    docs = await list_documents(postgres_session)
    assert docs[0].status == "ready"
    assert docs[0].page_count == 120
    assert docs[0].chunk_count == 300


async def test_vector_search_returns_top1(postgres_session: AsyncSession) -> None:
    doc_a = await insert_document(postgres_session, filename="a.pdf")
    doc_b = await insert_document(postgres_session, filename="b.pdf")

    chunks_a = [
        ChunkData(text=f"a-chunk-{i}", embedding=_vec(seed=i), page=i, heading="A")
        for i in range(5)
    ]
    chunks_b = [
        ChunkData(text=f"b-chunk-{i}", embedding=_vec(seed=100 + i), page=i, heading="B")
        for i in range(5)
    ]
    await insert_chunks_batch(postgres_session, doc_a.id, chunks_a)
    await insert_chunks_batch(postgres_session, doc_b.id, chunks_b)

    # Query exactly equal to chunk seed=2 → that chunk must be the top-1 hit.
    results = await vector_search(postgres_session, query_vec=_vec(seed=2), k=3)
    assert len(results) == 3
    assert results[0].text == "a-chunk-2"
    assert results[0].score > 0.9999     # identical vectors → score ≈ 1.0
    # Subsequent results must have non-increasing scores
    assert results[0].score >= results[1].score >= results[2].score


async def test_vector_search_doc_id_filter(postgres_session: AsyncSession) -> None:
    doc_a = await insert_document(postgres_session, filename="a.pdf")
    doc_b = await insert_document(postgres_session, filename="b.pdf")
    await insert_chunks_batch(
        postgres_session,
        doc_a.id,
        [ChunkData(text="a-only", embedding=_vec(seed=42))],
    )
    await insert_chunks_batch(
        postgres_session,
        doc_b.id,
        [ChunkData(text="b-only", embedding=_vec(seed=42))],
    )

    a_only = await vector_search(postgres_session, _vec(seed=42), k=10, doc_ids=[doc_a.id])
    assert {r.text for r in a_only} == {"a-only"}

    b_only = await vector_search(postgres_session, _vec(seed=42), k=10, doc_ids=[doc_b.id])
    assert {r.text for r in b_only} == {"b-only"}


async def test_delete_cascades(postgres_session: AsyncSession) -> None:
    doc = await insert_document(postgres_session, filename="c.pdf")
    await insert_chunks_batch(
        postgres_session,
        doc.id,
        [ChunkData(text=f"c-{i}", embedding=_vec(seed=200 + i)) for i in range(3)],
    )

    before = (
        await postgres_session.execute(select(DocChunk).where(DocChunk.document_id == doc.id))
    ).scalars().all()
    assert len(before) == 3

    await delete_document(postgres_session, doc.id)

    after = (
        await postgres_session.execute(select(DocChunk).where(DocChunk.document_id == doc.id))
    ).scalars().all()
    assert after == []

    doc_after = (
        await postgres_session.execute(select(Document).where(Document.id == doc.id))
    ).scalars().all()
    assert doc_after == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_update_status_nonexistent_doc_is_noop(postgres_session: AsyncSession) -> None:
    """`update_status` on an unknown id silently returns without raising."""
    await update_status(postgres_session, uuid4(), status="ready")


async def test_insert_chunks_batch_empty(postgres_session: AsyncSession) -> None:
    doc = await insert_document(postgres_session, filename="empty.pdf")
    inserted = await insert_chunks_batch(postgres_session, doc.id, [])
    assert inserted == 0
    rows = (
        await postgres_session.execute(select(DocChunk).where(DocChunk.document_id == doc.id))
    ).scalars().all()
    assert rows == []


async def test_vector_search_doc_id_filter_no_match(postgres_session: AsyncSession) -> None:
    """Filtering by a document id with zero chunks yields an empty result."""
    doc = await insert_document(postgres_session, filename="empty-doc.pdf")
    await insert_chunks_batch(
        postgres_session,
        doc.id,
        [ChunkData(text="x", embedding=_vec(seed=1))],
    )
    other_id = uuid4()        # never persisted

    results = await vector_search(postgres_session, _vec(seed=1), k=10, doc_ids=[other_id])
    assert results == []


async def test_vector_search_empty_table(postgres_session: AsyncSession) -> None:
    """Search over a table with no chunks returns an empty list."""
    results = await vector_search(postgres_session, _vec(seed=999), k=5)
    assert results == []
