"""Combine matchers → label + confidence + structured reasons.

Pipeline per paper (v0.7):
  1. Authors → AuthorMatcher (context-aware) → author_score, matched_people
  2. Affiliations → InstitutionMatcher → institution_score
  3. Title + abstract + keywords → TopicClassifier (boundary-aware + density)
  4. Network (second-degree + citation) → graph_signals
  5. Fulltext evidence (with negation + funding context)
  6. _apply_rules → label + confidence
     6a. Borderline (UNCERTAIN band) → cross-encoder rerank
     6b. Still uncertain → LLM judge (optional, via llm_judge module)
  7. Optional: learned classifier post-hoc override
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.classification_labels import (
    LABEL_ADJACENT,
    LABEL_CORE,
    LABEL_EXCLUDE,
    LABEL_RELATED,
    LABEL_SDL_FIELD as LABEL_SDL_FIELD,
    LABEL_UNCERTAIN,
)
from app.config import settings
from app.models import Author, Institution, Paper, PaperAuthor, PaperClassification, PaperEntity, PaperEvidence, Topic
from app.services.author_matcher import AuthorMatch, AuthorMatcher
from app.services.attribution_evidence_scoring import (
    SCORING_VERSION,
    AttributionEvidenceSignals,
    has_ac_funding_in_text,
    score_attribution_evidence,
)
from app.services.normalization_service import normalize_name
from app.services.evidence_extractor import _aggregate_score
from app.services.graph_service import GraphSignals, compute_graph_signals
from app.services.institution_matcher import InstitutionMatch, InstitutionMatcher
from app.services.sdl_dimensions import (
    infer_sdl_dimensions,
    merge_dimensions_into_evidence_summary,
)
from app.services.topic_classifier import ClassifyResult, TopicClassifier, TopicMatch

@dataclass
class FulltextEvidenceSnapshot:
    evidence_type: str
    evidence_source: str
    evidence_text: str
    score: float
    chunk_id: str | None


@dataclass
class ClassificationResult:
    label: str
    confidence: float
    author_score: float
    institution_score: float
    topic_score: float
    network_score: float
    fulltext_evidence_score: float
    citation_score: float
    matched_people: list[AuthorMatch]
    matched_institutions: list[InstitutionMatch]
    matched_topics: list[TopicMatch]
    fulltext_evidence: list[FulltextEvidenceSnapshot] = field(default_factory=list)
    entity_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    graph_signals: GraphSignals | None = None
    # v0.7 fields
    topic_density: int = 0
    negated_topic_hits: int = 0
    disqualifying_count: int = 0
    rerank_applied: bool = False
    judge_applied: bool = False
    learned_label: str | None = None
    learned_confidence: float | None = None
    learned_model_version: str | None = None
    attribution_evidence: AttributionEvidenceSignals | None = None
    aet_applied: bool = False


# ---------------------------------------------------------------------------
# Per-paper classification
# ---------------------------------------------------------------------------

def _classify_paper(
    paper: Paper,
    author_matcher: AuthorMatcher,
    institution_matcher: InstitutionMatcher,
    topic_classifier: TopicClassifier,
    evidence_index: dict[str, list[PaperEvidence]] | None = None,
    graph_signals: GraphSignals | None = None,
    entity_index: dict[str, list[PaperEntity]] | None = None,
    use_attribution_evidence: bool = False,
) -> ClassificationResult:
    # ---- Authors with contextual disambiguation -----------------------
    raw_author_names = [
        pa.author.canonical_name for pa in paper.authors if pa.author
    ]
    raw_affiliations = [
        pa.affiliation_text for pa in paper.authors if pa.affiliation_text
    ]

    matched_people: list[AuthorMatch] = []
    seen_people: set[str] = set()
    for raw_name in raw_author_names:
        match = author_matcher.match(
            raw_name,
            coauthor_names=raw_author_names,
            affiliations=raw_affiliations,
        )
        if match and match.person_id not in seen_people:
            matched_people.append(match)
            seen_people.add(match.person_id)

    author_score = max(
        (m.score for m in matched_people if m.is_ac_member), default=0.0
    )

    # ── AC-publication gold-set boost ─────────────────────────────────────
    # paper.ac_members_matched is written by the ingestion pipeline directly
    # from the AC Publications CSV — it is more authoritative than the live
    # fuzzy name-matcher because it bypasses normalization/threshold issues.
    # When the matcher missed an AC author (alias, non-canonical formatting,
    # Scopus name variant), this fills the gap and guarantees the paper
    # receives at least RELATED_RELEVANT.
    already_matched = {normalize_name(m.name) for m in matched_people if m.is_ac_member}
    for raw_name in (paper.ac_members_matched or []):
        raw_name = str(raw_name).strip()
        if not raw_name:
            continue
        norm = normalize_name(raw_name)
        if norm in already_matched:
            continue
        already_matched.add(norm)
        matched_people.append(
            AuthorMatch(
                person_id=f"acpub:{norm}",
                name=raw_name,
                institution=None,
                match_type="ac_publication_confirmed",
                score=0.95,
                is_ac_member=True,
                corroborating_signals=["ac_publication_database"],
            )
        )
    # Recompute after any synthetic additions so the rule tree sees the real score.
    author_score = max(
        (m.score for m in matched_people if m.is_ac_member), default=0.0
    )

    # ---- Institutions -------------------------------------------------
    matched_institutions: list[InstitutionMatch] = []
    seen_institutions: set[str] = set()
    for aff in raw_affiliations:
        match = institution_matcher.match(aff)
        if match and match.institution_id not in seen_institutions:
            matched_institutions.append(match)
            seen_institutions.add(match.institution_id)

    institution_score = max(
        (m.score for m in matched_institutions if m.is_partner), default=0.0
    )

    # ---- Topics with density ------------------------------------------
    keyword_text = " ".join(paper.keywords or []) if paper.keywords else ""
    topic_result: ClassifyResult = topic_classifier.classify_detailed(
        paper.title, paper.abstract, keyword_text
    )
    topic_score = topic_result.combined_score
    matched_topics = topic_result.matches
    topic_density = topic_result.topic_density

    # ---- Graph signals ------------------------------------------------
    if graph_signals is not None:
        network_score = graph_signals.network_score
        citation_score = graph_signals.citation_score
        has_second_degree = bool(graph_signals.second_degree_paths)
        cites_ac_core = bool(graph_signals.citation_signals)
    else:
        network_score = 0.0
        citation_score = 0.0
        has_second_degree = False
        cites_ac_core = False

    # ---- Full-text evidence ------------------------------------------
    fulltext_records: list[PaperEvidence] = (
        (evidence_index or {}).get(paper.id, []) if evidence_index else []
    )
    fulltext_score = _aggregate_score_from_rows(fulltext_records)
    fulltext_snapshots = [
        FulltextEvidenceSnapshot(
            evidence_type=row.evidence_type,
            evidence_source=row.evidence_source,
            evidence_text=row.evidence_text,
            score=row.score,
            chunk_id=row.chunk_id,
        )
        for row in fulltext_records
    ]
    disqualifying_count = sum(
        1 for r in fulltext_records if r.evidence_type == "disqualifying"
    )

    # Full-text funding evidence (from PDF extraction)
    has_funding_evidence = any(
        r.evidence_type == "funding_acknowledgement" and r.score > 0
        for r in fulltext_records
    )

    # ── Metadata-based AC funding signal ─────────────────────────────────
    # Use Scopus metadata funding fields when no full-text is available.
    # ac_acknowledged is set by ingest; also scan funding_text directly.
    if not has_funding_evidence:
        has_funding_evidence = bool(paper.ac_acknowledged) or has_ac_funding_in_text(
            paper.funding_text, paper.ac_programs
        )

    # ---- Typed SDL entities (cross-SDL extraction) ---------------------
    entity_rows: list[PaperEntity] = (entity_index or {}).get(paper.id, [])
    entity_score, entity_summary = _entity_signal(entity_rows)

    # ---- Apply rules --------------------------------------------------
    has_core_topic_match = any(
        match.is_core and match.score > 0 for match in matched_topics
    )
    label, confidence = _apply_rules(
        author_score=author_score,
        institution_score=institution_score,
        topic_score=topic_score,
        fulltext_score=fulltext_score,
        network_score=network_score,
        citation_score=citation_score,
        has_funding_evidence=has_funding_evidence,
        has_second_degree=has_second_degree,
        cites_ac_core=cites_ac_core,
        topic_density=topic_density,
        disqualifying_count=disqualifying_count,
        has_core_topic_match=has_core_topic_match,
        ac_known_publication=bool(paper.ac_known_publication),
        entity_score=entity_score,
    )
    attribution_evidence: AttributionEvidenceSignals | None = None
    aet_reason: str | None = None
    if use_attribution_evidence:
        attribution_evidence = score_attribution_evidence(
            evidence_rows=fulltext_records,
            author_score=author_score,
            institution_score=institution_score,
            topic_score=topic_score,
            network_score=network_score,
            citation_score=citation_score,
            has_funding_evidence=has_funding_evidence,
            has_second_degree=has_second_degree,
            cites_ac_core=cites_ac_core,
            has_core_topic_match=has_core_topic_match,
        )
        label, confidence, aet_reason = _apply_attribution_evidence_decision(
            label, confidence, attribution_evidence
        )

    reasons = _build_reasons(
        label=label,
        matched_people=matched_people,
        matched_institutions=matched_institutions,
        matched_topics=matched_topics,
        fulltext_records=fulltext_records,
        graph_signals=graph_signals,
        topic_density=topic_density,
        disqualifying_count=disqualifying_count,
        entity_summary=entity_summary,
    )
    if aet_reason and attribution_evidence:
        reasons.append(
            f"{aet_reason}: score={attribution_evidence.score:.2f}; "
            f"positive_paths={','.join(attribution_evidence.positive_path_ids) or 'none'}; "
            f"negative_paths={','.join(attribution_evidence.negative_path_ids) or 'none'}."
        )

    return ClassificationResult(
        label=label,
        confidence=confidence,
        author_score=round(author_score, 3),
        institution_score=round(institution_score, 3),
        topic_score=round(topic_score, 3),
        network_score=round(network_score, 3),
        fulltext_evidence_score=round(fulltext_score, 3),
        citation_score=round(citation_score, 3),
        entity_score=round(entity_score, 3),
        matched_people=matched_people,
        matched_institutions=matched_institutions,
        matched_topics=matched_topics,
        fulltext_evidence=fulltext_snapshots,
        reasons=reasons,
        graph_signals=graph_signals,
        topic_density=topic_density,
        negated_topic_hits=topic_result.negated_hit_count,
        disqualifying_count=disqualifying_count,
        attribution_evidence=attribution_evidence,
        aet_applied=use_attribution_evidence,
    )


def _entity_signal(rows: list[PaperEntity]) -> tuple[float, dict[str, list[str]]]:
    """Score typed-entity evidence (PaperEntity rows from entity extraction).

    Simple monotone formula over *distinct* normalized names:
      score = min(1.0, 0.25 * n_methods
                       + 0.20 * n_instruments_or_software
                       + 0.10 * n_materials)
    Methods (e.g. bayesian optimization) are most diagnostic of SDL work,
    instruments/software less so, materials least. Zero rows → (0.0, {}).
    """
    methods = sorted({r.normalized_name for r in rows if r.entity_type == "method"})
    tools = sorted(
        {r.normalized_name for r in rows if r.entity_type in ("instrument", "software")}
    )
    materials = sorted({r.normalized_name for r in rows if r.entity_type == "material"})
    score = min(1.0, 0.25 * len(methods) + 0.20 * len(tools) + 0.10 * len(materials))
    summary: dict[str, list[str]] = {}
    if methods:
        summary["method"] = methods
    if tools:
        summary["instrument_or_software"] = tools
    if materials:
        summary["material"] = materials
    return round(score, 3), summary


def _aggregate_score_from_rows(rows: list[PaperEvidence]) -> float:
    """Re-use the extractor's cap-and-sum so persisted rows score consistently."""
    from app.services.evidence_extractor import EvidenceRecord

    records = [
        EvidenceRecord(
            evidence_type=r.evidence_type,
            evidence_source=r.evidence_source,
            evidence_text=r.evidence_text,
            score=r.score,
            chunk_id=r.chunk_id,
        )
        for r in rows
    ]
    return _aggregate_score(records)


def _apply_attribution_evidence_decision(
    label: str,
    confidence: float,
    signals: AttributionEvidenceSignals,
) -> tuple[str, float, str | None]:
    """Apply conservative, auditable label changes from independent AET paths."""
    if signals.negative_score >= 0.25:
        if signals.has_strong_ac_evidence:
            return label, min(confidence, 0.75), "AET_CONFLICTING_EVIDENCE"
        if label in {LABEL_CORE, LABEL_RELATED}:
            return LABEL_ADJACENT, min(confidence, 0.6), "AET_STRONG_NEGATIVE"
        if label in {LABEL_ADJACENT, LABEL_UNCERTAIN}:
            return LABEL_EXCLUDE, min(confidence, 0.4), "AET_STRONG_NEGATIVE"

    if (
        label != LABEL_CORE
        and signals.score >= 0.5
        and signals.has_core_topic
        and signals.has_partner_affiliation
        and signals.has_collaboration
    ):
        return LABEL_CORE, max(confidence, 0.85), "AET_CORROBORATED_CORE"

    if (
        label in {LABEL_EXCLUDE, LABEL_UNCERTAIN}
        and signals.has_partner_affiliation
        and signals.has_collaboration
        and not signals.has_core_topic
        and not signals.has_sdl_method
    ):
        return LABEL_ADJACENT, max(confidence, 0.55), "AET_COLLABORATION_ONLY"

    return label, confidence, None


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


def _apply_rules(
    author_score: float,
    institution_score: float,
    topic_score: float,
    fulltext_score: float = 0.0,
    network_score: float = 0.0,
    citation_score: float = 0.0,
    has_funding_evidence: bool = False,
    has_second_degree: bool = False,
    cites_ac_core: bool = False,
    topic_density: int | None = None,
    disqualifying_count: int = 0,
    has_core_topic_match: bool | None = None,
    ac_known_publication: bool = False,
    entity_score: float = 0.0,
) -> tuple[str, float]:
    """Tightened decision tree (v0.7).

    Key change vs v0.3: CORE requires necessary conditions, not just any
    strong signal. The matrix below is conservative on purpose — borderline
    cases are pushed to UNCERTAIN and the cross-encoder / LLM judge resolves
    them downstream.

    v0.8 addition: Tier-0 hard overrides for AC-known publications.
    ac_known_publication=True means the paper is in the AC Publications gold
    set. That guarantees >= RELATED regardless of signal scores.
    """
    # Sensible inference for callers that don't pass v0.7-specific signals.
    if has_core_topic_match is None:
        has_core_topic_match = topic_score >= 0.5
    if topic_density is None:
        topic_density = 1 if topic_score >= 0.7 else 0

    has_fulltext = fulltext_score > 0
    has_graph = network_score > 0 or citation_score > 0

    if has_fulltext:
        base = (
            settings.author_weight_fulltext * author_score
            + settings.institution_weight_fulltext * institution_score
            + settings.topic_weight_fulltext * topic_score
            + settings.fulltext_evidence_weight * fulltext_score
        )
    else:
        base = (
            settings.author_weight * author_score
            + settings.institution_weight * institution_score
            + settings.topic_weight * topic_score
        )
    if has_graph:
        base += (
            settings.network_weight_v3 * network_score
            + settings.citation_weight * citation_score
        )
    if entity_score > 0:
        # Typed-entity evidence is additive-only: a small confidence nudge for
        # borderline papers, never enough to change a label tier by itself
        # (entity_weight = 0.05 → at most +0.05 on the blend).
        base += settings.entity_weight * entity_score

    # Disqualifying evidence subtracts from the blend.
    if disqualifying_count > 0:
        base = max(0.0, base - 0.15 * disqualifying_count)

    confidence = round(base, 3)

    # ── Tier-0: AC Publications gold-set guarantee ────────────────────────
    # Papers in the AC Publications gold set MUST be >= RELATED_RELEVANT.
    # This fires only when the signal-based path would produce a lower label
    # (i.e. when ac_members_matched was populated but the name matcher failed).
    # The synthetic author_score=0.95 injected in _classify_paper() usually
    # makes the Tier-1 rules fire first; this is a belt-and-suspenders backup.
    if ac_known_publication:
        # Promote to CORE if there's any SDL topic evidence; otherwise RELATED.
        if has_core_topic_match and (topic_score >= 0.3 or fulltext_score >= 0.3 or topic_density >= 1):
            return LABEL_CORE, max(confidence, 0.85)
        return LABEL_RELATED, max(confidence, 0.72)

    # ---------------- CORE: requires conjunctive conditions ----------------
    # An AC author *and* a core topic match (or fulltext evidence proving SDL).
    if (
        author_score >= 0.9
        and has_core_topic_match
        and (topic_score >= 0.5 or fulltext_score >= 0.5)
    ):
        return LABEL_CORE, max(confidence, 0.85)
    # Explicit funding acknowledgement + topic alignment ⇒ CORE.
    if has_funding_evidence and has_core_topic_match and topic_score >= 0.45:
        return LABEL_CORE, max(confidence, 0.85)
    # Strong author + topic_density (paper *is* about SDL) ⇒ CORE.
    if author_score >= 0.9 and topic_density >= 2:
        return LABEL_CORE, max(confidence, 0.82)

    # ---------------- RELATED: needs author OR (funding + topic) OR
    # (strong topic + partner inst + density) ----------------
    if author_score >= 0.9:
        # AC author but no core topic hit — RELATED (e.g. method paper from
        # AC author on a non-SDL topic).
        return LABEL_RELATED, max(confidence, 0.7)
    if has_funding_evidence:
        # AC funding evidence already passed the funding-context check in the
        # evidence extractor (`_has_funding_context`) — i.e. the AC mention
        # appears in a "funded by / supported by / acknowledge" window, not a
        # casual reference. That alone is sufficient for RELATED.
        return LABEL_RELATED, max(
            confidence, settings.funding_evidence_floor_score + 0.2
        )
    if topic_score >= 0.7 and institution_score >= 0.5 and topic_density >= 1:
        return LABEL_RELATED, max(confidence, 0.68)
    if cites_ac_core and topic_score >= 0.4:
        return LABEL_RELATED, max(confidence, 0.65)

    # ---------------- ADJACENT: weaker but real signals ----------------
    if topic_score >= 0.7 or fulltext_score >= 0.5:
        return LABEL_ADJACENT, max(confidence, 0.55)
    if has_second_degree and topic_score >= 0.15:
        return LABEL_ADJACENT, max(confidence, settings.second_degree_floor_score)
    # Typed-entity evidence alone (≥2 SDL method terms, or method + tool mix)
    # caps at ADJACENT — mirrors the topic-only rule above. It can never reach
    # RELATED/CORE without an author / funding / institution signal.
    if entity_score >= 0.5:
        return LABEL_ADJACENT, max(confidence, 0.5)

    # ---------------- UNCERTAIN: send to rerank / human ----------------
    # Disqualifying evidence pulls the floor down so the override is visible
    # even in the UNCERTAIN band.
    uncertain_floor = max(0.2, 0.5 - 0.15 * disqualifying_count)
    if cites_ac_core:
        return LABEL_UNCERTAIN, max(confidence, uncertain_floor)
    max_score = max(
        author_score, institution_score, topic_score, fulltext_score, network_score
    )
    if 0.4 <= max_score < 0.7:
        floor = max(0.2, 0.45 - 0.15 * disqualifying_count)
        return LABEL_UNCERTAIN, max(confidence, floor)

    return LABEL_EXCLUDE, confidence


# ---------------------------------------------------------------------------
# Borderline rerank using the cross-encoder
# ---------------------------------------------------------------------------


_AC_MISSION_QUERY = (
    "Acceleration Consortium mission: self-driving laboratories, "
    "autonomous chemistry, closed-loop Bayesian optimization, "
    "AC-funded materials discovery, AC member co-authorship"
)


# Module-level hook so tests can monkey-patch
# `app.services.relevance_classifier.get_reranker`.
def get_reranker():
    """Indirection over reranker.get_reranker so it can be monkeypatched."""
    from app.services.reranker import get_reranker as _real_get_reranker

    return _real_get_reranker()


def _apply_rerank_to_borderline(
    papers: list[Paper], results: dict[str, ClassificationResult]
) -> None:
    """For papers in the UNCERTAIN/ADJACENT band, run a cross-encoder over
    (AC mission, paper text) and downgrade those with low similarity.

    No-op when PAS_RERANKER != "cross-encoder" — `get_reranker` will return
    the NullReranker. We re-use the existing reranker so the system has one
    place to swap models.
    """
    from app.services.reranker import NullReranker

    reranker = get_reranker()
    if isinstance(reranker, NullReranker):
        return

    # Build candidate list from borderline papers.
    from app.services.retrieval_service import RetrievedChunk

    candidates: list[RetrievedChunk] = []
    paper_ids: list[str] = []
    for p in papers:
        r = results.get(p.id)
        if r is None:
            continue
        if r.label in {LABEL_UNCERTAIN, LABEL_ADJACENT} or (
            r.label == LABEL_RELATED and r.confidence < 0.7
        ):
            candidates.append(
                RetrievedChunk(
                    chunk_id=p.id,
                    paper_id=p.id,
                    section_type="title_abstract",
                    section_title=None,
                    text=" ".join(filter(None, [p.title, p.abstract or ""])),
                    bm25_score=0.0,
                    cosine_score=0.0,
                    score=r.confidence,
                )
            )
            paper_ids.append(p.id)

    if not candidates:
        return

    try:
        scored = reranker.rerank(_AC_MISSION_QUERY, candidates)
    except Exception:
        # Reranker is best-effort; failures must not block classification.
        return

    score_by_paper = {c.paper_id: c.score for c in scored}
    for pid in paper_ids:
        rerank_score = score_by_paper.get(pid)
        r = results.get(pid)
        if r is None or rerank_score is None:
            continue
        r.rerank_applied = True
        # Cross-encoder gives unbounded logits typically in [-10, 10]. We
        # normalize to [0, 1] with a sigmoid for fusion.
        import math

        norm = 1.0 / (1.0 + math.exp(-rerank_score))
        if norm < 0.3 and r.label != LABEL_CORE:
            # Confidently irrelevant.
            r.label = LABEL_EXCLUDE
            r.confidence = round(min(r.confidence, 0.3), 3)
            r.reasons.append(
                f"Cross-encoder rerank against AC mission produced "
                f"low similarity ({norm:.2f}) — downgraded to EXCLUDE."
            )
        elif norm > 0.7 and r.label == LABEL_UNCERTAIN:
            r.label = LABEL_RELATED
            r.confidence = round(max(r.confidence, 0.6), 3)
            r.reasons.append(
                f"Cross-encoder rerank confirmed AC-relevance ({norm:.2f}); "
                f"promoted to RELATED."
            )


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------


def _build_reasons(
    *,
    label: str,
    matched_people: list[AuthorMatch],
    matched_institutions: list[InstitutionMatch],
    matched_topics: list[TopicMatch],
    fulltext_records: list[PaperEvidence] | None = None,
    graph_signals: GraphSignals | None = None,
    topic_density: int = 0,
    disqualifying_count: int = 0,
    entity_summary: dict[str, list[str]] | None = None,
) -> list[str]:
    reasons: list[str] = []
    for m in matched_people:
        if m.is_ac_member:
            reasons.append(
                f"Matched AC member {m.name} via {m.match_type} (score {m.score:.2f})."
            )
    partner_insts = [m for m in matched_institutions if m.is_partner]
    if partner_insts:
        names = ", ".join(m.canonical_name for m in partner_insts)
        reasons.append(f"Affiliation includes AC partner institution(s): {names}.")
    core_topics = [t for t in matched_topics if t.is_core and t.score > 0]
    if core_topics:
        top = core_topics[0]
        sample_hits = ", ".join(top.hits[:3])
        reasons.append(
            f"Topic match on {top.name} (score {top.score:.2f}; hits: {sample_hits})."
        )
    adjacent_topics = [t for t in matched_topics if not t.is_core and t.score > 0]
    if adjacent_topics and not core_topics:
        reasons.append(f"Only adjacent topic match: {adjacent_topics[0].name}.")

    # v0.7: report negation / blacklist suppression for transparency.
    blacklisted = [t for t in matched_topics if t.blacklist_hits]
    if blacklisted:
        first = blacklisted[0]
        reasons.append(
            f"Topic {first.name} suppressed by blacklist hit "
            f"({first.blacklist_hits[0]})."
        )
    negated = [t for t in matched_topics if t.negation_hits and not t.hits]
    if negated:
        first = negated[0]
        reasons.append(
            f"Topic {first.name} hits were all in negated context "
            f"(e.g. {first.negation_hits[0]})."
        )
    if topic_density >= 2:
        reasons.append(
            f"Topic density {topic_density}: ≥2 core keywords co-occur in "
            f"the same paragraph (paper is *about* the topic, not just "
            f"name-dropping)."
        )
    if disqualifying_count > 0:
        reasons.append(
            f"{disqualifying_count} disqualifying-evidence row(s) recorded "
            f"(LLM judge or active learning)."
        )

    # Typed-entity evidence (PaperEntity rows from entity extraction).
    for entity_type, noun in (
        ("method", "method"),
        ("instrument_or_software", "instrument/software"),
        ("material", "material"),
    ):
        names = (entity_summary or {}).get(entity_type, [])
        if names:
            reasons.append(
                f"Found {len(names)} SDL {noun} term(s): {', '.join(names[:3])}."
            )

    if graph_signals:
        for path in graph_signals.second_degree_paths[:2]:
            shared = ", ".join(path.shared_papers[:3])
            reasons.append(
                f"Second-degree collaboration: co-author {path.via_author_name} "
                f"previously worked with AC member {path.ac_author_name} on "
                f"paper(s) {shared}."
            )
        for sig in graph_signals.citation_signals[:2]:
            reasons.append(
                f"Cites AC core paper "
                f"\"{sig.cited_ac_core_title}\" (doi {sig.cited_doi or 'n/a'})."
            )

    if fulltext_records:
        funding = [
            r
            for r in fulltext_records
            if r.evidence_type == "funding_acknowledgement" and r.score > 0
        ]
        if funding:
            snippet = funding[0].evidence_text.strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:160] + "…"
            reasons.append(
                f"Funding acknowledgement evidence (chunk {funding[0].chunk_id}): "
                f"“{snippet}”"
            )
        method = [
            r for r in fulltext_records if r.evidence_type == "sdl_methodology"
        ]
        if method:
            reasons.append(
                f"Methods section names SDL methodology "
                f"(chunk {method[0].chunk_id})."
            )
        captions = [
            r for r in fulltext_records if r.evidence_type == "figure_caption_sdl"
        ]
        if captions:
            reasons.append(
                f"Figure caption uses SDL terminology (chunk {captions[0].chunk_id})."
            )

    if label == LABEL_EXCLUDE and not reasons:
        reasons.append(
            "No author, partner institution, or core topic signal detected."
        )
    if label == LABEL_UNCERTAIN:
        reasons.append("Mid-range signal — recommend human review.")
    return reasons


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def classify_all(
    session: Session,
    *,
    use_learned: bool | None = None,
    use_judge: bool | None = None,
    use_attribution_evidence: bool | None = None,
    judge=None,  # LLMJudge override (tests)
    embedder=None,  # Embedder override (tests)
) -> list[Paper]:
    """Re-classify the entire corpus.

    Args:
      use_learned: if True (or PAS_LEARNED_CLASSIFIER=1), load the trained
        model and use its prediction as a soft override.
      use_judge: if True (or PAS_LLM_JUDGE=1), invoke the LLM judge on the
        UNCERTAIN bucket.
      use_attribution_evidence: apply AET path scoring when explicitly enabled
        or when PAS_ATTRIBUTION_EVIDENCE_CLASSIFIER_ENABLED=1.
    """
    if use_attribution_evidence is None:
        use_attribution_evidence = (
            settings.attribution_evidence_classifier_enabled
        )
    authors = list(session.execute(select(Author)).scalars())
    institutions = list(session.execute(select(Institution)).scalars())
    topics = list(session.execute(select(Topic)).scalars())

    # v0.7: pass coauthor context to author_matcher.
    author_matcher = AuthorMatcher(authors)
    institution_matcher = InstitutionMatcher(institutions)
    # Optional embedder for hybrid topic scoring.
    if embedder is None and os.environ.get("PAS_HYBRID_TOPIC", "0") == "1":
        from app.services.embedding_service import get_embedder

        embedder = get_embedder()
    topic_classifier = TopicClassifier(topics, embedder=embedder)

    evidence_index: dict[str, list[PaperEvidence]] = {}
    for ev in session.execute(select(PaperEvidence)).scalars():
        evidence_index.setdefault(ev.paper_id, []).append(ev)

    entity_index: dict[str, list[PaperEntity]] = {}
    for ent in session.execute(select(PaperEntity)).scalars():
        entity_index.setdefault(ent.paper_id, []).append(ent)

    # Graph signals: try to compute but degrade gracefully if OOM or missing scipy.
    # Papers still get classified via author/institution/topic/funding signals.
    graph_signals_by_paper: dict = {}
    try:
        graph_signals_by_paper = compute_graph_signals(session)
    except Exception as exc:
        import sys
        print(f"[classify_all] graph signals skipped ({type(exc).__name__}: {exc})",
              file=sys.stderr)

    # --- Batch processing to avoid loading all 10K papers at once ---
    # Get all paper IDs first (lean), then process in batches of 300.
    # Each batch is committed independently so progress is saved even if a later
    # batch fails. Human-confirmed papers are never overwritten.
    _BATCH = 300
    all_paper_ids: list[str] = [
        r[0] for r in session.execute(
            select(Paper.id).where(
                ~Paper.id.in_(
                    select(PaperClassification.paper_id).where(
                        PaperClassification.human_confirmed.is_(True)
                    )
                )
            )
        ).all()
    ]

    papers: list[Paper] = []   # accumulate for rerank/judge below
    results: dict[str, ClassificationResult] = {}

    for batch_start in range(0, len(all_paper_ids), _BATCH):
        batch_ids = all_paper_ids[batch_start: batch_start + _BATCH]
        batch_papers = list(
            session.execute(
                select(Paper).options(
                    selectinload(Paper.authors)
                    .selectinload(PaperAuthor.author)
                    .selectinload(Author.institution)
                ).where(Paper.id.in_(batch_ids))
            ).scalars()
        )
        batch_results: dict[str, ClassificationResult] = {}
        for paper in batch_papers:
            result = _classify_paper(
                paper,
                author_matcher,
                institution_matcher,
                topic_classifier,
                evidence_index=evidence_index,
                graph_signals=graph_signals_by_paper.get(paper.id),
                entity_index=entity_index,
                use_attribution_evidence=use_attribution_evidence,
            )
            batch_results[paper.id] = result
            papers.append(paper)
            results[paper.id] = result

        # Persist this batch immediately so progress is not lost on OOM
        for paper in batch_papers:
            result = batch_results[paper.id]
            if paper.classification is None:
                paper.classification = PaperClassification(
                    id=f"cls_{uuid.uuid4().hex[:12]}", paper_id=paper.id
                )
                session.add(paper.classification)
            cls = paper.classification
            if not cls.human_confirmed:
                cls.label = result.label
                cls.confidence = result.confidence
            else:
                cls.confidence = max(cls.confidence, result.confidence)
            cls.author_score = result.author_score
            cls.institution_score = result.institution_score
            cls.topic_score = result.topic_score
            cls.network_score = result.network_score
            cls.fulltext_evidence_score = result.fulltext_evidence_score
            cls.citation_score = result.citation_score
            cls.graph_signals = (
                result.graph_signals.to_dict() if result.graph_signals else None
            )
            cls.sdl_relevance_label = _sdl_memory_label(result.topic_score, result.fulltext_evidence_score)
            cls.ac_attribution_label = _ac_memory_label(
                result.author_score, result.institution_score,
                result.network_score, result.citation_score,
            )
            cls.model_agreement_status = cls.model_agreement_status or "single_model"
            cls.evidence_summary = merge_dimensions_into_evidence_summary(
                cls.evidence_summary,
                infer_sdl_dimensions(paper, topic_score=result.topic_score),
            )
            cls.evidence_summary = _merge_attribution_evidence_summary(
                cls.evidence_summary, result.attribution_evidence
            )
            cls.model_version = _model_version_for(result)
            cls.matched_people = _serialize_matched_people(result.matched_people)
            cls.matched_institutions = _serialize_matched_institutions(result.matched_institutions)
            cls.matched_topics = [
                {"topic_id": m.topic_id, "name": m.name, "is_core": m.is_core,
                 "score": m.score, "hits": m.hits, "density": m.density,
                 "negation_hits": m.negation_hits, "blacklist_hits": m.blacklist_hits}
                for m in result.matched_topics
            ]
            cls.reasons = result.reasons
            cls.last_classified_at = datetime.now(UTC)
        session.commit()   # ← commit each batch; progress is durable

    # v0.7: cross-encoder rerank for borderline cases (operates on in-memory results).
    _apply_rerank_to_borderline(papers, results)

    # v0.7: LLM judge for what's still UNCERTAIN.
    if use_judge is None:
        use_judge = os.environ.get("PAS_LLM_JUDGE", "0") == "1"
    if use_judge or judge is not None:
        _apply_judge_to_uncertain(papers, results, judge=judge, session=session)

    # v0.7: learned classifier post-hoc soft override.
    if use_learned is None:
        use_learned = os.environ.get("PAS_LEARNED_CLASSIFIER", "1") == "1"
    if use_learned:
        _apply_learned_override(papers, results, session=session)

    # All papers already persisted per-batch above.
    # v0.4: refresh proposition table once all classifications are settled.
    try:
        from app.services.proposition_extractor import persist_propositions
        persist_propositions(session)
    except Exception as exc:
        import sys
        print(f"[classify_all] proposition extraction skipped ({exc})", file=sys.stderr)

    return papers


# ---------------------------------------------------------------------------
# Incremental: classify only papers that need it
# ---------------------------------------------------------------------------


CURRENT_MODEL_VERSION = "rules-v0.7"


def _configured_model_version(
    use_attribution_evidence: bool | None = None,
    use_learned: bool | None = None,
    session: Session | None = None,
) -> str:
    attribution_enabled = (
        settings.attribution_evidence_classifier_enabled
        if use_attribution_evidence is None
        else use_attribution_evidence
    )
    learned_enabled = (
        os.environ.get("PAS_LEARNED_CLASSIFIER", "1") == "1"
        if use_learned is None
        else use_learned
    )
    base = CURRENT_MODEL_VERSION
    if learned_enabled:
        from app.services.learned_classifier import load_default_model

        learned = load_default_model(session)
        if learned is not None:
            base = learned.model_version or "learned-v0.7"
    return f"{base}+{SCORING_VERSION}" if attribution_enabled else base


def _operational_model_version(version: str | None) -> str:
    parts = (version or "").split("+")
    return "+".join(part for part in parts if part not in {"judge", "rerank"})


def papers_needing_classification(
    session: Session, *, current_version: str | None = None
) -> list[Paper]:
    """Pick the papers that the daily pipeline should re-classify.

    Selection logic:
      * never classified yet, OR
      * classified by an older model_version, OR
      * paper.updated_at > classification.last_classified_at (when those
        timestamps exist).

    Human-confirmed papers are excluded — their label is locked and should
    only be touched via /reviews/{id}.
    """
    target_version = current_version or _configured_model_version(
        session=session
    )

    candidates: list[Paper] = []
    for paper in session.execute(select(Paper)).scalars():
        cls = paper.classification
        if cls is None:
            candidates.append(paper)
            continue
        if cls.human_confirmed:
            continue
        # Stale model_version, e.g. "rules-v0.1" needs an upgrade pass.
        if _operational_model_version(cls.model_version) != target_version:
            candidates.append(paper)
            continue
        # Paper edited since last classification (e.g. full text added).
        if paper.updated_at and cls.last_classified_at:
            upd = paper.updated_at
            last = cls.last_classified_at
            if upd.tzinfo is None:
                upd = upd.replace(tzinfo=UTC)
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            # Allow a tiny grace window so identical timestamps don't trigger
            # re-classification (SQLite resolves to microseconds).
            if (upd - last).total_seconds() > 1.0:
                candidates.append(paper)
                continue
    return candidates


def classify_new(
    session: Session,
    *,
    force: bool = False,
    use_learned: bool | None = None,
    use_judge: bool | None = None,
    use_attribution_evidence: bool | None = None,
    judge=None,
    embedder=None,
) -> tuple[list[Paper], int, int]:
    """Incremental classify — only run the pipeline on papers that need it.

    Returns (touched_papers, new_classifications, refreshed_stale).

    If `force=True`, behaves identically to `classify_all` (still skips
    human-confirmed labels).
    """
    if force:
        before_versions: dict[str, str | None] = {}
        for p in session.execute(select(Paper)).scalars():
            before_versions[p.id] = p.classification.model_version if p.classification else None
        papers = classify_all(
            session,
            use_learned=use_learned,
            use_judge=use_judge,
            use_attribution_evidence=use_attribution_evidence,
            judge=judge,
            embedder=embedder,
        )
        new = sum(1 for p in papers if before_versions.get(p.id) is None)
        refreshed = len(papers) - new
        return papers, new, refreshed

    target_version = _configured_model_version(
        use_attribution_evidence,
        use_learned,
        session,
    )
    needing = papers_needing_classification(
        session, current_version=target_version
    )
    if not needing:
        return [], 0, 0

    new_count = sum(1 for p in needing if p.classification is None)
    refreshed = len(needing) - new_count

    # Re-use the full classify_all flow but scoped to the subset. The simplest
    # way is to mark the rest as "skip via human_confirmed" temporarily, but
    # that's invasive. We instead directly call _classify_paper for the subset
    # while still loading the matchers + graph signals once.
    _classify_subset(
        session,
        needing,
        use_learned=use_learned,
        use_judge=use_judge,
        use_attribution_evidence=use_attribution_evidence,
        judge=judge,
        embedder=embedder,
    )
    return needing, new_count, refreshed


def _classify_subset(
    session: Session,
    papers: list[Paper],
    *,
    use_learned: bool | None,
    use_judge: bool | None,
    use_attribution_evidence: bool | None,
    judge,
    embedder,
) -> None:
    """Apply the full classification stack to a subset of papers in place."""
    if not papers:
        return
    if use_attribution_evidence is None:
        use_attribution_evidence = (
            settings.attribution_evidence_classifier_enabled
        )

    from app.services.author_matcher import AuthorMatcher
    from app.services.graph_service import compute_graph_signals
    from app.services.institution_matcher import InstitutionMatcher

    authors = list(session.execute(select(Author)).scalars())
    institutions = list(session.execute(select(Institution)).scalars())
    topics = list(session.execute(select(Topic)).scalars())

    if embedder is None and os.environ.get("PAS_HYBRID_TOPIC", "0") == "1":
        from app.services.embedding_service import get_embedder

        embedder = get_embedder()

    author_matcher = AuthorMatcher(authors)
    institution_matcher = InstitutionMatcher(institutions)
    topic_classifier = TopicClassifier(topics, embedder=embedder)

    target_ids = {p.id for p in papers}
    evidence_index: dict[str, list[PaperEvidence]] = {}
    for ev in session.execute(
        select(PaperEvidence).where(PaperEvidence.paper_id.in_(target_ids))
    ).scalars():
        evidence_index.setdefault(ev.paper_id, []).append(ev)

    entity_index: dict[str, list[PaperEntity]] = {}
    for ent in session.execute(
        select(PaperEntity).where(PaperEntity.paper_id.in_(target_ids))
    ).scalars():
        entity_index.setdefault(ent.paper_id, []).append(ent)

    # Graph signals depend on the whole corpus but the result map covers
    # all papers, so we can index into it for our subset.
    graph_signals = compute_graph_signals(session)

    results: dict[str, ClassificationResult] = {}
    for paper in papers:
        results[paper.id] = _classify_paper(
            paper,
            author_matcher,
            institution_matcher,
            topic_classifier,
            evidence_index=evidence_index,
            graph_signals=graph_signals.get(paper.id),
            entity_index=entity_index,
            use_attribution_evidence=use_attribution_evidence,
        )

    _apply_rerank_to_borderline(papers, results)

    if use_judge is None:
        use_judge = os.environ.get("PAS_LLM_JUDGE", "0") == "1"
    if use_judge or judge is not None:
        _apply_judge_to_uncertain(papers, results, judge=judge, session=session)

    if use_learned is None:
        use_learned = os.environ.get("PAS_LEARNED_CLASSIFIER", "1") == "1"
    if use_learned:
        _apply_learned_override(papers, results, session=session)

    for paper in papers:
        result = results[paper.id]
        if paper.classification is None:
            paper.classification = PaperClassification(
                id=f"cls_{uuid.uuid4().hex[:12]}", paper_id=paper.id
            )
            session.add(paper.classification)
        cls = paper.classification
        if not cls.human_confirmed:
            cls.label = result.label
            cls.confidence = result.confidence
        else:
            cls.confidence = max(cls.confidence, result.confidence)
        cls.author_score = result.author_score
        cls.institution_score = result.institution_score
        cls.topic_score = result.topic_score
        cls.network_score = result.network_score
        cls.fulltext_evidence_score = result.fulltext_evidence_score
        cls.citation_score = result.citation_score
        cls.graph_signals = (
            result.graph_signals.to_dict() if result.graph_signals else None
        )
        cls.sdl_relevance_label = _sdl_memory_label(result.topic_score, result.fulltext_evidence_score)
        cls.ac_attribution_label = _ac_memory_label(
            result.author_score,
            result.institution_score,
            result.network_score,
            result.citation_score,
        )
        cls.model_agreement_status = cls.model_agreement_status or "single_model"
        cls.evidence_summary = merge_dimensions_into_evidence_summary(
            cls.evidence_summary,
            infer_sdl_dimensions(paper, topic_score=result.topic_score),
        )
        cls.evidence_summary = _merge_attribution_evidence_summary(
            cls.evidence_summary, result.attribution_evidence
        )
        cls.model_version = _model_version_for(result)
        cls.matched_people = _serialize_matched_people(result.matched_people)
        cls.matched_institutions = _serialize_matched_institutions(
            result.matched_institutions
        )
        cls.matched_topics = [
            {
                "topic_id": m.topic_id,
                "name": m.name,
                "is_core": m.is_core,
                "score": m.score,
                "hits": m.hits,
                "density": m.density,
                "negation_hits": m.negation_hits,
                "blacklist_hits": m.blacklist_hits,
            }
            for m in result.matched_topics
        ]
        cls.reasons = result.reasons
        cls.last_classified_at = datetime.now(UTC)

    session.commit()


def _merge_attribution_evidence_summary(
    summary: list[dict] | None,
    signals: AttributionEvidenceSignals | None,
) -> list[dict]:
    rows = [
        row
        for row in (summary or [])
        if row.get("type") != "attribution_evidence_decision"
    ]
    if signals is not None:
        rows.append(signals.to_summary())
    return rows


def _serialize_matched_people(matches: list[AuthorMatch]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for m in sorted(matches, key=lambda item: item.score, reverse=True):
        key = m.person_id or normalize_name(m.name)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "person_id": m.person_id,
                "name": m.name,
                "match_type": m.match_type,
                "score": round(m.score, 3),
                "institution": m.institution,
            }
        )
    return rows


def _serialize_matched_institutions(matches: list[InstitutionMatch]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for m in sorted(matches, key=lambda item: item.score, reverse=True):
        key = m.institution_id
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "institution_id": m.institution_id,
                "canonical_name": m.canonical_name,
                "is_partner": m.is_partner,
                "score": round(m.score, 3),
                "matched_text": m.matched_text,
            }
        )
    return rows


def _sdl_memory_label(topic_score: float, fulltext_score: float) -> str:
    score = max(topic_score, fulltext_score)
    if score >= 0.6:
        return "SDL_RELEVANT"
    if score >= 0.3:
        return "SDL_ADJACENT"
    return "SDL_NOT_RELEVANT"


def _ac_memory_label(
    author_score: float,
    institution_score: float,
    network_score: float,
    citation_score: float,
) -> str:
    score = max(author_score, institution_score, network_score, citation_score)
    if score >= 0.7:
        return "CORE_AC"
    if score >= 0.4:
        return "AC_RELATED"
    if score >= 0.2:
        return "WEAK_AC_SIGNAL"
    return "NO_AC_EVIDENCE"


def _model_version_for(result: ClassificationResult) -> str:
    if result.learned_label is not None:
        base = result.learned_model_version or "learned-v0.7"
    else:
        base = CURRENT_MODEL_VERSION
    suffixes: list[str] = []
    if result.aet_applied:
        suffixes.append(SCORING_VERSION)
    if result.judge_applied:
        suffixes.append("judge")
    elif result.rerank_applied:
        suffixes.append("rerank")
    return "+".join([base, *suffixes])


def _apply_judge_to_uncertain(
    papers: list[Paper],
    results: dict[str, ClassificationResult],
    *,
    judge=None,
    session: Session | None = None,
) -> None:
    """Hook the LLM judge into the UNCERTAIN bucket."""
    from app.services.llm_judge import get_judge

    if judge is None:
        judge = get_judge()
    targets = [
        p
        for p in papers
        if results[p.id].label == LABEL_UNCERTAIN
    ]
    if not targets:
        return
    for p in targets:
        r = results[p.id]
        try:
            verdict = judge.adjudicate(
                title=p.title,
                abstract=p.abstract or "",
                matched_topics=[
                    {"name": m.name, "hits": m.hits, "score": m.score}
                    for m in r.matched_topics
                ],
                evidence=[
                    {"type": e.evidence_type, "snippet": e.evidence_text}
                    for e in r.fulltext_evidence
                ],
                current_label=r.label,
                current_confidence=r.confidence,
            )
        except Exception:
            continue
        if verdict is None:
            continue
        r.judge_applied = True
        r.label = verdict.label
        r.confidence = round(max(0.0, min(1.0, verdict.confidence)), 3)
        for snippet in verdict.disqualifying_evidence or []:
            r.reasons.append(f"Judge: disqualifying — {snippet[:160]}")
            if session is not None:
                from app.services.evidence_extractor import (
                    add_disqualifying_evidence,
                )

                add_disqualifying_evidence(
                    session,
                    paper_id=p.id,
                    source="llm_judge",
                    snippet=snippet,
                )
        for reason in verdict.reasons or []:
            r.reasons.append(f"Judge: {reason}")


def _apply_learned_override(
    papers: list[Paper],
    results: dict[str, ClassificationResult],
    *,
    session: Session | None = None,
) -> None:
    """If a learned classifier is available, fuse its prediction in."""
    from app.services.learned_classifier import load_default_model

    model = load_default_model(session)
    if model is None:
        return
    for p in papers:
        r = results[p.id]
        try:
            pred_label, pred_conf = model.predict(
                _features_for_learned(p, r)
            )
        except Exception:
            continue
        r.learned_label = pred_label
        r.learned_confidence = round(pred_conf, 3)
        r.learned_model_version = model.model_version
        # Hard override only if the model is much more confident than rules.
        if (
            pred_label != r.label
            and pred_conf >= 0.75
            and pred_conf - r.confidence >= 0.15
        ):
            r.reasons.append(
                f"Learned classifier override: {r.label} → {pred_label} "
                f"(model conf {pred_conf:.2f})."
            )
            r.label = pred_label
            r.confidence = round(pred_conf, 3)


def _features_for_learned(
    paper: Paper, r: ClassificationResult
) -> dict[str, float]:
    """Build the feature dict for the learned classifier."""
    return {
        "author_score": r.author_score,
        "institution_score": r.institution_score,
        "topic_score": r.topic_score,
        "fulltext_evidence_score": r.fulltext_evidence_score,
        "network_score": r.network_score,
        "citation_score": r.citation_score,
        "topic_density": float(r.topic_density),
        "negated_topic_hits": float(r.negated_topic_hits),
        "disqualifying_count": float(r.disqualifying_count),
        "n_ac_authors": float(
            sum(1 for m in r.matched_people if m.is_ac_member)
        ),
        "n_partner_inst": float(
            sum(1 for m in r.matched_institutions if m.is_partner)
        ),
        "has_funding_evidence": float(
            any(
                e.evidence_type == "funding_acknowledgement" and e.score > 0
                for e in r.fulltext_evidence
            )
        ),
        "year": float(paper.year or 0),
        "provenance_prior": _provenance_prior(paper),
    }


def _provenance_prior(paper: Paper) -> float:
    """v0.7 #11: provenance-aware prior for the learned classifier."""
    prov = (paper.provenance or "").lower()
    if prov.startswith("discovered_auto"):
        return 0.5
    if prov.startswith("discovered_approved"):
        return 0.6
    if prov == "csv":
        return 0.7
    if prov.startswith("discovered_queued") or "recommend" in prov:
        return 0.3
    return 0.5


def classify_with_fulltext(session: Session, **kwargs) -> list[Paper]:
    """v0.2 convenience: re-extract evidence then classify in one call."""
    for paper in session.execute(
        select(Paper).where(Paper.full_text_available)
    ).scalars():
        from app.services.evidence_extractor import persist_evidence

        persist_evidence(session, paper.id)
    session.commit()
    papers = classify_all(session, **kwargs)
    from app.services.proposition_extractor import persist_propositions

    persist_propositions(session)
    return papers
