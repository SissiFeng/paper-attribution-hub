"""Add author_dedup_decisions table for human-reviewed merge/separate decisions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-03
"""
from __future__ import annotations
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "author_dedup_decisions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("author_id_a", sa.String(), nullable=False, index=True),
        sa.Column("author_id_b", sa.String(), nullable=False, index=True),
        sa.Column("decision", sa.String(), nullable=False),  # "merge" | "separate"
        sa.Column("decided_at", sa.DateTime(), nullable=False),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("author_id_a", "author_id_b", name="uq_dedup_pair"),
    )


def downgrade() -> None:
    op.drop_table("author_dedup_decisions")
