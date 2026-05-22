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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Author, Paper, PaperAuthor, PaperClassification, Topic


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
    ac_authors = list(
        session.execute(select(Author).where(Author.is_ac_member)).scalars()
    )
    if not ac_authors:
        return {"elements": [], "categories": [], "max_papers": 0}

    # Map author → papers + topics
    topic_lookup: dict[str, Topic] = {
        t.id: t for t in session.execute(select(Topic)).scalars()
    }

    elements: list[dict] = []
    category_paper_counts: dict[str, int] = defaultdict(int)
    seen_symbols: set[str] = set()

    for author in ac_authors:
        # All papers the author is on, with classification.
        rows = list(
            session.execute(
                select(Paper, PaperClassification)
                .join(PaperAuthor, PaperAuthor.paper_id == Paper.id)
                .outerjoin(
                    PaperClassification,
                    PaperClassification.paper_id == Paper.id,
                )
                .where(PaperAuthor.author_id == author.id)
            ).all()
        )

        papers = [r[0] for r in rows]
        classifications = [r[1] for r in rows if r[1] is not None]

        # Top topic across all classifications.
        topic_counter: Counter[str] = Counter()
        label_counter: Counter[str] = Counter()
        for cls in classifications:
            label_counter[cls.label] += 1
            for tm in cls.matched_topics or []:
                if not tm.get("is_core"):
                    continue
                tid = tm.get("topic_id")
                if not tid:
                    continue
                topic_counter[tid] += 1

        top_topic_id = topic_counter.most_common(1)[0][0] if topic_counter else None
        top_topic_name = (
            topic_lookup[top_topic_id].name if top_topic_id else "Uncategorized"
        )
        category = top_topic_id or "uncategorized"
        category_paper_counts[category] += len(papers)

        # Symbol — ensure uniqueness in the grid.
        sym = _symbol_for(author.canonical_name)
        original = sym
        suffix = 1
        while sym in seen_symbols and suffix < 26:
            # Disambiguate: replace second letter with next initial from first name.
            tokens = author.canonical_name.split()
            if len(tokens) >= 2 and len(tokens[0]) > suffix:
                sym = (original[0] + tokens[0][suffix].lower()).capitalize()
            else:
                # Fall back: numeric suffix is ugly, prefer cycling letters.
                idx = (ord("a") + suffix) - ord("a")
                sym = (original[0] + chr(ord("a") + idx)).capitalize()
            suffix += 1
        seen_symbols.add(sym)

        # Sample paper titles for hover.
        sample = [
            {
                "id": p.id,
                "title": p.title,
                "year": p.year,
                "label": (
                    next((c.label for c in classifications if c.paper_id == p.id), None)
                ),
            }
            for p in sorted(papers, key=lambda x: -(x.year or 0))[:5]
        ]

        elements.append(
            {
                "person_id": author.id,
                "symbol": sym,
                "name": author.canonical_name,
                "atomic_number": len(papers),
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
