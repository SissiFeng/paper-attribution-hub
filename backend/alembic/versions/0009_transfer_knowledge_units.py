"""Add transfer_knowledge_units table (TKU extraction layer).

Each paper is compressed into a structured, domain-separable unit so methods
and lessons can be transferred across self-driving labs.

Existing SQLite databases created via init_database()/create_all have no
alembic_version table. To upgrade such a DB:

    cd backend
    PAS_DATABASE_URL="sqlite:////path/to/db" alembic stamp 0008
    PAS_DATABASE_URL="sqlite:////path/to/db" alembic upgrade head

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transfer_knowledge_units",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("source_domain", sa.String(), nullable=False),
        sa.Column("problem_signature", sa.JSON(), nullable=False),
        sa.Column("method_core", sa.JSON(), nullable=False),
        sa.Column("assumptions", sa.JSON(), nullable=False),
        sa.Column("lessons", sa.JSON(), nullable=False),
        sa.Column("domain_bindings", sa.JSON(), nullable=False),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id"),
    )
    op.create_index(
        "ix_transfer_knowledge_units_paper_id",
        "transfer_knowledge_units",
        ["paper_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transfer_knowledge_units_paper_id",
        table_name="transfer_knowledge_units",
    )
    op.drop_table("transfer_knowledge_units")
