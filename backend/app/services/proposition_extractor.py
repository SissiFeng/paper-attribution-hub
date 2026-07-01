"""Promote raw evidence into structured propositions (parse.md §6).

A proposition is a triple `(paper_id, predicate, object)` plus a pointer
back to whichever evidence/chunk row produced it. The proposition layer
sits between v0.2 evidence chunks and v0.3 graph signals, giving the UI
and the classifier a single normalized claim shape regardless of where
the signal came from.

Predicates emitted today (all derived deterministically from earlier
layers — no LLM):

  funded_by(paper, "Acceleration Consortium")
  uses_method(paper, "Bayesian optimization")
  affiliated_with(paper, "University of Toronto")
  cites(paper, ac_core_id)
  belongs_to_topic(paper, topic_id)

Future predicates from parse.md:
  uses_platform(paper, software_or_instrument)
  uses_dataset(paper, dataset_name)
  research_objective(paper, "...")
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Author,
    Institution,
    Paper,
    PaperAuthor,
    PaperEvidence,
    PaperProposition,
    PaperReference,
    Topic,
)
from app.services.domain_tokenizer import get_vocabulary
from app.services.retrieval_operationalization import sdl_methodology_terms
from app.services.sdl_dimensions import dimensions_from_evidence_summary

PREDICATE_FUNDED_BY = "funded_by"
PREDICATE_USES_METHOD = "uses_method"
PREDICATE_AFFILIATED_WITH = "affiliated_with"
PREDICATE_CITES = "cites"
PREDICATE_BELONGS_TO_TOPIC = "belongs_to_topic"
PREDICATE_USES_PLATFORM = "uses_platform"
PREDICATE_USES_OPTIMIZATION_METHOD = "uses_optimization_method"
PREDICATE_TARGETS_DOMAIN = "targets_domain"
PREDICATE_HAS_AUTONOMY_LEVEL = "has_autonomy_level"
PREDICATE_REPORTS_FAILURE_OR_LIMITATION = "reports_failure_or_limitation"


@dataclass
class PropositionRecord:
    predicate: str
    object_value: str
    object_key: str | None
    claim_text: str
    confidence: float
    source_section: str | None = None
    source_evidence_id: str | None = None
    source_chunk_id: str | None = None
    extra: dict | None = None


_FUNDING_ENTITY_PATTERNS = [
    (re.compile(r"acceleration consortium", re.IGNORECASE), "Acceleration Consortium"),
    (re.compile(r"\bvector institute\b", re.IGNORECASE), "Vector Institute"),
    (re.compile(r"\bcifar\b", re.IGNORECASE), "CIFAR"),
    (re.compile(r"\bnserc\b", re.IGNORECASE), "NSERC"),
    (re.compile(r"\bcfi\b", re.IGNORECASE), "CFI"),
]


def _extract_funding(
    paper_id: str, evidence_rows: list[PaperEvidence]
) -> list[PropositionRecord]:
    out: list[PropositionRecord] = []
    seen: set[str] = set()
    for ev in evidence_rows:
        if ev.evidence_type != "funding_acknowledgement":
            continue
        for pattern, canonical in _FUNDING_ENTITY_PATTERNS:
            if pattern.search(ev.evidence_text) and canonical not in seen:
                seen.add(canonical)
                out.append(
                    PropositionRecord(
                        predicate=PREDICATE_FUNDED_BY,
                        object_value=canonical,
                        object_key=canonical.lower().replace(" ", "_"),
                        claim_text=f"{paper_id} was funded by {canonical}.",
                        confidence=0.95,
                        source_section=ev.evidence_source,
                        source_evidence_id=ev.id,
                        source_chunk_id=ev.chunk_id,
                    )
                )
    return out


_METHOD_KEYWORDS = [
    "Bayesian optimization",
    "active learning",
    "closed-loop optimization",
    "closed-loop experimentation",
    "robotic synthesis",
    "high-throughput experimentation",
    "high-throughput screening",
    "workflow orchestration",
    "automated synthesis",
    "self-driving laboratory",
    "self-driving lab",
    "autonomous platform",
    *sdl_methodology_terms(),
]
_METHOD_KEYWORDS = list(dict.fromkeys(_METHOD_KEYWORDS))

_FAILURE_PATTERNS = [
    "fails when",
    "failure",
    "limitation",
    "limited by",
    "constraint",
    "does not generalize",
    "performance deteriorates",
]


def _extract_methods(
    paper_id: str, evidence_rows: list[PaperEvidence]
) -> list[PropositionRecord]:
    out: list[PropositionRecord] = []
    seen: set[str] = set()
    for ev in evidence_rows:
        if ev.evidence_type not in {"sdl_methodology", "figure_caption_sdl"}:
            continue
        text_lower = ev.evidence_text.lower()
        for kw in _METHOD_KEYWORDS:
            if kw.lower() in text_lower and kw not in seen:
                seen.add(kw)
                out.append(
                    PropositionRecord(
                        predicate=PREDICATE_USES_METHOD,
                        object_value=kw,
                        object_key=kw.lower().replace(" ", "_"),
                        claim_text=f"{paper_id} uses {kw}.",
                        confidence=0.85,
                        source_section=ev.evidence_source,
                        source_evidence_id=ev.id,
                        source_chunk_id=ev.chunk_id,
                    )
                )
    return out


def _extract_affiliations(
    paper: Paper, session: Session
) -> list[PropositionRecord]:
    out: list[PropositionRecord] = []
    seen: set[str] = set()
    for pa in paper.authors:
        inst = pa.author.institution
        if inst is None:
            continue
        if inst.canonical_name in seen:
            continue
        seen.add(inst.canonical_name)
        confidence = 0.95 if inst.is_partner else 0.7
        out.append(
            PropositionRecord(
                predicate=PREDICATE_AFFILIATED_WITH,
                object_value=inst.canonical_name,
                object_key=inst.id,
                claim_text=f"{paper.id} has an author affiliated with {inst.canonical_name}.",
                confidence=confidence,
                source_section="metadata",
                extra={"is_partner": bool(inst.is_partner)},
            )
        )
    return out


def _extract_citations(
    paper_id: str, references: list[PaperReference]
) -> list[PropositionRecord]:
    out: list[PropositionRecord] = []
    for ref in references:
        if not ref.cited_ac_core_id:
            continue
        title = ref.cited_title or ref.cited_ac_core_id
        out.append(
            PropositionRecord(
                predicate=PREDICATE_CITES,
                object_value=title,
                object_key=ref.cited_ac_core_id,
                claim_text=f"{paper_id} cites the AC core paper \"{title}\".",
                confidence=0.95,
                source_section="references",
                extra={"doi": ref.cited_doi},
            )
        )
    return out


def _extract_topics(
    paper: Paper, topic_index: dict[str, Topic]
) -> list[PropositionRecord]:
    if paper.classification is None:
        return []
    out: list[PropositionRecord] = []
    seen: set[str] = set()
    for tm in paper.classification.matched_topics or []:
        topic_id = tm.get("topic_id")
        if not topic_id or topic_id in seen:
            continue
        if (tm.get("score") or 0) < 0.3:
            continue
        seen.add(topic_id)
        topic = topic_index.get(topic_id)
        topic_name = topic.name if topic else topic_id
        out.append(
            PropositionRecord(
                predicate=PREDICATE_BELONGS_TO_TOPIC,
                object_value=topic_name,
                object_key=topic_id,
                claim_text=(
                    f"{paper.id} belongs to topic \"{topic_name}\" "
                    f"(score {tm.get('score'):.2f})."
                ),
                confidence=float(tm.get("score") or 0.0),
                source_section="topic_classifier",
                extra={"is_core": bool(tm.get("is_core"))},
            )
        )
    return out


def _extract_dimensions(paper: Paper) -> list[PropositionRecord]:
    if paper.classification is None:
        return []
    dims = dimensions_from_evidence_summary(paper.classification.evidence_summary)
    if not dims:
        return []
    out: list[PropositionRecord] = []
    mapping = [
        ("platform_type", PREDICATE_USES_PLATFORM),
        ("optimization_method", PREDICATE_USES_OPTIMIZATION_METHOD),
        ("domain", PREDICATE_TARGETS_DOMAIN),
        ("automation_level", PREDICATE_HAS_AUTONOMY_LEVEL),
    ]
    for key, predicate in mapping:
        value = dims.get(key)
        if not value or value in {"none", "unknown", "other"}:
            continue
        out.append(
            PropositionRecord(
                predicate=predicate,
                object_value=value,
                object_key=value,
                claim_text=f"{paper.id} has SDL dimension {key}={value}.",
                confidence=0.65,
                source_section="classification_dimensions",
                extra={"dimension": key},
            )
        )
    return out


def _extract_failures(
    paper_id: str, evidence_rows: list[PaperEvidence]
) -> list[PropositionRecord]:
    out: list[PropositionRecord] = []
    for ev in evidence_rows:
        text = ev.evidence_text.lower()
        if any(p in text for p in _FAILURE_PATTERNS):
            out.append(
                PropositionRecord(
                    predicate=PREDICATE_REPORTS_FAILURE_OR_LIMITATION,
                    object_value="limitation",
                    object_key="limitation",
                    claim_text=ev.evidence_text[:500],
                    confidence=min(0.75, max(0.35, ev.score)),
                    source_section=ev.evidence_source,
                    source_evidence_id=ev.id,
                    source_chunk_id=ev.chunk_id,
                )
            )
    return out


def extract_propositions_for_paper(
    session: Session,
    paper_id: str,
    *,
    topic_index: dict[str, Topic] | None = None,
) -> list[PropositionRecord]:
    paper = session.get(Paper, paper_id)
    if paper is None:
        return []
    if topic_index is None:
        topic_index = {t.id: t for t in session.execute(select(Topic)).scalars()}

    evidence_rows = list(
        session.execute(
            select(PaperEvidence).where(PaperEvidence.paper_id == paper_id)
        ).scalars()
    )
    references = list(
        session.execute(
            select(PaperReference).where(PaperReference.citing_paper_id == paper_id)
        ).scalars()
    )

    records: list[PropositionRecord] = []
    records.extend(_extract_funding(paper_id, evidence_rows))
    records.extend(_extract_methods(paper_id, evidence_rows))
    records.extend(_extract_affiliations(paper, session))
    records.extend(_extract_citations(paper_id, references))
    records.extend(_extract_topics(paper, topic_index))
    records.extend(_extract_dimensions(paper))
    records.extend(_extract_failures(paper_id, evidence_rows))

    # Negative-phrase demotion: when a chunk supporting a method proposition
    # contains a negative phrase like "closed-loop control", flag it.
    vocab = get_vocabulary()
    if vocab.normalized_negatives():
        for rec in records:
            if rec.predicate != PREDICATE_USES_METHOD or rec.source_evidence_id is None:
                continue
            evidence_row = next(
                (e for e in evidence_rows if e.id == rec.source_evidence_id), None
            )
            if evidence_row is None:
                continue
            if any(
                neg in evidence_row.evidence_text.lower()
                for neg in vocab.normalized_negatives()
            ):
                rec.confidence *= 0.4
                rec.extra = {**(rec.extra or {}), "negative_phrase_detected": True}
    return records


def persist_propositions(session: Session) -> int:
    """Wipe and rebuild propositions for the whole corpus."""
    session.query(PaperProposition).delete()
    session.flush()
    topic_index = {t.id: t for t in session.execute(select(Topic)).scalars()}
    total = 0
    for paper in session.execute(select(Paper)).scalars():
        records = extract_propositions_for_paper(
            session, paper.id, topic_index=topic_index
        )
        for rec in records:
            session.add(
                PaperProposition(
                    id=f"prop_{uuid.uuid4().hex[:12]}",
                    paper_id=paper.id,
                    predicate=rec.predicate,
                    object_value=rec.object_value,
                    object_key=rec.object_key,
                    source_section=rec.source_section,
                    source_evidence_id=rec.source_evidence_id,
                    source_chunk_id=rec.source_chunk_id,
                    claim_text=rec.claim_text,
                    confidence=rec.confidence,
                    extra=rec.extra,
                )
            )
            total += 1
    session.commit()
    return total
