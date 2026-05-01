"""Procrastinate App singleton. Imported by `tasks.py` and the worker CLI:

    uv run procrastinate --app=backend.app.queue.app:app worker
"""
from __future__ import annotations

from procrastinate import App, PsycopgConnector

from backend.app.config import settings


def _psycopg_conninfo(database_url: str) -> str:
    """Procrastinate's PsycopgConnector takes a libpq-style conninfo string,
    not the SQLAlchemy URL we use elsewhere. Strip the `+asyncpg` driver
    suffix and convert `postgresql://` → libpq."""
    url = database_url
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url[len("postgresql+asyncpg://") :]
    return url


app = App(
    connector=PsycopgConnector(conninfo=_psycopg_conninfo(settings.database_url)),
    import_paths=["backend.app.queue.tasks"],
)
