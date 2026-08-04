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

import csv
import re
import unicodedata
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
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
    entries = _ac_member_entries(session)
    if not entries:
        return {"elements": [], "categories": [], "max_papers": 0}

    # Map author → papers + topics
    topic_lookup: dict[str, Topic] = {
        t.id: t for t in session.execute(select(Topic)).scalars()
    }

    elements: list[dict] = []
    category_paper_counts: dict[str, int] = defaultdict(int)
    seen_symbols: set[str] = set()

    # ── Batch-load all data in 4 queries rather than N per-author queries ────
    author_ids = sorted({aid for entry in entries for aid in entry["author_ids"]})

    # 1. Paper count per author via PaperAuthor (works when links exist).
    paper_counts: dict[str, int] = {}
    if author_ids:
        paper_counts = dict(
            session.execute(
                select(PaperAuthor.author_id, func.count(PaperAuthor.paper_id))
                .where(PaperAuthor.author_id.in_(author_ids))
                .group_by(PaperAuthor.author_id)
            ).all()
        )

    # 2. Label distribution per author (lean join, no Paper objects).
    label_rows = []
    if author_ids:
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
    sample_rows = []
    if author_ids:
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

    # 4. Fallback: count via Paper.ac_members_matched for members whose
    #    PaperAuthor links are missing (new CSV author IDs with no Scopus rows).
    #    Load all papers that have ac_members_matched populated.
    match_rows = session.execute(
        select(Paper.id, Paper.title, Paper.year, Paper.ac_members_matched,
               Paper.sdl_tags, PaperClassification.label)
        .outerjoin(PaperClassification, PaperClassification.paper_id == Paper.id)
        .where(Paper.ac_members_matched.is_not(None))
    ).all()
    # Build: norm(member_name) → list of paper dicts
    name_to_papers: dict[str, list[dict]] = defaultdict(list)
    name_to_label_counter: dict[str, Counter] = defaultdict(Counter)
    for pid, title, year, ac_members, sdl_tags, label in match_rows:
        for mname in (ac_members or []):
            nk = normalize_name(str(mname))
            if nk:
                name_to_papers[nk].append({
                    "id": pid, "title": title, "year": year,
                    "label": label, "sdl_tags": sdl_tags or [],
                })
                if label:
                    name_to_label_counter[nk][label] += 1

    for entry in entries:
        label_counter: Counter[str] = Counter()
        sample: list[dict] = []
        seen_papers: set[str] = set()
        paper_count = 0

        for author_id in entry["author_ids"]:
            label_counter.update(label_dist.get(author_id, Counter()))
            paper_count += paper_counts.get(author_id, 0)
            for paper in author_samples.get(author_id, []):
                if paper["id"] in seen_papers:
                    continue
                seen_papers.add(paper["id"])
                sample.append(paper)

        # If PaperAuthor links are missing, use ac_members_matched as fallback
        sdl_counter: Counter[str] = Counter()
        if paper_count == 0:
            all_names = [entry["name"], *_load_ac_members_csv_aliases(entry["name"])]
            for name in all_names:
                nk = normalize_name(name)
                matched = name_to_papers.get(nk, [])
                paper_count = max(paper_count, len(matched))
                label_counter.update(name_to_label_counter.get(nk, Counter()))
                for paper in sorted(matched, key=lambda p: -(p.get("year") or 0))[:5]:
                    if paper["id"] not in seen_papers:
                        seen_papers.add(paper["id"])
                        sample.append(paper)
                # Accumulate SDL tags from this paper for color
                for tag in (paper.get("sdl_tags") or []):
                    sdl_counter[str(tag).strip()] += 1
                if paper_count > 0:
                    break
        else:
            # Also gather SDL tags from the PaperAuthor path
            for pid, title, year, label in [
                (p["id"], p["title"], p["year"], p["label"]) for p in sample
            ]:
                pass  # sdl_tags not in sample, will fallback to "uncategorized"

        sample.sort(key=lambda p: (p["year"] or 0), reverse=True)
        sample = sample[:5]

        # Top SDL tag → color category (normalise tag to a short key)
        top_sdl_full = sdl_counter.most_common(1)[0][0] if sdl_counter else None
        top_sdl = _sdl_category_key(top_sdl_full) if top_sdl_full else "uncategorized"

        top_topic_name = top_sdl.replace("_", " ").title() if top_sdl != "uncategorized" else "Uncategorized"
        category = top_sdl
        category_paper_counts[category] += paper_count

        # Symbol — ensure uniqueness in the grid.
        sym = _symbol_for(entry["name"])
        original = sym
        suffix = 1
        while sym in seen_symbols and suffix < 26:
            tokens = entry["name"].split()
            if len(tokens) >= 2 and len(tokens[0]) > suffix:
                sym = (original[0] + tokens[0][suffix].lower()).capitalize()
            else:
                idx = (ord("a") + suffix) - ord("a")
                sym = (original[0] + chr(ord("a") + idx)).capitalize()
            suffix += 1
        seen_symbols.add(sym)

        elements.append(
            {
                "person_id": entry["person_id"],
                "symbol": sym,
                "name": entry["name"],
                "atomic_number": paper_count,
                "category": category,
                "category_label": top_topic_name,
                "institution": entry["institution"],
                "country": entry["country"],
                "orcid": entry["orcid"],
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


def _ac_member_entries(session: Session) -> list[dict]:
    authors = list(session.execute(select(Author)).scalars())
    authors_by_id = {a.id: a for a in authors}
    authors_by_norm: dict[str, list[Author]] = defaultdict(list)
    for author in authors:
        keys = {normalize_name(author.canonical_name)}
        keys.update(normalize_name(alias) for alias in (author.aliases or []))
        for key in keys:
            if key:
                authors_by_norm[key].append(author)

    csv_members = _load_ac_members_csv()
    assigned_author_ids: set[str] = set()
    entries: list[dict] = []

    for member in csv_members:
        matched: list[Author] = []
        if member["person_id"] in authors_by_id:
            matched.append(authors_by_id[member["person_id"]])
        for name in [member["name"], *member["aliases"]]:
            for author in authors_by_norm.get(normalize_name(name), []):
                if author not in matched:
                    matched.append(author)

        for author in matched:
            assigned_author_ids.add(author.id)
        best = _best_author_record(matched)
        institution = (
            best.institution.canonical_name
            if best and best.institution
            else member["institution"]
        )
        country = best.institution.country if best and best.institution else None
        entries.append(
            {
                "person_id": member["person_id"],
                "name": member["name"],
                "institution": institution,
                "country": country,
                "orcid": member["orcid"] or (best.orcid if best else None),
                "author_ids": [a.id for a in matched],
            }
        )

    for author in authors:
        if not author.is_ac_member or author.id in assigned_author_ids:
            continue
        entries.append(
            {
                "person_id": author.id,
                "name": author.canonical_name,
                "institution": author.institution.canonical_name if author.institution else None,
                "country": author.institution.country if author.institution else None,
                "orcid": author.orcid,
                "author_ids": [author.id],
            }
        )

    return entries


_SDL_CATEGORY_MAP = {
    "0": "sdl_ai",          # SDL 0 - AI & Automation
    "1": "sdl_robotics",    # SDL 1 - Robotics
    "2": "sdl_organic",     # SDL 2 - Organic
    "3": "sdl_inorganic",   # SDL 3 - Inorganic
    "4": "sdl_biology",     # SDL 4 - Biology
    "5": "sdl_formulations",# SDL 5 - Formulations
    "6": "sdl_energy",      # SDL 6 - Energy
    "7": "sdl_scale",       # SDL 7 - Scale up
}


def _sdl_category_key(tag: str) -> str:
    """'SDL 2 - Organic' → 'sdl_organic'"""
    import re as _re
    m = _re.search(r"SDL\s+(\d+)", tag, _re.IGNORECASE)
    if m:
        return _SDL_CATEGORY_MAP.get(m.group(1), "sdl_other")
    return "sdl_other"


_CSV_ALIAS_CACHE: dict[str, list[str]] = {}

def _load_ac_members_csv_aliases(canonical_name: str) -> list[str]:
    """Return aliases for a member name from the CSV (cached)."""
    if not _CSV_ALIAS_CACHE:
        for m in _load_ac_members_csv():
            _CSV_ALIAS_CACHE[m["name"]] = m["aliases"]
    return _CSV_ALIAS_CACHE.get(canonical_name, [])


def _load_ac_members_csv() -> list[dict]:
    if not settings.people_csv.exists():
        return []
    members: list[dict] = []
    with settings.people_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not str(row.get("is_ac_member", "")).strip().lower().startswith("t"):
                continue
            aliases = [
                alias.strip()
                for alias in str(row.get("aliases") or "").split(";")
                if alias.strip()
            ]
            members.append(
                {
                    "person_id": row["person_id"].strip(),
                    "name": row["name"].strip(),
                    "aliases": aliases,
                    "institution": (row.get("institution") or "").strip() or None,
                    "orcid": (row.get("orcid") or "").strip() or None,
                }
            )
    return members


def _best_author_record(authors: list[Author]) -> Author | None:
    if not authors:
        return None
    return sorted(
        authors,
        key=lambda author: (
            bool(author.orcid),
            bool(author.institution_id),
            author.is_ac_member,
        ),
        reverse=True,
    )[0]
