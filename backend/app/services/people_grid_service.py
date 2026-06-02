"""People-grid service (v0.7 — periodic table of AC members).

Each AC member becomes a "chemical element":

  * `symbol`: two letters from the surname (or single letter if name is one
    word). Capitalised, like real element symbols.
  * `atomic_number`: paper count attributed to this person (proxy for
    "research mass").
  * `period` / `group`: position on the grid. Derived from institution +
    paper count so people cluster meaningfully.
  * `category`: top topic, used as the cell color group.
  * `papers`: small sample for the hover tooltip.

The frontend turns this into a `<div>` grid that visually echoes a periodic
table.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Author, Paper, PaperAuthor, PaperClassification, Topic
from app.services.normalization_service import normalize_name


_LATIN_LETTER = re.compile(r"[A-Za-z]")


def _symbol_for(name: str) -> str:
    """Two-letter "element" symbol from the surname. Falls back to first
    initials if anything's off."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    parts = [p for p in re.split(r"[\s\-]+", ascii_name.strip()) if p]
    if not parts:
        return "??"
    # Use the last name's first 2 letters.
    surname = parts[-1]
    letters = "".join(c for c in surname if _LATIN_LETTER.match(c))
    if len(letters) >= 2:
        return (letters[0] + letters[1].lower()).capitalize()
    # Fallback: first letter of each name token.
    initials = "".join(p[0] for p in parts[:2] if p)
    initials = "".join(c for c in initials if _LATIN_LETTER.match(c))
    if len(initials) >= 2:
        return (initials[0] + initials[1].lower()).capitalize()
    return (letters or initials or "??")[:2].capitalize()


def build_people_grid(session: Session) -> dict:
    raw_authors = list(
        session.execute(select(Author).where(Author.is_ac_member)).scalars()
    )
    if not raw_authors:
        return {"elements": [], "categories": [], "max_papers": 0}

    # Deduplicate by normalized canonical name — multiple Author rows can exist
    # for the same person when different CSV imports create slight name variants.
    # Prefer the record that has an ORCID; otherwise keep whichever was loaded first.
    seen_norm: dict[str, Author] = {}
    for author in raw_authors:
        norm = normalize_name(author.canonical_name)
        if norm not in seen_norm:
            seen_norm[norm] = author
        elif author.orcid and not seen_norm[norm].orcid:
            seen_norm[norm] = author  # upgrade to the ORCID-bearing record
    ac_authors = list(seen_norm.values())

    # Map author → papers + topics
    topic_lookup: dict[str, Topic] = {
        t.id: t for t in session.execute(select(Topic)).scalars()
    }

    elements: list[dict] = []
    category_paper_counts: dict[str, int] = defaultdict(int)
    seen_symbols: set[str] = set()

    # ── Batch-load all data in 3 queries rather than N per-author queries ────
    author_ids = [a.id for a in ac_authors]

    # 1. Paper count per author (lean aggregation, no Paper objects).
    paper_counts: dict[str, int] = dict(
        session.execute(
            select(PaperAuthor.author_id, func.count(PaperAuthor.paper_id))
            .where(PaperAuthor.author_id.in_(author_ids))
            .group_by(PaperAuthor.author_id)
        ).all()
    )

    # 2. Label distribution per author (lean join, no Paper objects).
    label_rows = session.execute(
        select(PaperAuthor.author_id, PaperClassification.label, func.count())
        .join(PaperClassification, PaperClassification.paper_id == PaperAuthor.paper_id)
        .where(PaperAuthor.author_id.in_(author_ids))
        .group_by(PaperAuthor.author_id, PaperClassification.label)
    ).all()
    label_dist: dict[str, Counter[str]] = defaultdict(Counter)
    for aid, label, cnt in label_rows:
        label_dist[aid][label] = cnt

    # 3. Paper sample (5 most recent per author, minimal columns).
    sample_rows = session.execute(
        select(PaperAuthor.author_id, Paper.id, Paper.title, Paper.year, PaperClassification.label)
        .join(Paper, Paper.id == PaperAuthor.paper_id)
        .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(PaperAuthor.author_id.in_(author_ids))
        .where(Paper.year.is_not(None))
        .order_by(PaperAuthor.author_id, Paper.year.desc())
    ).all()
    author_samples: dict[str, list[dict]] = defaultdict(list)
    for aid, pid, title, year, label in sample_rows:
        if len(author_samples[aid]) < 5:
            author_samples[aid].append({"id": pid, "title": title, "year": year, "label": label})

    for author in ac_authors:
        label_counter = label_dist.get(author.id, Counter())
        paper_count = paper_counts.get(author.id, 0)

        # Top topic: matched_topics is NULL in production, so use "Uncategorized".
        top_topic_id = None
        top_topic_name = "Uncategorized"
        category = "uncategorized"
        category_paper_counts[category] += paper_count

        # Symbol — ensure uniqueness in the grid.
        sym = _symbol_for(author.canonical_name)
        original = sym
        suffix = 1
        while sym in seen_symbols and suffix < 26:
            tokens = author.canonical_name.split()
            if len(tokens) >= 2 and len(tokens[0]) > suffix:
                sym = (original[0] + tokens[0][suffix].lower()).capitalize()
            else:
                idx = (ord("a") + suffix) - ord("a")
                sym = (original[0] + chr(ord("a") + idx)).capitalize()
            suffix += 1
        seen_symbols.add(sym)

        sample = author_samples.get(author.id, [])

        elements.append(
            {
                "person_id": author.id,
                "symbol": sym,
                "name": author.canonical_name,
                "atomic_number": paper_count,
                "category": category,
                "category_label": top_topic_name,
                "institution": (
                    author.institution.canonical_name if author.institution else None
                ),
                "country": (
                    author.institution.country if author.institution else None
                ),
                "orcid": author.orcid,
                "core_count": label_counter.get("CORE_RELEVANT", 0),
                "related_count": label_counter.get("RELATED_RELEVANT", 0),
                "papers": sample,
            }
        )

    # Sort by atomic number descending so heaviest "elements" appear first.
    elements.sort(key=lambda e: -e["atomic_number"])

    # Categories with paper-count metadata so the UI can build a legend.
    categories = [
        {
            "id": cat,
            "label": (
                topic_lookup[cat].name if cat in topic_lookup else cat.replace("_", " ").title()
            ),
            "paper_count": count,
        }
        for cat, count in sorted(
            category_paper_counts.items(), key=lambda kv: -kv[1]
        )
    ]
    max_papers = max((e["atomic_number"] for e in elements), default=0)

    return {
        "elements": elements,
        "categories": categories,
        "max_papers": max_papers,
        "total_people": len(elements),
    }
