from __future__ import annotations

import json


def test_teacher_records_repaired_and_rejected_fields(tmp_path):
    from app.domain_adaptation.audit import FieldAuditOutcome
    from app.domain_adaptation.audit import RejectionReason
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    source_quote = (
        "To prepare the ink, 10 mg of catalyst powder and\n"
        "2 mg of acetylene black were mixed."
    )
    cited_quote = (
        "To prepare the ink, 10 mg of catalyst powder and "
        "2 mg of acetylene black were mixed."
    )
    paper = SourcePaper(
        paper_id="paper-audit",
        title="Auditable OER protocol",
        selection_tier="primary_oer",
        selection_reasons=["methods"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=source_quote + " The catalyst purity was 99.9%.",
            )
        ],
    )
    response_payload = {
        "protocols": [
            {
                "protocol_name": "Ink preparation",
                "protocol_type": "sample_preparation",
                "materials": [
                    {
                        "source_chunk_id": "methods-1",
                        "name": "catalyst powder",
                        "amount": "10 mg",
                        "purity": "99.9%",
                        "evidence_quote": cited_quote,
                    },
                    {
                        "source_chunk_id": "methods-1",
                        "name": "unsupported additive",
                        "evidence_quote": "",
                    },
                ],
                "instruments": [],
                "software": [],
                "steps": [],
                "characterization": [],
                "results": [],
                "caveats": [],
            }
        ]
    }

    class FakeBedrockClient:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [{"text": json.dumps(response_payload)}]
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 100, "outputTokens": 50},
            }

    extractor = BedrockTeacherExtractor(
        client=FakeBedrockClient(),
        model_id="moonshotai.kimi-k2.5",
        region="us-east-1",
    )

    protocols = extractor.extract(paper)

    assert len(protocols) == 1
    assert [material.name for material in protocols[0].materials] == [
        "catalyst powder"
    ]
    assert protocols[0].materials[0].purity is None
    records = {record.field_path: record for record in extractor.field_audit_records}
    assert records["materials[0].name"].outcome == FieldAuditOutcome.REPAIRED
    assert (
        records["materials[0].name"].rejection_reason
        == RejectionReason.WHITESPACE_MISMATCH
    )
    assert records["materials[0].name"].repair_succeeded is True
    assert (
        records["materials[0].purity"].rejection_reason
        == RejectionReason.VALUE_ELSEWHERE
    )
    assert (
        records["materials[1].name"].rejection_reason
        == RejectionReason.NO_SPAN
    )
    assert extractor.proposed_field_count == 4
    assert extractor.accepted_field_count == 2
    assert extractor.rejected_field_count == 2
    assert extractor.repair_succeeded_count == 1

    from app.domain_adaptation.builder import build_domain_adapter_package
    from app.domain_adaptation.models import DomainPackageConfig

    output_dir = tmp_path / "package"
    result = build_domain_adapter_package(
        papers=[paper],
        output_dir=output_dir,
        extractor=extractor,
        config=DomainPackageConfig(
            package_id="oer-electrocatalysis",
            package_version="0.2.0-pre-review",
            domain="oxygen evolution electrocatalysis",
            source_access="s3_markdown",
        ),
    )

    audit_rows = [
        json.loads(line)
        for line in (output_dir / "reports/teacher_field_audit.jsonl")
        .read_text()
        .splitlines()
    ]
    report = json.loads(
        (output_dir / "reports/quality_report.json").read_text()
    )
    assert len(audit_rows) == 3
    assert report["teacher_field_audit"] == {
        "accepted_field_count": 2,
        "field_acceptance_rate": 0.5,
        "proposed_field_count": 4,
        "rejected_field_count": 2,
        "rejection_reason_counts": {
            "no_span": 1,
            "value_elsewhere": 1,
        },
        "rejected_entity_type_counts": {"materials": 2},
        "repair_attempted_count": 1,
        "repair_reason_counts": {"whitespace_mismatch": 1},
        "repair_succeeded_count": 1,
    }
    assert report["teacher_runtime"] == {
        "input_token_count": 100,
        "invocation_count": 1,
        "latency_ms_total": 0,
        "output_token_count": 50,
        "response_failure_diagnostics": [],
        "response_schema_failure_count": 0,
        "salvaged_response_count": 0,
    }
    assert report["paper_coverage_by_selection_tier"] == {
        "primary_oer": {
            "paper_count": 1,
            "papers_with_protocols": 1,
            "coverage_rate": 1.0,
        }
    }
    assert report["teacher_paper_outcome_counts"] == {
        "retained_protocols": 1
    }
    assert report["teacher_paper_diagnostics"][0]["paper_id"] == "paper-audit"
    assert (
        report["teacher_paper_diagnostics"][0]["outcome"]
        == "retained_protocols"
    )
    assert result.manifest["validation"]["rejected_teacher_field_count"] == 2
    assert result.manifest["extraction"]["region"] == "us-east-1"


def test_teacher_accepts_deterministically_normalized_field_values():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    source_quote = (
        "The experimental procedure used a furnace and the sample was heated "
        "at 500 ℃ for 2 h."
    )
    cited_quote = (
        "The experimental procedure used a furnace and the sample was heated "
        "at 500 °C for 2 h."
    )
    response_payload = {
        "protocols": [
            {
                "protocol_name": "Heat treatment",
                "protocol_type": "sample_preparation",
                "materials": [],
                "instruments": [
                    {
                        "source_chunk_id": "methods-1",
                        "name": "furnace",
                        "settings": {"temperature": "500 °C"},
                        "evidence_quote": cited_quote,
                    }
                ],
                "software": [],
                "steps": [],
                "characterization": [],
                "results": [],
                "caveats": [],
            }
        ]
    }

    class FakeBedrockClient:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [{"text": json.dumps(response_payload)}]
                    }
                }
            }

    extractor = BedrockTeacherExtractor(
        client=FakeBedrockClient(),
        model_id="moonshotai.kimi-k2.5",
        region="us-east-1",
    )
    paper = SourcePaper(
        paper_id="paper-normalization",
        title="Normalized units",
        selection_tier="primary_oer",
        selection_reasons=["methods"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=(
                    source_quote
                    + " The treated sample was then measured using the same "
                    "experimental protocol."
                ),
            )
        ],
    )

    protocols = extractor.extract(paper)

    assert protocols[0].instruments[0].settings == {
        "temperature": "500 °C"
    }
    assert extractor.rejected_field_count == 0


def test_teacher_salvages_complete_protocols_from_truncated_json():
    from app.domain_adaptation.teacher import parse_teacher_response

    valid_protocol = {
        "protocol_name": "Complete protocol",
        "materials": [],
        "instruments": [],
        "software": [],
        "steps": [],
        "characterization": [],
        "results": [],
        "caveats": [],
    }
    truncated = (
        '{"protocols":['
        + json.dumps(valid_protocol)
        + ',{"protocol_name":"truncated","materials":['
    )

    parsed = parse_teacher_response(truncated)

    assert parsed.data == {"protocols": [valid_protocol]}
    assert parsed.schema_invalid is True
    assert parsed.salvaged_protocol_count == 1
    assert "Expecting" in (parsed.diagnostic or "")


def test_teacher_records_per_paper_abstention_diagnostic():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    class FakeBedrockClient:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {"content": [{"text": '{"protocols":[]}'}]}
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 80, "outputTokens": 8},
                "metrics": {"latencyMs": 500},
            }

    extractor = BedrockTeacherExtractor(
        client=FakeBedrockClient(),
        model_id="model-a",
        region="us-east-1",
    )
    paper = SourcePaper(
        paper_id="paper-abstain",
        title="A protocol-like primary paper",
        selection_tier="primary_oer",
        selection_reasons=["methods"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=(
                    "The catalyst was prepared by mixing 10 mg precursor and "
                    "heating it at 500 °C for 2 h. OER activity was measured "
                    "by LSV at 10 mV s−1 in 1 M KOH."
                ),
            )
        ],
    )

    assert extractor.extract(paper) == []
    assert [item.model_dump(mode="json") for item in extractor.paper_diagnostics] == [
        {
            "paper_id": "paper-abstain",
            "selection_tier": "primary_oer",
            "candidate_chunk_count": 1,
            "candidate_input_char_count": len(paper.chunks[0].text),
            "raw_protocol_count": 0,
            "retained_protocol_count": 0,
            "stop_reason": "end_turn",
            "response_schema_invalid": False,
            "salvaged_protocol_count": 0,
            "outcome": "model_abstained",
        }
    ]


def test_teacher_rejects_summarized_step_but_keeps_exact_evidence_action():
    from app.domain_adaptation.audit import RejectionReason
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    evidence_quote = (
        "The catalyst ink was sonicated for 30 min and then deposited onto "
        "the electrode."
    )
    response_payload = {
        "protocols": [
            {
                "protocol_name": "Electrode preparation",
                "protocol_type": "sample_preparation",
                "materials": [],
                "instruments": [],
                "software": [],
                "steps": [
                    {
                        "source_chunk_id": "methods-1",
                        "action": "Sonicate the ink and coat the electrode.",
                        "conditions": ["30 min"],
                        "evidence_quote": evidence_quote,
                    }
                ],
                "characterization": [],
                "results": [],
                "caveats": [],
            }
        ]
    }

    class FakeBedrockClient:
        def converse(self, **_kwargs):
            return {
                "output": {
                    "message": {
                        "content": [{"text": json.dumps(response_payload)}]
                    }
                }
            }

    extractor = BedrockTeacherExtractor(
        client=FakeBedrockClient(),
        model_id="moonshotai.kimi-k2.5",
        region="us-east-1",
    )
    paper = SourcePaper(
        paper_id="paper-step-fallback",
        title="Evidence-canonical steps",
        selection_tier="primary_oer",
        selection_reasons=["methods"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=(
                    evidence_quote
                    + " The electrochemical activity was then measured at "
                    "10 mV s−1 using the experimental protocol."
                ),
            )
        ],
    )

    protocols = extractor.extract(paper)

    assert protocols[0].steps[0].action == evidence_quote
    assert protocols[0].steps[0].conditions == ["30 min"]
    action_audit = next(
        record
        for record in extractor.field_audit_records
        if record.field_path == "steps[0].action"
    )
    assert action_audit.rejection_reason == RejectionReason.OVER_GENERALIZED
