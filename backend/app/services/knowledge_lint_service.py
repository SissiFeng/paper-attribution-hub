"""Knowledge-base lint checks for website/reporting readiness."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperClassification

HIGH_LABELS = {"CORE_RELEVANT", "RELATED_RELEVANT"}


@dataclass
class LintEntry:
    paper_id: str
    title: str
    label: str | None
    severity: str
    reason: str


@dataclass
class LintBucket:
    bucket: str
    label: str
    description: str
    severity: str
    count: int = 0
    entries: list[LintEntry] = field(default_factory=list)


@dataclass
class LintReport:
    total_papers_scanned: int
    website_blockers: int
    reporting_warnings: int
    buckets: list[LintBucket]


def build_knowledge_lint_report(session: Session, *, sample_size: int = 25) -> LintReport:
    papers = list(session.execute(select(Paper)).scalars())
    buckets = _buckets()

    dois = Counter((p.doi or "").strip().lower() for p in papers if p.doi)
    title_index: dict[str, set[str | None]] = defaultdict(set)
    for paper in papers:
        title_index[_norm_title(paper.title)].add((paper.doi or "").strip().lower() or None)

    for paper in papers:
        cls = paper.classification
        label = cls.label if cls else None
        ac_evidence = _has_ac_evidence(paper, cls)
        architecture = _architecture_count(paper, cls)

        if paper.doi and dois[paper.doi.strip().lower()] > 1:
            _add(
                buckets["duplicate_doi"],
                paper,
                label,
                "Duplicate DOI appears in the corpus.",
                sample_size,
            )

        if len(title_index[_norm_title(paper.title)]) > 1:
            _add(
                buckets["same_title_different_doi"],
                paper,
                label,
                "Same normalized title is associated with multiple DOI values.",
                sample_size,
            )

        if label in HIGH_LABELS and not ac_evidence:
            _add(
                buckets["core_ac_missing_evidence"],
                paper,
                label,
                "CORE/RELATED label has no AC author, publication, funding, acknowledgement, network, or citation evidence.",
                sample_size,
            )

        if label == "SDL_FIELD_RELEVANT" and architecture == 0:
            _add(
                buckets["sdl_missing_architecture"],
                paper,
                label,
                "SDL_FIELD_RELEVANT label has no AI, automation, closed-loop, or architecture signal.",
                sample_size,
            )

        if label in HIGH_LABELS and not paper.review and (paper.ac_high_impact or paper.ac_highly_relevant):
            _add(
                buckets["high_impact_unreviewed"],
                paper,
                label,
                "High-impact or highly relevant paper has not been manually reviewed.",
                sample_size,
            )

        if cls and cls.model_agreement_status in {"needs_ac_evidence_review", "human_corrected"}:
            _add(
                buckets["model_disagreement_unresolved"],
                paper,
                label,
                f"Model agreement status is {cls.model_agreement_status}.",
                sample_size,
            )

        if label == "EXCLUDE" and paper.ac_known_publication:
            _add(
                buckets["exclude_matches_ac_publications"],
                paper,
                label,
                "Paper is in AC Publications but classified EXCLUDE.",
                sample_size,
            )

        if paper.ac_known_publication and not paper.retrieval_tier:
            _add(
                buckets["ac_publication_missing_retrieval"],
                paper,
                label,
                "AC Publications paper is present only through the gold set, not Scopus retrieval.",
                sample_size,
            )

    website_blockers = sum(b.count for b in buckets.values() if b.severity == "blocker")
    reporting_warnings = sum(b.count for b in buckets.values() if b.severity != "blocker")
    return LintReport(
        total_papers_scanned=len(papers),
        website_blockers=website_blockers,
        reporting_warnings=reporting_warnings,
        buckets=list(buckets.values()),
    )


def _buckets() -> dict[str, LintBucket]:
    return {
        "duplicate_doi": LintBucket(
            "duplicate_doi",
            "Duplicate DOI",
            "Same DOI appears on multiple paper rows.",
            "blocker",
        ),
        "same_title_different_doi": LintBucket(
            "same_title_different_doi",
            "Same title, conflicting DOI",
            "Title-level duplicate with different DOI metadata.",
            "blocker",
        ),
        "core_ac_missing_evidence": LintBucket(
            "core_ac_missing_evidence",
            "AC label missing evidence",
            "Website-blocking AC attribution without direct supporting evidence.",
            "blocker",
        ),
        "sdl_missing_architecture": LintBucket(
            "sdl_missing_architecture",
            "SDL label missing architecture",
            "SDL-relevant paper lacks AI, automation, or closed-loop evidence.",
            "warning",
        ),
        "high_impact_unreviewed": LintBucket(
            "high_impact_unreviewed",
            "High impact unreviewed",
            "Important papers should be reviewed before public display.",
            "warning",
        ),
        "model_disagreement_unresolved": LintBucket(
            "model_disagreement_unresolved",
            "Model disagreement unresolved",
            "Prior model/human disagreement still needs curation.",
            "warning",
        ),
        "exclude_matches_ac_publications": LintBucket(
            "exclude_matches_ac_publications",
            "AC publication excluded",
            "AC Publications paper cannot be EXCLUDE without explicit rationale.",
            "blocker",
        ),
        "ac_publication_missing_retrieval": LintBucket(
            "ac_publication_missing_retrieval",
            "AC publication missing retrieval",
            "Gold-set paper did not enter through Tier 1/Tier 2 retrieval.",
            "warning",
        ),
    }


def _add(
    bucket: LintBucket,
    paper: Paper,
    label: str | None,
    reason: str,
    sample_size: int,
) -> None:
    bucket.count += 1
    if len(bucket.entries) < sample_size:
        bucket.entries.append(
            LintEntry(
                paper_id=paper.id,
                title=paper.title,
                label=label,
                severity=bucket.severity,
                reason=reason,
            )
        )


def _norm_title(title: str) -> str:
    return " ".join(title.lower().split())


def _architecture_count(paper: Paper, cls: PaperClassification | None) -> int:
    paper_count = int(bool(paper.ai_decision_score)) + int(bool(paper.automation_score)) + int(bool(paper.closed_loop_score))
    class_count = int((cls.architecture_signal if cls else 0.0) > 0)
    return max(paper_count, class_count)


def _has_ac_evidence(paper: Paper, cls: PaperClassification | None) -> bool:
    if paper.ac_known_publication or paper.ac_acknowledged or paper.ac_members_matched or paper.ac_programs:
        return True
    if (paper.ac_attribution_score or 0.0) >= 0.2:
        return True
    if cls is None:
        return False
    if max(cls.author_score, cls.institution_score, cls.network_score, cls.citation_score) >= 0.2:
        return True
    if max(cls.funding_signal, cls.acknowledgement_signal) >= 0.2:
        return True
    return False
