"""Align the TKU table with the persisted ORM contract.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-28
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "author_dedup_decisions",
            "decided_at",
            existing_type=sa.DateTime(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=False,
            postgresql_using="decided_at AT TIME ZONE 'UTC'",
        )
        op.drop_constraint(
            "transfer_knowledge_units_paper_id_key",
            "transfer_knowledge_units",
            type_="unique",
        )

    op.execute(
        sa.text(
            "UPDATE transfer_knowledge_units "
            "SET created_at = CURRENT_TIMESTAMP "
            "WHERE created_at IS NULL"
        )
    )
    with op.batch_alter_table("transfer_knowledge_units") as batch:
        batch.drop_index("ix_transfer_knowledge_units_paper_id")
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
        )
        batch.create_index(
            "ix_transfer_knowledge_units_paper_id",
            ["paper_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("transfer_knowledge_units") as batch:
        batch.drop_index("ix_transfer_knowledge_units_paper_id")
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=True,
        )
        batch.create_index(
            "ix_transfer_knowledge_units_paper_id",
            ["paper_id"],
            unique=False,
        )
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint(
            "transfer_knowledge_units_paper_id_key",
            "transfer_knowledge_units",
            ["paper_id"],
        )
        op.alter_column(
            "author_dedup_decisions",
            "decided_at",
            existing_type=sa.DateTime(timezone=True),
            type_=sa.DateTime(),
            existing_nullable=False,
            postgresql_using="decided_at AT TIME ZONE 'UTC'",
        )
