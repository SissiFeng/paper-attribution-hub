"""Verify that a fetched document is actually the target paper.

DOI is authoritative when both sides have one. Otherwise combine title
similarity (token Jaccard), author last-name overlap, and year agreement. A
title that matches but whose authors are disjoint is treated as UNCERTAIN, not
MATCH — that is the classic wrong-version / wrong-paper trap.

Pure and dependency-free so it can be called from the fetch pipeline without
coupling to it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {"a", "an", "the", "of", "for", "and", "on", "in", "to", "with", "via"}


@dataclass(frozen=True)
class DocIdentity:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str | None = None


@dataclass(frozen=True)
class IdentityVerdict:
    verdict: str  # MATCH | MISMATCH | UNCERTAIN
    score: float
    signals: dict[str, float]


def _norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d or None


def _title_tokens(title: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(title.lower()) if t not in _STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _last_names(authors: list[str]) -> set[str]:
    names: set[str] = set()
    for author in authors:
        parts = [p for p in re.split(r"[\s,]+", author.strip().lower()) if p]
        if parts:
            names.add(parts[-1])
    return names


def _author_overlap(a: list[str], b: list[str]) -> float:
    la, lb = _last_names(a), _last_names(b)
    if not la or not lb:
        return 0.0
    return len(la & lb) / min(len(la), len(lb))


def verify_identity(target: DocIdentity, fetched: DocIdentity) -> IdentityVerdict:
    td, fd = _norm_doi(target.doi), _norm_doi(fetched.doi)
    if td and fd:
        if td == fd:
            return IdentityVerdict("MATCH", 1.0, {"doi": 1.0})
        return IdentityVerdict("MISMATCH", 0.0, {"doi": 0.0})

    title_sim = _jaccard(_title_tokens(target.title), _title_tokens(fetched.title))
    author_sim = _author_overlap(target.authors, fetched.authors)
    have_authors = bool(target.authors and fetched.authors)
    year_match = (
        target.year is not None
        and fetched.year is not None
        and target.year == fetched.year
    )
    signals = {
        "title_sim": round(title_sim, 3),
        "author_sim": round(author_sim, 3),
        "year_match": 1.0 if year_match else 0.0,
    }
    score = round(0.6 * title_sim + 0.3 * author_sim + 0.1 * (1.0 if year_match else 0.0), 3)

    if title_sim < 0.3:
        verdict = "MISMATCH"
    elif title_sim >= 0.9:
        # Strong title match, but disjoint authors is the wrong-paper trap.
        verdict = "UNCERTAIN" if (have_authors and author_sim == 0.0) else "MATCH"
    elif title_sim >= 0.55 and (author_sim > 0.0 or year_match):
        verdict = "MATCH"
    else:
        verdict = "UNCERTAIN"

    return IdentityVerdict(verdict, score, signals)
