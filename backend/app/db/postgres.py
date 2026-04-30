import logging
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.config import settings

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_pg_healthy: bool = False


async def init_postgres() -> None:
    """Open the async engine and probe with `SELECT 1`. On failure log a warning
    and leave the app running with `_pg_healthy=False` so unrelated routes work."""
    global _engine, _sessionmaker, _pg_healthy
    _engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        _pg_healthy = True
        log.info("postgres ready url=%s", _redact(settings.database_url))
    except Exception as e:
        _pg_healthy = False
        log.warning("postgres unreachable: %s", e)


async def close_postgres() -> None:
    global _engine, _sessionmaker, _pg_healthy
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _pg_healthy = False


def is_healthy() -> bool:
    return _pg_healthy


def set_healthy(value: bool) -> None:
    """Test hook only; production code uses `init_postgres` to set this."""
    global _pg_healthy
    _pg_healthy = value


async def get_session() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("postgres not initialised")
    async with _sessionmaker() as session:
        yield session


def _redact(url: str) -> str:
    if "@" not in url:
        return url
    scheme_user, host = url.split("@", 1)
    if ":" in scheme_user:
        scheme, _ = scheme_user.split("://", 1)
        return f"{scheme}://...@{host}"
    return url
