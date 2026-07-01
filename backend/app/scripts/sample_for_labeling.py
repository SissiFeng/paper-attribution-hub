"""Stratified sampling of classified papers for human labeling.

Strata are predicted label x confidence band (low <0.5, mid 0.5-0.75,
high >0.75). UNCERTAIN and mid-confidence strata are oversampled because
they are the most informative for tuning classification thresholds.
Papers already in data/eval_labels.csv are excluded (matched by paper id,
then DOI, then normalized title).

Usage:
    python -m app.scripts.sample_for_labeling [--n 200] [--seed 42] [--output data/labeling_queue.csv]
"""
from __future__ import annotations

import argparse
import csv
import random
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, settings
from app.db import SessionLocal, init_database
from app.models import Paper
from app.services.normalization_service import normalize_doi

QUEUE_FIELDS = [
    "paper_id",
    "doi",
    "title",
    "year",
    "predicted_label",
    "confidence",
    "top_reasons",
    "human_label",
    "notes",
]

# Oversampling weights: a stratum's share of the queue is proportional to
# (stratum size x label weight x band weight), capped at the stratum size.
LABEL_WEIGHTS = {"UNCERTAIN": 3.0}
BAND_WEIGHTS = {"low": 1.0, "mid": 2.0, "high": 1.0}


def confidence_band(confidence: float) -> str:
    if confidence < 0.5:
        return "low"
    if confidence <= 0.75:
        return "mid"
    return "high"


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def load_exclusions(session: Session, eval_labels_path: Path) -> tuple[set, set, set]:
    """Paper ids, normalized DOIs and titles already in the gold set."""
    paper_ids: set[str] = set()
    if eval_labels_path.exists():
        with open(eval_labels_path, newline="") as fh:
            for row in csv.DictReader(fh):
                pid = (row.get("paper_id") or "").strip()
                if pid:
                    paper_ids.add(pid)
    dois: set[str] = set()
    titles: set[str] = set()
    for pid in paper_ids:
        paper = session.get(Paper, pid)
        if paper is None:
            continue
        if paper.doi:
            dois.add(normalize_doi(paper.doi))
        titles.add(normalize_title(paper.title))
    return paper_ids, dois, titles


def _allocate(sizes: dict[tuple[str, str], int], n: int) -> dict[tuple[str, str], int]:
    """Weighted proportional allocation capped at each stratum's size."""
    weighted = {
        key: size * LABEL_WEIGHTS.get(key[0], 1.0) * BAND_WEIGHTS[key[1]]
        for key, size in sizes.items()
    }
    quotas = {key: 0 for key in sizes}
    remaining = n
    while remaining > 0:
        open_keys = [k for k in sorted(sizes) if quotas[k] < sizes[k]]
        if not open_keys:
            break
        total_weight = sum(weighted[k] for k in open_keys)
        granted = 0
        for key in open_keys:
            share = int(remaining * weighted[key] / total_weight)
            take = min(share, sizes[key] - quotas[key])
            quotas[key] += take
            granted += take
        if granted == 0:
            # All fractional shares rounded to zero: hand out one-by-one,
            # heaviest stratum first.
            for key in sorted(open_keys, key=lambda k: (-weighted[k], k)):
                if granted == remaining:
                    break
                quotas[key] += 1
                granted += 1
        remaining -= granted
    return quotas


def sample_queue(
    session: Session, *, n: int, seed: int, eval_labels_path: Path
) -> tuple[list[dict], dict[tuple[str, str], tuple[int, int]]]:
    """Return (queue rows, {stratum: (available, sampled)})."""
    excluded_ids, excluded_dois, excluded_titles = load_exclusions(session, eval_labels_path)
    candidates = [
        p
        for p in session.execute(select(Paper)).scalars()
        if p.classification is not None
        and p.id not in excluded_ids
        and (normalize_doi(p.doi) not in excluded_dois if p.doi else True)
        and normalize_title(p.title) not in excluded_titles
    ]

    strata: dict[tuple[str, str], list[Paper]] = {}
    for paper in candidates:
        c = paper.classification
        strata.setdefault((c.label, confidence_band(c.confidence)), []).append(paper)
    for members in strata.values():
        members.sort(key=lambda p: p.id)

    quotas = _allocate({k: len(v) for k, v in strata.items()}, n)
    rng = random.Random(seed)
    rows: list[dict] = []
    breakdown: dict[tuple[str, str], tuple[int, int]] = {}
    for key in sorted(strata):
        members = strata[key]
        quota = quotas[key]
        picked = rng.sample(members, quota) if quota < len(members) else members
        breakdown[key] = (len(members), len(picked))
        for paper in picked:
            c = paper.classification
            rows.append(
                {
                    "paper_id": paper.id,
                    "doi": paper.doi or "",
                    "title": paper.title,
                    "year": paper.year if paper.year is not None else "",
                    "predicted_label": c.label,
                    "confidence": f"{c.confidence:.3f}",
                    "top_reasons": "; ".join((c.reasons or [])[:3]),
                    "human_label": "",
                    "notes": "",
                }
            )
    rows.sort(key=lambda r: r["paper_id"])
    return rows, breakdown


def write_queue(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a stratified labeling queue.")
    parser.add_argument("--n", type=int, default=200, help="Queue size (default 200).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=DATA_DIR / "labeling_queue.csv")
    args = parser.parse_args()

    init_database()
    with SessionLocal() as session:
        rows, breakdown = sample_queue(
            session, n=args.n, seed=args.seed, eval_labels_path=settings.eval_labels_csv
        )
    write_queue(args.output, rows)

    print(f"Wrote {len(rows)} papers to {args.output}")
    print(f"{'stratum (label x band)':<36} {'available':>9} {'sampled':>8}")
    for (label, band), (available, sampled) in sorted(breakdown.items()):
        print(f"{label + ' x ' + band:<36} {available:>9d} {sampled:>8d}")


if __name__ == "__main__":
    main()
