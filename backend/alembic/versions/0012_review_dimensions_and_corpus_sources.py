"""Separate review dimensions and persist explicit corpus sources.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-31
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels = None
depends_on = None


def _legacy_corpus_sources(row: sa.RowMapping) -> list[str]:
    provenance = str(row["provenance"] or "").lower()
    source = str(row["source"] or "").lower()
    if row["ac_known_publication"] or provenance == "ac_gold":
        return ["AC_MEMBER_CORPUS"]
    if provenance in {"manual", "manual_upload"} or source == "manual":
        return ["MANUALLY_ADDED"]
    if provenance in {"", "csv"} or source == "csv":
        return ["LEGACY_IMPORT"]
    return ["OTHER"]


def upgrade() -> None:
    op.add_column(
        "papers",
        sa.Column(
            "corpus_sources",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
    )
    bind = op.get_bind()
    papers = sa.table(
        "papers",
        sa.column("id", sa.String()),
        sa.column("source", sa.String()),
        sa.column("provenance", sa.String()),
        sa.column("ac_known_publication", sa.Boolean()),
        sa.column("corpus_sources", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(
            papers.c.id,
            papers.c.source,
            papers.c.provenance,
            papers.c.ac_known_publication,
        )
    ).mappings()
    for row in rows:
        bind.execute(
            papers.update()
            .where(papers.c.id == row["id"])
            .values(corpus_sources=_legacy_corpus_sources(row))
        )

    with op.batch_alter_table("human_reviews") as batch:
        batch.alter_column(
            "human_label",
            existing_type=sa.String(),
            nullable=True,
        )
        batch.add_column(sa.Column("sdl_judgement", sa.String(), nullable=True))
        batch.add_column(
            sa.Column("ac_relevance_judgement", sa.String(), nullable=True)
        )
        batch.add_column(
            sa.Column("ai_for_science_judgement", sa.String(), nullable=True)
        )
        batch.add_column(sa.Column("review_status", sa.String(), nullable=True))
        batch.add_column(sa.Column("evidence_level", sa.String(), nullable=True))
        batch.add_column(sa.Column("judgement_basis", sa.String(), nullable=True))
        batch.create_index(
            "ix_human_reviews_sdl_judgement",
            ["sdl_judgement"],
            unique=False,
        )
        batch.create_index(
            "ix_human_reviews_ac_relevance_judgement",
            ["ac_relevance_judgement"],
            unique=False,
        )
        batch.create_index(
            "ix_human_reviews_review_status",
            ["review_status"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE human_reviews "
            "SET human_label = 'UNCERTAIN' "
            "WHERE human_label IS NULL"
        )
    )
    with op.batch_alter_table("human_reviews") as batch:
        batch.drop_index("ix_human_reviews_review_status")
        batch.drop_index("ix_human_reviews_ac_relevance_judgement")
        batch.drop_index("ix_human_reviews_sdl_judgement")
        batch.drop_column("judgement_basis")
        batch.drop_column("evidence_level")
        batch.drop_column("review_status")
        batch.drop_column("ai_for_science_judgement")
        batch.drop_column("ac_relevance_judgement")
        batch.drop_column("sdl_judgement")
        batch.alter_column(
            "human_label",
            existing_type=sa.String(),
            nullable=False,
        )
    op.drop_column("papers", "corpus_sources")
