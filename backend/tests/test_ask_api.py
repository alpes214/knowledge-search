import json
from typing import Any
from uuid import UUID

import httpx
import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api import ask as ask_api
from backend.app.config import settings
from backend.app.db import postgres as postgres_module
from backend.app.embeddings import tei_client
from backend.app.main import app
from backend.app.repos.docs import ChunkData, insert_chunks_batch, insert_document
from backend.tests._fakes import (
    FakeOpenAI,
    completion_malformed_tool_call,
    completion_text,
    completion_tool_call,
)

pytestmark = pytest.mark.postgres


def _vec(seed: int) -> list[float]:
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


def _install_fake_openai(monkeypatch, fake: FakeOpenAI) -> None:
    """Replace AsyncOpenAI inside the ask route with our fake."""

    def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(ask_api, 'AsyncOpenAI', _factory)


def _parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.split('\n\n'):
        block = block.strip()
        if not block:
            continue
        event_type = ''
        data_payload = ''
        for line in block.split('\n'):
            if line.startswith('event: '):
                event_type = line[len('event: '):].strip()
            elif line.startswith('data: '):
                data_payload = line[len('data: '):]
        events.append((event_type, json.loads(data_payload) if data_payload else {}))
    return events


async def _post_ask(question: str) -> tuple[int, str]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.post('/ask', json={'question': question})
        body = r.text
    return r.status_code, body


@respx.mock
async def test_ask_happy_path(committing_session: AsyncSession, monkeypatch) -> None:
    doc_id = await _seed_doc_with_chunks(committing_session, 'doc-a.pdf', seeds=[1, 2, 3])
    _mock_tei_returns(query_seed=2)

    final = (
        'The answer is yes [1].\n\n'
        '[1] doc-a.pdf, page 2, "H"'
    )
    fake = FakeOpenAI(responses=[
        completion_tool_call(id='call_1', name='search_docs', arguments={'query': 'q', 'k': 3}),
        completion_text(final),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('what is the answer?')
    assert status == 200
    events = _parse_sse(body)
    types = [t for t, _ in events]
    assert 'tool_use' in types
    assert 'tool_result' in types
    assert 'text' in types
    assert types[-1] == 'done'

    done = next(d for t, d in events if t == 'done')
    assert done['answer'].startswith('The answer is yes [1].')
    assert len(done['citations']) == 1
    citation = done['citations'][0]
    assert citation['n'] == 1
    assert citation['filename'] == 'doc-a.pdf'
    assert citation['page'] == 2
    # chunk_id and document_id must be resolved from tool_result chunks, not zero/empty.
    assert citation['chunk_id'] != 0
    assert citation['document_id'] == str(doc_id)


@respx.mock
async def test_ask_no_corpus_refusal(monkeypatch) -> None:
    _mock_tei_returns(query_seed=99)

    refusal = 'I cannot answer this from the provided documents.'
    fake = FakeOpenAI(responses=[
        completion_tool_call(id='call_1', name='search_docs', arguments={'query': 'q'}),
        completion_text(refusal),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('something not in the docs')
    assert status == 200
    events = _parse_sse(body)
    done = next(d for t, d in events if t == 'done')
    assert done['answer'] == refusal
    assert done['citations'] == []


@respx.mock
async def test_ask_multi_iteration(committing_session: AsyncSession, monkeypatch) -> None:
    await _seed_doc_with_chunks(committing_session, 'doc-a.pdf', seeds=[1])
    _mock_tei_returns(query_seed=1)

    fake = FakeOpenAI(responses=[
        completion_tool_call(id='c1', name='search_docs', arguments={'query': 'first'}),
        completion_tool_call(id='c2', name='search_docs', arguments={'query': 'second'}),
        completion_text('Done [1].\n\n[1] doc-a.pdf, page 1, "H"'),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('compare A and B')
    assert status == 200
    events = _parse_sse(body)
    tool_uses = [d for t, d in events if t == 'tool_use']
    assert len(tool_uses) == 2
    assert events[-1][0] == 'done'


@respx.mock
async def test_ask_iteration_cap(committing_session: AsyncSession, monkeypatch) -> None:
    await _seed_doc_with_chunks(committing_session, 'doc-a.pdf', seeds=[1])
    _mock_tei_returns(query_seed=1)
    monkeypatch.setattr(settings, 'max_agent_iterations', 2)

    fake = FakeOpenAI(responses=[
        completion_tool_call(id='c1', name='search_docs', arguments={'query': 'q'}),
        completion_tool_call(id='c2', name='search_docs', arguments={'query': 'q'}),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('q')
    assert status == 200
    events = _parse_sse(body)
    final_event = events[-1]
    assert final_event[0] == 'error'
    assert final_event[1]['code'] == 'iteration_limit_exceeded'


@respx.mock
async def test_ask_malformed_tool_call(monkeypatch) -> None:
    fake = FakeOpenAI(responses=[
        completion_malformed_tool_call(id='c1', name='search_docs', raw_arguments='{not json'),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('q')
    assert status == 200
    events = _parse_sse(body)
    final_event = events[-1]
    assert final_event[0] == 'error'
    assert final_event[1]['code'] == 'malformed_tool_call'
    assert final_event[1]['retriable'] is False


@respx.mock
async def test_ask_tei_unavailable_during_tool(monkeypatch) -> None:
    respx.post(f'{settings.embed_base_url}/embeddings').mock(
        side_effect=httpx.ConnectError('connection refused')
    )

    fake = FakeOpenAI(responses=[
        completion_tool_call(id='c1', name='search_docs', arguments={'query': 'q'}),
    ])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('q')
    assert status == 200  # SSE stream opened cleanly even though tool failed
    events = _parse_sse(body)
    final_event = events[-1]
    assert final_event[0] == 'error'
    assert final_event[1]['code'] == 'tool_failed'


async def test_ask_llm_unavailable(monkeypatch) -> None:
    fake = FakeOpenAI(responses=[httpx.ConnectError('connection refused')])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('q')
    assert status == 200
    events = _parse_sse(body)
    final_event = events[-1]
    assert final_event[0] == 'error'
    assert final_event[1]['code'] == 'llm_unavailable'


async def test_ask_llm_5xx_maps_to_llm_unavailable(monkeypatch) -> None:
    """Ollama OOM and other 5xx errors should be retriable, not internal."""
    from openai import InternalServerError

    err = InternalServerError(
        message='model requires more system memory',
        response=httpx.Response(500, request=httpx.Request('POST', 'http://x')),
        body=None,
    )
    fake = FakeOpenAI(responses=[err])
    _install_fake_openai(monkeypatch, fake)

    status, body = await _post_ask('q')
    assert status == 200
    events = _parse_sse(body)
    final_event = events[-1]
    assert final_event[0] == 'error'
    assert final_event[1]['code'] == 'llm_unavailable'
    assert final_event[1]['retriable'] is True


async def test_ask_rejects_whitespace_question() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.post('/ask', json={'question': '   '})
    assert r.status_code == 422


async def test_ask_rejects_missing_question() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://test') as client:
        r = await client.post('/ask', json={})
    assert r.status_code == 422
