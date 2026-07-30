"""Add evidence-linked catalyst mentions and relations.

Revision ID: 0010_catalyst_entity_graph
Revises: 0009
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_catalyst_entity_graph"
down_revision: Union[str, None] = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_entity_mentions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("concept_id", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("surface_form", sa.String(), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("evidence_chunk_id", sa.String(), nullable=True),
        sa.Column("section", sa.String(), nullable=True),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("specificity", sa.String(), nullable=False),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.Column("extractor_version", sa.String(), nullable=False),
        sa.Column("ontology_version", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_chunk_id"], ["paper_chunks.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_entity_mentions_paper_id",
        "paper_entity_mentions",
        ["paper_id"],
    )
    op.create_index(
        "ix_paper_entity_mentions_concept",
        "paper_entity_mentions",
        ["entity_type", "concept_id"],
    )

    op.create_table(
        "paper_entity_relations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subject_mention_id", sa.String(), nullable=False),
        sa.Column("predicate", sa.String(), nullable=False),
        sa.Column("object_concept_id", sa.String(), nullable=True),
        sa.Column("object_value", sa.Text(), nullable=True),
        sa.Column("object_metadata", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("extractor", sa.String(), nullable=False),
        sa.Column("extractor_version", sa.String(), nullable=False),
        sa.Column("ontology_version", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_mention_id"],
            ["paper_entity_mentions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_entity_relations_subject_mention_id",
        "paper_entity_relations",
        ["subject_mention_id"],
    )
    op.create_index(
        "ix_paper_entity_relations_object",
        "paper_entity_relations",
        ["predicate", "object_concept_id"],
    )

    op.create_table(
        "paper_entity_extraction_states",
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("ontology_version", sa.String(), nullable=False),
        sa.Column("extractor_version", sa.String(), nullable=False),
        sa.Column("config_fingerprint", sa.String(), nullable=False),
        sa.Column("source_fingerprint", sa.String(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("paper_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_entity_extraction_states")
    op.drop_index(
        "ix_paper_entity_relations_object",
        table_name="paper_entity_relations",
    )
    op.drop_index(
        "ix_paper_entity_relations_subject_mention_id",
        table_name="paper_entity_relations",
    )
    op.drop_table("paper_entity_relations")
    op.drop_index(
        "ix_paper_entity_mentions_concept",
        table_name="paper_entity_mentions",
    )
    op.drop_index(
        "ix_paper_entity_mentions_paper_id",
        table_name="paper_entity_mentions",
    )
    op.drop_table("paper_entity_mentions")
