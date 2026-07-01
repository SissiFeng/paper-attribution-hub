"""Add sdl_labs, paper_lab_links, paper_entities tables.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-10
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sdl_labs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("institution", sa.String(), nullable=False),
        sa.Column("pi_names", sa.JSON(), nullable=False),
        sa.Column("domain_focus", sa.String(), nullable=False),
        sa.Column("platform_stack", sa.JSON(), nullable=True),
        sa.Column("automation_level", sa.String(), nullable=True),
        sa.Column("member_author_names", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "paper_lab_links",
        sa.Column(
            "paper_id", sa.String(), sa.ForeignKey("papers.id"), primary_key=True
        ),
        sa.Column(
            "lab_id", sa.String(), sa.ForeignKey("sdl_labs.id"), primary_key=True
        ),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
    )
    op.create_table(
        "paper_entities",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("paper_id", sa.String(), sa.ForeignKey("papers.id"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column(
            "evidence_chunk_id",
            sa.String(),
            sa.ForeignKey("paper_chunks.id"),
            nullable=True,
        ),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "paper_id", "entity_type", "normalized_name", name="uq_paper_entity"
        ),
    )
    op.create_index("ix_paper_entities_paper_id", "paper_entities", ["paper_id"])
    op.create_index(
        "ix_paper_entities_type_norm",
        "paper_entities",
        ["entity_type", "normalized_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_entities_type_norm", table_name="paper_entities")
    op.drop_index("ix_paper_entities_paper_id", table_name="paper_entities")
    op.drop_table("paper_entities")
    op.drop_table("paper_lab_links")
    op.drop_table("sdl_labs")
