"""Add review assignment and citation snapshot fields.

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-02
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "paper_classifications",
        sa.Column("review_assignee", sa.String(), nullable=True),
    )
    op.add_column(
        "paper_classifications",
        sa.Column("review_assigned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "paper_classifications",
        sa.Column("review_assigned_by", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_paper_classifications_review_assignee",
        "paper_classifications",
        ["review_assignee"],
    )
    op.add_column(
        "papers",
        sa.Column("citation_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column("citation_count_source", sa.String(), nullable=True),
    )
    op.add_column(
        "papers",
        sa.Column(
            "citation_count_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("papers", "citation_count_updated_at")
    op.drop_column("papers", "citation_count_source")
    op.drop_column("papers", "citation_count")
    op.drop_index(
        "ix_paper_classifications_review_assignee",
        table_name="paper_classifications",
    )
    op.drop_column("paper_classifications", "review_assigned_by")
    op.drop_column("paper_classifications", "review_assigned_at")
    op.drop_column("paper_classifications", "review_assignee")
