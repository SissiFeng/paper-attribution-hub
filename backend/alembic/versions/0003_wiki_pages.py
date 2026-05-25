"""Add wiki_pages table for knowledge digest layer.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-25
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_pages",
        sa.Column("id",             sa.String(),  primary_key=True),
        sa.Column("entity_type",    sa.String(),  nullable=False),
        sa.Column("entity_id",      sa.String(),  nullable=False, index=True),
        sa.Column("title",          sa.Text(),    nullable=False),
        sa.Column("sections",       sa.JSON(),    nullable=False, server_default="[]"),
        sa.Column("content_md",     sa.Text(),    nullable=True),
        sa.Column("model_version",  sa.String(),  nullable=False, server_default="template-v0.1"),
        sa.Column("prompt_version", sa.String(),  nullable=False, server_default="v0.1"),
        sa.Column("generated_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_stale",       sa.Boolean(), nullable=False, server_default="false"),
        sa.UniqueConstraint("entity_type", "entity_id", name="uq_wiki_entity"),
    )


def downgrade() -> None:
    op.drop_table("wiki_pages")
