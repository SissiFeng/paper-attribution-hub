"""Load a PaperSource into the database, idempotently."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

import pandas as pd

from app.adapters.base import PaperSource
from app.config import settings
from app.models import AcCorePaper, Author, Institution, Paper, PaperAuthor, Topic
from app.services.normalization_service import normalize_doi, normalize_name


@dataclass
class IngestionStats:
    papers: int = 0
    people: int = 0
    institutions: int = 0
    topics: int = 0
    ac_core_papers: int = 0
    skipped_duplicates: int = 0


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(str(p).lower() for p in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"


def ingest_institutions(session: Session, source: PaperSource) -> int:
    count = 0
    for rec in source.institutions():
        canonical = rec.canonical_name.strip()
        existing = session.execute(
            select(Institution).where(Institution.canonical_name == canonical)
        ).scalar_one_or_none()
        normalized_aliases = sorted(
            {normalize_name(a) for a in [canonical, *rec.aliases] if a}
        )
        if existing is None:
            session.add(
                Institution(
                    id=_stable_id("inst", canonical),
                    canonical_name=canonical,
                    aliases=rec.aliases,
                    normalized_aliases=normalized_aliases,
                    country=rec.country,
                    city=rec.city,
                    is_partner=rec.is_partner,
                )
            )
            count += 1
        else:
            existing.aliases = rec.aliases
            existing.normalized_aliases = normalized_aliases
            existing.country = rec.country
            existing.city = rec.city
            existing.is_partner = rec.is_partner
    session.flush()
    return count


def ingest_people(session: Session, source: PaperSource) -> int:
    count = 0
    institutions_by_name: dict[str, Institution] = {
        inst.canonical_name: inst for inst in session.execute(select(Institution)).scalars()
    }
    for rec in source.people():
        institution = institutions_by_name.get(rec.institution) if rec.institution else None
        existing = session.execute(
            select(Author).where(Author.id == rec.person_id)
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                Author(
                    id=rec.person_id,
                    canonical_name=rec.name,
                    aliases=rec.aliases,
                    normalized_name=normalize_name(rec.name),
                    orcid=rec.orcid or None,
                    institution_id=institution.id if institution else None,
                    department=rec.department,
                    lab=rec.lab,
                    role=rec.role,
                    is_ac_member=rec.is_ac_member,
                )
            )
            count += 1
        else:
            existing.canonical_name = rec.name
            existing.aliases = rec.aliases
            existing.normalized_name = normalize_name(rec.name)
            existing.orcid = rec.orcid or None
            existing.institution_id = institution.id if institution else None
            existing.department = rec.department
            existing.lab = rec.lab
            existing.role = rec.role
            existing.is_ac_member = rec.is_ac_member
    session.flush()
    return count


def ingest_topics(session: Session, source: PaperSource) -> int:
    count = 0
    for rec in source.topics():
        existing = session.get(Topic, rec.topic_id)
        keywords_json = [{"term": kw.term, "weight": kw.weight} for kw in rec.keywords]
        neg_kw = list(rec.negative_keywords or [])
        if existing is None:
            session.add(
                Topic(
                    id=rec.topic_id,
                    name=rec.name,
                    description=rec.description,
                    keywords=keywords_json,
                    negative_keywords=neg_kw,
                    is_core=rec.is_core,
                )
            )
            count += 1
        else:
            existing.name = rec.name
            existing.description = rec.description
            existing.keywords = keywords_json
            existing.is_core = rec.is_core
            # Merge negative_keywords (taxonomy YAML may have learned new ones
            # from the active learning loop between reset and ingest).
            merged = list(dict.fromkeys((existing.negative_keywords or []) + neg_kw))
            existing.negative_keywords = merged
    session.flush()
    return count


def ingest_papers(session: Session, source: PaperSource) -> tuple[int, int]:
    """Insert papers + paper_authors. Returns (inserted, skipped_duplicates)."""
    inserted = 0
    skipped = 0
    seen_dois: set[str] = {
        row[0] for row in session.execute(select(Paper.doi)).all() if row[0]
    }

    for rec in source.papers():
        if rec.doi and rec.doi in seen_dois:
            skipped += 1
            continue

        existing = session.get(Paper, rec.paper_id)
        if existing is None:
            paper = Paper(
                id=rec.paper_id,
                title=rec.title,
                abstract=rec.abstract,
                doi=rec.doi,
                year=rec.year,
                venue=rec.venue,
                source=rec.source,
                keywords=rec.keywords,
                raw_metadata=rec.raw,
            )
            session.add(paper)
            inserted += 1
        else:
            paper = existing
            paper.title = rec.title
            paper.abstract = rec.abstract
            paper.doi = rec.doi
            paper.year = rec.year
            paper.venue = rec.venue
            paper.keywords = rec.keywords
            paper.raw_metadata = rec.raw
            # Wipe existing paper_authors so we can rebuild from current source.
            for pa in list(paper.authors):
                session.delete(pa)
            session.flush()

        if rec.doi:
            seen_dois.add(rec.doi)

        _attach_authors(session, paper, rec.authors, rec.affiliations)

    session.flush()
    return inserted, skipped


def _attach_authors(
    session: Session, paper: Paper, author_names: list[str], affiliations: list[str]
) -> None:
    """Create lightweight Author rows for paper authors not already known."""
    seen_author_ids: set[str] = set()
    for order, name in enumerate(author_names):
        affiliation = affiliations[order] if order < len(affiliations) else None
        normalized = normalize_name(name)
        author_id = _stable_id("auth", normalized)
        author = session.get(Author, author_id)
        if author is None:
            # Check if we can match an existing Author by normalized_name first
            from sqlalchemy import select as _select

            author = session.execute(
                _select(Author).where(Author.normalized_name == normalized)
            ).scalar_one_or_none()
        if author is None:
            author = Author(
                id=author_id,
                canonical_name=name,
                aliases=[],
                normalized_name=normalized,
                is_ac_member=False,
            )
            session.add(author)
            session.flush()
        if author.id in seen_author_ids:
            continue
        seen_author_ids.add(author.id)
        session.add(
            PaperAuthor(
                paper_id=paper.id,
                author_id=author.id,
                author_order=order,
                affiliation_text=affiliation,
            )
        )


def ingest_ac_core_papers(session: Session) -> int:
    """Load curated AC landmark papers from CSV. Idempotent."""
    csv_path = settings.ac_core_papers_csv
    if not csv_path.exists():
        return 0
    df = pd.read_csv(csv_path)
    count = 0
    for _, row in df.iterrows():
        core_id = str(row["core_id"]).strip()
        existing = session.get(AcCorePaper, core_id)
        doi = normalize_doi(row.get("doi") if pd.notna(row.get("doi")) else None)
        authors = (
            [a.strip() for a in str(row.get("authors", "")).split(";") if a.strip()]
            if pd.notna(row.get("authors"))
            else []
        )
        year_val = row.get("year")
        year = int(year_val) if pd.notna(year_val) else None
        if existing is None:
            session.add(
                AcCorePaper(
                    id=core_id,
                    doi=doi,
                    title=str(row["title"]).strip(),
                    authors=authors,
                    year=year,
                    venue=str(row.get("venue")) if pd.notna(row.get("venue")) else None,
                    why_core=str(row.get("why_core")) if pd.notna(row.get("why_core")) else None,
                )
            )
            count += 1
        else:
            existing.doi = doi
            existing.title = str(row["title"]).strip()
            existing.authors = authors
            existing.year = year
            existing.venue = str(row.get("venue")) if pd.notna(row.get("venue")) else None
            existing.why_core = (
                str(row.get("why_core")) if pd.notna(row.get("why_core")) else None
            )
    session.flush()
    return count


def ingest_all(session: Session, source: PaperSource) -> IngestionStats:
    stats = IngestionStats()
    stats.institutions = ingest_institutions(session, source)
    stats.people = ingest_people(session, source)
    stats.topics = ingest_topics(session, source)
    stats.ac_core_papers = ingest_ac_core_papers(session)
    inserted, skipped = ingest_papers(session, source)
    stats.papers = inserted
    stats.skipped_duplicates = skipped
    session.commit()
    return stats
