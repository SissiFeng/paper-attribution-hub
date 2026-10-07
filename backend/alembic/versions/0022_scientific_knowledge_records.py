"""Add classification-neutral scientific knowledge records.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-26
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scientific_knowledge_records",
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("compiler_version", sa.String(length=64), nullable=False),
        sa.Column("source_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("assertions", sa.JSON(), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("paper_id"),
    )
    op.create_index(
        "ix_scientific_knowledge_records_source_snapshot_hash",
        "scientific_knowledge_records",
        ["source_snapshot_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scientific_knowledge_records_source_snapshot_hash",
        table_name="scientific_knowledge_records",
    )
    op.drop_table("scientific_knowledge_records")
