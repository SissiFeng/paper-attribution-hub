"""Ingest the Scopus batch CSV + AC Publications gold set into the database.

Steps
-----
1. Load & normalise tier1_tier2_merged_classification_ready.csv
2. Load & normalise AC Publications (Focused)-Grid view.csv
3. Deduplicate tier1_tier2 (DOI → EID → normalised-title+year+first-author)
4. Match AC gold rows → tier rows; write AC signals back
5. Add unmatched AC papers as provenance='ac_gold' so they enter the pipeline
6. Compute Tier-2 architecture component scores (AI / automation / closed-loop)
7. Upsert papers plus Scopus author / institution / paper-author links

Usage
-----
    python -m app.scripts.ingest_scopus_batch [--reset] [--dry-run]

Options
-------
--reset   Drop and recreate the database before ingesting.
--dry-run Print stats without writing to the database.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.retrieval_operationalization import architecture_terms

def _default_root() -> Path:
    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "data").exists() and (candidate / "backend").exists():
            return candidate
    return cwd


ROOT = Path(os.environ.get("PAS_REPO_ROOT", _default_root())).resolve()
DATA_ROOT = Path(os.environ.get("PAS_DATA_ROOT", "/data")).resolve()
if not DATA_ROOT.exists():
    DATA_ROOT = ROOT / "data"


def _first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


TIER_CSV = _first_existing(
    ROOT / "tier1_tier2_merged_classification_ready.csv",
    DATA_ROOT / "tier1_tier2_merged_classification_ready.csv.gz",
    DATA_ROOT / "tier1_tier2_merged_classification_ready.csv",
)
AC_CSV = _first_existing(
    ROOT / "AC Publications (Focused)-Grid view.csv",
    DATA_ROOT / "ac_publications_focused_grid_view.csv.gz",
    DATA_ROOT / "AC Publications (Focused)-Grid view.csv",
)

# Architecture keyword lists for Tier-2 component scoring
_AI_KW = [
    "machine learning", "deep learning", "neural network", "reinforcement learning",
    "bayesian optimization", "gaussian process", "active learning", "ai-driven",
    "ai driven", "artificial intelligence", "transformer", "language model",
    *architecture_terms("ai_decision_making"),
]
_AUTO_KW = [
    "automated", "high-throughput", "high throughput", "robotic", "autonomous experimentation",
    "liquid handling", "automated synthesis", "flow chemistry", "self-operating",
    "autonomous platform", *architecture_terms("automated_experimentation"),
]
_LOOP_KW = [
    "closed-loop", "closed loop", "iterative optimization", "self-driving",
    "autonomous discovery", "feedback loop", "sequential optimization",
    "design-build-test", "design build test", "active sampling",
    *architecture_terms("iterative_closed_loop"),
]

# AC institution/funding keywords for attribution scoring
_AC_INST_KW = [
    "acceleration consortium", "accelerating consortium",
    "university of toronto", "uoft",
]
_AC_FUND_KW = [
    "acceleration consortium", "cfi", "canada foundation for innovation",
    "nserc", "cfref", "canada first research excellence fund",
]


# ---------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------

_PROXY_DOI_RE = re.compile(r"/doi/(\S+)", re.IGNORECASE)
_DOI_PREFIX_RE = re.compile(r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE)
_DOI_PATTERN_RE = re.compile(r"(10\.\d{4,}/\S+)")


def _norm_doi(doi: Any) -> str | None:
    if pd.isna(doi):
        return None
    raw = str(doi).strip()

    # Library proxy URLs: extract /doi/10.xxx part
    m = _PROXY_DOI_RE.search(raw)
    if m:
        raw = m.group(1)

    # Strip doi.org prefix (with or without scheme)
    raw = _DOI_PREFIX_RE.sub("", raw)

    # Strip trailing punctuation that can creep in from copy-paste
    raw = raw.rstrip(".,; ")

    # Final sanity: must look like a DOI (starts with 10.)
    if not raw.startswith("10."):
        # Try to extract a DOI pattern as last resort
        m2 = _DOI_PATTERN_RE.search(raw)
        if m2:
            raw = m2.group(1).rstrip(".,; ")
        else:
            return None

    return raw.lower() or None


def _norm_title(title: Any) -> str:
    if pd.isna(title):
        return ""
    t = re.sub(r"[^a-z0-9 ]", " ", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def _norm_lookup(text: Any) -> str:
    if pd.isna(text):
        return ""
    folded = unicodedata.normalize("NFKD", str(text))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = re.sub(r"\([^)]*\)", " ", folded)
    folded = re.sub(r"[^a-z0-9 ]", " ", folded.lower())
    return re.sub(r"\s+", " ", folded).strip()


def _year(val: Any) -> int | None:
    try:
        y = int(float(str(val)))
        return y if 1990 <= y <= 2030 else None
    except (TypeError, ValueError):
        return None


def _str_or_none(val: Any) -> str | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    return s or None


def _bool_field(val: Any) -> bool | None:
    if pd.isna(val):
        return None
    s = str(val).strip().lower()
    if s in ("yes", "true", "1", "y"):
        return True
    if s in ("no", "false", "0", "n"):
        return False
    return None


_AC_FUNDING_RE = re.compile(
    r"acceleration\s+consortium"
    r"|accelerat\w*\s+consortium"
    r"|canada\s+first\s+research\s+excellence\s+fund"
    r"|CFREF.{0,30}accel"
    r"|AC\s+(?:PDF|Core\s+Development|Research\s+Moonshot|Translation)\s+Grant"
    r"|(?:funded|supported|acknowledge)\w*\s+by\s+the\s+(?:Acceleration|AC\b)"
    r"|Acceleration\s+Consortium\s+(?:of|at|for|grant)",
    re.IGNORECASE,
)


def _detect_ac_funding(*texts: str | None) -> bool:
    """Return True if any funding text contains a clear AC acknowledgement."""
    for t in texts:
        if t and _AC_FUNDING_RE.search(t):
            return True
    return False


def _split_tags(val: Any) -> list[str] | None:
    if pd.isna(val):
        return None
    parts = [p.strip() for p in re.split(r"[;,|]", str(val)) if p.strip()]
    return parts or None


def _split_pipe(val: Any) -> list[str]:
    if pd.isna(val):
        return []
    return [p.strip() for p in str(val).split("|")]


def _split_ac_members(val: Any) -> set[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return set()
    if isinstance(val, list):
        raw = ",".join(str(v) for v in val if v)
    else:
        raw = str(val)
    return {_norm_lookup(p) for p in raw.split(",") if _norm_lookup(p)}


def _first_affiliation_name(profile_name: str | None, affiliation_name: str | None) -> str | None:
    raw = (profile_name or "").strip() or (affiliation_name or "").strip()
    if not raw:
        return None
    return raw.split(";")[-1].strip().strip(";") or raw.strip(";")


def _stable_id(prefix: str, *parts: str) -> str:
    seed = "|".join(str(p).lower() for p in parts)
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _kw_present(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


# ---------------------------------------------------------------------------
# load
# ---------------------------------------------------------------------------

def _load_tier(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lstrip("﻿").str.strip('"')
    df["_doi"] = df["DOI"].apply(_norm_doi)
    df["_title_norm"] = df["Title"].apply(_norm_title)
    df["_year"] = df["Publication_Year"].apply(_year)
    df["_first_author"] = df["first_author_name"].fillna("").str.strip().str.lower()
    return df


def _load_ac(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, low_memory=False)
    df.columns = df.columns.str.strip().str.lstrip("﻿").str.strip('"')
    df["_doi"] = df["DOI"].apply(_norm_doi)
    df["_title_norm"] = df["Title"].apply(_norm_title)
    df["_year"] = df["Publication Year"].apply(_year)
    return df


# ---------------------------------------------------------------------------
# deduplication
# ---------------------------------------------------------------------------

def _dedup_tier(df: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per canonical paper.

    Priority: DOI exact → EID exact → normalised-title+year+first-author.
    Within a duplicate group, keep the row with RETRIEVAL_TIER == '1' (or
    '1+2') if present, otherwise keep the first occurrence.
    """
    def _tier_priority(t: str) -> int:
        if "1" in str(t):
            return 0
        return 1

    df = df.copy()
    df["_tier_pri"] = df["RETRIEVAL_TIER"].apply(_tier_priority)
    df = df.sort_values("_tier_pri")

    seen_doi: set[str] = set()
    seen_eid: set[str] = set()
    seen_key: set[str] = set()
    keep: list[int] = []

    for idx, row in df.iterrows():
        doi = row["_doi"]
        eid = _str_or_none(row.get("EID"))
        key = f"{row['_title_norm']}|{row['_year']}|{row['_first_author']}"

        if doi and doi in seen_doi:
            continue
        if eid and eid in seen_eid:
            continue
        if key and key in seen_key:
            continue

        if doi:
            seen_doi.add(doi)
        if eid:
            seen_eid.add(eid)
        if key:
            seen_key.add(key)
        keep.append(idx)

    return df.loc[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# AC gold matching
# ---------------------------------------------------------------------------

_FUZZY_THRESH = 0.85


def _match_ac_to_tier(tier: pd.DataFrame, ac: pd.DataFrame) -> dict[int, int]:
    """Return {ac_row_index: tier_row_index} for matched pairs."""
    tier_doi_idx: dict[str, int] = {}
    for i, row in tier.iterrows():
        if row["_doi"]:
            tier_doi_idx.setdefault(row["_doi"], i)

    tier_title_list = [
        (i, set(row["_title_norm"].split()), row["_year"])
        for i, row in tier.iterrows()
    ]

    matches: dict[int, int] = {}
    for ac_idx, ac_row in ac.iterrows():
        doi = ac_row["_doi"]
        if doi and doi in tier_doi_idx:
            matches[ac_idx] = tier_doi_idx[doi]
            continue

        ac_tok = set(ac_row["_title_norm"].split())
        ac_yr = ac_row["_year"]
        best_score, best_tier_idx = 0.0, None
        for t_idx, t_tok, t_yr in tier_title_list:
            if ac_yr and t_yr and abs(ac_yr - t_yr) > 1:
                continue
            score = _jaccard(ac_tok, t_tok)
            if score > best_score:
                best_score, best_tier_idx = score, t_idx

        if best_score >= _FUZZY_THRESH and best_tier_idx is not None:
            matches[ac_idx] = best_tier_idx

    return matches


def _write_ac_signals(tier: pd.DataFrame, ac: pd.DataFrame, matches: dict[int, int]) -> pd.DataFrame:
    """Stamp AC gold fields onto matched tier rows (in-place on a copy)."""
    tier = tier.copy()
    tier["_ac_known"] = False
    tier["_ac_acknowledged"] = None
    tier["_ac_highly_relevant"] = None
    tier["_ac_high_impact"] = None
    tier["_ac_programs"] = None
    tier["_ac_sdl_tags"] = None
    tier["_ac_research_tags"] = None
    tier["_ac_members_matched"] = None

    for ac_idx, tier_idx in matches.items():
        ac_row = ac.loc[ac_idx]
        tier.at[tier_idx, "_ac_known"] = True
        tier.at[tier_idx, "_ac_acknowledged"] = _bool_field(ac_row.get("Acknowledges AC"))
        tier.at[tier_idx, "_ac_highly_relevant"] = _bool_field(ac_row.get("Highly Relevant"))
        tier.at[tier_idx, "_ac_high_impact"] = _bool_field(ac_row.get("High Impact"))
        tier.at[tier_idx, "_ac_programs"] = _str_or_none(ac_row.get("AC Funded Programs"))
        tier.at[tier_idx, "_ac_sdl_tags"] = _split_tags(ac_row.get("SDL"))
        tier.at[tier_idx, "_ac_research_tags"] = _split_tags(ac_row.get("Research Tags"))
        members = _str_or_none(ac_row.get("AC Members"))
        tier.at[tier_idx, "_ac_members_matched"] = [members] if members else None

    return tier


# ---------------------------------------------------------------------------
# architecture score
# ---------------------------------------------------------------------------

def _arch_scores(
    title: Any,
    abstract: Any,
    author_keywords: Any = None,
    indexed_keywords: Any = None,
) -> tuple[float, float, float]:
    """Score AI / automation / closed-loop architecture components.

    Uses all available text: title + abstract + author_keywords + indexed_keywords.
    Keywords are weighted the same as body text — a keyword like
    "self-driving laboratory" is as diagnostic as the same phrase in the abstract.
    """
    text = " ".join(filter(None, [
        str(title or ""),
        str(abstract or ""),
        str(author_keywords or ""),
        str(indexed_keywords or ""),
    ])).lower()
    ai = 1.0 if _kw_present(text, _AI_KW) else 0.0
    auto = 1.0 if _kw_present(text, _AUTO_KW) else 0.0
    loop = 1.0 if _kw_present(text, _LOOP_KW) else 0.0
    return ai, auto, loop


def _author_links_from_row(row: pd.Series, ac_members: Any = None) -> list[dict]:
    names = _split_pipe(row.get("author_names"))
    scopus_ids = _split_pipe(row.get("author_scopus_ids"))
    affiliation_names = _split_pipe(row.get("author_affiliation_names_grouped"))
    profile_names = _split_pipe(row.get("author_affiliation_profile_names_grouped"))
    countries = _split_pipe(row.get("author_affiliation_countries_grouped"))
    cities = _split_pipe(row.get("author_affiliation_cities_grouped"))
    ac_member_names = _split_ac_members(ac_members)

    links: list[dict] = []
    for i, name in enumerate(names):
        if not name:
            continue
        scopus_id = scopus_ids[i] if i < len(scopus_ids) and scopus_ids[i] else None
        affiliation_text = (
            affiliation_names[i] if i < len(affiliation_names) and affiliation_names[i] else None
        )
        profile_name = profile_names[i] if i < len(profile_names) and profile_names[i] else None
        institution = _first_affiliation_name(profile_name, affiliation_text)
        country = countries[i] if i < len(countries) and countries[i] else None
        city = cities[i] if i < len(cities) and cities[i] else None
        links.append({
            "author_id": (
                _stable_id("auth_scopus", scopus_id)
                if scopus_id
                else _stable_id("auth", name, institution or "")
            ),
            "name": name,
            "scopus_id": scopus_id,
            "is_ac_member": _norm_lookup(name) in ac_member_names,
            "institution": institution,
            "country": country,
            "city": city,
            "affiliation_text": affiliation_text,
        })
    return links


# ---------------------------------------------------------------------------
# DB upsert
# ---------------------------------------------------------------------------

def _upsert_papers(session: Session, rows: list[dict]) -> tuple[int, int, int, int, int]:
    from app.models import Author, Institution, Paper, PaperAuthor  # avoid circular import

    inserted, updated = 0, 0
    authors_upserted, institutions_upserted, links_written = 0, 0, 0
    institutions_by_name: dict[str, Institution] = {
        inst.canonical_name: inst for inst in session.execute(select(Institution)).scalars()
    }
    institutions_by_id: dict[str, Institution] = {
        inst.id: inst for inst in institutions_by_name.values()
    }
    authors_by_id: dict[str, Author] = {
        author.id: author for author in session.execute(select(Author)).scalars()
    }
    seen_doi: set[str] = {
        r[0] for r in session.execute(select(Paper.doi)).all() if r[0]
    }
    seen_eid: set[str] = {
        r[0] for r in session.execute(select(Paper.eid)).all() if r[0]
    }

    for row in rows:
        doi = row.get("doi")
        eid = row.get("eid")

        # Find existing record
        paper: Paper | None = None
        if doi and doi in seen_doi:
            paper = session.execute(
                select(Paper).where(Paper.doi == doi)
            ).scalar_one_or_none()
        elif eid and eid in seen_eid:
            paper = session.execute(
                select(Paper).where(Paper.eid == eid)
            ).scalar_one_or_none()

        if paper is None:
            paper = Paper(id=row["id"])
            session.add(paper)
            inserted += 1
        else:
            updated += 1

        author_links = row.get("author_links") or []

        # Write all paper fields
        for field, value in row.items():
            if field not in {"id", "author_links"} and hasattr(paper, field):
                setattr(paper, field, value)

        if doi:
            seen_doi.add(doi)
        if eid:
            seen_eid.add(eid)

        if author_links:
            for pa in list(paper.authors):
                session.delete(pa)
            session.flush()

            seen_paper_authors: set[str] = set()
            for order, link in enumerate(author_links):
                if link["author_id"] in seen_paper_authors:
                    continue
                seen_paper_authors.add(link["author_id"])
                inst_id = None
                inst_name = link.get("institution")
                if inst_name:
                    candidate_inst_id = _stable_id("inst", inst_name)
                    inst = institutions_by_name.get(inst_name) or institutions_by_id.get(candidate_inst_id)
                    if inst is None:
                        inst = Institution(
                            id=candidate_inst_id,
                            canonical_name=inst_name,
                            aliases=[],
                            normalized_aliases=[_norm_title(inst_name)],
                            country=link.get("country"),
                            city=link.get("city"),
                        )
                        session.add(inst)
                        institutions_by_name[inst_name] = inst
                        institutions_by_id[inst.id] = inst
                        institutions_upserted += 1
                    else:
                        institutions_by_name[inst_name] = inst
                        if not inst.country and link.get("country"):
                            inst.country = link.get("country")
                        if not inst.city and link.get("city"):
                            inst.city = link.get("city")
                    inst_id = inst.id

                author = authors_by_id.get(link["author_id"])
                if author is None:
                    author = Author(
                        id=link["author_id"],
                        canonical_name=link["name"],
                        aliases=[],
                        normalized_name=_norm_title(link["name"]),
                        institution_id=inst_id,
                        is_ac_member=bool(link.get("is_ac_member")),
                        raw_metadata={"scopus_id": link.get("scopus_id")},
                    )
                    session.add(author)
                    authors_by_id[author.id] = author
                    authors_upserted += 1
                else:
                    author.canonical_name = link["name"]
                    author.normalized_name = _norm_title(link["name"])
                    if inst_id:
                        author.institution_id = inst_id
                    if link.get("is_ac_member"):
                        author.is_ac_member = True
                    raw = author.raw_metadata or {}
                    if link.get("scopus_id"):
                        raw["scopus_id"] = link.get("scopus_id")
                    author.raw_metadata = raw

                session.add(
                    PaperAuthor(
                        paper_id=paper.id,
                        author_id=author.id,
                        author_order=order,
                        affiliation_text=link.get("affiliation_text"),
                        match_confidence=1.0 if link.get("scopus_id") else 0.7,
                    )
                )
                links_written += 1

        # Flush every 500 rows to keep memory pressure low
        if (inserted + updated) % 500 == 0:
            session.flush()

    session.flush()
    return inserted, updated, authors_upserted, institutions_upserted, links_written


# ---------------------------------------------------------------------------
# main build
# ---------------------------------------------------------------------------

def _build_rows(tier: pd.DataFrame, ac: pd.DataFrame, matches: dict[int, int]) -> list[dict]:
    """Convert tier dataframe rows → list of dicts ready for DB upsert."""
    rows: list[dict] = []

    for _, row in tier.iterrows():
        title = _str_or_none(row.get("Title"))
        abstract = _str_or_none(row.get("Abstract"))
        author_kw = _str_or_none(row.get("Author_Keywords"))
        indexed_kw = _str_or_none(row.get("Indexed_Keywords"))
        ai_s, auto_s, loop_s = _arch_scores(title, abstract, author_kw, indexed_kw)

        funding_text = _str_or_none(row.get("funding_text"))
        funding_sponsors_raw = _str_or_none(row.get("funding_sponsors"))
        funding_sponsors = _split_tags(funding_sponsors_raw)

        # Detect AC funding acknowledgement from Scopus metadata fields —
        # supplements the AC Publications gold-set flag for papers the
        # gold set doesn't cover.
        _ac_funding_detected = _detect_ac_funding(
            funding_text,
            _str_or_none(row.get("funding_details")),
            funding_sponsors_raw,
            _str_or_none(row.get("Funding")),
        )

        doi = row["_doi"]
        eid = _str_or_none(row.get("EID"))
        paper_id = (
            _stable_id("scopus", doi) if doi
            else _stable_id("scopus", eid or row["_title_norm"])
        )

        rows.append({
            "id": paper_id,
            "title": title or "",
            "abstract": abstract,
            "doi": doi,
            "year": row["_year"],
            "venue": _str_or_none(row.get("Source_Title")),
            "source": "scopus",
            "provenance": "scopus_batch",
            "corpus_sources": (
                ["AC_MEMBER_CORPUS"]
                if bool(row.get("_ac_known", False))
                else []
            )
            + (
                ["STRICT_SDL_KEYWORD"]
                if "tier1" in str(row.get("RETRIEVAL_TIER") or "").lower()
                else []
            )
            + (
                ["ARCHITECTURE_BROAD_RETRIEVAL"]
                if "tier2" in str(row.get("RETRIEVAL_TIER") or "").lower()
                else []
            ),
            "keywords": _split_tags(author_kw),
            "indexed_keywords": _split_tags(indexed_kw),
            # Scopus provenance
            "eid": eid,
            "retrieval_tier": _str_or_none(row.get("RETRIEVAL_TIER")),
            "merge_tier_membership": _str_or_none(row.get("merge_tier_membership")),
            "query_string": _str_or_none(row.get("QUERY_STRING")),
            "funding_text": funding_text,
            "funding_sponsors": funding_sponsors,
            "author_links": _author_links_from_row(row, row.get("_ac_members_matched")),
            # AC gold signals
            "ac_known_publication": bool(row.get("_ac_known", False)),
            # ac_acknowledged: from gold-set CSV OR detected in Scopus funding text
            "ac_acknowledged": bool(row.get("_ac_acknowledged")) or _ac_funding_detected,
            "ac_highly_relevant": row.get("_ac_highly_relevant"),
            "ac_high_impact": row.get("_ac_high_impact"),
            "ac_members_matched": row.get("_ac_members_matched"),
            "ac_programs": row.get("_ac_programs"),
            "sdl_tags": row.get("_ac_sdl_tags"),
            "research_tags": row.get("_ac_research_tags"),
            # Architecture scores
            "ai_decision_score": ai_s,
            "automation_score": auto_s,
            "closed_loop_score": loop_s,
        })

    return rows


def _build_ac_only_rows(
    ac: pd.DataFrame,
    matched_ac_indices: set[int],
    tier_dois: set[str],
) -> list[dict]:
    """Build rows for AC papers NOT found in tier1_tier2 (provenance=ac_gold).

    Skips matched rows, rows whose DOI already exists in tier (fuzzy match missed
    them), and intra-AC duplicates (AC Publications has ~10 duplicate DOI groups).
    """
    rows: list[dict] = []
    seen_doi_local: set[str] = set()
    for ac_idx, row in ac.iterrows():
        if ac_idx in matched_ac_indices:
            continue
        doi = row["_doi"]
        # skip if DOI already present in tier (normalisation mismatch caused miss)
        if doi and doi in tier_dois:
            continue
        # skip intra-AC duplicates
        if doi and doi in seen_doi_local:
            continue
        if doi:
            seen_doi_local.add(doi)

        title = _str_or_none(row.get("Title"))
        doi = row["_doi"]
        paper_id = (
            _stable_id("acgold", doi) if doi
            else _stable_id("acgold", row["_title_norm"])
        )

        ai_s, auto_s, loop_s = _arch_scores(title, _str_or_none(row.get("Abstract Note")))

        rows.append({
            "id": paper_id,
            "title": title or "",
            "abstract": _str_or_none(row.get("Abstract Note")),
            "doi": doi,
            "year": row["_year"],
            "venue": _str_or_none(row.get("Publication Title")),
            "source": "ac_gold",
            "provenance": "ac_gold",
            "corpus_sources": ["AC_MEMBER_CORPUS"],
            "keywords": _split_tags(row.get("Research Tags")),
            # AC gold signals (all from AC Publications directly)
            "ac_known_publication": True,
            "ac_acknowledged": _bool_field(row.get("Acknowledges AC")),
            "ac_highly_relevant": _bool_field(row.get("Highly Relevant")),
            "ac_high_impact": _bool_field(row.get("High Impact")),
            "ac_programs": _str_or_none(row.get("AC Funded Programs")),
            "sdl_tags": _split_tags(row.get("SDL")),
            "research_tags": _split_tags(row.get("Research Tags")),
            "ac_members_matched": (
                [_str_or_none(row.get("AC Members"))]
                if _str_or_none(row.get("AC Members")) else None
            ),
            # Architecture scores
            "ai_decision_score": ai_s,
            "automation_score": auto_s,
            "closed_loop_score": loop_s,
        })

    return rows


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def run(
    dry_run: bool = False,
    reset: bool = False,
    seed_if_under: int | None = None,
    prune_non_real: bool = False,
    classify: bool = False,
) -> None:
    from app.db import SessionLocal, init_database, reset_database
    from app.models import Paper
    from app.models.proposition import PaperProposition

    if not TIER_CSV.exists():
        print(f"ERROR: {TIER_CSV} not found", file=sys.stderr)
        sys.exit(1)
    if not AC_CSV.exists():
        print(f"ERROR: {AC_CSV} not found", file=sys.stderr)
        sys.exit(1)

    if seed_if_under is not None and not reset:
        init_database()
        with SessionLocal() as session:
            paper_count = session.scalar(select(func.count(Paper.id))) or 0
        if paper_count >= seed_if_under:
            print(
                f"Seed skipped: database already has {paper_count} papers "
                f"(threshold={seed_if_under}).",
                file=sys.stderr,
            )
            return

    print("Loading CSVs...", file=sys.stderr)
    tier_raw = _load_tier(TIER_CSV)
    ac = _load_ac(AC_CSV)
    print(f"  tier raw: {len(tier_raw)} rows  |  ac gold: {len(ac)} rows", file=sys.stderr)

    print("Deduplicating tier1_tier2...", file=sys.stderr)
    tier = _dedup_tier(tier_raw)
    dropped = len(tier_raw) - len(tier)
    print(f"  kept {len(tier)} rows  (dropped {dropped} duplicates)", file=sys.stderr)

    print("Matching AC gold → tier papers...", file=sys.stderr)
    matches = _match_ac_to_tier(tier, ac)
    tier = _write_ac_signals(tier, ac, matches)
    print(
        f"  matched {len(matches)} AC papers  "
        f"({len(ac) - len(matches)} AC papers not in tier pool)",
        file=sys.stderr,
    )

    print("Building tier rows...", file=sys.stderr)
    tier_rows = _build_rows(tier, ac, matches)

    print("Building AC-only rows (not found in Scopus retrieval)...", file=sys.stderr)
    matched_ac_idx = set(matches.keys())
    tier_doi_set = set(tier["_doi"].dropna())
    ac_only_rows = _build_ac_only_rows(ac, matched_ac_idx, tier_doi_set)
    print(f"  {len(ac_only_rows)} AC papers added as provenance=ac_gold", file=sys.stderr)

    all_rows = tier_rows + ac_only_rows
    print(f"\nTotal rows to upsert: {len(all_rows)}", file=sys.stderr)
    print(
        f"  AC known in tier: {sum(1 for r in tier_rows if r['ac_known_publication'])}",
        file=sys.stderr,
    )
    print(
        f"  Tier 1: {sum(1 for r in tier_rows if r.get('retrieval_tier') == '1')}  "
        f"Tier 2: {sum(1 for r in tier_rows if r.get('retrieval_tier') == '2')}",
        file=sys.stderr,
    )
    arch3 = sum(
        1 for r in all_rows
        if r.get("ai_decision_score", 0) == 1
        and r.get("automation_score", 0) == 1
        and r.get("closed_loop_score", 0) == 1
    )
    print(f"  Full SDL architecture (all 3 components): {arch3}", file=sys.stderr)

    if dry_run:
        print("\n[dry-run] No writes performed.", file=sys.stderr)
        return

    if reset:
        print("Resetting database...", file=sys.stderr)
        reset_database()
    else:
        init_database()

    print("Writing to database...", file=sys.stderr)
    with SessionLocal() as session:
        # Seed the topic taxonomy first — without it every topic_score is 0.0
        # and the relevance classifier can never reach CORE_RELEVANT.
        from app.adapters import CsvPaperSource
        from app.services.ingestion_service import ingest_topics

        topics_seeded = ingest_topics(session, CsvPaperSource())
        print(f"      topics_seeded={topics_seeded}", file=sys.stderr)
        inserted, updated, authors, institutions, links = _upsert_papers(session, all_rows)
        if prune_non_real:
            stale = list(
                session.execute(
                    select(Paper).where(Paper.provenance.notin_(["scopus_batch", "ac_gold"]))
                ).scalars()
            )
            if stale:
                stale_ids = [p.id for p in stale]
                session.execute(
                    PaperProposition.__table__.delete().where(
                        PaperProposition.paper_id.in_(stale_ids)
                    )
                )
            for paper in stale:
                session.delete(paper)
            print(f"      pruned_non_real_papers={len(stale)}", file=sys.stderr)
        session.commit()

    print(
        f"\nDone. inserted={inserted}  updated={updated}  total={inserted + updated}",
        file=sys.stderr,
    )
    print(
        f"      authors_upserted={authors}  institutions_upserted={institutions}  paper_author_links={links}",
        file=sys.stderr,
    )

    if classify:
        from app.services.scopus_classifier import run_scopus_classification

        with SessionLocal() as session:
            stats = run_scopus_classification(session)
            session.commit()
        print(f"      classification={stats}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Scopus batch + AC gold into DB.")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate tables first.")
    parser.add_argument("--dry-run", action="store_true", help="Print stats, don't write.")
    parser.add_argument(
        "--seed-if-under",
        type=int,
        default=None,
        help="Only ingest when the database has fewer than this many papers.",
    )
    parser.add_argument(
        "--prune-non-real",
        action="store_true",
        help="Delete papers outside provenance=scopus_batch/ac_gold after ingest.",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Run Scopus/AC rule classification after ingest.",
    )
    args = parser.parse_args()
    run(
        dry_run=args.dry_run,
        reset=args.reset,
        seed_if_under=args.seed_if_under,
        prune_non_real=args.prune_non_real,
        classify=args.classify,
    )


if __name__ == "__main__":
    main()
