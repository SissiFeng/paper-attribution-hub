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
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Author, Institution, Paper, PaperClassification, PaperEvidence, Topic
from app.services.author_matcher import AuthorMatch, AuthorMatcher
from app.services.evidence_extractor import _aggregate_score
from app.services.graph_service import GraphSignals, compute_graph_signals
from app.services.institution_matcher import InstitutionMatch, InstitutionMatcher
from app.services.topic_classifier import ClassifyResult, TopicClassifier, TopicMatch

LABEL_CORE = "CORE_RELEVANT"
LABEL_RELATED = "RELATED_RELEVANT"
LABEL_ADJACENT = "ADJACENT"
LABEL_UNCERTAIN = "UNCERTAIN"
LABEL_EXCLUDE = "EXCLUDE"


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

    has_funding_evidence = any(
        r.evidence_type == "funding_acknowledgement" and r.score > 0
        for r in fulltext_records
    )

    # ---- Apply rules --------------------------------------------------
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
        has_core_topic_match=any(m.is_core and m.score > 0 for m in matched_topics),
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
        matched_people=matched_people,
        matched_institutions=matched_institutions,
        matched_topics=matched_topics,
        fulltext_evidence=fulltext_snapshots,
        reasons=reasons,
        graph_signals=graph_signals,
        topic_density=topic_density,
        negated_topic_hits=topic_result.negated_hit_count,
        disqualifying_count=disqualifying_count,
    )


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
) -> tuple[str, float]:
    """Tightened decision tree (v0.7).

    Key change vs v0.3: CORE requires necessary conditions, not just any
    strong signal. The matrix below is conservative on purpose — borderline
    cases are pushed to UNCERTAIN and the cross-encoder / LLM judge resolves
    them downstream.
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

    # Disqualifying evidence subtracts from the blend.
    if disqualifying_count > 0:
        base = max(0.0, base - 0.15 * disqualifying_count)

    confidence = round(base, 3)

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
    judge=None,  # LLMJudge override (tests)
    embedder=None,  # Embedder override (tests)
) -> list[Paper]:
    """Re-classify the entire corpus.

    Args:
      use_learned: if True (or PAS_LEARNED_CLASSIFIER=1), load the trained
        model and use its prediction as a soft override.
      use_judge: if True (or PAS_LLM_JUDGE=1), invoke the LLM judge on the
        UNCERTAIN bucket.
    """
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

    graph_signals_by_paper = compute_graph_signals(session)

    papers = list(session.execute(select(Paper)).scalars())
    results: dict[str, ClassificationResult] = {}
    for paper in papers:
        result = _classify_paper(
            paper,
            author_matcher,
            institution_matcher,
            topic_classifier,
            evidence_index=evidence_index,
            graph_signals=graph_signals_by_paper.get(paper.id),
        )
        results[paper.id] = result

    # v0.7: cross-encoder rerank for borderline cases.
    _apply_rerank_to_borderline(papers, results)

    # v0.7: LLM judge for what's still UNCERTAIN.
    if use_judge is None:
        use_judge = os.environ.get("PAS_LLM_JUDGE", "0") == "1"
    if use_judge or judge is not None:
        _apply_judge_to_uncertain(papers, results, judge=judge, session=session)

    # v0.7: learned classifier post-hoc soft override.
    if use_learned is None:
        use_learned = os.environ.get("PAS_LEARNED_CLASSIFIER", "0") == "1"
    if use_learned:
        _apply_learned_override(papers, results)

    # Persist.
    for paper in papers:
        result = results[paper.id]
        if paper.classification is None:
            paper.classification = PaperClassification(
                id=f"cls_{uuid.uuid4().hex[:12]}", paper_id=paper.id
            )
            session.add(paper.classification)
        cls = paper.classification
        # Never auto-overwrite a human-confirmed label. We still re-record
        # signals (so analytics stay accurate) but keep the locked label.
        if not cls.human_confirmed:
            cls.label = result.label
            cls.confidence = result.confidence
        else:
            cls.label = cls.label  # explicit no-op for readability
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
        cls.model_version = _model_version_for(result)
        cls.matched_people = [
            {
                "person_id": m.person_id,
                "name": m.name,
                "match_type": m.match_type,
                "score": round(m.score, 3),
                "institution": m.institution,
            }
            for m in result.matched_people
        ]
        cls.matched_institutions = [
            {
                "institution_id": m.institution_id,
                "canonical_name": m.canonical_name,
                "is_partner": m.is_partner,
                "score": round(m.score, 3),
                "matched_text": m.matched_text,
            }
            for m in result.matched_institutions
        ]
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

    # v0.4: refresh proposition table once classifications are settled.
    from app.services.proposition_extractor import persist_propositions

    persist_propositions(session)
    return papers


# ---------------------------------------------------------------------------
# Incremental: classify only papers that need it
# ---------------------------------------------------------------------------


CURRENT_MODEL_VERSION = "rules-v0.7"


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
    target_version = current_version or CURRENT_MODEL_VERSION

    candidates: list[Paper] = []
    for paper in session.execute(select(Paper)).scalars():
        cls = paper.classification
        if cls is None:
            candidates.append(paper)
            continue
        if cls.human_confirmed:
            continue
        # Stale model_version, e.g. "rules-v0.1" needs an upgrade pass.
        if (cls.model_version or "").rsplit("+", 1)[0] != target_version:
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
            judge=judge,
            embedder=embedder,
        )
        new = sum(1 for p in papers if before_versions.get(p.id) is None)
        refreshed = len(papers) - new
        return papers, new, refreshed

    needing = papers_needing_classification(session)
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
    judge,
    embedder,
) -> None:
    """Apply the full classification stack to a subset of papers in place."""
    if not papers:
        return

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
        )

    _apply_rerank_to_borderline(papers, results)

    if use_judge is None:
        use_judge = os.environ.get("PAS_LLM_JUDGE", "0") == "1"
    if use_judge or judge is not None:
        _apply_judge_to_uncertain(papers, results, judge=judge, session=session)

    if use_learned is None:
        use_learned = os.environ.get("PAS_LEARNED_CLASSIFIER", "0") == "1"
    if use_learned:
        _apply_learned_override(papers, results)

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
        cls.model_version = _model_version_for(result)
        cls.matched_people = [
            {
                "person_id": m.person_id,
                "name": m.name,
                "match_type": m.match_type,
                "score": round(m.score, 3),
                "institution": m.institution,
            }
            for m in result.matched_people
        ]
        cls.matched_institutions = [
            {
                "institution_id": m.institution_id,
                "canonical_name": m.canonical_name,
                "is_partner": m.is_partner,
                "score": round(m.score, 3),
                "matched_text": m.matched_text,
            }
            for m in result.matched_institutions
        ]
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


def _model_version_for(result: ClassificationResult) -> str:
    if result.learned_label is not None:
        return "learned-v0.7"
    if result.judge_applied:
        return "rules-v0.7+judge"
    if result.rerank_applied:
        return "rules-v0.7+rerank"
    if result.citation_score > 0 or (
        result.graph_signals and result.graph_signals.second_degree_paths
    ):
        return "rules-v0.7"
    if result.fulltext_evidence_score > 0:
        return "rules-v0.7"
    return "rules-v0.7"


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
    papers: list[Paper], results: dict[str, ClassificationResult]
) -> None:
    """If a learned classifier is available, fuse its prediction in."""
    from app.services.learned_classifier import load_default_model

    model = load_default_model()
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
