from httpx import AsyncClient

from backend.app.db import postgres


async def test_health_reports_postgres_ok(
    client: AsyncClient,
) -> None:
    postgres.set_status("ok")
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "postgres": "ok"}


async def test_health_reports_postgres_down(
    client: AsyncClient,
) -> None:
    postgres.set_status("down")
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "postgres": "down"}


async def test_health_reports_schema_missing(
    client: AsyncClient,
) -> None:
    postgres.set_status("schema_missing")
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "postgres": "schema_missing"}


async def test_docs_health_endpoint(
    client: AsyncClient,
) -> None:
    postgres.set_status("ok")
    r = await client.get("/docs/health")
    assert r.status_code == 200
    assert r.json() == {"postgres": "ok"}


async def test_unimplemented_endpoints_return_501(client: AsyncClient) -> None:
    # POST /docs is implemented in Phase 3.
    assert (await client.get("/search?q=x")).status_code == 501
    assert (await client.post("/ask", json={})).status_code == 501
