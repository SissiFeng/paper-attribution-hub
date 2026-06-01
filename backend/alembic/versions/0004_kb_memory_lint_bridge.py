"""Add knowledge-base memory and Scopus evidence columns.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-01
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("papers") as batch:
        batch.add_column(sa.Column("indexed_keywords", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("eid", sa.String(), nullable=True))
        batch.add_column(sa.Column("retrieval_tier", sa.String(), nullable=True))
        batch.add_column(sa.Column("merge_tier_membership", sa.String(), nullable=True))
        batch.add_column(sa.Column("query_string", sa.Text(), nullable=True))
        batch.add_column(sa.Column("funding_text", sa.Text(), nullable=True))
        batch.add_column(sa.Column("funding_sponsors", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ac_known_publication", sa.Boolean(), nullable=False, server_default="false"))
        batch.add_column(sa.Column("ac_acknowledged", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("ac_highly_relevant", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("ac_high_impact", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("ac_members_matched", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ac_programs", sa.String(), nullable=True))
        batch.add_column(sa.Column("sdl_tags", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("research_tags", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("ac_attribution_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("sdl_relevance_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("ai_decision_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("automation_score", sa.Float(), nullable=True))
        batch.add_column(sa.Column("closed_loop_score", sa.Float(), nullable=True))
        batch.create_index("ix_papers_eid", ["eid"], unique=True)
        batch.create_index("ix_papers_retrieval_tier", ["retrieval_tier"])
        batch.create_index("ix_papers_ac_known_publication", ["ac_known_publication"])

    with op.batch_alter_table("paper_classifications") as batch:
        batch.add_column(sa.Column("funding_signal", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("acknowledgement_signal", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("retrieval_signal", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("architecture_signal", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("sdl_relevance_label", sa.String(), nullable=True))
        batch.add_column(sa.Column("ac_attribution_label", sa.String(), nullable=True))
        batch.add_column(sa.Column("model_agreement_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("disagreement_type", sa.String(), nullable=True))
        batch.add_column(sa.Column("evidence_summary", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("future_rule_update", sa.Text(), nullable=True))

    with op.batch_alter_table("human_reviews") as batch:
        batch.add_column(sa.Column("disagreement_type", sa.String(), nullable=True))
        batch.add_column(sa.Column("rationale", sa.Text(), nullable=True))
        batch.add_column(sa.Column("evidence", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("future_rule_update", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("human_reviews") as batch:
        batch.drop_column("future_rule_update")
        batch.drop_column("evidence")
        batch.drop_column("rationale")
        batch.drop_column("disagreement_type")

    with op.batch_alter_table("paper_classifications") as batch:
        batch.drop_column("future_rule_update")
        batch.drop_column("evidence_summary")
        batch.drop_column("disagreement_type")
        batch.drop_column("model_agreement_status")
        batch.drop_column("ac_attribution_label")
        batch.drop_column("sdl_relevance_label")
        batch.drop_column("architecture_signal")
        batch.drop_column("retrieval_signal")
        batch.drop_column("acknowledgement_signal")
        batch.drop_column("funding_signal")

    with op.batch_alter_table("papers") as batch:
        batch.drop_index("ix_papers_ac_known_publication")
        batch.drop_index("ix_papers_retrieval_tier")
        batch.drop_index("ix_papers_eid")
        batch.drop_column("closed_loop_score")
        batch.drop_column("automation_score")
        batch.drop_column("ai_decision_score")
        batch.drop_column("sdl_relevance_score")
        batch.drop_column("ac_attribution_score")
        batch.drop_column("research_tags")
        batch.drop_column("sdl_tags")
        batch.drop_column("ac_programs")
        batch.drop_column("ac_members_matched")
        batch.drop_column("ac_high_impact")
        batch.drop_column("ac_highly_relevant")
        batch.drop_column("ac_acknowledged")
        batch.drop_column("ac_known_publication")
        batch.drop_column("funding_sponsors")
        batch.drop_column("funding_text")
        batch.drop_column("query_string")
        batch.drop_column("merge_tier_membership")
        batch.drop_column("retrieval_tier")
        batch.drop_column("eid")
        batch.drop_column("indexed_keywords")
