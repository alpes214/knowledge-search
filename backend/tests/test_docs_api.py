"""API contract for /docs upload + GET + DELETE."""
from pathlib import Path

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.db import postgres as postgres_module
from backend.app.docs import pipeline
from backend.app.embeddings import tei_client
from backend.app.main import app
from backend.app.queue.tasks import ingest_document

pytestmark = pytest.mark.postgres

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def _vec(seed: int = 0) -> list[float]:
    raw = [float((i + seed) % 7) for i in range(settings.embed_dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


@pytest.fixture(autouse=True)
async def _wire(postgres_engine, monkeypatch, tmp_path, committing_session):
    """Wire postgres + staging dir, and replace `ingest_document.defer_async`
    with a synchronous call to `pipeline.ingest` so the test sees the full
    state transition without spinning up a Procrastinate worker."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sm = async_sessionmaker(postgres_engine, expire_on_commit=False)
    monkeypatch.setattr(postgres_module, "_engine", postgres_engine)
    monkeypatch.setattr(postgres_module, "_sessionmaker", sm)
    monkeypatch.setattr(settings, "staging_dir", tmp_path)

    async def _run_inline(**kwargs):
        from uuid import UUID
        await pipeline.ingest(UUID(kwargs["doc_id"]))

    monkeypatch.setattr(ingest_document, "defer_async", _run_inline)
    yield
    await tei_client.close()


@respx.mock
async def test_upload_runs_pipeline_to_ready() -> None:
    import json as _json

    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        side_effect=lambda r: httpx.Response(
            200,
            json={
                "data": [
                    {"index": i, "embedding": _vec(i)}
                    for i in range(len(_json.loads(r.content)["input"]))
                ]
            },
        )
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/docs", files={"file": ("sample.pdf", FIXTURE.read_bytes(), "application/pdf")}
        )
        assert r.status_code == 201
        doc_id = r.json()["doc_id"]

        get = await client.get(f"/docs/{doc_id}")
        assert get.status_code == 200
        body = get.json()
        assert body["status"] == "ready"
        assert body["chunk_count"] > 0

        # cleanup
        delete = await client.delete(f"/docs/{doc_id}")
        assert delete.status_code == 204


async def test_upload_rejects_non_pdf() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post(
            "/docs", files={"file": ("notes.txt", b"hello", "text/plain")}
        )
        assert r.status_code == 415


async def test_get_unknown_doc_returns_404() -> None:
    from uuid import uuid4

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get(f"/docs/{uuid4()}")
        assert r.status_code == 404
