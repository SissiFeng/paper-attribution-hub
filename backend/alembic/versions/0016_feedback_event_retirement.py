"""Retire invalid feedback without consuming eligible batch peers.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_feedback_events",
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "training_feedback_events",
        sa.Column("retirement_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_training_feedback_events_retired_at",
        "training_feedback_events",
        ["retired_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_feedback_events_retired_at",
        table_name="training_feedback_events",
    )
    op.drop_column("training_feedback_events", "retirement_reason")
    op.drop_column("training_feedback_events", "retired_at")
