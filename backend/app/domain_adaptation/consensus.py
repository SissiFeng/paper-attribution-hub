"""Source-grounded, multi-teacher consensus without pretending silver is gold."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from app.domain_adaptation.models import DomainModel, EvidenceScope, ProtocolUnit


PerturbationStatus = Literal["not_tested", "passed", "failed"]
ConsensusTier = Literal["A", "B", "C"]
ConsensusDecisionType = Literal["accepted_silver", "disputed", "abstained"]
PerturbationType = Literal["evidence_deletion", "numeric_replacement"]
PerturbationExpectedBehavior = Literal[
    "omit_or_abstain",
    "extract_replacement",
]
SourceValueOccurrence = Literal[
    "exact_unique",
    "ambiguous",
    "not_exact",
    "unlocated",
]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:16]}"


def normalize_consensus_value(value: str) -> str:
    """Normalize presentation only; never add scientific domain knowledge."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("\u00ad", "")
    normalized = re.sub(r"[‐‑‒–—―−﹘﹣－]", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


class ProposalEvidence(DomainModel):
    evidence_id: str
    source_chunk_id: str
    quote: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    document_char_start: int | None = Field(default=None, ge=0)
    document_char_end: int | None = Field(default=None, ge=0)
    source_sha256: str


class ModelFieldProposal(DomainModel):
    schema_version: str = "domain-teacher-field-proposal-v0.2"
    model_alias: str
    model_family: str
    model_id: str
    paper_id: str
    evidence_scope: EvidenceScope
    protocol_name: str
    entity_type: str
    entity_key: str
    field_name: str
    field_path: str
    source_value: str
    source_value_occurrence: SourceValueOccurrence = "unlocated"
    source_value_char_start: int | None = Field(default=None, ge=0)
    source_value_char_end: int | None = Field(default=None, gt=0)
    evidence: ProposalEvidence | None = None
    evidence_valid: bool
    validation_reason: str | None = None
    perturbation_status: PerturbationStatus = "not_tested"

    @model_validator(mode="after")
    def valid_evidence_is_present(self) -> "ModelFieldProposal":
        if self.evidence_valid and self.evidence is None:
            raise ValueError("Evidence-valid proposals require an evidence locator")
        if self.source_value_occurrence == "exact_unique":
            if (
                self.evidence is None
                or self.source_value_char_start is None
                or self.source_value_char_end is None
            ):
                raise ValueError("Exact source values require quote-relative offsets")
            if (
                self.evidence.quote[
                    self.source_value_char_start : self.source_value_char_end
                ]
                != self.source_value
            ):
                raise ValueError("Source-value offsets do not match source_value")
        elif (
            self.source_value_char_start is not None
            or self.source_value_char_end is not None
        ):
            raise ValueError("Only exact-unique source values may have offsets")
        return self


class ConsensusAlternative(DomainModel):
    normalized_value: str
    source_values: list[str]
    supporting_model_aliases: list[str]
    supporting_model_families: list[str]
    evidence_ids: list[str]


class ConsensusDecision(DomainModel):
    schema_version: str = "domain-teacher-consensus-decision-v0.1"
    decision_id: str
    slot_id: str
    paper_id: str
    evidence_scope: EvidenceScope
    entity_type: str
    entity_key: str
    field_name: str
    decision: ConsensusDecisionType
    tier: ConsensusTier
    normalized_value: str | None = None
    source_values: list[str] = Field(default_factory=list)
    supporting_model_aliases: list[str] = Field(default_factory=list)
    supporting_model_families: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    alternatives: list[ConsensusAlternative] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    training_eligible: bool = False


class ConsensusReport(DomainModel):
    schema_version: str = "domain-teacher-consensus-report-v0.1"
    proposal_count: int = Field(ge=0)
    slot_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    disputed_count: int = Field(ge=0)
    abstained_count: int = Field(ge=0)
    claims_boundary: str = (
        "Consensus silver is not human gold and does not establish scientific "
        "precision or recall."
    )


class SourceGroundedConsensus(DomainModel):
    schema_version: str = "domain-teacher-source-grounded-consensus-v0.1"
    accepted: list[ConsensusDecision]
    disputed: list[ConsensusDecision]
    abstained: list[ConsensusDecision]
    report: ConsensusReport


class ClaimPerturbationCase(DomainModel):
    schema_version: str = "domain-teacher-claim-perturbation-case-v0.2"
    case_id: str
    claim_key: str
    decision_id: str
    perturbation_type: PerturbationType
    expected_behavior: PerturbationExpectedBehavior
    target_model_aliases: list[str] = Field(min_length=2)
    paper_id: str
    source_chunk_id: str
    entity_type: str
    entity_key: str
    field_name: str
    original_source_value: str
    source_value_char_start: int | None = Field(default=None, ge=0)
    source_value_char_end: int | None = Field(default=None, gt=0)
    expected_source_value: str | None = None
    original_quote: str
    mutated_quote: str


class ModelClaimPerturbationResult(DomainModel):
    schema_version: str = "domain-teacher-claim-perturbation-result-v0.1"
    model_alias: str
    decision_id: str
    evidence_deletion_passed: bool
    numeric_replacement_passed: bool | None = None


def _slot_parts(proposal: ModelFieldProposal) -> tuple[str, ...]:
    source_chunk_id = (
        proposal.evidence.source_chunk_id if proposal.evidence is not None else ""
    )
    return (
        proposal.paper_id,
        proposal.evidence_scope,
        source_chunk_id,
        proposal.entity_type,
        normalize_consensus_value(proposal.entity_key),
        proposal.field_name,
    )


def proposal_claim_key(proposal: ModelFieldProposal) -> str:
    """Return a model-neutral exact claim identity for pairwise audits."""
    return _stable_id(
        "claim",
        *_slot_parts(proposal),
        normalize_consensus_value(proposal.source_value),
    )


def _numeric_replacement(value: str) -> str | None:
    match = re.search(r"(?<![\w.])(\d+(?:\.\d+)?)", value)
    if match is None:
        return None
    original = match.group(1)
    number = Decimal(original)
    if "." in original:
        increment = Decimal(1).scaleb(-(len(original) - original.index(".") - 1))
        replacement = format(number + increment, "f")
    else:
        replacement = str(int(number) + 1)
    return value[: match.start(1)] + replacement + value[match.end(1) :]


def _unique_exact_value_span(
    value: str, quote: str
) -> tuple[SourceValueOccurrence, int | None, int | None]:
    starts: list[int] = []
    cursor = 0
    while True:
        start = quote.find(value, cursor)
        if start < 0:
            break
        starts.append(start)
        cursor = start + max(len(value), 1)
    if not starts:
        return "not_exact", None, None
    if len(starts) > 1:
        return "ambiguous", None, None
    return "exact_unique", starts[0], starts[0] + len(value)


def _proposal_source_value_span(
    proposal: ModelFieldProposal,
) -> tuple[int, int] | None:
    if proposal.evidence is None:
        return None
    if proposal.source_value_occurrence == "exact_unique":
        if (
            proposal.source_value_char_start is None
            or proposal.source_value_char_end is None
        ):
            return None
        return proposal.source_value_char_start, proposal.source_value_char_end
    occurrence, start, end = _unique_exact_value_span(
        proposal.source_value, proposal.evidence.quote
    )
    if occurrence != "exact_unique" or start is None or end is None:
        return None
    return start, end


def _proposal_numeric_replacement(
    proposal: ModelFieldProposal,
) -> str | None:
    if proposal.entity_type == "steps" and not proposal.field_name.startswith(
        "param:"
    ):
        return None
    return _numeric_replacement(proposal.source_value)


def generate_perturbation_cases(
    *,
    proposals: list[ModelFieldProposal],
    decisions: list[ConsensusDecision],
) -> list[ClaimPerturbationCase]:
    """Compile source edits for consensus claims awaiting falsification."""
    proposals_by_evidence_id: dict[str, list[ModelFieldProposal]] = defaultdict(list)
    for proposal in proposals:
        if proposal.evidence is not None and proposal.evidence_valid:
            proposals_by_evidence_id[proposal.evidence.evidence_id].append(proposal)
    cases: list[ClaimPerturbationCase] = []
    for decision in sorted(decisions, key=lambda item: item.decision_id):
        if decision.reasons != ["perturbation_not_verified"]:
            continue
        alternative = decision.alternatives[0]
        representative_with_span = next(
            (
                (proposal, value_span)
                for evidence_id in alternative.evidence_ids
                for proposal in proposals_by_evidence_id[evidence_id]
                for value_span in [_proposal_source_value_span(proposal)]
                if proposal.entity_type == decision.entity_type
                and normalize_consensus_value(proposal.entity_key)
                == normalize_consensus_value(decision.entity_key)
                and proposal.field_name == decision.field_name
                and normalize_consensus_value(proposal.source_value)
                == alternative.normalized_value
                and proposal.evidence is not None
                and value_span is not None
            ),
            None,
        )
        if representative_with_span is None:
            continue
        representative, value_span = representative_with_span
        if representative.evidence is None:
            continue
        value_start, value_end = value_span
        claim_key = _stable_id(
            "claim",
            decision.decision_id,
            alternative.normalized_value,
        )
        original_value = representative.source_value
        original_quote = representative.evidence.quote
        deletion_quote = original_quote[:value_start] + original_quote[value_end:]
        cases.append(
            ClaimPerturbationCase(
                case_id=_stable_id(
                    "perturb", decision.decision_id, "evidence_deletion"
                ),
                claim_key=claim_key,
                decision_id=decision.decision_id,
                perturbation_type="evidence_deletion",
                expected_behavior="omit_or_abstain",
                target_model_aliases=alternative.supporting_model_aliases,
                paper_id=representative.paper_id,
                source_chunk_id=representative.evidence.source_chunk_id,
                entity_type=representative.entity_type,
                entity_key=representative.entity_key,
                field_name=representative.field_name,
                original_source_value=original_value,
                source_value_char_start=value_start,
                source_value_char_end=value_end,
                original_quote=original_quote,
                mutated_quote=deletion_quote,
            )
        )
        replacement_value = _proposal_numeric_replacement(representative)
        if replacement_value is not None:
            cases.append(
                ClaimPerturbationCase(
                    case_id=_stable_id(
                        "perturb", decision.decision_id, "numeric_replacement"
                    ),
                    claim_key=claim_key,
                    decision_id=decision.decision_id,
                    perturbation_type="numeric_replacement",
                    expected_behavior="extract_replacement",
                    target_model_aliases=alternative.supporting_model_aliases,
                    paper_id=representative.paper_id,
                    source_chunk_id=representative.evidence.source_chunk_id,
                    entity_type=representative.entity_type,
                    entity_key=representative.entity_key,
                    field_name=representative.field_name,
                    original_source_value=original_value,
                    source_value_char_start=value_start,
                    source_value_char_end=value_end,
                    expected_source_value=replacement_value,
                    original_quote=original_quote,
                    mutated_quote=(
                        original_quote[:value_start]
                        + replacement_value
                        + original_quote[value_end:]
                    ),
                )
            )
    perturbation_order = {"evidence_deletion": 0, "numeric_replacement": 1}
    return sorted(
        cases,
        key=lambda item: (
            item.decision_id,
            perturbation_order[item.perturbation_type],
        ),
    )


def apply_perturbation_results(
    proposals: list[ModelFieldProposal],
    *,
    decisions: list[ConsensusDecision],
    results: list[ModelClaimPerturbationResult],
) -> list[ModelFieldProposal]:
    """Attach model-specific falsification outcomes without changing claims."""
    decision_by_id = {item.decision_id: item for item in decisions}
    if len(decision_by_id) != len(decisions):
        raise ValueError("Perturbation decisions contain duplicate IDs")
    by_model_decision: dict[tuple[str, str], ModelClaimPerturbationResult] = {}
    for result in results:
        if result.decision_id not in decision_by_id:
            raise ValueError(f"Unknown perturbation decision: {result.decision_id}")
        key = (result.model_alias, result.decision_id)
        if key in by_model_decision:
            raise ValueError("Perturbation results contain duplicate model claims")
        by_model_decision[key] = result
    updated: list[ModelFieldProposal] = []
    for proposal in proposals:
        matching_decisions = [
            decision
            for decision in decisions
            if _proposal_matches_decision(proposal, decision)
        ]
        matching_results = [
            by_model_decision[(proposal.model_alias, decision.decision_id)]
            for decision in matching_decisions
            if (proposal.model_alias, decision.decision_id) in by_model_decision
        ]
        if len(matching_results) > 1:
            raise ValueError(
                "One model proposal matched multiple perturbation decisions"
            )
        matched_result = next(iter(matching_results), None)
        if matched_result is None:
            updated.append(proposal)
            continue
        numeric_case_required = (
            _proposal_numeric_replacement(proposal) is not None
        )
        passed = matched_result.evidence_deletion_passed and (
            matched_result.numeric_replacement_passed is True
            if numeric_case_required
            else matched_result.numeric_replacement_passed is not False
        )
        updated.append(
            proposal.model_copy(
                update={"perturbation_status": "passed" if passed else "failed"}
            )
        )
    return updated


def _proposal_matches_decision(
    proposal: ModelFieldProposal,
    decision: ConsensusDecision,
) -> bool:
    if proposal.evidence is None or not proposal.evidence_valid:
        return False
    if not decision.alternatives:
        return False
    alternative = decision.alternatives[0]
    return (
        proposal.evidence.evidence_id in alternative.evidence_ids
        and proposal.entity_type == decision.entity_type
        and normalize_consensus_value(proposal.entity_key)
        == normalize_consensus_value(decision.entity_key)
        and proposal.field_name == decision.field_name
        and normalize_consensus_value(proposal.source_value)
        == alternative.normalized_value
    )


def _alternative(proposals: list[ModelFieldProposal]) -> ConsensusAlternative:
    return ConsensusAlternative(
        normalized_value=normalize_consensus_value(proposals[0].source_value),
        source_values=sorted({item.source_value for item in proposals}),
        supporting_model_aliases=sorted({item.model_alias for item in proposals}),
        supporting_model_families=sorted({item.model_family for item in proposals}),
        evidence_ids=sorted(
            {
                item.evidence.evidence_id
                for item in proposals
                if item.evidence is not None
            }
        ),
    )


def _evidence_spans_overlap(proposals: list[ModelFieldProposal]) -> bool:
    evidence = [item.evidence for item in proposals if item.evidence is not None]
    if not evidence:
        return False
    return max(item.char_start for item in evidence) < min(
        item.char_end for item in evidence
    )


def _occurrence_slots(
    proposals: list[ModelFieldProposal],
) -> list[tuple[tuple[str, ...], list[ModelFieldProposal]]]:
    """Separate repeated entity occurrences by overlapping source intervals."""
    by_base: dict[tuple[str, ...], list[ModelFieldProposal]] = defaultdict(list)
    for proposal in proposals:
        by_base[_slot_parts(proposal)].append(proposal)

    slots: list[tuple[tuple[str, ...], list[ModelFieldProposal]]] = []
    for base_parts, base_proposals in sorted(by_base.items()):
        unsupported = [
            item for item in base_proposals if not item.evidence_valid
        ]
        if unsupported:
            slots.append(((*base_parts, "unsupported"), unsupported))
        valid = sorted(
            (item for item in base_proposals if item.evidence_valid),
            key=lambda item: (
                item.evidence.char_start if item.evidence is not None else -1,
                item.evidence.char_end if item.evidence is not None else -1,
                item.model_alias,
            ),
        )
        clusters: list[list[ModelFieldProposal]] = []
        for proposal in valid:
            if proposal.evidence is None:
                continue
            matching = [
                index
                for index, cluster in enumerate(clusters)
                if any(
                    item.evidence is not None
                    and proposal.evidence.char_start < item.evidence.char_end
                    and item.evidence.char_start < proposal.evidence.char_end
                    for item in cluster
                )
            ]
            if not matching:
                clusters.append([proposal])
                continue
            merged = [proposal]
            for index in reversed(matching):
                merged.extend(clusters.pop(index))
            clusters.append(merged)
        for cluster in clusters:
            evidence = [item.evidence for item in cluster if item.evidence is not None]
            slots.append(
                (
                    (
                        *base_parts,
                        str(min(item.char_start for item in evidence)),
                        str(max(item.char_end for item in evidence)),
                    ),
                    cluster,
                )
            )
    return sorted(slots, key=lambda item: item[0])


def build_source_grounded_consensus(
    proposals: list[ModelFieldProposal],
    *,
    min_family_agreement: int = 2,
) -> SourceGroundedConsensus:
    """Accept only stable, evidence-valid agreement from independent families."""
    if min_family_agreement < 2:
        raise ValueError("At least two independent model families are required")
    slots = _occurrence_slots(proposals)

    accepted: list[ConsensusDecision] = []
    disputed: list[ConsensusDecision] = []
    abstained: list[ConsensusDecision] = []
    for slot_parts, slot_proposals in slots:
        valid = [item for item in slot_proposals if item.evidence_valid]
        by_value: dict[str, list[ModelFieldProposal]] = defaultdict(list)
        for proposal in valid:
            by_value[normalize_consensus_value(proposal.source_value)].append(
                proposal
            )
        alternatives = sorted(
            (_alternative(items) for items in by_value.values()),
            key=lambda item: (-len(item.supporting_model_families), item.normalized_value),
        )
        if not alternatives:
            slot_id = _stable_id("slot", *slot_parts)
            abstained.append(
                ConsensusDecision(
                    decision_id=_stable_id("consensus", slot_id, "abstained"),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="abstained",
                    tier="C",
                    alternatives=[_alternative(slot_proposals)],
                    reasons=["no_deterministically_valid_evidence"],
                )
            )
            continue
        winner = alternatives[0]
        if (
            len(alternatives) == 1
            and len(winner.supporting_model_families) >= min_family_agreement
            and _evidence_spans_overlap(valid)
            and all(item.perturbation_status == "passed" for item in valid)
        ):
            slot_id = _stable_id("slot", *slot_parts)
            accepted.append(
                ConsensusDecision(
                    decision_id=_stable_id(
                        "consensus", slot_id, winner.normalized_value
                    ),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="accepted_silver",
                    tier="A",
                    normalized_value=winner.normalized_value,
                    source_values=winner.source_values,
                    supporting_model_aliases=winner.supporting_model_aliases,
                    supporting_model_families=winner.supporting_model_families,
                    evidence_ids=winner.evidence_ids,
                    alternatives=alternatives,
                    reasons=["independent_source_grounded_consensus"],
                    training_eligible=True,
                )
            )
            continue
        if len(alternatives) > 1:
            slot_id = _stable_id("slot", *slot_parts)
            disputed.append(
                ConsensusDecision(
                    decision_id=_stable_id("consensus", slot_id, "disputed"),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="disputed",
                    tier="B",
                    alternatives=alternatives,
                    reasons=["valid_value_contradiction"],
                )
            )
            continue
        if len(winner.supporting_model_families) < min_family_agreement:
            slot_id = _stable_id("slot", *slot_parts)
            disputed.append(
                ConsensusDecision(
                    decision_id=_stable_id("consensus", slot_id, "disputed"),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="disputed",
                    tier="B",
                    alternatives=alternatives,
                    reasons=["insufficient_independent_families"],
                )
            )
            continue
        if not _evidence_spans_overlap(valid):
            slot_id = _stable_id("slot", *slot_parts)
            disputed.append(
                ConsensusDecision(
                    decision_id=_stable_id("consensus", slot_id, "disputed"),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="disputed",
                    tier="B",
                    alternatives=alternatives,
                    reasons=["evidence_spans_do_not_overlap"],
                )
            )
            continue
        if not all(item.perturbation_status == "passed" for item in valid):
            reason = (
                "perturbation_failed"
                if any(item.perturbation_status == "failed" for item in valid)
                else "perturbation_not_verified"
            )
            slot_id = _stable_id("slot", *slot_parts)
            disputed.append(
                ConsensusDecision(
                    decision_id=_stable_id("consensus", slot_id, "disputed"),
                    slot_id=slot_id,
                    paper_id=slot_proposals[0].paper_id,
                    evidence_scope=slot_proposals[0].evidence_scope,
                    entity_type=slot_proposals[0].entity_type,
                    entity_key=slot_proposals[0].entity_key,
                    field_name=slot_proposals[0].field_name,
                    decision="disputed",
                    tier="B",
                    alternatives=alternatives,
                    reasons=[reason],
                )
            )

    report = ConsensusReport(
        proposal_count=len(proposals),
        slot_count=len(slots),
        accepted_count=len(accepted),
        disputed_count=len(disputed),
        abstained_count=len(abstained),
    )
    return SourceGroundedConsensus(
        accepted=accepted,
        disputed=disputed,
        abstained=abstained,
        report=report,
    )


def load_model_proposals_from_package(
    package_dir: str | Path,
    *,
    model_alias: str,
    model_family: str,
) -> list[ModelFieldProposal]:
    """Project deterministically validated package fields into blind proposals."""
    package = Path(package_dir)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    extraction = manifest.get("extraction", {})
    if extraction.get("mode") != "teacher":
        raise ValueError("Consensus inputs must come from teacher-model packages")
    model_id = str(extraction.get("model") or "")
    if not model_id:
        raise ValueError("Teacher package manifest is missing its model ID")

    protocols: list[ProtocolUnit] = []
    for line in (package / "knowledge/protocols.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        payload.pop("schema_version", None)
        protocols.append(ProtocolUnit.model_validate(payload))

    proposals: list[ModelFieldProposal] = []
    for protocol in protocols:
        evidence_by_id = {item.evidence_id: item for item in protocol.evidence}

        def append_fields(
            *,
            entity_type: str,
            entity_id: str,
            entity_key: str,
            values: list[tuple[str, str | None]],
            evidence_ids: list[str],
        ) -> None:
            evidence = next(
                (
                    evidence_by_id[evidence_id]
                    for evidence_id in evidence_ids
                    if evidence_id in evidence_by_id
                ),
                None,
            )
            if evidence is None:
                return
            locator = ProposalEvidence(
                evidence_id=evidence.evidence_id,
                source_chunk_id=evidence.chunk_id,
                quote=evidence.quote,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
                document_char_start=evidence.document_char_start,
                document_char_end=evidence.document_char_end,
                source_sha256=evidence.source_sha256,
            )
            for field_name, value in values:
                if value is None:
                    continue
                occurrence, value_start, value_end = _unique_exact_value_span(
                    value, locator.quote
                )
                proposals.append(
                    ModelFieldProposal(
                        model_alias=model_alias,
                        model_family=model_family,
                        model_id=model_id,
                        paper_id=protocol.paper_id,
                        evidence_scope=protocol.evidence_scope,
                        protocol_name=protocol.protocol_name,
                        entity_type=entity_type,
                        entity_key=entity_key,
                        field_name=field_name,
                        field_path=(
                            f"{protocol.protocol_id}/{entity_type}/"
                            f"{entity_id}/{field_name}"
                        ),
                        source_value=value,
                        source_value_occurrence=occurrence,
                        source_value_char_start=value_start,
                        source_value_char_end=value_end,
                        evidence=locator,
                        evidence_valid=True,
                    )
                )

        for material in protocol.materials:
            append_fields(
                entity_type="materials",
                entity_id=material.entity_id,
                entity_key=material.name,
                values=[
                    ("name", material.name),
                    ("role", material.role),
                    ("amount", material.amount),
                    ("purity", material.purity),
                    ("supplier", material.supplier),
                    ("pretreatment", material.pretreatment),
                ],
                evidence_ids=material.evidence_ids,
            )
        for instrument in protocol.instruments:
            append_fields(
                entity_type="instruments",
                entity_id=instrument.entity_id,
                entity_key=instrument.name,
                values=[
                    ("name", instrument.name),
                    ("model", instrument.model),
                    ("manufacturer", instrument.manufacturer),
                    *[
                        (f"setting:{normalize_consensus_value(key)}", value)
                        for key, value in sorted(instrument.settings.items())
                    ],
                ],
                evidence_ids=instrument.evidence_ids,
            )
        for software in protocol.software:
            append_fields(
                entity_type="software",
                entity_id=software.entity_id,
                entity_key=software.name,
                values=[
                    ("name", software.name),
                    ("version", software.version),
                    *[
                        (f"setting:{normalize_consensus_value(key)}", value)
                        for key, value in sorted(software.settings.items())
                    ],
                ],
                evidence_ids=software.evidence_ids,
            )
        for step in protocol.steps:
            if step.verb is None or not step.targets:
                continue
            step_entity_key = f"{step.verb}|{step.targets[0]}"
            append_fields(
                entity_type="steps",
                entity_id=step.step_id,
                entity_key=step_entity_key,
                values=[
                    ("verb", step.verb),
                    *[
                        (f"target:{index}", target)
                        for index, target in enumerate(step.targets)
                    ],
                    *[
                        (f"param:{normalize_consensus_value(key)}", value)
                        for key, value in sorted(step.params.items())
                    ],
                    ("notes", step.notes),
                ],
                evidence_ids=step.evidence_ids,
            )
        for characterization in protocol.characterization:
            append_fields(
                entity_type="characterization",
                entity_id=characterization.entity_id,
                entity_key=characterization.technique,
                values=[
                    ("technique", characterization.technique),
                    ("output", characterization.output),
                    *[
                        (f"setting:{normalize_consensus_value(key)}", value)
                        for key, value in sorted(characterization.settings.items())
                    ],
                ],
                evidence_ids=characterization.evidence_ids,
            )
        for result in protocol.results:
            append_fields(
                entity_type="results",
                entity_id=result.result_id,
                entity_key=result.metric,
                values=[
                    ("metric", result.metric),
                    ("raw_value", result.raw_value),
                    ("context", result.context),
                ],
                evidence_ids=result.evidence_ids,
            )
        for caveat in protocol.caveats:
            append_fields(
                entity_type="caveats",
                entity_id=caveat.caveat_id,
                entity_key=caveat.text,
                values=[("text", caveat.text)],
                evidence_ids=caveat.evidence_ids,
            )
    return sorted(
        proposals,
        key=lambda item: (
            item.paper_id,
            item.entity_type,
            normalize_consensus_value(item.entity_key),
            item.field_name,
            item.source_value,
        ),
    )
