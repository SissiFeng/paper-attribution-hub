"""Fail-closed validation for evidence-bound scientific records."""

from __future__ import annotations

import hashlib

from app.domain_adaptation.models import ProtocolUnit, SourcePaper


class EvidenceValidationError(ValueError):
    pass


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_protocol_unit(protocol: ProtocolUnit, paper: SourcePaper) -> list[str]:
    violations: list[str] = []
    chunks = {chunk.chunk_id: chunk for chunk in paper.chunks}
    evidence_ids: set[str] = set()

    if protocol.paper_id != paper.paper_id:
        violations.append("protocol paper_id does not match its source paper")

    for evidence in protocol.evidence:
        if evidence.evidence_id in evidence_ids:
            violations.append(f"duplicate evidence_id: {evidence.evidence_id}")
        evidence_ids.add(evidence.evidence_id)
        chunk = chunks.get(evidence.chunk_id)
        if chunk is None:
            violations.append(f"unknown evidence chunk_id: {evidence.chunk_id}")
            continue
        if evidence.paper_id != paper.paper_id:
            violations.append(f"evidence paper_id mismatch: {evidence.evidence_id}")
        if _sha256(chunk.text) != evidence.source_sha256:
            violations.append(f"source hash mismatch: {evidence.evidence_id}")
        if evidence.char_end > len(chunk.text):
            violations.append(f"evidence range exceeds source: {evidence.evidence_id}")
            continue
        if chunk.text[evidence.char_start : evidence.char_end] != evidence.quote:
            violations.append(
                f"evidence quote is not an exact substring at its range: "
                f"{evidence.evidence_id}"
            )
        if chunk.document_char_start is not None:
            expected_document_start = chunk.document_char_start + evidence.char_start
            expected_document_end = chunk.document_char_start + evidence.char_end
            if evidence.document_char_start != expected_document_start:
                violations.append(
                    f"document evidence start mismatch: {evidence.evidence_id}"
                )
            if evidence.document_char_end != expected_document_end:
                violations.append(
                    f"document evidence end mismatch: {evidence.evidence_id}"
                )

    referenced_ids: set[str] = set()
    for collection_name, collection in (
        ("material", protocol.materials),
        ("instrument", protocol.instruments),
        ("software", protocol.software),
        ("step", protocol.steps),
        ("characterization", protocol.characterization),
        ("result", protocol.results),
        ("caveat", protocol.caveats),
        ("relation", protocol.relations),
    ):
        for item in collection:
            if not item.evidence_ids:
                violations.append(f"{collection_name} has no evidence_ids")
            referenced_ids.update(item.evidence_ids)
    for evidence_id in sorted(referenced_ids - evidence_ids):
        violations.append(f"field references unknown evidence_id: {evidence_id}")

    valid_node_ids = {protocol.protocol_id}
    for collection in (
        protocol.materials,
        protocol.instruments,
        protocol.software,
        protocol.steps,
        protocol.characterization,
        protocol.results,
        protocol.caveats,
    ):
        for item in collection:
            for attribute in (
                "entity_id",
                "step_id",
                "result_id",
                "caveat_id",
            ):
                value = getattr(item, attribute, None)
                if isinstance(value, str):
                    valid_node_ids.add(value)
    for relation in protocol.relations:
        if relation.subject_id not in valid_node_ids:
            violations.append(
                f"relation has unknown subject_id: {relation.relation_id}"
            )
        if relation.object_id not in valid_node_ids:
            violations.append(
                f"relation has unknown object_id: {relation.relation_id}"
            )

    for chunk_id in protocol.source_chunk_ids:
        chunk = chunks.get(chunk_id)
        if chunk is None:
            violations.append(f"unknown protocol source_chunk_id: {chunk_id}")
            continue
        section = f"{chunk.section_type} {chunk.section_title or ''}".casefold()
        if "reference" in section or "acknowledg" in section:
            violations.append(f"excluded section used as protocol source: {chunk_id}")
    return violations


def require_valid_protocol_unit(protocol: ProtocolUnit, paper: SourcePaper) -> None:
    violations = validate_protocol_unit(protocol, paper)
    if violations:
        raise EvidenceValidationError("; ".join(violations))
