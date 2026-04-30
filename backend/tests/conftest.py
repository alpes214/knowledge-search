from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def postgres_url(request: pytest.FixtureRequest) -> Iterator[str]:
    """Spin up a one-off Postgres container; opt-in via @pytest.mark.postgres.

    Default `pytest` runs do NOT start Docker; only `pytest -m postgres` will."""
    if "postgres" not in {m.name for m in request.node.iter_markers()}:
        pytest.skip("postgres fixture requires @pytest.mark.postgres")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("pgvector/pgvector:pg17", driver="asyncpg") as pg:
        yield pg.get_connection_url()
