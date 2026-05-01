from typing import Any

import httpx
import pytest
import respx

from backend.app.config import settings
from backend.app.embeddings import tei_client


def _vec(seed: int = 0) -> list[float]:
    # Returns an L2-normalised constant vector of the right dimension.
    raw = [float((i + seed) % 7) for i in range(settings.embed_dim)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def _embeddings_response(n: int) -> dict[str, Any]:
    return {
        "object": "list",
        "model": settings.embed_model,
        "data": [{"object": "embedding", "index": i, "embedding": _vec(i)} for i in range(n)],
    }


@pytest.fixture(autouse=True)
async def _close_client():
    yield
    await tei_client.close()


@respx.mock
async def test_embed_batches_inputs_in_groups_of_32() -> None:
    captured_lengths: list[int] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        body = request.content
        import json as _json

        payload = _json.loads(body)
        captured_lengths.append(len(payload["input"]))
        return httpx.Response(200, json=_embeddings_response(len(payload["input"])))

    respx.post(f"{settings.embed_base_url}/embeddings").mock(side_effect=_handler)

    vectors = await tei_client.embed([f"text-{i}" for i in range(64)])
    assert len(vectors) == 64
    assert captured_lengths == [32, 32]


@respx.mock
async def test_embed_raises_on_4xx() -> None:
    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        return_value=httpx.Response(400, json={"error": "bad input"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await tei_client.embed(["x"])


@respx.mock
async def test_embed_raises_on_5xx() -> None:
    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        return_value=httpx.Response(503, json={"error": "service unavailable"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await tei_client.embed(["x"])


@respx.mock
async def test_embed_validates_returned_dimension() -> None:
    bad = {
        "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}],   # too short
    }
    respx.post(f"{settings.embed_base_url}/embeddings").mock(
        return_value=httpx.Response(200, json=bad)
    )
    with pytest.raises(ValueError, match="dim"):
        await tei_client.embed(["x"])


async def test_embed_empty_input_returns_empty() -> None:
    assert await tei_client.embed([]) == []
