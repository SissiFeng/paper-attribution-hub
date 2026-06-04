"""Rule-based classifier for papers ingested from the Scopus batch.

Runs BEFORE any LLM or embedding call.  Produces:
  - label (CORE_RELEVANT / RELATED_RELEVANT / SDL_FIELD_RELEVANT / ADJACENT / UNCERTAIN)
  - ac_attribution_score  (0-1, how strongly this is an AC paper)
  - sdl_relevance_score   (0-1, how strongly this is an SDL paper)
  - four evidence signals stored on PaperClassification
  - review_priority       (0-1, for the human review queue)
  - needs_review flag

Label decision matrix
---------------------
ac_attribution  sdl_relevance  label
high (≥0.7)     any            CORE_RELEVANT
medium (≥0.4)   high (≥0.6)   CORE_RELEVANT
medium (≥0.4)   medium (≥0.3)  RELATED_RELEVANT
low             high (≥0.6)   SDL_FIELD_RELEVANT
low             medium (≥0.3)  ADJACENT
low             low            UNCERTAIN / EXCLUDE

Review priority ordering (descending)
--------------------------------------
1. High confidence + NOT in AC Publications  (missed attribution?)
2. AC Publications paper NOT found by Scopus retrieval (provenance=ac_gold)
3. High citation + UNCERTAIN
4. AC member matched but no funding/acknowledgement
5. Tier 2 with complete SDL architecture (all 3 components)
6. Duplicates / metadata conflicts
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.services.relevance_classifier import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_EXCLUDE,
    LABEL_RELATED,
    LABEL_SDL_FIELD,
    LABEL_UNCERTAIN,
)
from app.services.sdl_dimensions import infer_sdl_dimensions

if TYPE_CHECKING:
    from app.models import Paper, PaperClassification


# Funding text patterns that signal AC connection
_AC_FUND_RE = re.compile(
    r"acceleration\s+consortium|accelerating\s+consortium"
    r"|university\s+of\s+toronto"
    r"|cfref|canada\s+first\s+research\s+excellence"
    r"|nserc.{0,40}acceleration"
    r"|cfi.{0,40}acceleration",
    re.IGNORECASE,
)

# Funding patterns that signal general SDL/materials research funding
_SDL_FUND_RE = re.compile(
    r"doe|department\s+of\s+energy|nsf|national\s+science\s+foundation"
    r"|dfg|epsrc|nserc|anr|erc\b",
    re.IGNORECASE,
)


@dataclass
class ScopusClassifyResult:
    paper_id: str
    label: str
    confidence: float
    ac_attribution_score: float
    sdl_relevance_score: float
    funding_signal: float
    acknowledgement_signal: float
    retrieval_signal: float
    architecture_signal: float
    needs_review: bool
    review_priority: float
    classification_dimensions: dict[str, str] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    model_version: str = "scopus-rules-v1.0"


def classify_paper(paper: "Paper") -> ScopusClassifyResult:
    """Classify a single paper using rule-based signals from Scopus + AC gold fields."""
    reasons: list[str] = []

    # ── 1. Acknowledgement signal ────────────────────────────────────────
    ack_signal = 0.0
    if paper.ac_acknowledged:
        ack_signal = 1.0
        reasons.append("Explicitly acknowledges AC")
    elif paper.ac_known_publication and paper.provenance == "ac_gold":
        ack_signal = 0.7
        reasons.append("In AC Publications gold set")

    # ── 2. Funding signal ────────────────────────────────────────────────
    fund_signal = 0.0
    if paper.ac_programs:
        fund_signal = 1.0
        reasons.append(f"AC funded program: {paper.ac_programs}")
    elif paper.funding_text and _AC_FUND_RE.search(paper.funding_text):
        fund_signal = 0.85
        reasons.append("AC/UofT mention in funding text")
    elif paper.funding_text and _SDL_FUND_RE.search(paper.funding_text):
        fund_signal = 0.2
        reasons.append("General research funding (non-AC)")

    # ── 3. Retrieval signal ───────────────────────────────────────────────
    tier = paper.retrieval_tier or ""
    if "1" in tier and "2" in tier:
        ret_signal = 1.0
        reasons.append("Found by both Tier-1 (label) and Tier-2 (architecture) queries")
    elif tier == "1":
        ret_signal = 0.8
        reasons.append("Found by Tier-1 SDL label query")
    elif tier == "2":
        ret_signal = 0.5
        reasons.append("Found by Tier-2 architecture query")
    elif paper.provenance == "ac_gold":
        ret_signal = 0.3
        reasons.append("Not retrieved by Scopus; sourced from AC Publications directly")
    else:
        ret_signal = 0.0

    # ── 4. Architecture signal ────────────────────────────────────────────
    ai_s = paper.ai_decision_score or 0.0
    auto_s = paper.automation_score or 0.0
    loop_s = paper.closed_loop_score or 0.0
    component_count = int(ai_s > 0) + int(auto_s > 0) + int(loop_s > 0)
    arch_signal = component_count / 3.0

    if component_count == 3:
        reasons.append("Complete SDL architecture: AI + automation + closed-loop")
    elif component_count == 2:
        reasons.append(f"Partial SDL architecture: {component_count}/3 components")
    elif component_count == 1:
        reasons.append("Weak SDL architecture match: 1/3 components")

    # ── 5. Author / AC member signal (from ac_members_matched) ───────────
    has_ac_member = bool(paper.ac_members_matched)
    if has_ac_member:
        reasons.append(f"AC member(s) in authors: {', '.join(paper.ac_members_matched)}")

    # ── 6. SDL tag signal (keywords are explicit author-assigned terms) ───
    # Combine sdl_tags (from AC gold) with paper.keywords (Author_Keywords from Scopus)
    # and paper.indexed_keywords (Scopus-assigned terms).
    all_keywords = list(paper.sdl_tags or []) + list(paper.keywords or []) + list(paper.indexed_keywords or [])
    has_sdl_tag = bool(paper.sdl_tags)
    has_sdl_keyword = any(
        any(t in kw.lower() for t in ("self-driving", "autonomous lab", "autonomous discovery",
                                      "materials acceleration", "closed-loop optimization",
                                      "high-throughput experimentation", "bayesian optim"))
        for kw in all_keywords
    )
    if has_sdl_tag:
        reasons.append(f"SDL tags: {', '.join(paper.sdl_tags)}")
    if has_sdl_keyword and not has_sdl_tag:
        reasons.append("SDL terminology in author/indexed keywords")

    # ── 7. Highly relevant flag ───────────────────────────────────────────
    if paper.ac_highly_relevant:
        reasons.append("Marked Highly Relevant in AC Publications")

    # ── 8. Fulltext evidence (post-PDF-ingest boost) ──────────────────────
    fulltext_ack_boost = 0.0
    fulltext_fund_boost = 0.0
    if paper.full_text_available and paper.classification is not None:
        ft_score = getattr(paper.classification, "fulltext_evidence_score", 0.0) or 0.0
        if ft_score >= 0.3:
            # Acknowledgements section explicitly mentions AC → strong AC signal
            fulltext_ack_boost = min(ft_score, 0.8)
            reasons.append(f"Fulltext evidence score: {ft_score:.2f} (acknowledgements/methods)")
        elif ft_score > 0:
            fulltext_fund_boost = ft_score * 0.5
            reasons.append(f"Weak fulltext evidence: {ft_score:.2f}")

    # ── Compute composite scores ──────────────────────────────────────────
    # ac_attribution: fulltext evidence can override weak metadata signals
    ack_signal_eff = min(ack_signal + fulltext_ack_boost, 1.0)
    fund_signal_eff = min(fund_signal + fulltext_fund_boost, 1.0)

    ac_score = (
        0.35 * ack_signal_eff
        + 0.30 * fund_signal_eff
        + 0.20 * (1.0 if has_ac_member else 0.0)
        + 0.10 * (1.0 if paper.ac_highly_relevant else 0.0)
        + 0.05 * ret_signal
    )
    ac_score = min(ac_score, 1.0)

    # sdl_relevance: architecture + retrieval + SDL keyword signals
    sdl_kw_signal = 1.0 if (has_sdl_tag or has_sdl_keyword) else 0.0
    sdl_score = (
        0.45 * arch_signal
        + 0.30 * ret_signal
        + 0.25 * sdl_kw_signal
    )
    sdl_score = min(sdl_score, 1.0)

    # ── Label decision ────────────────────────────────────────────────────
    label, confidence = _decide_label(ac_score, sdl_score, paper)

    # ── Review priority ───────────────────────────────────────────────────
    priority, needs_review = _compute_priority(paper, label, ac_score, sdl_score)

    return ScopusClassifyResult(
        paper_id=paper.id,
        label=label,
        confidence=confidence,
        ac_attribution_score=round(ac_score, 4),
        sdl_relevance_score=round(sdl_score, 4),
        funding_signal=round(fund_signal, 4),
        acknowledgement_signal=round(ack_signal, 4),
        retrieval_signal=round(ret_signal, 4),
        architecture_signal=round(arch_signal, 4),
        needs_review=needs_review,
        review_priority=round(priority, 4),
        classification_dimensions=infer_sdl_dimensions(paper, topic_score=sdl_score),
        reasons=reasons,
    )


def _decide_label(
    ac: float, sdl: float, paper: "Paper"
) -> tuple[str, float]:
    # AC Publications is the positive gold set. A paper stamped from that
    # source must never fall below RELATED because weak metadata extraction
    # (missing abstract, missing SDL tags, name variants) is not negative
    # evidence against the curated AC label.
    if paper.ac_known_publication:
        if (
            paper.ac_highly_relevant
            or paper.ac_acknowledged
            or paper.ac_programs
            or sdl >= 0.6
        ):
            return LABEL_CORE, max(0.85, min(0.95, 0.6 + max(ac, sdl) * 0.4))
        return LABEL_RELATED, max(0.72, min(0.9, 0.55 + max(ac, sdl) * 0.4))

    # In the Scopus batch path, the AC Publications file is the positive
    # label source. Non-gold papers with AC-like metadata are candidates for
    # review/discovery, but they should not count as AC-positive labels until
    # curated into the gold set.
    if sdl >= 0.6:
        return LABEL_SDL_FIELD, min(0.85, 0.4 + sdl * 0.6)
    if sdl >= 0.4:
        return LABEL_SDL_FIELD, 0.65
    if sdl >= 0.2 or ac >= 0.1:
        return LABEL_ADJACENT, 0.55
    if paper.retrieval_tier:
        return LABEL_UNCERTAIN, 0.40

    return LABEL_EXCLUDE, 0.80


def _sdl_label(score: float) -> str:
    if score >= 0.6:
        return "SDL_RELEVANT"
    if score >= 0.3:
        return "SDL_ADJACENT"
    return "SDL_NOT_RELEVANT"


def _ac_label(score: float) -> str:
    if score >= 0.7:
        return "CORE_AC"
    if score >= 0.4:
        return "AC_RELATED"
    if score >= 0.2:
        return "WEAK_AC_SIGNAL"
    return "NO_AC_EVIDENCE"


def _agreement_status(label: str, ac_score: float, sdl_score: float) -> str:
    if label == LABEL_SDL_FIELD and sdl_score >= 0.6 and ac_score < 0.2:
        return "sdl_yes_ac_no"
    if label in (LABEL_CORE, LABEL_RELATED) and ac_score < 0.3:
        return "needs_ac_evidence_review"
    return "single_model"


def _evidence_summary(result: ScopusClassifyResult) -> list[dict]:
    return [
        {"type": "funding", "score": result.funding_signal},
        {"type": "acknowledgement", "score": result.acknowledgement_signal},
        {"type": "retrieval", "score": result.retrieval_signal},
        {"type": "architecture", "score": result.architecture_signal},
        {"type": "classification_dimensions", "dimensions": result.classification_dimensions},
    ]


def _compute_priority(
    paper: "Paper", label: str, ac: float, sdl: float
) -> tuple[float, bool]:
    """Return (review_priority 0-1, needs_review bool).

    Priority tiers (higher = surface sooner):
    1. High-confidence tier but NOT in AC Publications  → may be missed attribution
    2. AC gold paper not retrieved by Scopus            → retrieval gap
    3. High citation + UNCERTAIN                        → high-value uncertain
    4. AC member matched but no funding/ack             → weak evidence, needs check
    5. Tier-2 with full SDL architecture                → strong SDL, classify carefully
    """
    priority = 0.0
    needs_review = False

    # Tier 1: high-confidence SDL/AC-like metadata but not already known to AC.
    if not paper.ac_known_publication and (
        (label == LABEL_SDL_FIELD and sdl >= 0.5) or ac >= 0.2
    ):
        priority = max(priority, 0.85)
        needs_review = True

    # Tier 2: AC gold paper missing from Scopus retrieval
    if paper.provenance == "ac_gold":
        priority = max(priority, 0.80)
        needs_review = True

    # Tier 3: uncertain + well-cited
    if label == LABEL_UNCERTAIN:
        needs_review = True
        priority = max(priority, 0.60)

    # Tier 4: AC member but no funding/ack
    if paper.ac_members_matched and not paper.ac_acknowledged and not paper.ac_programs:
        priority = max(priority, 0.65)
        needs_review = True

    # Tier 5: complete SDL architecture
    ai = paper.ai_decision_score or 0.0
    auto = paper.automation_score or 0.0
    loop = paper.closed_loop_score or 0.0
    if ai == 1 and auto == 1 and loop == 1 and label not in (LABEL_CORE, LABEL_RELATED):
        priority = max(priority, 0.55)
        needs_review = True

    return priority, needs_review


# ---------------------------------------------------------------------------
# batch entry point
# ---------------------------------------------------------------------------

def _stable_cls_id(paper_id: str) -> str:
    seed = f"cls|{paper_id}"
    return f"cls_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:12]}"


def run_scopus_classification(
    session: Session,
    batch_size: int = 500,
    overwrite_human_confirmed: bool = False,
) -> dict[str, int]:
    """Classify all papers with provenance in ('scopus_batch', 'ac_gold').

    Skips papers that already have human_confirmed=True (unless overwrite=True).
    Returns a stats dict.
    """
    from app.models import Paper, PaperClassification  # avoid circular at import

    provenance_filter = ["scopus_batch", "ac_gold"]
    query = select(Paper).where(Paper.provenance.in_(provenance_filter))

    stats = {"classified": 0, "skipped_confirmed": 0, "errors": 0}
    offset = 0

    while True:
        papers = session.execute(query.offset(offset).limit(batch_size)).scalars().all()
        if not papers:
            break
        offset += batch_size

        for paper in papers:
            # Skip human-confirmed unless explicitly overwriting
            if (
                paper.classification is not None
                and paper.classification.human_confirmed
                and not overwrite_human_confirmed
            ):
                stats["skipped_confirmed"] += 1
                continue

            try:
                result = classify_paper(paper)
            except Exception:
                stats["errors"] += 1
                continue

            # Write attribution scores back to Paper
            paper.ac_attribution_score = result.ac_attribution_score
            paper.sdl_relevance_score = result.sdl_relevance_score

            # Upsert classification row
            cls = paper.classification
            if cls is None:
                cls = PaperClassification(
                    id=_stable_cls_id(paper.id),
                    paper_id=paper.id,
                )
                session.add(cls)

            cls.label = result.label
            cls.confidence = result.confidence
            cls.funding_signal = result.funding_signal
            cls.acknowledgement_signal = result.acknowledgement_signal
            cls.retrieval_signal = result.retrieval_signal
            cls.architecture_signal = result.architecture_signal
            cls.sdl_relevance_label = _sdl_label(result.sdl_relevance_score)
            cls.ac_attribution_label = _ac_label(result.ac_attribution_score)
            cls.model_agreement_status = _agreement_status(
                result.label,
                result.ac_attribution_score,
                result.sdl_relevance_score,
            )
            cls.evidence_summary = _evidence_summary(result)
            cls.needs_review = result.needs_review
            cls.review_priority = result.review_priority
            cls.reasons = result.reasons
            cls.model_version = result.model_version
            cls.last_classified_at = datetime.now(UTC)

            stats["classified"] += 1

        session.flush()

    session.commit()
    return stats
