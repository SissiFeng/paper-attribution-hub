from __future__ import annotations

import json
import hashlib
import io
from pathlib import Path
import sys

import httpx
import pytest


METHOD_TEXT = (
    "Cyclic voltammetry, LSV, EIS, and chronopotentiometry were performed "
    "using an electrochemical workstation (Corrtest 2350H). "
    "To prepare the catalyst ink, 10 mg of catalyst powder and 2 mg of "
    "acetylene black were mixed in a container. Then, 470 μL of anhydrous "
    "ethanol, 500 μL of deionized water, and 30 μL of Nafion solution were "
    "pipetted into the container. The mixture was sonicated in an ice bath "
    "for more than 2 h. The OER activity was evaluated by LSV from 1.2 to "
    "1.8 V vs RHE at 10 mV s−1 in 1 M KOH."
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_cli_keeps_s3_and_teacher_regions_separate(monkeypatch):
    from app.scripts.build_domain_adapter_package import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-domain-adapter",
            "--aws-region",
            "ca-central-1",
            "--teacher-region",
            "us-east-1",
            "--model-id",
            "moonshotai.kimi-k2.5",
            "--package-version",
            "0.2.0-pre-review",
        ],
    )

    args = parse_args()

    assert args.aws_region == "ca-central-1"
    assert args.teacher_region == "us-east-1"
    assert args.model_id == "moonshotai.kimi-k2.5"
    assert args.package_version == "0.2.0-pre-review"


def test_cli_configures_bedrock_for_long_running_teacher_calls(monkeypatch):
    from app.scripts.build_domain_adapter_package import parse_args

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build-domain-adapter",
            "--bedrock-read-timeout",
            "300",
            "--bedrock-max-attempts",
            "4",
            "--bedrock-max-output-tokens",
            "14000",
        ],
    )

    args = parse_args()

    assert args.bedrock_read_timeout == 300
    assert args.bedrock_max_attempts == 4
    assert args.bedrock_max_output_tokens == 14000


def test_benchmark_build_can_freeze_the_evaluation_paper_slice():
    from app.domain_adaptation.source import load_pilot_selection
    from app.scripts.build_domain_adapter_package import (
        DEFAULT_SELECTION,
        select_selection_items,
    )

    selection = load_pilot_selection(DEFAULT_SELECTION)
    selected = select_selection_items(selection, "evaluation")

    assert len(selected) == 4
    assert all(item.task_split == "evaluation" for item in selected)


def _source_paper():
    from app.domain_adaptation.models import SourceChunk, SourcePaper

    return SourcePaper(
        paper_id="DOI:10.1000_oer-primary",
        title="A reproducible OER catalyst protocol",
        year=2025,
        doi="10.1000/oer-primary",
        selection_tier="primary_oer",
        selection_reasons=["OER protocol language in the full text"],
        source_bucket="paper-attribution-artifacts-dev-247893369214",
        source_prefix="raw/zotero/group=6631056/",
        chunks=[
            SourceChunk(
                chunk_id="methods-1",
                section_type="unknown",
                section_title=None,
                text=(
                    METHOD_TEXT
                    + "\n\n## References:\n\n"
                    "Institute of Electrical and Electronics Engineers."
                ),
            ),
            SourceChunk(
                chunk_id="references-1",
                section_type="references",
                section_title="References",
                text="University of Toronto. Oxygen evolution bibliography.",
            ),
            SourceChunk(
                chunk_id="introduction-1",
                section_type="introduction",
                section_title="Introduction",
                text=(
                    "Oxygen evolution is important for sustainable energy, but "
                    "this introductory statement contains no experimental protocol."
                ),
            ),
        ],
    )


def test_heuristic_extractor_builds_evidence_bound_protocol():
    from app.domain_adaptation.extractors import HeuristicOerExtractor
    from app.domain_adaptation.validation import validate_protocol_unit

    paper = _source_paper()
    protocols = HeuristicOerExtractor().extract(paper)

    assert len(protocols) == 1
    protocol = protocols[0]
    assert {item.name for item in protocol.materials} >= {
        "catalyst powder",
        "acetylene black",
        "anhydrous ethanol",
        "deionized water",
        "Nafion solution",
        "KOH",
    }
    assert any(
        item.model == "Corrtest 2350H" for item in protocol.instruments
    )
    assert {item.technique for item in protocol.characterization} >= {
        "LSV",
        "EIS",
        "chronopotentiometry",
    }
    assert protocol.relations == []
    assert any("10 mg" in value for step in protocol.steps for value in step.conditions)
    assert validate_protocol_unit(protocol, paper) == []

    source_text = paper.chunks[0].text
    for evidence in protocol.evidence:
        assert source_text[evidence.char_start : evidence.char_end] == evidence.quote


def test_heuristic_extractor_removes_inline_publication_metadata():
    from app.domain_adaptation.extractors import HeuristicOerExtractor
    from app.domain_adaptation.extractors import scientific_content
    from app.domain_adaptation.models import SourceChunk, SourcePaper

    paper = SourcePaper(
        paper_id="DOI:10.1000_oer-mixed-export",
        title="OER paper with a mixed export chunk",
        selection_tier="primary_oer",
        selection_reasons=["OER methods are present"],
        source_bucket="paper-attribution-artifacts-dev-247893369214",
        source_prefix="raw/zotero/group=6631056/",
        chunks=[
            SourceChunk(
                chunk_id="mixed-methods",
                section_type="unknown",
                text=(
                    METHOD_TEXT
                    + " Chinese powders were chilled for 10 min."
                    + " The measurements were conducted at the Department of "
                    "Chemical Engineering, University of Toronto."
                    + "|ACKNOWLEDGMENTS| Python software was provided by a colleague."
                    + "|REFERENCES| Electrochemical methods handbook."
                ),
            )
        ],
    )

    protocols = HeuristicOerExtractor().extract(paper)

    assert len(protocols) == 1
    serialized = json.dumps(protocols[0].model_dump(), ensure_ascii=False)
    assert "Department of" not in serialized
    assert "University of Toronto" not in serialized
    assert "ACKNOWLEDGMENTS" not in serialized
    assert "REFERENCES" not in serialized
    assert "Python" not in serialized
    assert [item.model for item in protocols[0].instruments] == ["Corrtest 2350H"]
    assert scientific_content(
        METHOD_TEXT + " Author Contributions project administration and editing."
    ) == METHOD_TEXT


def test_evidence_validator_rejects_unsupported_teacher_output():
    from app.domain_adaptation.models import EvidenceSpan, ProtocolUnit
    from app.domain_adaptation.validation import EvidenceValidationError
    from app.domain_adaptation.validation import require_valid_protocol_unit

    paper = _source_paper()
    unsupported = ProtocolUnit(
        protocol_id="protocol-unsupported",
        paper_id=paper.paper_id,
        protocol_name="Unsupported teacher protocol",
        protocol_type="electrochemical_testing",
        source_chunk_ids=["methods-1"],
        evidence=[
            EvidenceSpan(
                evidence_id="evidence-unsupported",
                paper_id=paper.paper_id,
                chunk_id="methods-1",
                quote="The experiment used a fictional 9000 K furnace.",
                char_start=0,
                char_end=47,
                source_sha256="0" * 64,
            )
        ],
    )

    with pytest.raises(EvidenceValidationError, match="exact substring"):
        require_valid_protocol_unit(unsupported, paper)


def test_evidence_validator_rejects_unbound_structured_fields():
    from app.domain_adaptation.models import MaterialInput, ProtocolUnit
    from app.domain_adaptation.validation import EvidenceValidationError
    from app.domain_adaptation.validation import require_valid_protocol_unit

    paper = _source_paper()
    unbound = ProtocolUnit(
        protocol_id="protocol-unbound",
        paper_id=paper.paper_id,
        protocol_name="Unbound material",
        protocol_type="electrode_preparation",
        source_chunk_ids=["methods-1"],
        materials=[
            MaterialInput(
                entity_id="material-unbound",
                name="fictional catalyst",
                evidence_ids=[],
            )
        ],
    )

    with pytest.raises(EvidenceValidationError, match="has no evidence_ids"):
        require_valid_protocol_unit(unbound, paper)


def test_bedrock_teacher_maps_only_exactly_grounded_fields():
    from app.domain_adaptation.teacher import BedrockTeacherExtractor
    from app.domain_adaptation.models import SourceChunk
    from app.domain_adaptation.validation import validate_protocol_unit

    supported_quote = (
        "To prepare the catalyst ink, 10 mg of catalyst powder and 2 mg of "
        "acetylene black were mixed in a container."
    )
    characterization_quote = (
        "XPS measurements were performed after the electrode was annealed at "
        "500 °C for 2 h using a Thermo Scientific K-Alpha instrument."
    )
    response_payload = {
        "protocols": [
            {
                "source_chunk_ids": ["methods-1", "methods-2"],
                "protocol_name": "Catalyst ink preparation",
                "protocol_type": "electrode_preparation",
                "materials": [
                    {
                        "name": "catalyst powder",
                        "amount": "10 mg",
                        "role": "catalyst",
                        "source_chunk_id": "methods-1",
                        "evidence_quote": supported_quote,
                    },
                    {
                        "name": "fictional additive",
                        "amount": "5 mg",
                        "source_chunk_id": "methods-1",
                        "evidence_quote": "A fictional additive was used.",
                    },
                ],
                "instruments": [],
                "software": [],
                "steps": [
                    {
                        "order": 1,
                        "action": supported_quote,
                        "conditions": ["10 mg", "2 mg"],
                        "notes": "fictional note",
                        "source_chunk_id": "methods-1",
                        "evidence_quote": supported_quote,
                    }
                ],
                "characterization": [
                    {
                        "technique": "XPS",
                        "settings": {"annealing_temperature": "500 °C"},
                        "source_chunk_id": "methods-2",
                        "evidence_quote": characterization_quote,
                    }
                ],
                "results": [],
                "caveats": [],
            }
        ]
    }

    class FakeBedrockClient:
        def __init__(self):
            self.calls = []

        def converse(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [{"text": json.dumps(response_payload)}]
                    }
                }
            }

    client = FakeBedrockClient()
    extractor = BedrockTeacherExtractor(
        client=client,
        model_id="anthropic.claude-sonnet-4-6",
        region="ca-central-1",
    )
    paper = _source_paper().model_copy(
        update={
            "chunks": _source_paper().chunks
            + [
                SourceChunk(
                    chunk_id="methods-2",
                    section_type="methods",
                    section_title="Characterization",
                    text=characterization_quote,
                )
            ]
        }
    )
    protocols = extractor.extract(paper)

    assert len(protocols) == 1
    assert [item.name for item in protocols[0].materials] == ["catalyst powder"]
    assert protocols[0].steps[0].notes is None
    assert protocols[0].source_chunk_ids == ["methods-1", "methods-2"]
    assert [item.technique for item in protocols[0].characterization] == ["XPS"]
    assert {item.chunk_id for item in protocols[0].evidence} == {
        "methods-1",
        "methods-2",
    }
    assert extractor.unsupported_claim_count == 2
    assert validate_protocol_unit(protocols[0], paper) == []
    assert client.calls[0]["modelId"] == "anthropic.claude-sonnet-4-6"
    assert "SECRET" not in json.dumps(client.calls[0])


def test_bedrock_teacher_resumes_from_paper_cache(tmp_path):
    from app.domain_adaptation.teacher import BedrockTeacherExtractor

    supported_quote = (
        "To prepare the catalyst ink, 10 mg of catalyst powder and 2 mg of "
        "acetylene black were mixed in a container."
    )
    response_payload = {
        "protocols": [
            {
                "source_chunk_ids": ["methods-1"],
                "protocol_name": "Catalyst ink preparation",
                "protocol_type": "electrode_preparation",
                "materials": [
                    {
                        "name": "catalyst powder",
                        "amount": "10 mg",
                        "source_chunk_id": "methods-1",
                        "evidence_quote": supported_quote,
                    },
                    {
                        "name": "unsupported additive",
                        "source_chunk_id": "methods-1",
                        "evidence_quote": "This quote is absent.",
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
        def __init__(self):
            self.call_count = 0

        def converse(self, **_kwargs):
            self.call_count += 1
            return {
                "output": {
                    "message": {
                        "content": [{"text": json.dumps(response_payload)}]
                    }
                },
                "stopReason": "end_turn",
                "usage": {"inputTokens": 101, "outputTokens": 52},
                "metrics": {"latencyMs": 1234},
            }

    client = FakeBedrockClient()
    first = BedrockTeacherExtractor(
        client=client,
        model_id="moonshotai.kimi-k2.5",
        region="us-east-1",
        cache_dir=tmp_path,
    )
    first_protocols = first.extract(_source_paper())
    cache_path = next(tmp_path.rglob("*.json"))
    stale_cache = json.loads(cache_path.read_text())
    stale_cache["mapping_version"] = "stale-mapper"
    cache_path.write_text(json.dumps(stale_cache))
    second = BedrockTeacherExtractor(
        client=client,
        model_id="moonshotai.kimi-k2.5",
        region="us-east-1",
        cache_dir=tmp_path,
    )
    second_protocols = second.extract(_source_paper())

    assert client.call_count == 1
    assert second_protocols == first_protocols
    assert first.unsupported_claim_count == 1
    assert second.unsupported_claim_count == 1
    assert second.proposed_field_count == first.proposed_field_count == 3
    assert second.accepted_field_count == first.accepted_field_count == 2
    assert second.rejected_field_count == first.rejected_field_count == 1
    assert second.field_audit_records == first.field_audit_records
    assert second.input_token_count == first.input_token_count == 101
    assert second.output_token_count == first.output_token_count == 52
    assert second.invocation_count == first.invocation_count == 1
    assert second.latency_ms_total == first.latency_ms_total == 1234
    cache = json.loads(cache_path.read_text())
    assert cache["schema_version"] == "bedrock-teacher-paper-cache-v0.2"
    assert cache["mapping_version"] == "evidence-field-mapper-v0.2"
    assert cache["teacher_response"]["stop_reason"] == "end_turn"
    assert cache["teacher_response"]["metrics"] == {"latencyMs": 1234}
    assert cache["teacher_response"]["raw_text"] == json.dumps(response_payload)


def test_package_builder_writes_four_layers_deterministically(tmp_path):
    from app.domain_adaptation.builder import build_domain_adapter_package
    from app.domain_adaptation.extractors import HeuristicOerExtractor
    from app.domain_adaptation.models import DomainPackageConfig

    output_dir = tmp_path / "oer-package"
    config = DomainPackageConfig(
        package_id="oer-electrocatalysis",
        package_version="0.1.0-pilot",
        domain="oxygen evolution electrocatalysis",
        source_access="imported_api",
    )

    first = build_domain_adapter_package(
        papers=[_source_paper()],
        output_dir=output_dir,
        extractor=HeuristicOerExtractor(),
        config=config,
    )
    snapshot = {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    second = build_domain_adapter_package(
        papers=[_source_paper()],
        output_dir=output_dir,
        extractor=HeuristicOerExtractor(),
        config=config,
    )

    assert first.changed_files == len(snapshot)
    assert second.changed_files == 0
    assert snapshot == {
        path.relative_to(output_dir).as_posix(): path.read_bytes()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    assert set(snapshot) == {
        "corpus/continued_pretraining.jsonl",
        "knowledge/paper_records.jsonl",
        "knowledge/protocols.jsonl",
        "knowledge/scientific_chunks.jsonl",
        "manifest.json",
        "reports/quality_report.json",
        "reports/teacher_field_audit.jsonl",
        "source/selection_manifest.json",
        "tasks/evaluation/eval.jsonl",
        "tasks/sft/train.jsonl",
    }

    manifest = json.loads(snapshot["manifest.json"])
    assert manifest["classification_neutral"] is True
    assert manifest["institution_entities_included"] is False
    assert manifest["extraction"]["mode"] == "heuristic_baseline"
    assert manifest["extraction"]["inference_config"] is None
    assert manifest["counts"]["paper_count"] == 1
    assert manifest["counts"]["scientific_chunk_count"] == 1
    assert manifest["counts"]["protocol_count"] == 1
    assert manifest["package_descriptor"] == {
        "schema_version": "domain-package-descriptor-v0.1",
        "package_id": "oer-electrocatalysis",
        "package_version": "0.1.0-pilot",
        "package_kind": "domain",
        "domain": "oxygen evolution electrocatalysis",
        "facets": [],
        "dependencies": [],
    }
    assert manifest["validation"]["unsupported_evidence_count"] == 0
    for relative_path, expected_sha256 in manifest["artifact_sha256"].items():
        assert hashlib.sha256(snapshot[relative_path]).hexdigest() == expected_sha256
    scientific_chunk = json.loads(
        snapshot["knowledge/scientific_chunks.jsonl"].decode().splitlines()[0]
    )
    protocol_row = json.loads(
        snapshot["knowledge/protocols.jsonl"].decode().splitlines()[0]
    )
    assert protocol_row["scientific_chunk_ids"] == [
        scientific_chunk["scientific_chunk_id"]
    ]
    assert {relation["predicate"] for relation in protocol_row["relations"]} >= {
        "uses_material",
        "has_step",
        "uses_characterization",
    }
    assert scientific_chunk["source_chunk_ids"] == ["methods-1"]
    assert "protocol" in scientific_chunk["semantic_roles"]
    corpus_row = json.loads(
        snapshot["corpus/continued_pretraining.jsonl"].decode().splitlines()[0]
    )
    assert corpus_row["scientific_chunk_id"] == scientific_chunk["scientific_chunk_id"]
    assert corpus_row["source_segments"] == scientific_chunk["segments"]

    serialized = b"".join(snapshot.values()).decode("utf-8")
    assert "University of Toronto" not in serialized
    assert "Institute of Electrical and Electronics Engineers" not in serialized
    assert "references-1" not in serialized
    assert "introductory statement" not in serialized
    assert "recommend" not in serialized.lower()
    train_rows = [
        json.loads(line)
        for line in snapshot["tasks/sft/train.jsonl"].decode().splitlines()
    ]
    eval_rows = [
        json.loads(line)
        for line in snapshot["tasks/evaluation/eval.jsonl"].decode().splitlines()
    ]
    source_text = _source_paper().chunks[0].text
    for task in train_rows + eval_rows:
        assert task["source_context"]
        assert task["response_schema"]
        assert "catalyst powder" not in json.dumps(task["response_schema"])
        assert {item["evidence_id"] for item in task["source_context"]} == set(
            task["evidence_ids"]
        )
        for item in task["source_context"]:
            assert item["quote"] in source_text
    assert {row["paper_id"] for row in train_rows}.isdisjoint(
        {row["paper_id"] for row in eval_rows}
    )


def test_imported_api_source_discards_attribution_and_affiliation_fields():
    from app.domain_adaptation.models import PilotSelectionItem
    from app.domain_adaptation.source import ImportedApiSource

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/papers"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "DOI:10.1000_oer-primary",
                        "title": "A reproducible OER catalyst protocol",
                        "year": 2025,
                        "doi": "10.1000/oer-primary",
                        "classification": {"label": "SECRET_ATTRIBUTION_LABEL"},
                        "authors": [
                            {
                                "name": "A. Researcher",
                                "affiliation": "SECRET_INSTITUTION",
                            }
                        ],
                    }
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "chunk_id": "methods-1",
                    "paper_id": "DOI:10.1000_oer-primary",
                    "section_type": "unknown",
                    "section_title": None,
                    "text": METHOD_TEXT,
                }
            ],
        )

    source = ImportedApiSource(
        base_url="https://example.test/api",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        source_bucket="paper-attribution-artifacts-dev-247893369214",
        source_prefix="raw/zotero/group=6631056/",
    )
    papers = source.load(
        [
            PilotSelectionItem(
                paper_id="DOI:10.1000_oer-primary",
                selection_tier="primary_oer",
                selection_reasons=["OER protocol language in the full text"],
            )
        ]
    )

    assert len(papers) == 1
    serialized = papers[0].model_dump_json()
    assert "SECRET_ATTRIBUTION_LABEL" not in serialized
    assert "SECRET_INSTITUTION" not in serialized
    assert papers[0].chunks[0].text == METHOD_TEXT


def test_oer_pilot_selection_is_fixed_to_twenty_auditable_papers():
    from app.domain_adaptation.source import load_pilot_selection

    selection = load_pilot_selection(
        PROJECT_ROOT / "data/domain_adapters/oer_electrocatalysis_pilot.json"
    )

    assert selection.package_id == "oer-electrocatalysis"
    assert len(selection.papers) == 20
    assert len({item.paper_id for item in selection.papers}) == 20
    tiers = {item.selection_tier for item in selection.papers}
    assert tiers == {"primary_oer", "oer_case_study", "oer_review"}
    assert sum(item.task_split == "evaluation" for item in selection.papers) == 4


def test_s3_markdown_source_verifies_manifest_hash_and_restores_sections():
    from app.domain_adaptation.models import PilotSelectionItem
    from app.domain_adaptation.source import S3MarkdownSource

    markdown = (
        "# A reproducible OER catalyst protocol\n\n"
        "## Introduction\n\nOER is important for sustainable energy.\n\n"
        "## Experimental methods\n\n### Catalyst ink preparation\n\n"
        + METHOD_TEXT
        + "\n\n## References\n\nUniversity of Toronto bibliography.\n"
    ).encode("utf-8")
    markdown_key = (
        "raw/zotero/group=6631056/item=ITEM1/attachment=ATTACH1/"
        "version=4/document.md"
    )
    manifest_key = (
        "manifests/zotero/group=6631056/item=ITEM1/attachment=ATTACH1/"
        "version=4/document-manifest.json"
    )
    manifest = {
        "schema_version": 1,
        "kind": "zotero_markdown_document",
        "status": "ready",
        "paper_id": "DOI:10.1000_oer-primary",
        "created_at": "2026-08-01T00:00:00Z",
        "zotero": {"group_id": "6631056", "attachment_version": 4},
        "markdown": {
            "bucket": "paper-attribution-artifacts-dev-247893369214",
            "key": markdown_key,
            "sha256": hashlib.sha256(markdown).hexdigest(),
        },
    }

    class FakePaginator:
        def paginate(self, **kwargs):
            assert kwargs["Prefix"] == "manifests/zotero/group=6631056/"
            return [{"Contents": [{"Key": manifest_key}]}]

    class FakeS3Client:
        def get_paginator(self, operation):
            assert operation == "list_objects_v2"
            return FakePaginator()

        def get_object(self, *, Bucket, Key):
            assert Bucket == "paper-attribution-artifacts-dev-247893369214"
            if Key == manifest_key:
                return {"Body": io.BytesIO(json.dumps(manifest).encode())}
            assert Key == markdown_key
            return {"Body": io.BytesIO(markdown)}

    def metadata_handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Frozen benchmark metadata must bypass the API")

    source = S3MarkdownSource(
        s3_client=FakeS3Client(),
        metadata_client=httpx.Client(
            transport=httpx.MockTransport(metadata_handler)
        ),
        metadata_api_base="https://example.test/api",
        bucket="paper-attribution-artifacts-dev-247893369214",
        group_id="6631056",
        frozen_metadata={
            "DOI:10.1000_oer-primary": {
                "paper_id": "DOI:10.1000_oer-primary",
                "title": "A reproducible OER catalyst protocol",
                "year": 2025,
                "doi": "10.1000/oer-primary",
            }
        },
    )
    papers = source.load(
        [
            PilotSelectionItem(
                paper_id="DOI:10.1000_oer-primary",
                selection_tier="primary_oer",
                selection_reasons=["Full-text OER protocol evidence"],
            )
        ]
    )

    assert len(papers) == 1
    paper = papers[0]
    assert paper.source_markdown_key == markdown_key
    assert paper.source_markdown_sha256 == hashlib.sha256(markdown).hexdigest()
    assert any(chunk.section_type == "experimental" for chunk in paper.chunks)
    method_chunk = next(
        chunk for chunk in paper.chunks if chunk.section_type == "experimental"
    )
    assert method_chunk.text == METHOD_TEXT
    assert method_chunk.section_path == [
        "Experimental methods",
        "Catalyst ink preparation",
    ]
    assert markdown.decode()[
        method_chunk.document_char_start : method_chunk.document_char_end
    ] == METHOD_TEXT
    assert "classification" not in paper.model_dump_json()
