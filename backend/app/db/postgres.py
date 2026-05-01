import logging
from collections.abc import AsyncIterator
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
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

PgStatus = Literal["ok", "schema_missing", "down"]
_pg_status: PgStatus = "down"


async def init_postgres() -> None:
    """Open the async engine, probe connectivity, and check that the schema is
    present (`doc_chunks` exists). On failure, log and leave the app running
    so unrelated routes still work — `/health` reports the status."""
    global _engine, _sessionmaker, _pg_status
    _engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    try:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            try:
                await conn.execute(text("SELECT 1 FROM doc_chunks LIMIT 0"))
                _pg_status = "ok"
                log.info("postgres ready url=%s", _redact(settings.database_url))
            except ProgrammingError:
                _pg_status = "schema_missing"
                log.warning(
                    "postgres reachable but schema missing — run `alembic upgrade head`"
                )
    except Exception as e:
        _pg_status = "down"
        log.warning("postgres unreachable: %s", e)


async def close_postgres() -> None:
    global _engine, _sessionmaker, _pg_status
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
    _pg_status = "down"


def status() -> PgStatus:
    return _pg_status


def is_healthy() -> bool:
    return _pg_status == "ok"


def set_status(value: PgStatus) -> None:
    """Test hook only; production code uses `init_postgres` to set this."""
    global _pg_status
    _pg_status = value


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
