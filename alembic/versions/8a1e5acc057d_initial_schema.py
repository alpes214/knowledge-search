"""initial schema

Revision ID: 8a1e5acc057d
Revises:
Create Date: 2026-05-01 10:33:19.731760

"""
from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from alembic import op

revision: str = "8a1e5acc057d"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Embedding dimension pinned at the schema level. Must match `EMBED_DIM` in
# `backend/app/db/models.py`. Changing this requires a new migration that
# re-embeds all chunks against the new dimension.
EMBED_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # for gen_random_uuid()

    op.create_table(
        "documents",
        sa.Column(
            "id",
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default=sa.text("'processing'"),
        ),
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=True),
    )

    op.create_table(
        "doc_chunks",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("heading", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.Vector(EMBED_DIM),
            nullable=False,
        ),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_doc_chunks_document_id", "doc_chunks", ["document_id"])

    # HNSW index for cosine-distance vector search. Default parameters
    # (m=16, ef_construction=64) are fine for v0; production tuning typically
    # bumps to m=32, ef_construction=200 for higher recall.
    op.execute(
        "CREATE INDEX ix_doc_chunks_embedding_hnsw "
        "ON doc_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_doc_chunks_embedding_hnsw")
    op.drop_index("ix_doc_chunks_document_id", table_name="doc_chunks")
    op.drop_table("doc_chunks")
    op.drop_table("documents")
    # Extensions stay — other databases on the cluster might use them.
