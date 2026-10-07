"""Add paper-specific authorship metadata and enrichment runs.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-12
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metadata_enrichment_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_path", sa.Text(), nullable=False),
        sa.Column("input_sha256", sa.String(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_metadata_enrichment_runs_input_sha256",
        "metadata_enrichment_runs",
        ["input_sha256"],
    )
    op.create_index(
        "ix_metadata_enrichment_runs_status",
        "metadata_enrichment_runs",
        ["status"],
    )
    op.create_table(
        "paper_authorship_metadata",
        sa.Column("paper_id", sa.String(), nullable=False),
        sa.Column("author_id", sa.String(), nullable=False),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.Column("author_position", sa.String(), nullable=False),
        sa.Column("is_corresponding", sa.Boolean(), nullable=True),
        sa.Column("openalex_author_id", sa.String(), nullable=True),
        sa.Column("orcid", sa.String(), nullable=True),
        sa.Column("affiliations", sa.JSON(), nullable=False),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("source_record_ids", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("provenance_hash", sa.String(), nullable=False),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["authors.id"]),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("paper_id", "author_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_authorship_metadata")
    op.drop_index(
        "ix_metadata_enrichment_runs_status",
        table_name="metadata_enrichment_runs",
    )
    op.drop_index(
        "ix_metadata_enrichment_runs_input_sha256",
        table_name="metadata_enrichment_runs",
    )
    op.drop_table("metadata_enrichment_runs")
