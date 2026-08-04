"""Deterministic, read-only attribution Skill dispatcher with replay records."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attribution_skill_contract import (
    ATTRIBUTION_SKILL_CONTRACT_VERSION,
    AttributionCostSummary,
    AttributionDecisionResult,
    AttributionDeterminationOutcome,
    AttributionEvidencePacket,
    AttributionFailure,
    AttributionInvocationBudget,
    AttributionReadSkillName,
    AttributionSkillInvocation,
    AttributionSkillOutcome,
    AuthorIdentityResolutionOutcome,
    AuditableAttributionEvidence,
    ClassifierDisagreementOutcome,
    EvidenceCollectionOutcome,
    EvidenceSourceProvenance,
    EvidenceTemporalValidity,
    MembershipVerificationOutcome,
)
from app.classification_labels import normalize_classification_label
from app.models import (
    AttributionSkillInvocationRecord,
    Paper,
    PaperEvidence,
    PaperLabLink,
)
from app.services.attribution_evidence_tree import (
    TREE_VERSION,
    build_attribution_evidence_tree,
)
from app.schemas import AttributionEvidenceTreeOut

SKILL_VERSION = "0.1.0"
DEFAULT_POLICY_VERSION = "ac-attribution-policy-v0.1"
SNAPSHOT_SCHEMA_VERSION = "ac-attribution-input-snapshot-v0.1"

READ_SKILL_NAMES: tuple[AttributionReadSkillName, ...] = (
    "determine_ac_paper_attribution",
    "resolve_ambiguous_author_identity",
    "verify_membership_at_publication_time",
    "collect_auditable_attribution_evidence",
    "adjudicate_classifier_disagreement",
)

_MEMBERSHIP_EVIDENCE_TYPES = {
    "membership",
    "ac_membership",
    "membership_interval",
    "ac_member_match",
    "ac_author",
    "ac_affiliation",
}
_DIRECT_ATTRIBUTION_EVIDENCE_TYPES = {
    "ac_gold_publication",
    "ac_acknowledgement",
    "ac_program",
    "ac_funding",
    "funding_acknowledgement",
}
_RELEVANCE_LABELS = {
    "CORE_RELEVANT",
    "RELATED_RELEVANT",
    "SDL_FIELD_RELEVANT",
    "ADJACENT",
    "EXCLUDE",
}


class AttributionSkillInvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invocation_id: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9._~-]+$",
    )
    skill_name: AttributionReadSkillName
    paper_id: str = Field(min_length=1, max_length=200)
    invocation_reason: str = Field(min_length=1, max_length=1000)
    policy_version: Literal["ac-attribution-policy-v0.1"] = DEFAULT_POLICY_VERSION
    budget: AttributionInvocationBudget = Field(
        default_factory=AttributionInvocationBudget
    )


class AttributionSkillCatalog(BaseModel):
    contract_version: Literal["ac-attribution-skill-v0.1"] = (
        ATTRIBUTION_SKILL_CONTRACT_VERSION
    )
    skill_version: str = SKILL_VERSION
    policy_version: str = DEFAULT_POLICY_VERSION
    read_skills: list[AttributionReadSkillName]
    network_update_skill_included: bool = False


class InvocationConflictError(ValueError):
    pass


class PaperNotFoundError(ValueError):
    pass


class InvocationNotFoundError(ValueError):
    pass


class AttributionSkillSessionError(RuntimeError):
    pass


class UnsupportedStoredContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class _SkillContext:
    request: AttributionSkillInvokeRequest
    paper: Paper
    evidence_tree: AttributionEvidenceTreeOut
    evidence_rows: list[PaperEvidence]
    lab_links: list[PaperLabLink]
    snapshot: dict
    snapshot_id: str
    content_hash: str
    generated_at: datetime


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode()).hexdigest()


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _json_date(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


def _classification_snapshot(paper: Paper) -> dict | None:
    classification = paper.classification
    if classification is None:
        return None
    return {
        "id": classification.id,
        "label": classification.label,
        "confidence": classification.confidence,
        "author_score": classification.author_score,
        "institution_score": classification.institution_score,
        "topic_score": classification.topic_score,
        "network_score": classification.network_score,
        "fulltext_evidence_score": classification.fulltext_evidence_score,
        "citation_score": classification.citation_score,
        "graph_signals": classification.graph_signals,
        "matched_people": classification.matched_people,
        "matched_institutions": classification.matched_institutions,
        "matched_topics": classification.matched_topics,
        "reasons": classification.reasons,
        "model_version": classification.model_version,
        "needs_review": classification.needs_review,
        "human_confirmed": classification.human_confirmed,
        "human_confirmed_at": _json_date(classification.human_confirmed_at),
        "human_confirmed_by": classification.human_confirmed_by,
        "funding_signal": classification.funding_signal,
        "acknowledgement_signal": classification.acknowledgement_signal,
        "retrieval_signal": classification.retrieval_signal,
        "architecture_signal": classification.architecture_signal,
        "sdl_relevance_label": classification.sdl_relevance_label,
        "ac_attribution_label": classification.ac_attribution_label,
        "model_agreement_status": classification.model_agreement_status,
        "disagreement_type": classification.disagreement_type,
        "evidence_summary": classification.evidence_summary,
        "future_rule_update": classification.future_rule_update,
    }


def _review_snapshot(paper: Paper) -> dict | None:
    review = paper.review
    if review is None:
        return None
    return {
        "id": review.id,
        "human_label": review.human_label,
        "corrected_topics": review.corrected_topics,
        "corrected_people": review.corrected_people,
        "reviewer": review.reviewer,
        "notes": review.notes,
        "disagreement_type": review.disagreement_type,
        "rationale": review.rationale,
        "evidence": review.evidence,
        "future_rule_update": review.future_rule_update,
        "created_at": _json_date(review.created_at),
    }


def _build_context(
    session: Session,
    request: AttributionSkillInvokeRequest,
    paper: Paper,
    *,
    generated_at: datetime,
) -> _SkillContext:
    evidence_tree = build_attribution_evidence_tree(session, paper.id)
    evidence_rows = list(
        session.execute(
            select(PaperEvidence)
            .where(PaperEvidence.paper_id == paper.id)
            .order_by(PaperEvidence.id)
        ).scalars()
    )
    lab_links = list(
        session.execute(
            select(PaperLabLink)
            .where(PaperLabLink.paper_id == paper.id)
            .order_by(PaperLabLink.lab_id)
        ).scalars()
    )
    snapshot = {
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        "paper": {
            "id": paper.id,
            "title": paper.title,
            "abstract": paper.abstract,
            "doi": paper.doi,
            "year": paper.year,
            "venue": paper.venue,
            "source": paper.source,
            "provenance": paper.provenance,
            "keywords": paper.keywords,
            "indexed_keywords": paper.indexed_keywords,
            "funding_text": paper.funding_text,
            "funding_sponsors": paper.funding_sponsors,
            "ac_known_publication": paper.ac_known_publication,
            "ac_acknowledged": paper.ac_acknowledged,
            "ac_highly_relevant": paper.ac_highly_relevant,
            "ac_high_impact": paper.ac_high_impact,
            "ac_members_matched": paper.ac_members_matched,
            "ac_programs": paper.ac_programs,
            "ac_attribution_score": paper.ac_attribution_score,
            "sdl_relevance_score": paper.sdl_relevance_score,
            "updated_at": _json_date(paper.updated_at),
        },
        "authors": [
            {
                "paper_id": link.paper_id,
                "author_id": link.author_id,
                "author_order": link.author_order,
                "affiliation_text": link.affiliation_text,
                "match_confidence": link.match_confidence,
                "canonical_name": link.author.canonical_name,
                "normalized_name": link.author.normalized_name,
                "orcid": link.author.orcid,
                "institution_id": link.author.institution_id,
                "is_ac_member": link.author.is_ac_member,
            }
            for link in paper.authors
        ],
        "classification": _classification_snapshot(paper),
        "human_review": _review_snapshot(paper),
        "lab_links": [
            {
                "paper_id": link.paper_id,
                "lab_id": link.lab_id,
                "source": link.source,
                "confidence": link.confidence,
            }
            for link in lab_links
        ],
        "paper_evidence": [
            {
                "id": row.id,
                "chunk_id": row.chunk_id,
                "evidence_type": row.evidence_type,
                "evidence_source": row.evidence_source,
                "evidence_text": row.evidence_text,
                "score": row.score,
                "extra": row.extra,
                "created_at": _json_date(row.created_at),
            }
            for row in evidence_rows
        ],
        "evidence_tree": evidence_tree.model_dump(mode="json"),
    }
    snapshot = json.loads(_canonical_json(snapshot))
    content_hash = _sha256(snapshot)
    return _SkillContext(
        request=request,
        paper=paper,
        evidence_tree=evidence_tree,
        evidence_rows=evidence_rows,
        lab_links=lab_links,
        snapshot=snapshot,
        snapshot_id=f"pas-paper-snapshot:{content_hash[:24]}",
        content_hash=content_hash,
        generated_at=generated_at,
    )


def _fallback_snapshot(paper: Paper, exc: Exception) -> dict:
    return {
        "snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
        "paper": {"id": paper.id, "title": paper.title},
        "snapshot_error": {
            "type": type(exc).__name__,
            "detail": "Attribution input snapshot construction failed.",
        },
    }


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _temporal_validity(
    evidence_type: str,
    row: PaperEvidence | None,
) -> EvidenceTemporalValidity:
    if row is not None and evidence_type in _MEMBERSHIP_EVIDENCE_TYPES:
        raw = (row.extra or {}).get("temporal_validity")
        if isinstance(raw, dict):
            status = raw.get("status")
            if status in {"valid", "invalid", "unknown", "conflicting"}:
                valid_from = _parse_date(raw.get("valid_from"))
                valid_to = _parse_date(raw.get("valid_to"))
                malformed_date = (
                    raw.get("valid_from") is not None and valid_from is None
                ) or (raw.get("valid_to") is not None and valid_to is None)
                invalid_interval = bool(
                    valid_from and valid_to and valid_from > valid_to
                )
                if (
                    malformed_date
                    or invalid_interval
                    or (status == "valid" and valid_from is None and valid_to is None)
                ):
                    return EvidenceTemporalValidity(
                        status="unknown",
                        basis="Membership temporal metadata is malformed.",
                    )
                return EvidenceTemporalValidity(
                    status=status,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    basis=str(raw.get("basis") or "Paper evidence temporal metadata")[
                        :500
                    ],
                )
            return EvidenceTemporalValidity(
                status="unknown",
                basis="Membership temporal metadata is malformed.",
            )
    if evidence_type in _MEMBERSHIP_EVIDENCE_TYPES:
        return EvidenceTemporalValidity(
            status="unknown",
            basis="No membership validity interval is recorded.",
        )
    return EvidenceTemporalValidity(
        status="not_applicable",
        basis="The evidence is tied to this paper rather than a reusable time interval.",
    )


def _path_source_row(
    context: _SkillContext,
    evidence_type: str,
    quote: str,
    source_chunk_id: str | None,
) -> PaperEvidence | None:
    for row in context.evidence_rows:
        if row.evidence_type != evidence_type or row.evidence_text != quote:
            continue
        if source_chunk_id is None or row.chunk_id == source_chunk_id:
            return row
    return None


def _aet_evidence(context: _SkillContext) -> list[AuditableAttributionEvidence]:
    items: list[AuditableAttributionEvidence] = []
    for path in context.evidence_tree.evidence_paths:
        chunk_id = path.source_chunk_ids[0] if path.source_chunk_ids else None
        source_row = _path_source_row(
            context,
            path.evidence_type,
            path.quote,
            chunk_id,
        )
        source_record_id = source_row.id if source_row else path.path_id
        provider = (
            source_row.evidence_source
            if source_row
            else "pas_attribution_evidence_tree"
        )
        confidence = (
            path.confidence
            if path.confidence is not None
            else min(1.0, max(abs(path.weight), abs(path.raw_score)))
        )
        items.append(
            AuditableAttributionEvidence(
                evidence_id=path.path_id,
                evidence_type=path.evidence_type,
                polarity=(
                    "supporting" if path.polarity == "positive" else "contradicting"
                ),
                claim=path.quote,
                confidence=confidence,
                provenance=EvidenceSourceProvenance(
                    provider=provider,
                    source_record_id=source_record_id,
                    source_uri=(
                        f"/papers/{context.paper.id}/attribution-evidence-tree"
                    ),
                    retrieved_at=(
                        _aware(source_row.created_at) if source_row else None
                    ),
                    content_hash=_sha256(
                        {
                            "path": path.model_dump(mode="json"),
                            "source_record_id": source_record_id,
                        }
                    ),
                ),
                temporal_validity=_temporal_validity(path.evidence_type, source_row),
                quote=path.quote,
                source_chunk_id=chunk_id,
                page_start=path.page_start if (path.page_start or 0) >= 1 else None,
                page_end=path.page_end if (path.page_end or 0) >= 1 else None,
                detector_type=path.detector_type,
                detector_version=TREE_VERSION,
            )
        )
    return items


def _structured_evidence(
    *,
    context: _SkillContext,
    evidence_type: str,
    polarity: Literal["supporting", "contradicting"],
    claim: str,
    confidence: float,
    provider: str,
    source_record_id: str,
    temporal_validity: EvidenceTemporalValidity | None = None,
    source_value: object,
) -> AuditableAttributionEvidence:
    evidence_hash = _sha256(
        {
            "evidence_type": evidence_type,
            "provider": provider,
            "source_record_id": source_record_id,
            "source_value": source_value,
        }
    )
    return AuditableAttributionEvidence(
        evidence_id=f"structured:{evidence_hash[:32]}",
        evidence_type=evidence_type,
        polarity=polarity,
        claim=claim,
        confidence=max(0.0, min(1.0, confidence)),
        provenance=EvidenceSourceProvenance(
            provider=provider,
            source_record_id=source_record_id,
            source_uri=f"/papers/{context.paper.id}",
            content_hash=evidence_hash,
        ),
        temporal_validity=temporal_validity
        or EvidenceTemporalValidity(
            status="not_applicable",
            basis="The evidence is specific to this paper.",
        ),
    )


def _collect_evidence(context: _SkillContext) -> list[AuditableAttributionEvidence]:
    paper = context.paper
    evidence = _aet_evidence(context)

    if paper.ac_known_publication:
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="ac_gold_publication",
                polarity="supporting",
                claim="The paper is present in the curated AC Publications gold set.",
                confidence=1.0,
                provider="ac_publications_gold_set",
                source_record_id=f"papers:{paper.id}:ac_known_publication",
                source_value=True,
            )
        )
    if paper.ac_acknowledged:
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="ac_acknowledgement",
                polarity="supporting",
                claim="The paper record explicitly acknowledges AC support.",
                confidence=0.95,
                provider="papers",
                source_record_id=f"papers:{paper.id}:ac_acknowledged",
                source_value=True,
            )
        )
    if paper.ac_programs and paper.ac_programs.strip():
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="ac_program",
                polarity="supporting",
                claim=f"The paper is linked to AC program(s): {paper.ac_programs}.",
                confidence=0.9,
                provider="papers",
                source_record_id=f"papers:{paper.id}:ac_programs",
                source_value=paper.ac_programs,
            )
        )
    if paper.ac_members_matched:
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="ac_member_match",
                polarity="supporting",
                claim=(
                    "The paper metadata matches AC member name(s): "
                    + ", ".join(sorted(paper.ac_members_matched))
                    + "."
                ),
                confidence=max(
                    (
                        link.match_confidence
                        for link in paper.authors
                        if link.match_confidence is not None
                    ),
                    default=0.5,
                ),
                provider="papers",
                source_record_id=f"papers:{paper.id}:ac_members_matched",
                source_value=sorted(paper.ac_members_matched),
                temporal_validity=EvidenceTemporalValidity(
                    status="unknown",
                    basis="Matched names have no membership validity interval.",
                ),
            )
        )

    for link in paper.authors:
        if not link.author.is_ac_member:
            continue
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="ac_author",
                polarity="supporting",
                claim=(
                    f"{link.author.canonical_name} is marked as an AC member "
                    "and is linked to this paper."
                ),
                confidence=link.match_confidence or 0.5,
                provider="authors",
                source_record_id=f"authors:{link.author.id}",
                source_value={
                    "author_id": link.author.id,
                    "match_confidence": link.match_confidence,
                    "is_ac_member": link.author.is_ac_member,
                },
                temporal_validity=EvidenceTemporalValidity(
                    status="unknown",
                    basis="The author record has no membership validity interval.",
                ),
            )
        )

    classification = paper.classification
    if classification is not None:
        if classification.ac_attribution_label in {
            "CORE_AC",
            "AC_RELATED",
            "WEAK_AC_SIGNAL",
        }:
            score = {
                "CORE_AC": 0.8,
                "AC_RELATED": 0.6,
                "WEAK_AC_SIGNAL": 0.3,
            }[classification.ac_attribution_label]
            evidence.append(
                _structured_evidence(
                    context=context,
                    evidence_type="classifier_ac_signal",
                    polarity="supporting",
                    claim=(
                        "The classifier attribution dimension is "
                        f"{classification.ac_attribution_label}."
                    ),
                    confidence=score,
                    provider="paper_classifications",
                    source_record_id=(
                        f"paper_classifications:{classification.id}:"
                        "ac_attribution_label"
                    ),
                    source_value=classification.ac_attribution_label,
                )
            )
        if _has_classifier_disagreement(context):
            evidence.append(
                _structured_evidence(
                    context=context,
                    evidence_type="classifier_disagreement",
                    polarity="contradicting",
                    claim=(
                        "Classifier outputs or evidence dimensions require "
                        "adjudication."
                    ),
                    confidence=max(classification.review_priority, 0.6),
                    provider="paper_classifications",
                    source_record_id=(
                        f"paper_classifications:{classification.id}:agreement"
                    ),
                    source_value={
                        "model_agreement_status": (
                            classification.model_agreement_status
                        ),
                        "disagreement_type": classification.disagreement_type,
                        "needs_review": classification.needs_review,
                    },
                )
            )

    for link in context.lab_links:
        evidence.append(
            _structured_evidence(
                context=context,
                evidence_type="lab_attribution",
                polarity="supporting",
                claim=(
                    f"The paper is linked to SDL lab {link.lab_id} "
                    f"through {link.source}."
                ),
                confidence=link.confidence,
                provider="paper_lab_links",
                source_record_id=(f"paper_lab_links:{link.paper_id}:{link.lab_id}"),
                source_value={
                    "lab_id": link.lab_id,
                    "source": link.source,
                    "confidence": link.confidence,
                },
                temporal_validity=EvidenceTemporalValidity(
                    status="unknown",
                    basis="The lab link has no validity interval.",
                ),
            )
        )

    by_id = {item.evidence_id: item for item in evidence}
    return [by_id[evidence_id] for evidence_id in sorted(by_id)]


def _relevance_label(paper: Paper) -> str | None:
    if paper.review is not None:
        label = normalize_classification_label(paper.review.human_label)
        if label in _RELEVANCE_LABELS:
            return label
    if paper.classification is not None:
        label = normalize_classification_label(paper.classification.label)
        if label in _RELEVANCE_LABELS:
            return label
    return None


def _supporting_ids(
    evidence: list[AuditableAttributionEvidence],
) -> list[str]:
    return [item.evidence_id for item in evidence if item.polarity == "supporting"]


def _contradicting_ids(
    evidence: list[AuditableAttributionEvidence],
) -> list[str]:
    return [item.evidence_id for item in evidence if item.polarity == "contradicting"]


def _packet(
    context: _SkillContext,
    evidence: list[AuditableAttributionEvidence],
    decision: AttributionDecisionResult | None = None,
) -> AttributionEvidencePacket:
    return AttributionEvidencePacket(
        packet_id=f"packet:{_sha256(context.request.invocation_id)[:24]}",
        paper_id=context.paper.id,
        paper_snapshot_id=context.snapshot_id,
        generated_at=context.generated_at,
        evidence=evidence,
        decision=decision,
    )


def _review_decision(
    context: _SkillContext,
    evidence: list[AuditableAttributionEvidence],
    *,
    ambiguities: list[str],
    action: str,
) -> AttributionDecisionResult:
    confidence = max((item.confidence for item in evidence), default=0.0)
    return AttributionDecisionResult(
        decision="REVIEW_REQUIRED",
        relevance_label=_relevance_label(context.paper),
        confidence=min(0.65, confidence),
        authority="machine_provisional",
        policy_version=context.request.policy_version,
        supporting_evidence_ids=_supporting_ids(evidence),
        contradicting_evidence_ids=_contradicting_ids(evidence),
        unresolved_ambiguities=ambiguities,
        recommended_review_action=action,
    )


def _gold_decision(
    context: _SkillContext,
    evidence: list[AuditableAttributionEvidence],
) -> AttributionDecisionResult:
    contradictions = _contradicting_ids(evidence)
    gold_ids = [
        item.evidence_id
        for item in evidence
        if item.evidence_type == "ac_gold_publication" and item.polarity == "supporting"
    ]
    return AttributionDecisionResult(
        decision="ATTRIBUTED",
        relevance_label=_relevance_label(context.paper),
        confidence=1.0,
        authority="human_confirmed",
        policy_version=context.request.policy_version,
        supporting_evidence_ids=gold_ids,
        contradicting_evidence_ids=contradictions,
        unresolved_ambiguities=(
            ["Contradicting evidence remains recorded despite gold-set authority."]
            if contradictions
            else []
        ),
        recommended_review_action=(
            "Review the contradiction without overwriting the curated gold record."
            if contradictions
            else None
        ),
    )


def _has_classifier_disagreement(context: _SkillContext) -> bool:
    classification = context.paper.classification
    if classification is None:
        return False
    agreement_status = classification.model_agreement_status
    return bool(
        classification.needs_review
        or classification.disagreement_type
        or agreement_status not in {None, "single_model", "human_confirmed"}
    )


def _has_evidence_conflict(
    context: _SkillContext,
    evidence: list[AuditableAttributionEvidence],
) -> bool:
    return bool(
        _supporting_ids(evidence) and _contradicting_ids(evidence)
    ) or _has_classifier_disagreement(context)


def _handle_collect(
    context: _SkillContext,
) -> tuple[
    Literal["succeeded", "review_required"],
    AttributionEvidencePacket,
    AttributionSkillOutcome,
    list[str],
]:
    evidence = _collect_evidence(context)
    outcome = EvidenceCollectionOutcome(
        outcome_type="evidence_collection",
        evidence_count=len(evidence),
        supporting_count=len(_supporting_ids(evidence)),
        contradicting_count=len(_contradicting_ids(evidence)),
    )
    return (
        "succeeded",
        _packet(context, evidence),
        outcome,
        [
            "collect_auditable_attribution_evidence",
            "preserve_supporting_and_contradicting_evidence",
        ],
    )


def _identity_ambiguities(context: _SkillContext) -> list[str]:
    ambiguities: list[str] = []
    if not context.paper.authors:
        return ["No normalized paper-author records are available."]

    normalized_to_ids: dict[str, set[str]] = {}
    for link in context.paper.authors:
        normalized = (link.author.normalized_name or "").strip().casefold()
        normalized_to_ids.setdefault(normalized, set()).add(link.author.id)
        if link.author.is_ac_member and (
            link.match_confidence is None or link.match_confidence < 0.8
        ):
            ambiguities.append(
                f"AC author {link.author.canonical_name} has match confidence "
                f"{link.match_confidence!r}, below the 0.8 identity threshold."
            )
    for normalized, author_ids in normalized_to_ids.items():
        if normalized and len(author_ids) > 1:
            ambiguities.append(
                f"Normalized author name {normalized!r} maps to multiple author IDs."
            )

    linked_names = {
        link.author.canonical_name.strip().casefold() for link in context.paper.authors
    }
    for name in context.paper.ac_members_matched or []:
        if name.strip().casefold() not in linked_names:
            ambiguities.append(
                f"Matched AC member name {name!r} has no exact normalized author link."
            )
    return ambiguities


def _handle_identity(
    context: _SkillContext,
) -> tuple[
    Literal["succeeded", "review_required"],
    AttributionEvidencePacket,
    AttributionSkillOutcome,
    list[str],
]:
    evidence = _collect_evidence(context)
    ambiguities = _identity_ambiguities(context)
    author_ids = sorted(link.author_id for link in context.paper.authors)
    if not ambiguities:
        return (
            "succeeded",
            _packet(context, evidence),
            AuthorIdentityResolutionOutcome(
                outcome_type="author_identity_resolution",
                resolved=True,
                resolved_author_ids=author_ids,
            ),
            ["resolve_ambiguous_author_identity", "identity_checks_passed"],
        )
    decision = _review_decision(
        context,
        evidence,
        ambiguities=ambiguities,
        action=(
            "Review author identifiers, affiliations, and candidate AC roster "
            "matches; record the resolved author ID before attribution."
        ),
    )
    return (
        "review_required",
        _packet(context, evidence, decision),
        AuthorIdentityResolutionOutcome(
            outcome_type="author_identity_resolution",
            resolved=False,
            resolved_author_ids=[],
            ambiguities=ambiguities,
        ),
        ["resolve_ambiguous_author_identity", "route_identity_to_human_review"],
    )


def _membership_valid_for_year(
    evidence: AuditableAttributionEvidence,
    year: int | None,
) -> bool:
    validity = evidence.temporal_validity
    if validity.status != "valid" or year is None:
        return False
    if validity.valid_from is None and validity.valid_to is None:
        return False
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    return not (
        (validity.valid_to is not None and validity.valid_to < year_start)
        or (validity.valid_from is not None and validity.valid_from > year_end)
    )


def _handle_membership(
    context: _SkillContext,
) -> tuple[
    Literal["succeeded", "review_required"],
    AttributionEvidencePacket,
    AttributionSkillOutcome,
    list[str],
]:
    evidence = _collect_evidence(context)
    membership = [
        item for item in evidence if item.evidence_type in _MEMBERSHIP_EVIDENCE_TYPES
    ]
    valid = [
        item
        for item in membership
        if item.polarity == "supporting"
        and _membership_valid_for_year(item, context.paper.year)
    ]
    invalid_or_conflicting = [
        item
        for item in membership
        if item.temporal_validity.status in {"invalid", "conflicting"}
    ]
    if valid and not invalid_or_conflicting:
        decision = AttributionDecisionResult(
            decision="ATTRIBUTED",
            relevance_label=_relevance_label(context.paper),
            confidence=max(item.confidence for item in valid),
            authority="machine_provisional",
            policy_version=context.request.policy_version,
            supporting_evidence_ids=[item.evidence_id for item in valid],
            contradicting_evidence_ids=[],
        )
        return (
            "succeeded",
            _packet(context, evidence, decision),
            MembershipVerificationOutcome(
                outcome_type="membership_verification",
                verified=True,
                publication_year=context.paper.year,
                valid_membership_evidence_ids=[item.evidence_id for item in valid],
            ),
            [
                "verify_membership_at_publication_time",
                "validate_membership_interval_against_publication_year",
            ],
        )

    ambiguities: list[str] = []
    if context.paper.year is None:
        ambiguities.append("The publication year is missing.")
    if not membership:
        ambiguities.append("No membership evidence is recorded.")
    if membership and not valid:
        ambiguities.append(
            "Membership evidence has no valid interval covering the publication year."
        )
    if invalid_or_conflicting:
        ambiguities.append("Membership temporal evidence is invalid or conflicting.")
    decision = _review_decision(
        context,
        evidence,
        ambiguities=ambiguities,
        action=(
            "Obtain a dated membership, institution, or project record covering "
            "the paper's work/publication period, then rerun this Skill."
        ),
    )
    return (
        "review_required",
        _packet(context, evidence, decision),
        MembershipVerificationOutcome(
            outcome_type="membership_verification",
            verified=False,
            publication_year=context.paper.year,
            ambiguities=ambiguities,
        ),
        [
            "verify_membership_at_publication_time",
            "fail_closed_on_missing_or_conflicting_interval",
        ],
    )


def _handle_disagreement(
    context: _SkillContext,
) -> tuple[
    Literal["succeeded", "review_required"],
    AttributionEvidencePacket,
    AttributionSkillOutcome,
    list[str],
]:
    evidence = _collect_evidence(context)
    if not _has_evidence_conflict(context, evidence):
        return (
            "succeeded",
            _packet(context, evidence),
            ClassifierDisagreementOutcome(
                outcome_type="classifier_disagreement",
                disagreement_detected=False,
                adjudicated=True,
            ),
            ["adjudicate_classifier_disagreement", "no_disagreement_detected"],
        )
    if context.paper.ac_known_publication:
        return (
            "succeeded",
            _packet(context, evidence, _gold_decision(context, evidence)),
            ClassifierDisagreementOutcome(
                outcome_type="classifier_disagreement",
                disagreement_detected=True,
                adjudicated=True,
            ),
            [
                "adjudicate_classifier_disagreement",
                "apply_curated_gold_authority",
                "retain_contradicting_evidence",
            ],
        )
    decision = _review_decision(
        context,
        evidence,
        ambiguities=[
            "Classifier or evidence dimensions disagree and no higher authority resolves them."
        ],
        action=(
            "Review the cited supporting and contradicting spans; record a human "
            "decision and disagreement type before rerunning attribution."
        ),
    )
    return (
        "review_required",
        _packet(context, evidence, decision),
        ClassifierDisagreementOutcome(
            outcome_type="classifier_disagreement",
            disagreement_detected=True,
            adjudicated=False,
            ambiguities=list(decision.unresolved_ambiguities),
        ),
        ["adjudicate_classifier_disagreement", "route_conflict_to_human_review"],
    )


def _handle_determine(
    context: _SkillContext,
) -> tuple[
    Literal["succeeded", "review_required"],
    AttributionEvidencePacket,
    AttributionSkillOutcome,
    list[str],
]:
    evidence = _collect_evidence(context)
    if context.paper.ac_known_publication:
        decision = _gold_decision(context, evidence)
        return (
            "succeeded",
            _packet(context, evidence, decision),
            AttributionDeterminationOutcome(
                outcome_type="attribution_determination",
                decision=decision.decision,
            ),
            [
                "determine_ac_paper_attribution",
                "apply_curated_gold_authority",
                "retain_conflicts",
            ],
        )

    direct = [
        item
        for item in evidence
        if item.polarity == "supporting"
        and (
            item.evidence_type in _DIRECT_ATTRIBUTION_EVIDENCE_TYPES
            or (
                item.evidence_type in _MEMBERSHIP_EVIDENCE_TYPES
                and _membership_valid_for_year(item, context.paper.year)
            )
        )
    ]
    if direct and not _has_evidence_conflict(context, evidence):
        decision = AttributionDecisionResult(
            decision="ATTRIBUTED",
            relevance_label=_relevance_label(context.paper),
            confidence=max(item.confidence for item in direct),
            authority="machine_provisional",
            policy_version=context.request.policy_version,
            supporting_evidence_ids=[item.evidence_id for item in direct],
            contradicting_evidence_ids=[],
        )
        return (
            "succeeded",
            _packet(context, evidence, decision),
            AttributionDeterminationOutcome(
                outcome_type="attribution_determination",
                decision=decision.decision,
            ),
            [
                "determine_ac_paper_attribution",
                "apply_direct_ac_evidence_policy",
            ],
        )

    ambiguities = []
    if not direct:
        ambiguities.append(
            "No curated gold record, explicit AC acknowledgement/program, "
            "or temporally valid membership evidence establishes attribution."
        )
    if _has_evidence_conflict(context, evidence):
        ambiguities.append("Supporting and contradicting evidence remain unresolved.")
    decision = _review_decision(
        context,
        evidence,
        ambiguities=ambiguities,
        action=(
            "Review direct AC provenance and dated relationship evidence; do not "
            "infer NOT_ATTRIBUTED from missing metadata alone."
        ),
    )
    return (
        "review_required",
        _packet(context, evidence, decision),
        AttributionDeterminationOutcome(
            outcome_type="attribution_determination",
            decision=decision.decision,
        ),
        ["determine_ac_paper_attribution", "fail_closed_to_human_review"],
    )


_HANDLERS: dict[
    AttributionReadSkillName,
    Callable[
        [_SkillContext],
        tuple[
            Literal["succeeded", "review_required"],
            AttributionEvidencePacket,
            AttributionSkillOutcome,
            list[str],
        ],
    ],
] = {
    "determine_ac_paper_attribution": _handle_determine,
    "resolve_ambiguous_author_identity": _handle_identity,
    "verify_membership_at_publication_time": _handle_membership,
    "collect_auditable_attribution_evidence": _handle_collect,
    "adjudicate_classifier_disagreement": _handle_disagreement,
}


def attribution_skill_catalog() -> AttributionSkillCatalog:
    return AttributionSkillCatalog(read_skills=list(READ_SKILL_NAMES))


def _persist_invocation(
    session: Session,
    *,
    request: AttributionSkillInvokeRequest,
    request_hash: str,
    snapshot: dict,
    invocation: AttributionSkillInvocation,
) -> AttributionSkillInvocation:
    decision = (
        invocation.output_packet.decision
        if invocation.output_packet is not None
        else None
    )
    session.add(
        AttributionSkillInvocationRecord(
            invocation_id=invocation.invocation_id,
            paper_id=invocation.paper_id,
            skill_name=invocation.skill_name,
            skill_version=invocation.skill_version,
            policy_version=invocation.policy_version,
            status=invocation.status,
            input_snapshot_id=invocation.input_snapshot_id,
            input_content_hash=invocation.input_content_hash,
            request_hash=request_hash,
            request_json=request.model_dump(mode="json"),
            input_snapshot=snapshot,
            invocation_json=invocation.model_dump(mode="json"),
            decision=decision.decision if decision else None,
            final_confidence=decision.confidence if decision else None,
            failure_category=(
                invocation.failure.category if invocation.failure else None
            ),
            retrieval_api_calls=invocation.cost.retrieval_api_calls,
            fulltext_retrieval_status=(invocation.cost.fulltext_retrieval_status),
            extraction_seconds=invocation.cost.extraction_seconds,
            model_calls=invocation.cost.model_calls,
            input_tokens=invocation.cost.input_tokens,
            output_tokens=invocation.cost.output_tokens,
            estimated_cost_usd=invocation.cost.estimated_cost_usd,
            graph_queries=invocation.cost.graph_queries,
            human_review_seconds=invocation.cost.human_review_seconds,
            retries=invocation.cost.retries,
            resolution_path=list(invocation.resolution_path),
        )
    )
    return invocation


def get_recorded_attribution_invocation(
    session: Session, invocation_id: str
) -> AttributionSkillInvocation:
    record = session.get(AttributionSkillInvocationRecord, invocation_id)
    if record is None:
        raise InvocationNotFoundError(invocation_id)
    return _validate_stored_invocation(record.invocation_json)


def replay_matching_attribution_invocation(
    session: Session,
    request: AttributionSkillInvokeRequest,
) -> AttributionSkillInvocation:
    """Replay only when a commit race stored the exact same request."""
    record = session.get(
        AttributionSkillInvocationRecord,
        request.invocation_id,
    )
    if record is None:
        raise InvocationNotFoundError(request.invocation_id)
    if record.request_hash != _sha256(request.model_dump(mode="json")):
        raise InvocationConflictError(
            "invocation_id already exists for a different request"
        )
    return _validate_stored_invocation(record.invocation_json)


def _decode_stored_v01(value: dict) -> AttributionSkillInvocation:
    return AttributionSkillInvocation.model_validate_json(_canonical_json(value))


_STORED_INVOCATION_DECODERS: dict[str, Callable[[dict], AttributionSkillInvocation]] = {
    ATTRIBUTION_SKILL_CONTRACT_VERSION: _decode_stored_v01,
}


def _validate_stored_invocation(value: dict) -> AttributionSkillInvocation:
    """Decode immutable history through its frozen contract version."""
    contract_version = value.get("contract_version")
    decoder = _STORED_INVOCATION_DECODERS.get(contract_version)
    if decoder is None:
        raise UnsupportedStoredContractError(
            f"Unsupported stored attribution contract: {contract_version!r}"
        )
    return decoder(value)


def _assert_clean_session(session: Session) -> None:
    if session.new or session.dirty or session.deleted:
        raise AttributionSkillSessionError(
            "Attribution Skill invocation requires a clean SQLAlchemy session."
        )


def _prepare_snapshot_transaction(session: Session) -> None:
    """Use one PostgreSQL MVCC snapshot for all evidence materialization."""
    _assert_clean_session(session)
    if session.get_bind().dialect.name != "postgresql":
        return
    if session.in_transaction():
        raise AttributionSkillSessionError(
            "PostgreSQL attribution invocation requires a fresh transaction."
        )
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def _budget_exhaustion_detail(
    budget: AttributionInvocationBudget,
    cost: AttributionCostSummary,
    *,
    elapsed: float,
) -> str | None:
    checks = (
        (
            "wall seconds",
            elapsed,
            budget.max_wall_seconds,
        ),
        (
            "retrieval API calls",
            cost.retrieval_api_calls,
            budget.max_retrieval_api_calls,
        ),
        ("model calls", cost.model_calls, budget.max_model_calls),
        ("input tokens", cost.input_tokens, budget.max_input_tokens),
        (
            "estimated cost USD",
            cost.estimated_cost_usd,
            budget.max_estimated_cost_usd,
        ),
    )
    for name, actual, maximum in checks:
        if maximum is not None and actual > maximum:
            return f"{name} {actual} exceeded configured maximum {maximum}."
    return None


def invoke_attribution_skill(
    session: Session,
    request: AttributionSkillInvokeRequest,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> AttributionSkillInvocation:
    """Run one Skill once, or replay the immutable record for the same nonce."""
    _prepare_snapshot_transaction(session)
    request_json = request.model_dump(mode="json")
    request_hash = _sha256(request_json)
    existing = session.get(AttributionSkillInvocationRecord, request.invocation_id)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise InvocationConflictError(
                "invocation_id already exists for a different request"
            )
        return _validate_stored_invocation(existing.invocation_json)

    paper = session.get(Paper, request.paper_id)
    if paper is None:
        session.rollback()
        raise PaperNotFoundError(request.paper_id)

    started_at = datetime.now(UTC)
    start_clock = monotonic()
    context: _SkillContext | None = None
    try:
        context = _build_context(
            session,
            request,
            paper,
            generated_at=started_at,
        )
        status, packet, outcome, handler_path = _HANDLERS[request.skill_name](context)
        _assert_clean_session(session)
        elapsed = max(0.0, monotonic() - start_clock)
        cost = AttributionCostSummary(extraction_seconds=elapsed)
        budget_failure = _budget_exhaustion_detail(
            request.budget,
            cost,
            elapsed=elapsed,
        )
        if budget_failure is not None:
            invocation = AttributionSkillInvocation(
                invocation_id=request.invocation_id,
                skill_name=request.skill_name,
                skill_version=SKILL_VERSION,
                policy_version=request.policy_version,
                status="budget_exhausted",
                paper_id=paper.id,
                input_snapshot_id=context.snapshot_id,
                input_content_hash=context.content_hash,
                invocation_reason=request.invocation_reason,
                budget=request.budget,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                failure=AttributionFailure(
                    stage="system",
                    category="budget_exhausted",
                    detail=budget_failure,
                    retryable=False,
                ),
                cost=cost,
                resolution_path=[
                    "verify_invocation_nonce",
                    "build_input_snapshot",
                    *handler_path,
                    "fail_closed_on_wall_budget",
                ],
            )
        else:
            invocation = AttributionSkillInvocation(
                invocation_id=request.invocation_id,
                skill_name=request.skill_name,
                skill_version=SKILL_VERSION,
                policy_version=request.policy_version,
                status=status,
                paper_id=paper.id,
                input_snapshot_id=context.snapshot_id,
                input_content_hash=context.content_hash,
                invocation_reason=request.invocation_reason,
                budget=request.budget,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                output_packet=packet,
                skill_outcome=outcome,
                cost=cost,
                resolution_path=[
                    "verify_invocation_nonce",
                    "build_input_snapshot",
                    *handler_path,
                    "persist_replay_record",
                ],
            )
    except Exception as exc:
        if isinstance(
            exc,
            (
                InvocationConflictError,
                PaperNotFoundError,
                InvocationNotFoundError,
            ),
        ):
            raise
        snapshot = (
            context.snapshot if context is not None else _fallback_snapshot(paper, exc)
        )
        snapshot_id = (
            context.snapshot_id
            if context is not None
            else f"pas-paper-snapshot:{_sha256(snapshot)[:24]}"
        )
        session.rollback()
        content_hash = _sha256(snapshot)
        failed = AttributionSkillInvocation(
            invocation_id=request.invocation_id,
            skill_name=request.skill_name,
            skill_version=SKILL_VERSION,
            policy_version=request.policy_version,
            status="failed",
            paper_id=paper.id,
            input_snapshot_id=snapshot_id,
            input_content_hash=content_hash,
            invocation_reason=request.invocation_reason,
            budget=request.budget,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            failure=AttributionFailure(
                stage="system",
                category="internal_error",
                detail=(f"{type(exc).__name__}: attribution Skill execution failed."),
                retryable=False,
            ),
            cost=AttributionCostSummary(),
            resolution_path=[
                "verify_invocation_nonce",
                *(
                    ["build_input_snapshot"]
                    if context is not None
                    else ["fail_to_build_input_snapshot"]
                ),
                "fail_closed_on_runtime_error",
                "persist_replay_record",
            ],
        )
        invocation = failed
    return _persist_invocation(
        session,
        request=request,
        request_hash=request_hash,
        snapshot=(snapshot if invocation.status == "failed" else context.snapshot),
        invocation=invocation,
    )
