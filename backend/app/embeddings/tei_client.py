"""HTTP client for the TEI (Text Embeddings Inference) embeddings endpoint.

Speaks the OpenAI-compatible `POST /v1/embeddings` shape. Batches inputs
in groups of `_BATCH_SIZE` per request. Raises on any HTTP error so that
Procrastinate's task-level retry can re-run the whole ingest task on
transient failures."""
from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.app.config import settings

log = logging.getLogger(__name__)

_BATCH_SIZE = 32

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        # TEI ignores Authorization; sent for future-compat with auth-gated endpoints.
        _client = httpx.AsyncClient(
            base_url=settings.embed_base_url,
            timeout=httpx.Timeout(30.0, connect=5.0),
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        )
    return _client


async def close() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _embed_batch(batch: list[str]) -> list[list[float]]:
    payload: dict[str, Any] = {"model": settings.embed_model, "input": batch}
    response = await _get_client().post("/embeddings", json=payload)
    response.raise_for_status()
    body = response.json()

    data = body.get("data") or []
    if len(data) != len(batch):
        raise ValueError(
            f"TEI returned {len(data)} embeddings for {len(batch)} inputs"
        )
    vectors = [item["embedding"] for item in data]
    for v in vectors:
        if len(v) != settings.embed_dim:
            raise ValueError(
                f"TEI returned vector of dim {len(v)}, expected {settings.embed_dim}"
            )
    return vectors


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed an arbitrary number of texts. Returns one vector per input,
    in the same order. Splits into batches of `_BATCH_SIZE` internally."""
    if not texts:
        return []
    out: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        vectors = await _embed_batch(batch)
        out.extend(vectors)
    return out
