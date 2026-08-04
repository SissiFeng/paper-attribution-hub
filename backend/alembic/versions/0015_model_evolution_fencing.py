"""Fence training leases and persist promotion decision provenance.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-01
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_training_runs",
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "model_training_runs",
        sa.Column("promotion_gate_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "model_training_runs",
        sa.Column("runtime_versions", sa.JSON(), nullable=True),
    )
    op.add_column(
        "model_training_runs",
        sa.Column("cache_sync_status", sa.String(), nullable=True),
    )
    op.add_column(
        "model_training_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_model_training_runs_heartbeat_at",
        "model_training_runs",
        ["heartbeat_at"],
        unique=False,
    )
    op.add_column(
        "model_training_state",
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("model_training_state", "lease_generation")
    op.drop_index(
        "ix_model_training_runs_heartbeat_at",
        table_name="model_training_runs",
    )
    op.drop_column("model_training_runs", "heartbeat_at")
    op.drop_column("model_training_runs", "cache_sync_status")
    op.drop_column("model_training_runs", "runtime_versions")
    op.drop_column("model_training_runs", "promotion_gate_config")
    op.drop_column("model_training_runs", "lease_generation")
