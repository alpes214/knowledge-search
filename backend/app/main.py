import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.api import ask, docs, search
from backend.app.config import settings
from backend.app.db.postgres import close_postgres, init_postgres
from backend.app.db.postgres import status as pg_status
from backend.app.logging_conf import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    await init_postgres()
    log.info("knowledge-search started")
    try:
        yield
    finally:
        await close_postgres()
        log.info("knowledge-search stopped")


app = FastAPI(title="Knowledge Search", lifespan=lifespan)
app.include_router(docs.router)
app.include_router(search.router)
app.include_router(ask.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "postgres": pg_status()}
