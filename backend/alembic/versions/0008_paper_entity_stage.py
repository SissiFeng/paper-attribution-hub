"""Add stage + usage_snippet columns to paper_entities.

For method entities the extractor now records the pipeline stage
(data/method_stages.yaml id) and the sentence the method was matched in.

Existing SQLite databases created via init_database()/create_all have no
alembic_version table. To upgrade such a DB:

    cd backend
    PAS_DATABASE_URL="sqlite:////path/to/db" alembic stamp 0007
    PAS_DATABASE_URL="sqlite:////path/to/db" alembic upgrade head

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-11
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_entities", sa.Column("stage", sa.String(), nullable=True))
    op.add_column(
        "paper_entities", sa.Column("usage_snippet", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("paper_entities", "usage_snippet")
    op.drop_column("paper_entities", "stage")
