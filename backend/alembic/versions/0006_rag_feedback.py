"""Add rag_feedback table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-04
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_feedback",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("failure_type", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("answer_model", sa.String(), nullable=True),
        sa.Column("source_chunk_ids", sa.JSON(), nullable=True),
        sa.Column("source_paper_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rag_feedback_failure_type", "rag_feedback", ["failure_type"])
    op.create_index("ix_rag_feedback_created_at", "rag_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_feedback_created_at", table_name="rag_feedback")
    op.drop_index("ix_rag_feedback_failure_type", table_name="rag_feedback")
    op.drop_table("rag_feedback")
