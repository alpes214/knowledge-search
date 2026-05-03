from uuid import UUID

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.db import postgres as postgres_module
from backend.app.embeddings import tei_client
from backend.app.main import app
from backend.app.repos.docs import ChunkData, insert_chunks_batch, insert_document

pytestmark = pytest.mark.postgres


def _vec(seed: int) -> list[float]:
    """Deterministic L2-normalised vector for a given seed (mirrors test_repo_search)."""
    import random

    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(settings.embed_dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


@pytest.fixture(autouse=True)
async def _wire(postgres_engine, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    sm = async_sessionmaker(postgres_engine, expire_on_commit=False)
    monkeypatch.setattr(postgres_module, '_engine', postgres_engine)
    monkeypatch.setattr(postgres_module, '_sessionmaker', sm)
    yield
    await tei_client.close()


def _mock_tei_returns(query_seed: int) -> None:
    """Mock TEI to return a single fixed-seed vector for any embed call."""
    respx.post(f'{settings.embed_base_url}/embeddings').mock(
        side_effect=lambda r: httpx.Response(
            200, json={'data': [{'index': 0, 'embedding': _vec(query_seed)}]}
        )
    )


async def _seed_doc_with_chunks(
    session: AsyncSession, filename: str, seeds: list[int]
) -> UUID:
    doc = await insert_document(session, filename=filename, sha256=f'sha-{filename}')
    chunks = [
        ChunkData(text=f'{filename}-chunk-{s}', embedding=_vec(s), page=s, heading='H')
        for s in seeds
    ]
    await insert_chunks_batch(session, doc.id, chunks)
    await session.commit()
    return doc.id


@respx.mock
async def test_search_returns_top_match(committing_session: AsyncSession) -> None:
    doc_id = await _seed_doc_with_chunks(
        committing_session, 'doc-a.pdf', seeds=[1, 2, 3, 4, 5]
    )
    _mock_tei_returns(query_seed=2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'anything', 'k': 3})

    assert r.status_code == 200
    body = r.json()
    assert body['query'] == 'anything'
    # Random-gauss vectors in 1024-D are nearly orthogonal -- only the exact
    # match (seed=2) passes the default min_score; assert the top match is
    # correct and let the threshold drop the others.
    assert body['results'], 'expected at least one result above min_score'
    top = body['results'][0]
    assert top['filename'] == 'doc-a.pdf'
    assert top['text'] == 'doc-a.pdf-chunk-2'
    assert top['score'] > 0.9999
    assert UUID(top['document_id']) == doc_id
    scores = [r['score'] for r in body['results']]
    assert scores == sorted(scores, reverse=True)


@respx.mock
async def test_search_doc_id_filter(committing_session: AsyncSession) -> None:
    doc_a = await _seed_doc_with_chunks(committing_session, 'a.pdf', seeds=[42])
    await _seed_doc_with_chunks(committing_session, 'b.pdf', seeds=[42])
    _mock_tei_returns(query_seed=42)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x', 'doc_id': str(doc_a)})

    assert r.status_code == 200
    body = r.json()
    assert body['results']
    assert {result['filename'] for result in body['results']} == {'a.pdf'}


@respx.mock
async def test_search_min_score_drops_everything(
    committing_session: AsyncSession, monkeypatch
) -> None:
    await _seed_doc_with_chunks(committing_session, 'doc.pdf', seeds=[1, 2, 3])
    _mock_tei_returns(query_seed=999)  # unrelated direction
    monkeypatch.setattr(settings, 'search_min_score', 0.99)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x'})

    assert r.status_code == 200
    assert r.json()['results'] == []


@respx.mock
async def test_search_empty_corpus_returns_empty_results() -> None:
    _mock_tei_returns(query_seed=0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'anything'})

    assert r.status_code == 200
    assert r.json()['results'] == []


async def test_search_rejects_whitespace_only_q() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': '   '})
    assert r.status_code == 422


async def test_search_rejects_missing_q() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search')
    assert r.status_code == 422


async def test_search_rejects_k_out_of_range() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x', 'k': 0})
        assert r.status_code == 422
        r = await client.get('/search', params={'q': 'x', 'k': 101})
        assert r.status_code == 422


async def test_search_rejects_malformed_doc_id() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x', 'doc_id': 'not-a-uuid'})
    assert r.status_code == 422


@respx.mock
async def test_search_returns_503_when_tei_unavailable() -> None:
    respx.post(f'{settings.embed_base_url}/embeddings').mock(
        side_effect=httpx.ConnectError('connection refused')
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x'})

    assert r.status_code == 503
    assert 'embedding service unavailable' in r.json()['detail']


@respx.mock
async def test_search_returns_503_when_tei_times_out(
    committing_session: AsyncSession, monkeypatch
) -> None:
    """Anchor: a timeout from TEI should also be mapped to 503, not 500."""
    respx.post(f'{settings.embed_base_url}/embeddings').mock(
        side_effect=httpx.TimeoutException('read timeout')
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.get('/search', params={'q': 'x'})

    assert r.status_code == 503
