"""Descriptive institution analytics from verified Tier 1 full texts.

The source is ``PaperEntity(entity_type="institution")`` extracted only from
the Markdown front matter. Results are paper-level affiliation mentions and
co-occurrences, not resolved author affiliations or proof of collaboration.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperAuthor, PaperEntity
from app.services.filter_spec import PaperFilter, apply_filter
from app.services.normalization_service import normalize_institution

_UOFT_ALIASES = {
    "uoft",
    "u of t",
    "univ toronto",
    "university of toronto",
    "university toronto",
}


def _is_focus_institution(name: str, focus: str) -> bool:
    normalized_name = normalize_institution(name)
    normalized_focus = normalize_institution(focus)
    if normalized_focus in _UOFT_ALIASES:
        return normalized_name in _UOFT_ALIASES
    return normalized_name == normalized_focus


def build_institution_comparison(
    session: Session,
    filt: PaperFilter,
    *,
    focus: str = "University of Toronto",
    limit: int = 25,
) -> dict:
    filtered = apply_filter(
        select(Paper.id, Paper.year, Paper.full_text_available),
        filt,
    ).subquery()
    paper_rows = session.execute(
        select(filtered.c.id, filtered.c.year, filtered.c.full_text_available)
    ).all()
    paper_year = {paper_id: year for paper_id, year, _ in paper_rows}
    fulltext_papers = {
        paper_id
        for paper_id, _year, full_text_available in paper_rows
        if full_text_available
    }

    entity_rows = session.execute(
        select(
            filtered.c.id,
            filtered.c.year,
            PaperEntity.normalized_name,
            PaperEntity.confidence,
        )
        .join(PaperEntity, PaperEntity.paper_id == filtered.c.id)
        .where(PaperEntity.entity_type == "institution")
    ).all()

    paper_institutions: dict[str, set[str]] = defaultdict(set)
    institution_papers: dict[str, set[str]] = defaultdict(set)
    confidence_by_institution: dict[str, list[float]] = defaultdict(list)
    for paper_id, _year, institution, confidence in entity_rows:
        canonical = str(institution or "").strip()
        if not canonical:
            continue
        paper_institutions[paper_id].add(canonical)
        institution_papers[canonical].add(paper_id)
        confidence_by_institution[canonical].append(float(confidence or 0.0))

    focus_name = next(
        (
            institution
            for institution in institution_papers
            if _is_focus_institution(institution, focus)
        ),
        "University of Toronto"
        if normalize_institution(focus) in _UOFT_ALIASES
        else focus,
    )
    focus_paper_ids = {
        paper_id
        for paper_id, institutions in paper_institutions.items()
        if any(_is_focus_institution(name, focus) for name in institutions)
    }

    institutions = []
    for institution, paper_ids in institution_papers.items():
        if _is_focus_institution(institution, focus):
            shared = 0
        else:
            shared = len(paper_ids & focus_paper_ids)
        confidences = confidence_by_institution[institution]
        institutions.append(
            {
                "name": institution,
                "paper_count": len(paper_ids),
                "share_of_corpus": round(
                    len(paper_ids) / len(paper_rows), 4
                )
                if paper_rows
                else 0.0,
                "shared_papers_with_focus": shared,
                "mean_extraction_confidence": round(
                    sum(confidences) / len(confidences), 4
                ),
            }
        )
    institutions.sort(
        key=lambda row: (
            not _is_focus_institution(row["name"], focus),
            -row["paper_count"],
            row["name"],
        )
    )

    yearly = []
    for year in sorted({year for year in paper_year.values() if year is not None}):
        year_papers = {
            paper_id for paper_id, paper_year_value in paper_year.items()
            if paper_year_value == year
        }
        yearly.append(
            {
                "year": year,
                "corpus_papers": len(year_papers),
                "focus_papers": len(year_papers & focus_paper_ids),
                "other_institution_papers": sum(
                    1
                    for paper_id in year_papers
                    if any(
                        not _is_focus_institution(name, focus)
                        for name in paper_institutions.get(paper_id, set())
                    )
                ),
            }
        )

    papers_with_affiliations = len(paper_institutions)
    return {
        "available": True,
        "scope": {
            "corpus_papers": len(paper_rows),
            "fulltext_papers": len(fulltext_papers),
            "papers_with_affiliations": papers_with_affiliations,
            "institution_count": len(institution_papers),
            "institution_paper_mentions": sum(
                len(paper_ids) for paper_ids in institution_papers.values()
            ),
            "extraction_coverage": round(
                papers_with_affiliations / len(fulltext_papers), 4
            )
            if fulltext_papers
            else 0.0,
        },
        "focus": {
            "name": focus_name,
            "paper_count": len(focus_paper_ids),
            "share_of_corpus": round(
                len(focus_paper_ids) / len(paper_rows), 4
            )
            if paper_rows
            else 0.0,
            "coaffiliated_papers": sum(
                1
                for paper_id in focus_paper_ids
                if len(paper_institutions.get(paper_id, set())) > 1
            ),
        },
        "institutions": institutions[:limit],
        "yearly": yearly,
        "audit": {
            "source": "verified_zotero_tier1_markdown_frontmatter",
            "extractor": "frontmatter_affiliation_v1",
            "unit": "distinct_papers",
            "paper_count": (
                "Distinct filtered Tier 1 papers in the current S3-backed "
                "full-text corpus."
            ),
            "institution_paper_count": (
                "Distinct papers whose front matter names the institution."
            ),
            "shared_papers_with_focus": (
                "Distinct papers whose front matter names both the focus and "
                "comparison institution; this is affiliation co-occurrence, "
                "not a resolved author-level collaboration claim."
            ),
            "classification_used": False,
            "ac_member_seed_used": False,
        },
    }


def build_descriptive_network_growth(
    session: Session,
    filt: PaperFilter,
) -> dict:
    """Build growth counts without classifier or AC-derived state."""
    filtered = apply_filter(
        select(Paper.id, Paper.year).where(Paper.year.is_not(None)),
        filt,
    ).subquery()
    paper_rows = session.execute(
        select(filtered.c.id, filtered.c.year)
    ).all()
    paper_year = {paper_id: year for paper_id, year in paper_rows}

    author_rows = session.execute(
        select(
            filtered.c.id,
            filtered.c.year,
            PaperAuthor.author_id,
        ).join(PaperAuthor, PaperAuthor.paper_id == filtered.c.id)
    ).all()
    institution_rows = session.execute(
        select(
            filtered.c.id,
            filtered.c.year,
            PaperEntity.normalized_name,
        )
        .join(PaperEntity, PaperEntity.paper_id == filtered.c.id)
        .where(PaperEntity.entity_type == "institution")
    ).all()

    authors_by_paper: dict[str, set[str]] = defaultdict(set)
    institutions_by_paper: dict[str, set[str]] = defaultdict(set)
    for paper_id, _year, author_id in author_rows:
        authors_by_paper[paper_id].add(author_id)
    for paper_id, _year, institution in institution_rows:
        if institution:
            institutions_by_paper[paper_id].add(institution)

    years = sorted(set(paper_year.values()))
    yearly = []
    for year in years:
        year_papers = {
            paper_id
            for paper_id, paper_year_value in paper_year.items()
            if paper_year_value == year
        }
        yearly.append(
            {
                "year": year,
                "papers": len(year_papers),
                "authors": len(
                    {
                        author_id
                        for paper_id in year_papers
                        for author_id in authors_by_paper.get(paper_id, set())
                    }
                ),
                "institutions": len(
                    {
                        institution
                        for paper_id in year_papers
                        for institution in institutions_by_paper.get(
                            paper_id, set()
                        )
                    }
                ),
                "countries": 0,
                "collaborations": sum(
                    1
                    for paper_id in year_papers
                    if len(institutions_by_paper.get(paper_id, set())) > 1
                ),
            }
        )

    cumulative = []
    cumulative_papers = 0
    cumulative_collaborations = 0
    seen_authors: set[str] = set()
    seen_institutions: set[str] = set()
    for point in yearly:
        year = point["year"]
        year_papers = {
            paper_id
            for paper_id, paper_year_value in paper_year.items()
            if paper_year_value == year
        }
        cumulative_papers += len(year_papers)
        cumulative_collaborations += point["collaborations"]
        for paper_id in year_papers:
            seen_authors.update(authors_by_paper.get(paper_id, set()))
            seen_institutions.update(
                institutions_by_paper.get(paper_id, set())
            )
        cumulative.append(
            {
                "year": year,
                "papers": cumulative_papers,
                "authors": len(seen_authors),
                "institutions": len(seen_institutions),
                "countries": 0,
                "collaborations": cumulative_collaborations,
            }
        )
    return {"yearly": yearly, "cumulative": cumulative}
