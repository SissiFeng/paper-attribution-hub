from __future__ import annotations

import json

import pytest
from pydantic import ValidationError


def _cutoff(*, alias: str = "opus", cutoff: str | None = "2024-01-01"):
    from app.domain_adaptation.memory_evidence_experiment import ModelCutoffEvidence

    if cutoff is None:
        return ModelCutoffEvidence(
            model_alias=alias,
            model_family="anthropic",
            model_id=f"provider.{alias}",
            evidence_status="unknown",
        )
    return ModelCutoffEvidence(
        model_alias=alias,
        model_family="anthropic",
        model_id=f"provider.{alias}",
        knowledge_cutoff_date=cutoff,
        evidence_status="provider_documented",
        source_url="https://provider.example/model-card",
        source_retrieved_date="2026-09-01",
    )


def _paper(
    paper_id: str,
    publication_date: str,
    citations: int,
    *,
    report_type: str = "primary_experiment",
):
    from app.domain_adaptation.memory_evidence_experiment import ExperimentAPaper

    return ExperimentAPaper(
        paper_id=paper_id,
        doi=f"10.1000/{paper_id}",
        publication_date=publication_date,
        report_type=report_type,
        citation_count=citations,
        citation_source="openalex",
        citation_snapshot_date="2026-09-01",
        source_markdown_sha256="a" * 64,
    )


def _policy():
    from app.domain_adaptation.memory_evidence_experiment import ExperimentADesignPolicy

    return ExperimentADesignPolicy(
        min_primary_papers=2,
        max_primary_papers=4,
        min_pre_cutoff_papers_per_model=1,
        min_post_cutoff_papers_per_model=1,
        cutoff_buffer_days=90,
    )


def test_experiment_a_stratifies_primary_papers_and_excludes_boundary_cases():
    from app.domain_adaptation.memory_evidence_experiment import (
        ExperimentADesignInput,
        build_experiment_a_design,
    )

    design = build_experiment_a_design(
        ExperimentADesignInput(
            experiment_id="oer-memory-evidence-v0.1",
            domain="oer-electrocatalysis",
            policy=_policy(),
            model_cutoffs=[_cutoff()],
            papers=[
                _paper("pre", "2023-01-01", 100),
                _paper("post", "2025-01-01", 2),
                _paper("boundary", "2024-01-15", 20),
                _paper(
                    "review",
                    "2025-03-01",
                    50,
                    report_type="review",
                ),
            ],
        )
    )

    assignments = {item.paper_id: item for item in design.assignments}
    assert assignments["pre"].temporal_stratum == "pre_cutoff"
    assert assignments["pre"].eligible is True
    assert assignments["post"].temporal_stratum == "post_cutoff"
    assert assignments["post"].eligible is True
    assert assignments["boundary"].temporal_stratum == "cutoff_boundary"
    assert assignments["boundary"].exclusion_reasons == [
        "cutoff_boundary_buffer"
    ]
    assert assignments["review"].temporal_stratum == "not_applicable"
    assert assignments["review"].exclusion_reasons == ["not_primary_experiment"]
    assert {assignments["pre"].citation_stratum, assignments["post"].citation_stratum} == {
        "low",
        "high",
    }
    assert design.report.ready is True
    assert design.report.failed_gates == []
    assert design.analysis_plan.primary_outcome == "numeric_substitution_following"
    assert "proxy" in design.analysis_plan.claims_boundary


def test_experiment_a_fails_closed_when_cutoff_is_not_documented():
    from app.domain_adaptation.memory_evidence_experiment import (
        ExperimentADesignInput,
        build_experiment_a_design,
    )

    design = build_experiment_a_design(
        ExperimentADesignInput(
            experiment_id="oer-memory-evidence-unknown-cutoff",
            domain="oer-electrocatalysis",
            policy=_policy(),
            model_cutoffs=[_cutoff(cutoff=None)],
            papers=[
                _paper("paper-a", "2023-01-01", 10),
                _paper("paper-b", "2025-01-01", 1),
            ],
        )
    )

    assert design.report.ready is False
    assert design.report.failed_gates == ["documented_model_cutoffs"]
    assert {item.temporal_stratum for item in design.assignments} == {
        "unknown_cutoff"
    }
    assert all(not item.eligible for item in design.assignments)


def test_cutoff_evidence_requires_a_source_for_a_declared_date():
    from app.domain_adaptation.memory_evidence_experiment import ModelCutoffEvidence

    with pytest.raises(ValidationError, match="source URL"):
        ModelCutoffEvidence(
            model_alias="opus",
            model_family="anthropic",
            model_id="provider.opus",
            knowledge_cutoff_date="2024-01-01",
            evidence_status="provider_documented",
            source_retrieved_date="2026-09-01",
        )


def test_experiment_a_artifact_builder_is_deterministic_and_non_overwriting(
    tmp_path,
):
    from app.scripts.build_memory_evidence_experiment import (
        build_memory_evidence_experiment,
    )

    payload = {
        "experiment_id": "oer-memory-evidence-v0.1",
        "domain": "oer-electrocatalysis",
        "policy": _policy().model_dump(mode="json"),
        "model_cutoffs": [_cutoff().model_dump(mode="json")],
        "papers": [
            _paper("pre", "2023-01-01", 100).model_dump(mode="json"),
            _paper("post", "2025-01-01", 2).model_dump(mode="json"),
        ],
    }
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(payload))
    output = tmp_path / "experiment-a"

    result = build_memory_evidence_experiment(input_path, output)

    assert result["ready"] is True
    assert result["assignment_count"] == 2
    assert (output / "design/assignments.jsonl").exists()
    assert (output / "design/analysis_plan.json").exists()
    assert (output / "reports/design_report.json").exists()
    assert (output / "manifest.json").exists()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        build_memory_evidence_experiment(input_path, output)


def test_prepare_experiment_a_input_joins_package_selection_to_metadata(tmp_path):
    import sqlite3

    from app.scripts.prepare_memory_evidence_experiment import (
        prepare_memory_evidence_experiment,
    )

    database = tmp_path / "papers.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """CREATE TABLE papers (
        id TEXT PRIMARY KEY, doi TEXT, raw_metadata TEXT, citation_count INTEGER,
        citation_count_source TEXT, citation_count_updated_at TEXT)"""
    )
    raw_metadata = {
        "tier1_metadata_agent": {
            "openalex": {"publication_date": "2023-07-24"}
        }
    }
    connection.execute(
        "INSERT INTO papers VALUES (?, ?, ?, ?, ?, ?)",
        (
            "paper-primary",
            "10.1000/primary",
            json.dumps(raw_metadata),
            42,
            "openalex",
            "2026-08-12 15:43:45",
        ),
    )
    connection.commit()
    connection.close()
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "papers": [
                    {
                        "paper_id": "paper-primary",
                        "doi": "10.1000/primary",
                        "selection_tier": "primary_oer",
                        "source_markdown_sha256": "b" * 64,
                    }
                ]
            }
        )
    )
    cutoffs = tmp_path / "cutoffs.json"
    cutoffs.write_text(
        json.dumps({"model_cutoffs": [_cutoff(cutoff=None).model_dump(mode="json")]})
    )
    output = tmp_path / "experiment_input.json"

    result = prepare_memory_evidence_experiment(
        experiment_id="oer-memory-evidence-v0.1",
        domain="oer-electrocatalysis",
        selection_manifest_path=selection,
        database_path=database,
        cutoff_registry_path=cutoffs,
        output_path=output,
        policy=_policy(),
    )

    assert result["paper_count"] == 1
    payload = json.loads(output.read_text())
    assert payload["papers"][0]["publication_date"] == "2023-07-24"
    assert payload["papers"][0]["publication_date_precision"] == "day"
    assert payload["papers"][0]["citation_count"] == 42
    assert payload["papers"][0]["report_type"] == "primary_experiment"
