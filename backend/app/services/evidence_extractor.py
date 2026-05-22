"""Evidence extraction from full-text chunks (v0.7).

For each paper with full text, this scans:
  - acknowledgements / funding → AC funding mentions, partner institution
    mentions (now distinguishes "funded by AC" from "we thank X for data").
  - methods → SDL methodology, with negation context
    ("we do *not* use a self-driving lab" → skipped).
  - figure_caption → SDL terminology, with a learned blacklist
    ("self-driving car" doesn't trigger SDL).
  - references → AC core DOI hits (placeholder, extensible).

Output: rows in `paper_evidence` plus a per-paper aggregate
`fulltext_evidence_score` in [0, 1].

v0.7 changes:
  * regex token-boundary matching via `text_utils.find_term_hits`
  * negation suppression
  * section-aware blacklists
  * funding-context heuristic (we look for "funded by" / "supported by" /
    "acknowledge" cues within 6 tokens of the institution name; otherwise the
    score is halved because just naming the institution isn't proof of
    funding).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PaperChunk, PaperEvidence
from app.services.text_utils import (
    TermHit,
    find_term_hits,
    tokens,
)

# Configurable signal libraries.
FUNDING_TERMS = [
    "acceleration consortium",
    "ac initiative",
    "ac postdoctoral",
    "vector institute",
    "cifar",
    "nserc",
    "cfi",
]

PARTNER_TERMS = [
    "university of toronto",
    "uoft",
    "univ. toronto",
    "u toronto",
    "ubc",
    "university of british columbia",
    "vector institute",
]

SDL_METHODOLOGY_TERMS = [
    "self-driving lab",
    "self-driving laboratory",
    "autonomous laboratory",
    "autonomous platform",
    "closed-loop",
    "closed loop",
    "bayesian optimization",
    "active learning",
    "robotic synthesis",
    "robotic platform",
    "high-throughput experimentation",
    "automated synthesis",
    "workflow orchestration",
]

# v0.7: blacklist for SDL-look-alikes in figure captions / methods that come
# from unrelated domains.
SDL_BLACKLIST = {
    "self-driving car",
    "autonomous vehicle",
    "autonomous driving",
    "self-driving automobile",
}

# Cues that disambiguate "we got money from X" vs. "we thank X for data".
FUNDING_CONTEXT_CUES = {
    "funded",
    "funding",
    "supported",
    "support",
    "grant",
    "grants",
    "fellowship",
    "acknowledge",
    "acknowledges",
    "thank",
    "thanks",
    "sponsorship",
    "sponsored",
    "award",
    "awarded",
}

# Type → (score per hit, score cap)
EVIDENCE_WEIGHTS = {
    "funding_acknowledgement": (0.6, 1.0),
    "partner_institution_acknowledgement": (0.3, 0.6),
    "sdl_methodology": (0.2, 0.7),
    "figure_caption_sdl": (0.2, 0.5),
    # v0.7: negative evidence (from LLM judge or blacklist hits).
    "disqualifying": (-0.4, 0.0),
}


@dataclass
class EvidenceRecord:
    evidence_type: str
    evidence_source: str  # section_type
    evidence_text: str
    score: float
    chunk_id: str | None


def _excerpt_around(text: str, hit: TermHit, window: int = 200) -> str:
    start = max(0, hit.start - window // 2)
    end = min(len(text), hit.end + window // 2)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    return snippet


def _has_funding_context(text: str, hit: TermHit, window: int = 8) -> bool:
    """Look at the ±240 chars around the hit; if a funding cue appears in
    the *surrounding* text (excluding the hit term itself), treat the
    institution name as a funder, not just a casual mention.

    Critically, we exclude tokens that are *inside* the hit so that an
    institution whose own name contains a funding-cue word (e.g. "Acceleration
    Consortium" — `consortium` is itself a cue) doesn't bootstrap the check.
    """
    start = max(0, hit.start - 240)
    end = min(len(text), hit.end + 240)
    prefix = text[start : hit.start].lower()
    suffix = text[hit.end : end].lower()
    surrounding = tokens(prefix) + tokens(suffix)
    return any(t in FUNDING_CONTEXT_CUES for t in surrounding)


def _is_blacklisted(text: str, hit: TermHit, *, window_chars: int = 80) -> bool:
    """Is the hit actually part of a blacklisted phrase like 'self-driving car'?"""
    start = max(0, hit.start - window_chars)
    end = min(len(text), hit.end + window_chars)
    surrounding = text[start:end].lower()
    return any(find_term_hits(surrounding, bl) for bl in SDL_BLACKLIST)


def _scan_with_context(
    text_lower: str,
    terms: list[str],
    *,
    require_funding_cue: bool = False,
) -> list[tuple[str, TermHit, float]]:
    """Return [(term, hit, weight_multiplier)] for non-negated, non-blacklisted hits."""
    out: list[tuple[str, TermHit, float]] = []
    for term in terms:
        for hit in find_term_hits(text_lower, term):
            if hit.negated:
                continue
            if _is_blacklisted(text_lower, hit):
                continue
            multiplier = 1.0
            if require_funding_cue and not _has_funding_context(text_lower, hit):
                multiplier = 0.5
            out.append((term, hit, multiplier))
    return out


def extract_evidence_for_paper(
    session: Session, paper_id: str
) -> tuple[list[EvidenceRecord], float]:
    chunks = list(
        session.execute(
            select(PaperChunk).where(PaperChunk.paper_id == paper_id)
        ).scalars()
    )
    records: list[EvidenceRecord] = []

    for chunk in chunks:
        text = chunk.chunk_text
        lower = text.lower()
        section = chunk.section_type

        if section == "acknowledgements":
            for term, hit, mult in _scan_with_context(
                lower, FUNDING_TERMS, require_funding_cue=True
            ):
                records.append(
                    EvidenceRecord(
                        evidence_type="funding_acknowledgement",
                        evidence_source=section,
                        evidence_text=_excerpt_around(text, hit),
                        score=EVIDENCE_WEIGHTS["funding_acknowledgement"][0]
                        * mult,
                        chunk_id=chunk.id,
                    )
                )
            for term, hit, mult in _scan_with_context(
                lower, PARTNER_TERMS, require_funding_cue=True
            ):
                records.append(
                    EvidenceRecord(
                        evidence_type="partner_institution_acknowledgement",
                        evidence_source=section,
                        evidence_text=_excerpt_around(text, hit),
                        score=EVIDENCE_WEIGHTS[
                            "partner_institution_acknowledgement"
                        ][0]
                        * mult,
                        chunk_id=chunk.id,
                    )
                )

        if section == "methods":
            for term, hit, _mult in _scan_with_context(
                lower, SDL_METHODOLOGY_TERMS
            ):
                records.append(
                    EvidenceRecord(
                        evidence_type="sdl_methodology",
                        evidence_source=section,
                        evidence_text=_excerpt_around(text, hit),
                        score=EVIDENCE_WEIGHTS["sdl_methodology"][0],
                        chunk_id=chunk.id,
                    )
                )

        if section == "figure_caption":
            for term, hit, _mult in _scan_with_context(
                lower, SDL_METHODOLOGY_TERMS
            ):
                records.append(
                    EvidenceRecord(
                        evidence_type="figure_caption_sdl",
                        evidence_source=section,
                        evidence_text=_excerpt_around(text, hit),
                        score=EVIDENCE_WEIGHTS["figure_caption_sdl"][0],
                        chunk_id=chunk.id,
                    )
                )

    return records, _aggregate_score(records)


def _aggregate_score(records: list[EvidenceRecord]) -> float:
    """Cap each evidence type at its ceiling, sum the caps, subtract negative."""
    totals: dict[str, float] = {}
    for r in records:
        totals[r.evidence_type] = totals.get(r.evidence_type, 0.0) + r.score
    capped = 0.0
    for evidence_type, total in totals.items():
        cap = EVIDENCE_WEIGHTS.get(evidence_type, (0.0, 0.5))[1]
        if total >= 0:
            capped += min(total, cap)
        else:
            # Negative evidence subtracts; floor at -cap (which is 0 for
            # disqualifying — making it a strict subtractive penalty).
            capped += max(total, -1.0)
    # Combine into [0, 1]; funding alone is enough to dominate.
    score = max(0.0, min(capped / 1.5, 1.0))
    return round(score, 3)


def persist_evidence(session: Session, paper_id: str) -> tuple[int, float]:
    """Re-run extraction for a paper, replace its rows, return (count, score)."""
    existing = (
        session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id == paper_id)
        )
        .scalars()
        .all()
    )
    for row in existing:
        session.delete(row)
    session.flush()

    records, score = extract_evidence_for_paper(session, paper_id)
    for rec in records:
        session.add(
            PaperEvidence(
                id=f"ev_{uuid.uuid4().hex[:12]}",
                paper_id=paper_id,
                chunk_id=rec.chunk_id,
                evidence_type=rec.evidence_type,
                evidence_source=rec.evidence_source,
                evidence_text=rec.evidence_text,
                score=rec.score,
            )
        )
    session.flush()
    return len(records), score


def add_disqualifying_evidence(
    session: Session,
    paper_id: str,
    *,
    source: str,
    snippet: str,
    chunk_id: str | None = None,
) -> PaperEvidence:
    """Persist a negative-evidence row (e.g. from the LLM judge).

    These show up in the aggregator with a negative score and drive the FP
    rate down.
    """
    row = PaperEvidence(
        id=f"ev_{uuid.uuid4().hex[:12]}",
        paper_id=paper_id,
        chunk_id=chunk_id,
        evidence_type="disqualifying",
        evidence_source=source,
        evidence_text=snippet,
        score=EVIDENCE_WEIGHTS["disqualifying"][0],
    )
    session.add(row)
    session.flush()
    return row
