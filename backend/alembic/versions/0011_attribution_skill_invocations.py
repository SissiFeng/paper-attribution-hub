"""Persist replayable attribution Skill invocations.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attribution_skill_invocations",
        sa.Column("invocation_id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("skill_name", sa.String(), nullable=False),
        sa.Column("skill_version", sa.String(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_snapshot_id", sa.String(), nullable=False),
        sa.Column("input_content_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("invocation_json", sa.JSON(), nullable=False),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("final_confidence", sa.Float(), nullable=True),
        sa.Column("failure_category", sa.String(), nullable=True),
        sa.Column(
            "retrieval_api_calls",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "fulltext_retrieval_status",
            sa.String(),
            server_default="not_requested",
            nullable=False,
        ),
        sa.Column(
            "extraction_seconds",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "model_calls",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "input_tokens",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "output_tokens",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "estimated_cost_usd",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "graph_queries",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "human_review_seconds",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "retries",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "resolution_path",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("invocation_id"),
    )
    op.create_index(
        "ix_attribution_skill_invocations_paper_id",
        "attribution_skill_invocations",
        ["paper_id"],
    )
    op.create_index(
        "ix_attribution_skill_invocations_skill_name",
        "attribution_skill_invocations",
        ["skill_name"],
    )
    op.create_index(
        "ix_attribution_skill_invocations_status",
        "attribution_skill_invocations",
        ["status"],
    )
    op.create_index(
        "ix_attribution_skill_invocations_decision",
        "attribution_skill_invocations",
        ["decision"],
    )
    op.create_index(
        "ix_attribution_skill_invocations_failure_category",
        "attribution_skill_invocations",
        ["failure_category"],
    )
    op.create_index(
        "ix_attribution_skill_invocations_created_at",
        "attribution_skill_invocations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attribution_skill_invocations_created_at",
        table_name="attribution_skill_invocations",
    )
    op.drop_index(
        "ix_attribution_skill_invocations_failure_category",
        table_name="attribution_skill_invocations",
    )
    op.drop_index(
        "ix_attribution_skill_invocations_decision",
        table_name="attribution_skill_invocations",
    )
    op.drop_index(
        "ix_attribution_skill_invocations_status",
        table_name="attribution_skill_invocations",
    )
    op.drop_index(
        "ix_attribution_skill_invocations_skill_name",
        table_name="attribution_skill_invocations",
    )
    op.drop_index(
        "ix_attribution_skill_invocations_paper_id",
        table_name="attribution_skill_invocations",
    )
    op.drop_table("attribution_skill_invocations")
