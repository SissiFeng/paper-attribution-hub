"""Derive silver eval labels from the curated AC Publications gold set.

Writes `data/eval_labels_silver.csv` with the same schema as the hand-curated
`data/eval_labels.csv`. The notes
field starts with "silver:" + the rule name. The hand-curated file is never
written to, and paper_ids already present there are skipped.

Rules (conservative — silver labels must be high-precision):
  a. provenance='ac_gold' AND ac_members_matched non-empty AND
     (ac_acknowledged OR ac_highly_relevant)            → CORE_RELEVANT
  b. provenance='ac_gold' AND ac_members_matched non-empty (no ack flags)
                                                        → CORE_RELEVANT
     The AC Publications CSV is the curated AC publication list; its
     "AC Members" column is curator-confirmed member authorship — ingest
     (ingest_scopus_batch) marks those authors is_ac_member=True and the
     classifier injects a 0.95 "ac_publication_confirmed" author match.
     Member-authored curated publications therefore match the hand-label
     semantics of CORE_RELEVANT ("direct AC author").
  c. provenance='ac_gold' AND no members matched        → RELATED_RELEVANT
  d. No silver negatives: an EXCLUDE label asserts irrelevance, but absence
     of curated flags is absence of evidence, not evidence of absence —
     negatives need human judgment.

gold_topics: lowercase-slugged sdl_tags joined with ';' (empty if none).

Usage:
    python -m app.scripts.build_silver_eval_labels [--output PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Paper

RULE_MEMBER_ACK = "ac_gold_member_acknowledged"      # rule a
RULE_MEMBER = "ac_gold_member"                       # rule b
RULE_NO_MEMBER = "ac_gold_no_member"                 # rule c

_LABEL_BY_RULE = {
    RULE_MEMBER_ACK: "CORE_RELEVANT",
    RULE_MEMBER: "CORE_RELEVANT",
    RULE_NO_MEMBER: "RELATED_RELEVANT",
}

_CSV_FIELDS = [
    "paper_id",
    "gold_label",
    "gold_topics",
    "notes",
    "label_scope",
    "annotation_source",
    "evidence_level",
]


def _slug(tag: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", tag.lower()).strip("_")


def _hand_labeled_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(newline="") as f:
        return {str(row["paper_id"]).strip() for row in csv.DictReader(f)}


def derive_silver_rows(
    session: Session, hand_labeled_ids: set[str]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Return (csv rows, per-rule counts incl. skipped_hand_labeled)."""
    rows: list[dict[str, str]] = []
    counts = {RULE_MEMBER_ACK: 0, RULE_MEMBER: 0, RULE_NO_MEMBER: 0,
              "skipped_hand_labeled": 0}
    papers = session.execute(
        select(Paper).where(Paper.provenance == "ac_gold").order_by(Paper.id)
    ).scalars()
    for paper in papers:
        if paper.id in hand_labeled_ids:
            counts["skipped_hand_labeled"] += 1
            continue
        members = [m for m in (paper.ac_members_matched or []) if str(m).strip()]
        if members and (paper.ac_acknowledged or paper.ac_highly_relevant):
            rule = RULE_MEMBER_ACK
        elif members:
            rule = RULE_MEMBER
        else:
            rule = RULE_NO_MEMBER
        counts[rule] += 1
        topics = ";".join(
            slug for slug in (_slug(t) for t in (paper.sdl_tags or [])) if slug
        )
        rows.append(
            {
                "paper_id": paper.id,
                "gold_label": _LABEL_BY_RULE[rule],
                "gold_topics": topics,
                "notes": f"silver:{rule}",
                "label_scope": "AC_REPORTING",
                "annotation_source": "ac_metadata_silver",
                "evidence_level": "METADATA_ONLY",
            }
        )
    return rows, counts


def run(
    output: Path,
    *,
    hand_labels: Path | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    from app.db import SessionLocal, init_database

    hand_labels = hand_labels or settings.eval_labels_csv
    if output.resolve() == hand_labels.resolve():
        raise SystemExit(
            "Refusing to overwrite the hand-curated eval labels file."
        )

    init_database()
    with SessionLocal() as session:
        rows, counts = derive_silver_rows(session, _hand_labeled_ids(hand_labels))

    for rule in (RULE_MEMBER_ACK, RULE_MEMBER, RULE_NO_MEMBER):
        print(f"  {rule} ({_LABEL_BY_RULE[rule]}): {counts[rule]}", file=sys.stderr)
    print(f"  skipped (already hand-labeled): {counts['skipped_hand_labeled']}",
          file=sys.stderr)

    if dry_run:
        print("[dry-run] No file written.", file=sys.stderr)
        return counts

    with output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} silver labels to {output}", file=sys.stderr)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive silver eval labels from curated AC-gold signals."
    )
    parser.add_argument(
        "--output", type=Path, default=settings.eval_labels_silver_csv
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print per-rule counts, don't write."
    )
    args = parser.parse_args()
    run(args.output, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
