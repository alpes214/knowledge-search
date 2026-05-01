"""add doc metadata columns

Revision ID: 8e06856bbcdf
Revises: 8a1e5acc057d
Create Date: 2026-05-01 20:04:28.395611

Adds `documents.sha256` (indexed, for upload idempotency) and
`documents.error_message`. Switches the `status` server default from
`'processing'` to `'pending'` to match the queued-task model.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8e06856bbcdf"
down_revision: str | None = "8a1e5acc057d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("sha256", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("error_message", sa.Text, nullable=True))
    op.create_index("ix_documents_sha256", "documents", ["sha256"])
    op.alter_column(
        "documents",
        "status",
        existing_type=sa.String(32),
        existing_nullable=False,
        server_default=sa.text("'pending'"),
    )


def downgrade() -> None:
    op.alter_column(
        "documents",
        "status",
        existing_type=sa.String(32),
        existing_nullable=False,
        server_default=sa.text("'processing'"),
    )
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_column("documents", "error_message")
    op.drop_column("documents", "sha256")
