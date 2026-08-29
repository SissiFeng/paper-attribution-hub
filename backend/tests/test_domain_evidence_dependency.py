from __future__ import annotations

import json


def _protocol_and_claims():
    from app.domain_adaptation.gold import CandidateClaim, normalize_gold_value
    from app.domain_adaptation.models import EvidenceSpan, ProtocolUnit

    direct_quote = "The catalyst was heated at 500 ℃ for 2 h."
    cited_quote = (
        "Following Ref. 12 with minor modifications, the sample was annealed "
        "at 500 °C."
    )
    evidence = [
        EvidenceSpan(
            evidence_id="ev-direct",
            paper_id="paper-1",
            chunk_id="methods-1",
            quote=direct_quote,
            char_start=10,
            char_end=10 + len(direct_quote),
            source_sha256="a" * 64,
        ),
        EvidenceSpan(
            evidence_id="ev-cited",
            paper_id="paper-1",
            chunk_id="methods-2",
            quote=cited_quote,
            char_start=30,
            char_end=30 + len(cited_quote),
            source_sha256="b" * 64,
        ),
    ]
    protocol = ProtocolUnit(
        protocol_id="protocol-1",
        paper_id="paper-1",
        protocol_name="Annealing",
        protocol_type="thermal_treatment",
        source_paper_tier="primary_oer",
        evidence_scope="primary_report",
        source_chunk_ids=["methods-1", "methods-2"],
        evidence=evidence,
    )

    def claim(claim_id: str, value: str, evidence_index: int):
        item = evidence[evidence_index]
        return CandidateClaim(
            candidate_claim_id=claim_id,
            paper_id="paper-1",
            protocol_id="protocol-1",
            source_entity_id=f"step-{evidence_index}",
            entity_type="step",
            field_name="conditions[0]",
            source_value=value,
            normalized_value=normalize_gold_value(value),
            evidence_ids=[item.evidence_id],
            evidence_chunk_id=item.chunk_id,
            evidence_quote=item.quote,
            char_start=item.char_start,
            char_end=item.char_end,
        )

    return protocol, [
        claim("claim-direct", "500 °C", 0),
        claim("claim-cited", "500 °C", 1),
    ]


def test_dependency_queue_proposes_orthogonal_labels_without_creating_gold():
    from app.domain_adaptation.evidence_dependency import (
        build_evidence_dependency_annotations,
    )

    protocol, claims = _protocol_and_claims()

    annotations = build_evidence_dependency_annotations([protocol], claims)

    by_claim = {item.candidate_claim_id: item for item in annotations}
    direct = by_claim["claim-direct"]
    assert direct.proposed_labels.origin == "author_reported_primary_experiment"
    assert direct.proposed_labels.support == "deterministically_aligned"
    assert direct.proposed_labels.modification == "none"
    assert direct.review_status == "pending"
    assert direct.reviewed_labels is None
    assert direct.direct_evidence[0].evidence_id == "ev-direct"

    cited = by_claim["claim-cited"]
    assert cited.proposed_labels.origin == "cited_method"
    assert cited.proposed_labels.support == "exact"
    assert cited.proposed_labels.modification == "explicitly_modified"
    assert cited.review_status == "pending"


def test_reviewed_derived_field_requires_rule_and_input_dependencies():
    import pytest
    from pydantic import ValidationError

    from app.domain_adaptation.evidence_dependency import (
        EvidenceDependencyAnnotation,
        EvidenceDependencyLabels,
        FieldDerivation,
        build_evidence_dependency_annotations,
    )

    protocol, claims = _protocol_and_claims()
    pending = build_evidence_dependency_annotations([protocol], claims)[0]
    reviewed_labels = EvidenceDependencyLabels(
        origin="author_reported_primary_experiment",
        support="explicitly_derived",
        modification="none",
    )
    payload = pending.model_dump(mode="json")
    payload.update(
        {
            "review_status": "reviewed",
            "reviewed_labels": reviewed_labels.model_dump(mode="json"),
            "reviewer": "reviewer-1",
        }
    )

    with pytest.raises(ValidationError, match="requires a derivation"):
        EvidenceDependencyAnnotation.model_validate(payload)

    payload["depends_on_dependency_ids"] = ["evidence_dependency_input"]
    payload["derivation"] = FieldDerivation(
        rule_id="temperature_unit_normalization_v1",
        expression="T_degC = T_reported_degC",
        input_dependency_ids=["evidence_dependency_input"],
        assumptions=["Degree Celsius symbol normalization only"],
    ).model_dump(mode="json")
    reviewed = EvidenceDependencyAnnotation.model_validate(payload)

    assert reviewed.reviewed_labels == reviewed_labels
    assert reviewed.derivation is not None


def test_complete_protocol_scope_cannot_contain_pending_dependencies():
    import pytest

    from app.domain_adaptation.evidence_dependency import (
        build_evidence_dependency_annotations,
        summarize_evidence_dependency_annotations,
    )
    from app.domain_adaptation.gold import GoldProtocolAnnotation

    protocol, claims = _protocol_and_claims()
    annotations = build_evidence_dependency_annotations([protocol], claims)
    complete_scope = GoldProtocolAnnotation(
        gold_protocol_id="gold-protocol-1",
        paper_id="paper-1",
        protocol_id="protocol-1",
        review_status="reviewed",
        annotation_complete=True,
    )

    with pytest.raises(ValueError, match="pending evidence dependency"):
        summarize_evidence_dependency_annotations(
            annotations=annotations,
            gold_protocols=[complete_scope],
            candidate_claims=claims,
        )


def test_prepare_dependency_annotations_writes_non_overwriting_review_queue(
    tmp_path,
):
    import pytest

    from app.domain_adaptation.gold import GoldProtocolAnnotation
    from app.scripts.prepare_evidence_dependency_annotations import (
        prepare_evidence_dependency_annotations,
    )

    protocol, claims = _protocol_and_claims()
    package = tmp_path / "package"
    (package / "knowledge").mkdir(parents=True)
    (package / "gold").mkdir(parents=True)
    (package / "knowledge/protocols.jsonl").write_text(
        json.dumps(protocol.model_dump(mode="json")) + "\n"
    )
    (package / "gold/candidate_claims.jsonl").write_text(
        "".join(json.dumps(item.model_dump(mode="json")) + "\n" for item in claims)
    )
    gold_protocol = GoldProtocolAnnotation(
        gold_protocol_id="gold-protocol-1",
        paper_id="paper-1",
        protocol_id="protocol-1",
    )
    (package / "gold/gold_protocols.jsonl").write_text(
        json.dumps(gold_protocol.model_dump(mode="json")) + "\n"
    )

    result = prepare_evidence_dependency_annotations(package)

    assert result == {
        "annotation_count": 2,
        "pending_count": 2,
        "reviewed_count": 0,
    }
    rows = [
        json.loads(line)
        for line in (package / "gold/evidence_dependencies.jsonl")
        .read_text()
        .splitlines()
    ]
    assert len(rows) == 2
    assert all(row["review_status"] == "pending" for row in rows)
    assert (package / "gold/schemas/evidence_dependencies.schema.json").is_file()
    assert (package / "reports/evidence_dependency_summary.json").is_file()

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        prepare_evidence_dependency_annotations(package)
