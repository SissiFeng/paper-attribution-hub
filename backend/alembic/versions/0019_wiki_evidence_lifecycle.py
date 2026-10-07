"""Add deterministic provenance and lifecycle fields to wiki pages.

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wiki_pages",
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_wiki_pages_source_snapshot_hash",
        "wiki_pages",
        ["source_snapshot_hash"],
    )
    op.add_column(
        "wiki_pages",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "wiki_pages",
        sa.Column(
            "source_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "wiki_pages",
        sa.Column(
            "compile_status",
            sa.String(),
            nullable=False,
            server_default="complete",
        ),
    )
    op.create_index(
        "ix_wiki_pages_compile_status",
        "wiki_pages",
        ["compile_status"],
    )
    op.add_column(
        "wiki_pages",
        sa.Column("compile_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wiki_pages", "compile_error")
    op.drop_index("ix_wiki_pages_compile_status", table_name="wiki_pages")
    op.drop_column("wiki_pages", "compile_status")
    op.drop_column("wiki_pages", "source_metadata")
    op.drop_column("wiki_pages", "content_hash")
    op.drop_index("ix_wiki_pages_source_snapshot_hash", table_name="wiki_pages")
    op.drop_column("wiki_pages", "source_snapshot_hash")
