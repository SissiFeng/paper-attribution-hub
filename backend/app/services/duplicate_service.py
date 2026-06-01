"""Duplicate candidate grouping for paper records.

This is intentionally advisory: it suggests a canonical row but does not merge
or delete records. Website publication needs a human-reviewed canonical choice.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper

PREPRINT_DOI_PREFIXES = (
    "10.1101/",   # bioRxiv / medRxiv
    "10.26434/",  # ChemRxiv
    "10.48550/",  # arXiv
)


@dataclass
class DuplicateCandidate:
    paper_id: str
    title: str
    doi: str | None
    year: int | None
    provenance: str
    label: str | None
    is_preprint: bool
    score: float


@dataclass
class DuplicateGroup:
    key: str
    title: str
    group_type: str
    severity: str
    canonical_paper_id: str
    reason: str
    candidates: list[DuplicateCandidate] = field(default_factory=list)


def build_duplicate_report(session: Session) -> dict:
    groups = build_duplicate_groups(session)
    return {
        "group_count": len(groups),
        "paper_count": sum(len(g.candidates) for g in groups),
        "blocker_groups": sum(1 for g in groups if g.severity == "blocker"),
        "warning_groups": sum(1 for g in groups if g.severity == "warning"),
        "groups": groups,
    }


def build_duplicate_groups(session: Session) -> list[DuplicateGroup]:
    papers = list(session.execute(select(Paper)).scalars())
    by_title: dict[str, list[Paper]] = defaultdict(list)
    for paper in papers:
        by_title[_norm_title(paper.title)].append(paper)

    groups: list[DuplicateGroup] = []
    for key, rows in by_title.items():
        doi_values = {(p.doi or "").strip().lower() for p in rows}
        if len(rows) < 2 or len(doi_values) <= 1:
            continue

        candidates = [_candidate(p) for p in rows]
        candidates.sort(key=lambda c: (-c.score, c.year or 0, c.paper_id))
        canonical = candidates[0]
        group_type, severity, reason = _classify_group(candidates)
        groups.append(
            DuplicateGroup(
                key=key,
                title=canonical.title,
                group_type=group_type,
                severity=severity,
                canonical_paper_id=canonical.paper_id,
                reason=reason,
                candidates=candidates,
            )
        )

    groups.sort(key=lambda g: (g.severity != "blocker", -len(g.candidates), g.title.lower()))
    return groups


def _candidate(paper: Paper) -> DuplicateCandidate:
    cls = paper.classification
    doi = (paper.doi or "").strip().lower() or None
    score = 0.0
    if doi:
        score += 1.0
    if doi and not _is_preprint_doi(doi):
        score += 2.0
    if paper.provenance == "scopus_batch":
        score += 0.6
    if paper.ac_known_publication:
        score += 0.5
    if paper.year:
        score += min(0.4, max(0, paper.year - 2000) / 100)
    return DuplicateCandidate(
        paper_id=paper.id,
        title=paper.title,
        doi=doi,
        year=paper.year,
        provenance=paper.provenance or paper.source or "unknown",
        label=cls.label if cls else None,
        is_preprint=bool(doi and _is_preprint_doi(doi)),
        score=round(score, 3),
    )


def _classify_group(candidates: list[DuplicateCandidate]) -> tuple[str, str, str]:
    has_preprint = any(c.is_preprint for c in candidates)
    has_published = any(c.doi and not c.is_preprint for c in candidates)
    if has_preprint and has_published:
        return (
            "preprint_published_version",
            "warning",
            "Same title appears as a preprint and a published DOI; choose one canonical website record.",
        )
    if all(c.provenance == "ac_gold" for c in candidates):
        return (
            "ac_gold_version_conflict",
            "warning",
            "Duplicate appears only in AC Publications; likely version history or metadata duplication.",
        )
    return (
        "conflicting_metadata",
        "blocker",
        "Same title has multiple DOI values without a clear preprint-to-published pattern.",
    )


def _is_preprint_doi(doi: str) -> bool:
    return doi.startswith(PREPRINT_DOI_PREFIXES)


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())
