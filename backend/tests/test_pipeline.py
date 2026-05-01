"""End-to-end pipeline test: real Postgres, mocked TEI, real fixture PDF."""
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import postgres as postgres_module
from backend.app.db.models import DocChunk
from backend.app.docs import pipeline
from backend.app.embeddings import tei_client
from backend.app.repos.docs import insert_document

pytestmark = pytest.mark.postgres

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def _vec(seed: int = 0) -> list[float]:
    raw = [float((i + seed) % 7) for i in range(settings.embed_dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def _embeddings_response(n: int) -> dict[str, list[dict[str, Any]]]:
    return {"data": [{"index": i, "embedding": _vec(i)} for i in range(n)]}


@pytest.fixture(autouse=True)
async def _wire_postgres(postgres_engine, monkeypatch):
    """Point the global `postgres` module at the same engine the test fixture
    uses so `pipeline.ingest`'s `session_factory()` resolves correctly."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sm = async_sessionmaker(postgres_engine, expire_on_commit=False)
    monkeypatch.setattr(postgres_module, "_engine", postgres_engine)
    monkeypatch.setattr(postgres_module, "_sessionmaker", sm)
    yield
    await tei_client.close()


@pytest.fixture
def staging_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "staging_dir", tmp_path)
    return tmp_path


@respx.mock
async def test_pipeline_ingests_pdf_end_to_end(
    committing_session: AsyncSession, staging_dir: Path
) -> None:
    import json as _json

    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        side_effect=lambda r: httpx.Response(
            200, json=_embeddings_response(len(_json.loads(r.content)["input"]))
        )
    )

    doc = await insert_document(
        committing_session, filename="sample.pdf", sha256="abc123", status="pending"
    )
    await committing_session.commit()

    (staging_dir / f"{doc.id}.pdf").write_bytes(FIXTURE.read_bytes())

    await pipeline.ingest(doc.id)

    await committing_session.refresh(doc)
    assert doc.status == "ready"
    assert doc.chunk_count is not None and doc.chunk_count > 0
    assert doc.page_count == 2
    assert doc.error_message is None

    chunks = (
        await committing_session.execute(
            select(DocChunk).where(DocChunk.document_id == doc.id)
        )
    ).scalars().all()
    assert len(chunks) == doc.chunk_count
    assert all(len(c.embedding) == settings.embed_dim for c in chunks)
    assert {c.page for c in chunks if c.page} <= {1, 2}


@respx.mock
async def test_pipeline_failure_persists_error(
    committing_session: AsyncSession, staging_dir: Path
) -> None:
    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    doc = await insert_document(
        committing_session, filename="sample.pdf", sha256="def456", status="pending"
    )
    await committing_session.commit()

    (staging_dir / f"{doc.id}.pdf").write_bytes(FIXTURE.read_bytes())

    with pytest.raises(httpx.HTTPStatusError):
        await pipeline.ingest(doc.id)

    await committing_session.refresh(doc)
    assert doc.status == "failed"
    assert doc.error_message
    chunks = (
        await committing_session.execute(
            select(DocChunk).where(DocChunk.document_id == doc.id)
        )
    ).scalars().all()
    assert chunks == []


async def test_pipeline_missing_staging_file(
    committing_session: AsyncSession, staging_dir: Path
) -> None:
    doc = await insert_document(
        committing_session, filename="missing.pdf", sha256="ghi789", status="pending"
    )
    await committing_session.commit()

    # No file written to staging_dir.
    with pytest.raises(FileNotFoundError):
        await pipeline.ingest(doc.id)

    await committing_session.refresh(doc)
    assert doc.status == "failed"
    assert "missing" in (doc.error_message or "").lower()
