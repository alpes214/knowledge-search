from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import settings
from backend.app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def postgres_engine() -> AsyncIterator[AsyncEngine]:
    """Engine pointed at the dev `ks-postgres` (already running, migration
    applied). Function-scoped so each test gets its own connection pool tied
    to its own event loop — avoids cross-loop asyncpg errors. Skips the
    marked tests if the DB is unreachable."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except OperationalError as e:
        await engine.dispose()
        pytest.skip(f"postgres not reachable at {settings.database_url}: {e}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def postgres_session(postgres_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test transactional session. Always rolls back at teardown so tests
    leave no rows behind, regardless of order."""
    sessionmaker = async_sessionmaker(postgres_engine, expire_on_commit=False)
    async with postgres_engine.connect() as conn:
        outer = await conn.begin()
        async with sessionmaker(bind=conn) as session:
            try:
                yield session
            finally:
                await outer.rollback()


@pytest_asyncio.fixture
async def committing_session(postgres_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Non-transactional session for tests that exercise code which opens its
    own sessions (e.g., the ingest pipeline running outside the request scope).
    Tracks all `Document` rows created during the test and deletes them at
    teardown so the database stays clean."""
    from sqlalchemy import delete as _delete
    from sqlalchemy import select as _select

    from backend.app.db.models import Document

    sessionmaker = async_sessionmaker(postgres_engine, expire_on_commit=False)
    before_ids: set[Any] = set()
    async with sessionmaker() as snapshot:
        rows = await snapshot.execute(_select(Document.id))
        before_ids = {r[0] for r in rows.all()}

    session = sessionmaker()
    try:
        yield session
    finally:
        await session.close()
        async with sessionmaker() as cleanup:
            rows = await cleanup.execute(_select(Document.id))
            new_ids = {r[0] for r in rows.all()} - before_ids
            if new_ids:
                await cleanup.execute(_delete(Document).where(Document.id.in_(new_ids)))
                await cleanup.commit()
