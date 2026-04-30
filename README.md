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
