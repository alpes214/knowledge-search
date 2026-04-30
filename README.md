# Knowledge Search

Document Q&A: upload PDFs, embed into Postgres+pgvector, search and ask grounded questions with cited excerpts.

Backend: FastAPI + SQLAlchemy + pgvector. Frontend: Next.js. Embeddings: bge-m3 via TEI on a separate host. LLM: Ollama on a separate host.

## Quickstart

```bash
cp .env.example .env                    # adjust hosts if needed
docker compose up -d postgres
uv sync
uv run alembic upgrade head             # once Phase 2 lands
uv run uvicorn backend.app.main:app --reload
# → http://localhost:8000/docs (Swagger), /health
```

Frontend:

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

## Licence

Released under **GNU AGPL v3.0** — see `LICENSE`.

A **commercial licence** is available for closed-source integrations, hosted SaaS without source disclosure, or organisations whose policy disallows AGPL components. See `COMMERCIAL.md`.
