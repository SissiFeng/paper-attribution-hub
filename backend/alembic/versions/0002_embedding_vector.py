"""Migrate paper_chunks.embedding from JSON to pgvector(1536).

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:00:01.000000

This migration is a no-op on SQLite (pgvector is PostgreSQL-only).
On PostgreSQL it enables the vector extension and alters the column type.

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        ALTER TABLE paper_chunks
        ALTER COLUMN embedding
        TYPE vector(1536)
        USING CASE
            WHEN embedding IS NULL THEN NULL
            ELSE CAST(embedding::text AS vector(1536))
        END
    """)


def downgrade() -> None:
    if not _is_postgres():
        return

    op.execute("""
        ALTER TABLE paper_chunks
        ALTER COLUMN embedding
        TYPE json
        USING embedding::text::json
    """)
