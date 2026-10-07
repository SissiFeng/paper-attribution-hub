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


def test_teacher_preserves_primary_scope_for_non_oer_domain():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    source_quote = (
        "The electrolyte was prepared by mixing 10 mL water with 1 g salt "
        "and stirring for 2 h before battery testing."
    )
    response_payload = {
        "protocols": [
            {
                "protocol_name": "Electrolyte preparation",
                "protocol_type": "electrolyte_preparation",
                "materials": [
                    {
                        "source_chunk_id": "methods-1",
                        "name": "water",
                        "amount": "10 mL",
                        "evidence_quote": source_quote,
                    }
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
                }
            }

    extractor = BedrockTeacherExtractor(
        client=FakeBedrockClient(),
        model_id="teacher.model",
        region="us-east-1",
    )
    paper = SourcePaper(
        paper_id="paper-battery-primary",
        title="Automated battery electrolyte optimization",
        selection_tier="primary_battery_electrolyte",
        evidence_scope="primary_report",
        selection_reasons=["primary experiment"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=source_quote,
            )
        ],
    )

    protocols = extractor.extract(paper)

    assert len(protocols) == 1
    assert protocols[0].evidence_scope == "primary_report"
    assert protocols[0].source_paper_tier == "primary_battery_electrolyte"


def test_teacher_chunk_selection_accepts_explicit_non_oer_domain_terms():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    class EmptyBedrockClient:
        def converse(self, **_kwargs):
            return {
                "output": {"message": {"content": [{"text": '{"protocols": []}'}]}}
            }

    extractor = BedrockTeacherExtractor(
        client=EmptyBedrockClient(),
        model_id="teacher.model",
        region="us-east-1",
        prompt_version="scientific-protocol-teacher-v0.3",
        domain_terms=("electrolyte",),
        minimum_chunk_score=2,
    )
    paper = SourcePaper(
        paper_id="paper-battery-domain-term",
        title="Battery electrolyte study",
        selection_tier="primary_battery_electrolyte",
        evidence_scope="primary_report",
        selection_reasons=["primary experiment"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="methods",
                text=(
                    "The electrolyte optimization architecture coordinates "
                    "multiple remote capabilities through a shared task queue. "
                    "Its workflow description provides operational scientific "
                    "context for every connected tenant in the platform."
                ),
            )
        ],
    )

    assert extractor.extract(paper) == []
    assert extractor.prompt_version == "scientific-protocol-teacher-v0.3"
    assert extractor.paper_diagnostics[0].candidate_chunk_count == 1


def test_scope_aware_teacher_marks_secondary_evidence_and_abstention_rule():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    class CapturingBedrockClient:
        def __init__(self):
            self.calls = []

        def converse(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "output": {"message": {"content": [{"text": '{"protocols": []}'}]}}
            }

    client = CapturingBedrockClient()
    extractor = BedrockTeacherExtractor(
        client=client,
        model_id="teacher.model",
        region="us-east-1",
        prompt_version="scientific-protocol-teacher-v0.4-scope-aware",
        domain_terms=("electrolyte",),
        minimum_chunk_score=2,
        scope_aware=True,
    )
    paper = SourcePaper(
        paper_id="paper-secondary-review",
        title="Battery electrolyte review",
        selection_tier="battery_electrolyte_review",
        evidence_scope="secondary_report",
        selection_reasons=["secondary evidence control"],
        source_bucket="bucket",
        source_prefix="raw/",
        chunks=[
            SourceChunk(
                chunk_id="review-1",
                section_type="results",
                text=(
                    "The review describes an electrolyte workflow and its "
                    "reported performance in enough detail to enter candidate "
                    "selection, but it does not report a current experiment."
                ),
            )
        ],
    )

    assert extractor.extract(paper) == []
    prompt = client.calls[0]["messages"][0]["content"][0]["text"]
    assert "Evidence scope: secondary_report" in prompt
    assert "two ordered actions" in prompt


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


def test_teacher_maps_steps_to_atomic_verb_targets_and_params():
    from app.domain_adaptation.models import SourceChunk, SourcePaper
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    evidence_quote = (
        "The catalyst ink was prepared by sonicating a mixture of 3 mg "
        "catalyst, 500 μL DI water, and 20 μL Nafion."
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
                        "verb": "sonicating",
                        "targets": ["mixture"],
                        "params": {
                            "catalyst_amount": "3 mg",
                            "water_volume": "500 μL",
                            "nafion_volume": "20 μL",
                        },
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
        paper_id="paper-atomic-step",
        title="Atomic evidence-bound steps",
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
                    + " The ink was then deposited onto the electrode."
                ),
            )
        ],
    )

    protocols = extractor.extract(paper)

    step = protocols[0].steps[0]
    assert step.action == "sonicating"
    assert step.verb == "sonicating"
    assert step.targets == ["mixture"]
    assert step.params == {
        "catalyst_amount": "3 mg",
        "nafion_volume": "20 μL",
        "water_volume": "500 μL",
    }
    assert step.conditions == []
    assert len(step.evidence_ids) == 1
    assert protocols[0].evidence[0].quote == evidence_quote
    assert extractor.accepted_field_count >= 5
    assert not [
        record
        for record in extractor.field_audit_records
        if record.entity_type == "steps"
    ]
