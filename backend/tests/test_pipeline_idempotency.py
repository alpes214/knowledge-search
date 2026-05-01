"""Two uploads of the same bytes return the same `doc_id` — no re-ingest."""
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import postgres as postgres_module
from backend.app.db.models import Document
from backend.app.embeddings import tei_client
from backend.app.main import app
from backend.app.queue.tasks import ingest_document

pytestmark = pytest.mark.postgres

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


@pytest.fixture(autouse=True)
async def _wire(postgres_engine, monkeypatch, tmp_path):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sm = async_sessionmaker(postgres_engine, expire_on_commit=False)
    monkeypatch.setattr(postgres_module, "_engine", postgres_engine)
    monkeypatch.setattr(postgres_module, "_sessionmaker", sm)
    monkeypatch.setattr(settings, "staging_dir", tmp_path)
    # Stop Procrastinate from actually deferring jobs during tests.
    monkeypatch.setattr(ingest_document, "defer_async", _noop_defer)
    yield
    await tei_client.close()


async def _noop_defer(**kwargs):
    return None


async def test_upload_same_bytes_twice_is_idempotent(
    committing_session: AsyncSession,
) -> None:
    transport = ASGITransport(app=app)
    body = FIXTURE.read_bytes()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post(
            "/docs",
            files={"file": ("sample.pdf", body, "application/pdf")},
        )
        assert r1.status_code == 201
        first = r1.json()
        assert first["status"] == "pending"

        r2 = await client.post(
            "/docs",
            files={"file": ("sample.pdf", body, "application/pdf")},
        )
        assert r2.status_code == 201
        second = r2.json()
        assert second["doc_id"] == first["doc_id"]

    rows = (
        await committing_session.execute(
            select(Document).where(Document.sha256 != None)  # noqa: E711
        )
    ).scalars().all()
    matching = [d for d in rows if str(d.id) == first["doc_id"]]
    assert len(matching) == 1
