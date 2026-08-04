"""Persist staged screening routes for classified papers.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-31
"""

from __future__ import annotations

import math
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels = None
depends_on = None


def _legacy_route(
    *,
    label: str,
    confidence: float,
    human_confirmed: bool,
    human_label: str | None,
    review_status: str | None,
) -> tuple[str, str, str]:
    if review_status == "NEEDS_FULLTEXT":
        return (
            "HUMAN_REVIEW",
            "FULLTEXT_REVIEW",
            "Migrated review requires full text or supporting information.",
        )
    if human_confirmed or review_status == "COMPLETED" or human_label:
        return (
            "HUMAN_RESOLVED",
            "RESOLVED",
            "Migrated human judgement is complete.",
        )
    normalized_label = str(label or "").strip().upper()
    if normalized_label == "INCLUDE":
        normalized_label = "RELATED_RELEVANT"
    if normalized_label in {
        "CORE_RELEVANT",
        "RELATED_RELEVANT",
        "SDL_FIELD_RELEVANT",
    }:
        return (
            "HUMAN_REVIEW",
            "POSITIVE_REVIEW",
            f"Migrated positive prediction ({normalized_label}).",
        )
    if (
        not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
        or normalized_label == "UNCERTAIN"
        or normalized_label
        not in {
            "ADJACENT",
            "EXCLUDE",
        }
        or confidence < 0.75
    ):
        return (
            "HUMAN_REVIEW",
            "UNCERTAIN_REVIEW",
            f"Migrated uncertain prediction ({normalized_label}, confidence "
            f"{confidence:.2f}).",
        )
    return (
        "BROAD_SCORED",
        "SCREENED_OUT",
        f"Migrated high-confidence non-positive prediction "
        f"({normalized_label}, confidence {confidence:.2f}).",
    )


def upgrade() -> None:
    with op.batch_alter_table("paper_classifications") as batch:
        batch.add_column(
            sa.Column("screening_stage", sa.String(), nullable=True)
        )
        batch.add_column(
            sa.Column("screening_route", sa.String(), nullable=True)
        )
        batch.add_column(
            sa.Column("screening_reason", sa.Text(), nullable=True)
        )
        batch.create_index(
            "ix_paper_classifications_screening_stage",
            ["screening_stage"],
            unique=False,
        )
        batch.create_index(
            "ix_paper_classifications_screening_route",
            ["screening_route"],
            unique=False,
        )

    bind = op.get_bind()
    classifications = sa.table(
        "paper_classifications",
        sa.column("id", sa.String()),
        sa.column("paper_id", sa.String()),
        sa.column("label", sa.String()),
        sa.column("confidence", sa.Float()),
        sa.column("human_confirmed", sa.Boolean()),
        sa.column("screening_stage", sa.String()),
        sa.column("screening_route", sa.String()),
        sa.column("screening_reason", sa.Text()),
    )
    reviews = sa.table(
        "human_reviews",
        sa.column("paper_id", sa.String()),
        sa.column("human_label", sa.String()),
        sa.column("review_status", sa.String()),
    )
    reviews_by_paper = {
        row["paper_id"]: row
        for row in bind.execute(
            sa.select(
                reviews.c.paper_id,
                reviews.c.human_label,
                reviews.c.review_status,
            )
        ).mappings()
    }
    rows = bind.execute(
        sa.select(
            classifications.c.id,
            classifications.c.paper_id,
            classifications.c.label,
            classifications.c.confidence,
            classifications.c.human_confirmed,
        )
    ).mappings()
    for row in rows:
        review = reviews_by_paper.get(row["paper_id"], {})
        stage, route, reason = _legacy_route(
            label=row["label"],
            confidence=float(row["confidence"]),
            human_confirmed=bool(row["human_confirmed"]),
            human_label=review.get("human_label"),
            review_status=review.get("review_status"),
        )
        bind.execute(
            classifications.update()
            .where(classifications.c.id == row["id"])
            .values(
                screening_stage=stage,
                screening_route=route,
                screening_reason=reason,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("paper_classifications") as batch:
        batch.drop_index("ix_paper_classifications_screening_route")
        batch.drop_index("ix_paper_classifications_screening_stage")
        batch.drop_column("screening_reason")
        batch.drop_column("screening_route")
        batch.drop_column("screening_stage")
