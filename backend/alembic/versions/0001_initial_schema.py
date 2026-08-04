"""Create the schema that shipped in the initial repository revision.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000

Keep this migration frozen. Importing the live ORM metadata here caused fresh
databases to create tables owned by later migrations before those migrations
ran. The definitions below were generated from repository commit ``4fda9bf``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ac_core_papers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", sa.JSON(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column("why_core", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ac_core_papers_doi", "ac_core_papers", ["doi"], unique=True)

    op.create_table(
        "external_cache",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("request_key", sa.String(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_external_cache_request_key",
        "external_cache",
        ["request_key"],
        unique=False,
    )
    op.create_index(
        "ix_external_cache_source", "external_cache", ["source"], unique=False
    )

    op.create_table(
        "institutions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("canonical_name", sa.String(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("normalized_aliases", sa.JSON(), nullable=True),
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("city", sa.String(), nullable=True),
        sa.Column("is_partner", sa.Boolean(), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_institutions_canonical_name",
        "institutions",
        ["canonical_name"],
        unique=True,
    )
    op.create_index(
        "ix_institutions_is_partner",
        "institutions",
        ["is_partner"],
        unique=False,
    )

    op.create_table(
        "papers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("full_text_available", sa.Boolean(), nullable=False),
        sa.Column("pdf_path", sa.String(), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doi"),
    )
    op.create_index("ix_papers_provenance", "papers", ["provenance"], unique=False)

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("discovered_candidates", sa.Integer(), nullable=False),
        sa.Column("auto_ingested", sa.Integer(), nullable=False),
        sa.Column("queued_for_review", sa.Integer(), nullable=False),
        sa.Column("classified_new", sa.Integer(), nullable=False),
        sa.Column("reclassified_stale", sa.Integer(), nullable=False),
        sa.Column("enqueued_for_review", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pipeline_runs_started_at",
        "pipeline_runs",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_runs_status", "pipeline_runs", ["status"], unique=False
    )

    op.create_table(
        "topics",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", sa.JSON(), nullable=True),
        sa.Column("negative_keywords", sa.JSON(), nullable=True),
        sa.Column("is_core", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "authors",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("canonical_name", sa.String(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("orcid", sa.String(), nullable=True),
        sa.Column("institution_id", sa.String(), nullable=True),
        sa.Column("department", sa.String(), nullable=True),
        sa.Column("lab", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("is_ac_member", sa.Boolean(), nullable=False),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("orcid"),
    )
    op.create_index(
        "ix_authors_canonical_name", "authors", ["canonical_name"], unique=False
    )
    op.create_index(
        "ix_authors_is_ac_member", "authors", ["is_ac_member"], unique=False
    )
    op.create_index(
        "ix_authors_normalized_name", "authors", ["normalized_name"], unique=False
    )

    op.create_table(
        "discovery_candidates",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("doi", sa.String(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(), nullable=True),
        sa.Column("authors", sa.JSON(), nullable=True),
        sa.Column("affiliations", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("triggers", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("auto_eligible", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("resulting_paper_id", sa.String(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["resulting_paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_discovery_candidates_auto_eligible",
        "discovery_candidates",
        ["auto_eligible"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_candidates_doi",
        "discovery_candidates",
        ["doi"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_candidates_external_id",
        "discovery_candidates",
        ["external_id"],
        unique=True,
    )
    op.create_index(
        "ix_discovery_candidates_source",
        "discovery_candidates",
        ["source"],
        unique=False,
    )
    op.create_index(
        "ix_discovery_candidates_status",
        "discovery_candidates",
        ["status"],
        unique=False,
    )

    op.create_table(
        "human_reviews",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("human_label", sa.String(), nullable=False),
        sa.Column("corrected_topics", sa.JSON(), nullable=True),
        sa.Column("corrected_people", sa.JSON(), nullable=True),
        sa.Column("reviewer", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_reviews_paper_id",
        "human_reviews",
        ["paper_id"],
        unique=True,
    )

    op.create_table(
        "paper_classifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("author_score", sa.Float(), nullable=False),
        sa.Column("institution_score", sa.Float(), nullable=False),
        sa.Column("topic_score", sa.Float(), nullable=False),
        sa.Column("network_score", sa.Float(), nullable=False),
        sa.Column("fulltext_evidence_score", sa.Float(), nullable=False),
        sa.Column("citation_score", sa.Float(), nullable=False),
        sa.Column("graph_signals", sa.JSON(), nullable=True),
        sa.Column("matched_people", sa.JSON(), nullable=True),
        sa.Column("matched_institutions", sa.JSON(), nullable=True),
        sa.Column("matched_topics", sa.JSON(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("review_priority", sa.Float(), nullable=False),
        sa.Column("human_confirmed", sa.Boolean(), nullable=False),
        sa.Column("human_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_confirmed_by", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_classifications_human_confirmed",
        "paper_classifications",
        ["human_confirmed"],
        unique=False,
    )
    op.create_index(
        "ix_paper_classifications_label",
        "paper_classifications",
        ["label"],
        unique=False,
    )
    op.create_index(
        "ix_paper_classifications_needs_review",
        "paper_classifications",
        ["needs_review"],
        unique=False,
    )
    op.create_index(
        "ix_paper_classifications_paper_id",
        "paper_classifications",
        ["paper_id"],
        unique=True,
    )

    op.create_table(
        "paper_references",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("citing_paper_id", sa.String(), nullable=False),
        sa.Column("cited_paper_id", sa.String(), nullable=True),
        sa.Column("cited_ac_core_id", sa.String(), nullable=True),
        sa.Column("cited_doi", sa.String(), nullable=True),
        sa.Column("cited_title", sa.Text(), nullable=True),
        sa.Column("cited_authors", sa.JSON(), nullable=True),
        sa.Column("cited_year", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["cited_ac_core_id"], ["ac_core_papers.id"]),
        sa.ForeignKeyConstraint(["cited_paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["citing_paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_references_cited_ac_core_id",
        "paper_references",
        ["cited_ac_core_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_references_cited_doi",
        "paper_references",
        ["cited_doi"],
        unique=False,
    )
    op.create_index(
        "ix_paper_references_cited_paper_id",
        "paper_references",
        ["cited_paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_references_citing_paper_id",
        "paper_references",
        ["citing_paper_id"],
        unique=False,
    )

    op.create_table(
        "paper_sections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("section_type", sa.String(), nullable=False),
        sa.Column("section_title", sa.String(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_sections_paper_id",
        "paper_sections",
        ["paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_sections_section_type",
        "paper_sections",
        ["section_type"],
        unique=False,
    )

    op.create_table(
        "paper_authors",
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.Column("affiliation_text", sa.Text(), nullable=True),
        sa.Column("match_confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("paper_id", "author_id"),
    )

    op.create_table(
        "paper_chunks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("section_id", sa.String(), nullable=True),
        sa.Column("section_type", sa.String(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("indexed_text", sa.Text(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("embedding_backend", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["section_id"], ["paper_sections.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_chunks_paper_id", "paper_chunks", ["paper_id"], unique=False
    )
    op.create_index(
        "ix_paper_chunks_section_type",
        "paper_chunks",
        ["section_type"],
        unique=False,
    )

    op.create_table(
        "paper_evidence",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=True),
        sa.Column("evidence_type", sa.String(), nullable=False),
        sa.Column("evidence_source", sa.String(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["paper_chunks.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_evidence_evidence_source",
        "paper_evidence",
        ["evidence_source"],
        unique=False,
    )
    op.create_index(
        "ix_paper_evidence_evidence_type",
        "paper_evidence",
        ["evidence_type"],
        unique=False,
    )
    op.create_index(
        "ix_paper_evidence_paper_id",
        "paper_evidence",
        ["paper_id"],
        unique=False,
    )

    op.create_table(
        "paper_propositions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("predicate", sa.String(), nullable=False),
        sa.Column("object_value", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(), nullable=True),
        sa.Column("source_section", sa.String(), nullable=True),
        sa.Column("source_evidence_id", sa.String(), nullable=True),
        sa.Column("source_chunk_id", sa.String(), nullable=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.ForeignKeyConstraint(["source_chunk_id"], ["paper_chunks.id"]),
        sa.ForeignKeyConstraint(["source_evidence_id"], ["paper_evidence.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_propositions_object_key",
        "paper_propositions",
        ["object_key"],
        unique=False,
    )
    op.create_index(
        "ix_paper_propositions_paper_id",
        "paper_propositions",
        ["paper_id"],
        unique=False,
    )
    op.create_index(
        "ix_paper_propositions_predicate",
        "paper_propositions",
        ["predicate"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_paper_propositions_predicate", table_name="paper_propositions")
    op.drop_index("ix_paper_propositions_paper_id", table_name="paper_propositions")
    op.drop_index("ix_paper_propositions_object_key", table_name="paper_propositions")
    op.drop_table("paper_propositions")

    op.drop_index("ix_paper_evidence_paper_id", table_name="paper_evidence")
    op.drop_index("ix_paper_evidence_evidence_type", table_name="paper_evidence")
    op.drop_index("ix_paper_evidence_evidence_source", table_name="paper_evidence")
    op.drop_table("paper_evidence")

    op.drop_index("ix_paper_chunks_section_type", table_name="paper_chunks")
    op.drop_index("ix_paper_chunks_paper_id", table_name="paper_chunks")
    op.drop_table("paper_chunks")
    op.drop_table("paper_authors")

    op.drop_index("ix_paper_sections_section_type", table_name="paper_sections")
    op.drop_index("ix_paper_sections_paper_id", table_name="paper_sections")
    op.drop_table("paper_sections")

    op.drop_index("ix_paper_references_citing_paper_id", table_name="paper_references")
    op.drop_index("ix_paper_references_cited_paper_id", table_name="paper_references")
    op.drop_index("ix_paper_references_cited_doi", table_name="paper_references")
    op.drop_index("ix_paper_references_cited_ac_core_id", table_name="paper_references")
    op.drop_table("paper_references")

    op.drop_index(
        "ix_paper_classifications_paper_id", table_name="paper_classifications"
    )
    op.drop_index(
        "ix_paper_classifications_needs_review",
        table_name="paper_classifications",
    )
    op.drop_index("ix_paper_classifications_label", table_name="paper_classifications")
    op.drop_index(
        "ix_paper_classifications_human_confirmed",
        table_name="paper_classifications",
    )
    op.drop_table("paper_classifications")

    op.drop_index("ix_human_reviews_paper_id", table_name="human_reviews")
    op.drop_table("human_reviews")

    op.drop_index("ix_discovery_candidates_status", table_name="discovery_candidates")
    op.drop_index("ix_discovery_candidates_source", table_name="discovery_candidates")
    op.drop_index(
        "ix_discovery_candidates_external_id", table_name="discovery_candidates"
    )
    op.drop_index("ix_discovery_candidates_doi", table_name="discovery_candidates")
    op.drop_index(
        "ix_discovery_candidates_auto_eligible",
        table_name="discovery_candidates",
    )
    op.drop_table("discovery_candidates")

    op.drop_index("ix_authors_normalized_name", table_name="authors")
    op.drop_index("ix_authors_is_ac_member", table_name="authors")
    op.drop_index("ix_authors_canonical_name", table_name="authors")
    op.drop_table("authors")
    op.drop_table("topics")

    op.drop_index("ix_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_papers_provenance", table_name="papers")
    op.drop_table("papers")

    op.drop_index("ix_institutions_is_partner", table_name="institutions")
    op.drop_index("ix_institutions_canonical_name", table_name="institutions")
    op.drop_table("institutions")

    op.drop_index("ix_external_cache_source", table_name="external_cache")
    op.drop_index("ix_external_cache_request_key", table_name="external_cache")
    op.drop_table("external_cache")

    op.drop_index("ix_ac_core_papers_doi", table_name="ac_core_papers")
    op.drop_table("ac_core_papers")
