"""Add auditable human-feedback model evolution state.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-31
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_training_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trigger_review_count", sa.Integer(), nullable=False),
        sa.Column(
            "trigger_event_ids",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "trigger_paper_ids",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("backend", sa.String(), nullable=False),
        sa.Column(
            "training_example_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "validation_example_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("training_dataset_hash", sa.String(), nullable=True),
        sa.Column("validation_dataset_hash", sa.String(), nullable=True),
        sa.Column("label_boundary_hashes", sa.JSON(), nullable=True),
        sa.Column("evaluation_scope", sa.String(), nullable=True),
        sa.Column("candidate_metrics", sa.JSON(), nullable=True),
        sa.Column("incumbent_metrics", sa.JSON(), nullable=True),
        sa.Column("validation_candidate_metrics", sa.JSON(), nullable=True),
        sa.Column("validation_incumbent_metrics", sa.JSON(), nullable=True),
        sa.Column("candidate_model_path", sa.Text(), nullable=True),
        sa.Column("production_model_path", sa.Text(), nullable=True),
        sa.Column("candidate_model_sha256", sa.String(), nullable=True),
        sa.Column("model_artifact", sa.LargeBinary(), nullable=True),
        sa.Column("incumbent_model_sha256", sa.String(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=True),
        sa.Column("promotion_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_model_training_runs_status",
        "model_training_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_model_training_runs_started_at",
        "model_training_runs",
        ["started_at"],
        unique=False,
    )

    op.create_table(
        "model_training_state",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "batch_size",
            sa.Integer(),
            server_default="20",
            nullable=False,
        ),
        sa.Column("active_run_id", sa.String(), nullable=True),
        sa.Column("production_run_id", sa.String(), nullable=True),
        sa.Column("current_model_version", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "model_training_state",
            sa.column("id", sa.String()),
            sa.column("batch_size", sa.Integer()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": "learned_classifier",
                "batch_size": 20,
                "updated_at": datetime.now(UTC),
            }
        ],
    )

    op.create_table(
        "training_feedback_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("review_id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("human_label", sa.String(), nullable=False),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column("incumbent_label", sa.String(), nullable=True),
        sa.Column("incumbent_confidence", sa.Float(), nullable=True),
        sa.Column("consumed_by_run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["consumed_by_run_id"],
            ["model_training_runs.id"],
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["human_reviews.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_training_feedback_events_review_id",
        "training_feedback_events",
        ["review_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_feedback_events_paper_id",
        "training_feedback_events",
        ["paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_feedback_events_consumed_by_run_id",
        "training_feedback_events",
        ["consumed_by_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_feedback_events_created_at",
        "training_feedback_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_feedback_events_created_at",
        table_name="training_feedback_events",
    )
    op.drop_index(
        "ix_training_feedback_events_consumed_by_run_id",
        table_name="training_feedback_events",
    )
    op.drop_index(
        "ix_training_feedback_events_paper_id",
        table_name="training_feedback_events",
    )
    op.drop_index(
        "ix_training_feedback_events_review_id",
        table_name="training_feedback_events",
    )
    op.drop_table("training_feedback_events")
    op.drop_table("model_training_state")
    op.drop_index(
        "ix_model_training_runs_started_at",
        table_name="model_training_runs",
    )
    op.drop_index(
        "ix_model_training_runs_status",
        table_name="model_training_runs",
    )
    op.drop_table("model_training_runs")
