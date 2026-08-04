"""Author deduplication service.

Pipeline:
  1. Blocking — group Author records by (last_name_norm, first_initial)
  2. Scoring  — within each block, score candidate pairs on 4 signals:
       name_similarity (rapidfuzz) · co-authorship overlap · institution ·
       ORCID exact match
  3. Decision — score ≥ HIGH_THRESHOLD → auto-merge candidate
              — UNCERTAIN_LOW ≤ score < HIGH_THRESHOLD → flag for human review
              — prior human "separate" decision → skip
  4. Merge    — update PaperAuthor rows, merge aliases, delete duplicate

Usage (via admin endpoints):
  GET  /admin/dedup-candidates       → pairs needing human review
  POST /admin/dedup-merge            → confirm two IDs are same person
  POST /admin/dedup-separate         → confirm two IDs are different people
  POST /admin/dedup-authors          → run auto-merge (high-confidence only)
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Author, AuthorDedupDecision, PaperAuthor

# ── Thresholds ────────────────────────────────────────────────────────────────
# Deliberately conservative: short names in a large corpus produce many
# false positives when the threshold is too low.
HIGH_THRESHOLD = 0.90      # auto-merge above this (ORCID match or very high name sim)
UNCERTAIN_LOW  = 0.72      # flag for human review between LOW and HIGH
# Below UNCERTAIN_LOW → assume different person (no flag)


# ── Normalisation helpers ─────────────────────────────────────────────────────

def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )


def _blocking_key(name: str) -> tuple[str, str]:
    """(last_name_norm, first_initial) — ignores middle initials."""
    cleaned = _strip_accents(name).lower()
    # split on whitespace/hyphen, drop single-char tokens (middle initials)
    parts = [p for p in re.split(r"[\s\-]+", cleaned) if len(p) > 1]
    last = parts[-1] if parts else ""
    first_init = parts[0][0] if parts else ""
    return last, first_init


def _name_similarity(a: str, b: str) -> float:
    try:
        from rapidfuzz.fuzz import token_sort_ratio
        return token_sort_ratio(_strip_accents(a).lower(), _strip_accents(b).lower()) / 100.0
    except ImportError:
        # fallback: exact after strip
        return 1.0 if _strip_accents(a).lower() == _strip_accents(b).lower() else 0.0


# ── Scoring ───────────────────────────────────────────────────────────────────

@dataclass
class DedupCandidate:
    author_a: Author
    author_b: Author
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def id_pair(self) -> tuple[str, str]:
        a, b = sorted([self.author_a.id, self.author_b.id])
        return a, b


def _score_pair(
    a: Author,
    b: Author,
    papers_by_author: dict[str, set[str]],
) -> DedupCandidate:
    reasons: list[str] = []
    score = 0.0

    # 1. ORCID exact match → definitive same person
    if a.orcid and b.orcid and a.orcid == b.orcid:
        return DedupCandidate(a, b, score=1.0,
                               reasons=["ORCID exact match"])

    # 2. Name similarity (0–0.5 contribution)
    ns = _name_similarity(a.canonical_name, b.canonical_name)
    score += ns * 0.5
    if ns >= 0.85:
        reasons.append(f"Name similarity {ns:.0%}")

    # 3. Co-authorship overlap (0–0.3)
    # Require ≥2 shared papers to avoid false positives on common names.
    papers_a = papers_by_author.get(a.id, set())
    papers_b = papers_by_author.get(b.id, set())
    shared = len(papers_a & papers_b)
    if papers_a and papers_b and shared >= 2:
        overlap = shared / min(len(papers_a), len(papers_b))
        score += overlap * 0.3
        reasons.append(f"Share {shared} papers")

    # 4. Same institution (0–0.2)
    if a.institution_id and b.institution_id and a.institution_id == b.institution_id:
        score += 0.2
        reasons.append("Same institution")

    return DedupCandidate(a, b, round(score, 3), reasons)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def find_candidates(
    session: Session,
    *,
    ac_members_only: bool = True,
) -> tuple[list[DedupCandidate], list[DedupCandidate]]:
    """Return (auto_merge_list, human_review_list).

    ac_members_only=True (default): only compare authors flagged is_ac_member=True.
    This avoids the massive false-positive rate on common Chinese/Korean names in
    the general 10K corpus.

    Pairs with a prior human decision are excluded from both lists.
    """
    stmt = select(Author)
    if ac_members_only:
        stmt = stmt.where(Author.is_ac_member.is_(True))
    authors = list(session.execute(stmt).scalars())

    # Build paper-sets per author
    pa_rows = session.execute(
        select(PaperAuthor.author_id, PaperAuthor.paper_id)
    ).all()
    papers_by_author: dict[str, set[str]] = defaultdict(set)
    for aid, pid in pa_rows:
        papers_by_author[aid].add(pid)

    # Load prior human decisions (pairs to skip)
    decided_pairs: set[tuple[str, str]] = set()
    for dec in session.execute(select(AuthorDedupDecision)).scalars():
        a, b = sorted([dec.author_id_a, dec.author_id_b])
        decided_pairs.add((a, b))

    # Blocking: group by (last_name, first_initial)
    blocks: dict[tuple[str, str], list[Author]] = defaultdict(list)
    for author in authors:
        key = _blocking_key(author.canonical_name)
        blocks[key].append(author)

    auto_merge: list[DedupCandidate] = []
    human_review: list[DedupCandidate] = []

    for block in blocks.values():
        if len(block) < 2:
            continue
        for i, a in enumerate(block):
            for b in block[i + 1:]:
                pair = tuple(sorted([a.id, b.id]))
                if pair in decided_pairs:
                    continue  # human already decided
                cand = _score_pair(a, b, papers_by_author)
                if cand.score >= HIGH_THRESHOLD:
                    auto_merge.append(cand)
                elif cand.score >= UNCERTAIN_LOW:
                    human_review.append(cand)

    return (
        sorted(auto_merge, key=lambda c: -c.score),
        sorted(human_review, key=lambda c: -c.score),
    )


def merge_authors(session: Session, keep_id: str, remove_id: str,
                  decided_by: str | None = None) -> dict:
    """Merge remove_id → keep_id: reassign PaperAuthor rows and delete duplicate."""
    keep = session.get(Author, keep_id)
    remove = session.get(Author, remove_id)
    if not keep or not remove:
        return {"error": f"Author not found: {keep_id!r} or {remove_id!r}"}

    # Reassign PaperAuthor rows
    reassigned = 0
    for pa in session.execute(
        select(PaperAuthor).where(PaperAuthor.author_id == remove_id)
    ).scalars():
        # Avoid duplicate (paper_id, keep_id) if already exists
        exists = session.execute(
            select(PaperAuthor).where(
                PaperAuthor.paper_id == pa.paper_id,
                PaperAuthor.author_id == keep_id,
            )
        ).scalar_one_or_none()
        if exists:
            session.delete(pa)
        else:
            pa.author_id = keep_id
        reassigned += 1

    # Merge aliases
    existing_aliases = set(keep.aliases or [])
    existing_aliases.add(remove.canonical_name)
    existing_aliases.update(remove.aliases or [])
    keep.aliases = sorted(existing_aliases - {keep.canonical_name})

    # Carry over ORCID if missing
    if not keep.orcid and remove.orcid:
        keep.orcid = remove.orcid

    # Record decision
    _record_decision(session, keep_id, remove_id, "merge", decided_by)

    session.delete(remove)
    session.flush()

    return {
        "kept": keep_id,
        "removed": remove_id,
        "reassigned_paper_authors": reassigned,
    }


def record_separate(session: Session, author_id_a: str, author_id_b: str,
                    decided_by: str | None = None) -> None:
    """Record that two authors are confirmed different people — don't show again."""
    _record_decision(session, author_id_a, author_id_b, "separate", decided_by)
    session.flush()


def _record_decision(session: Session, a: str, b: str,
                     decision: str, decided_by: str | None) -> None:
    id_a, id_b = sorted([a, b])
    existing = session.execute(
        select(AuthorDedupDecision).where(
            AuthorDedupDecision.author_id_a == id_a,
            AuthorDedupDecision.author_id_b == id_b,
        )
    ).scalar_one_or_none()
    if existing:
        existing.decision = decision
        existing.decided_at = datetime.now(UTC)
        existing.decided_by = decided_by
    else:
        session.add(AuthorDedupDecision(
            id=f"dd_{uuid.uuid4().hex[:10]}",
            author_id_a=id_a,
            author_id_b=id_b,
            decision=decision,
            decided_at=datetime.now(UTC),
            decided_by=decided_by,
        ))


def run_auto_dedup(session: Session) -> dict:
    """Auto-merge all high-confidence pairs, return summary."""
    auto_merge, review = find_candidates(session)
    merged = []
    for cand in auto_merge:
        # Prefer CSV anchor ID (shorter = A001..A082) as canonical
        a, b = cand.author_a, cand.author_b
        keep, remove = (a, b) if len(a.id) <= len(b.id) else (b, a)
        result = merge_authors(session, keep.id, remove.id, decided_by="auto_dedup")
        if "error" not in result:
            merged.append(result)
    session.commit()
    return {
        "auto_merged": len(merged),
        "pending_human_review": len(review),
        "merged_details": merged,
    }
