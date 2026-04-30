import pytest
from httpx import AsyncClient

from backend.app.db import postgres


@pytest.mark.asyncio
async def test_health_reports_postgres_ok_when_flag_set(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres, "_pg_healthy", True)
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "postgres": "ok"}


@pytest.mark.asyncio
async def test_health_reports_postgres_down_when_flag_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres, "_pg_healthy", False)
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "postgres": "down"}


@pytest.mark.asyncio
async def test_docs_health_endpoint(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(postgres, "_pg_healthy", True)
    r = await client.get("/docs/health")
    assert r.status_code == 200
    assert r.json() == {"postgres": "ok"}


@pytest.mark.asyncio
async def test_unimplemented_endpoints_return_501(client: AsyncClient) -> None:
    assert (await client.post("/docs")).status_code == 501
    assert (await client.get("/search?q=x")).status_code == 501
    assert (await client.post("/ask", json={})).status_code == 501
