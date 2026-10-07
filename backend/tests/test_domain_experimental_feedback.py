from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def _package_ref(package_id: str, version: str = "1.0.0"):
    from app.domain_adaptation.package_graph import PackageReference

    return PackageReference(package_id=package_id, package_version=version)


def _completed_run(run_id: str = "run-1"):
    from app.domain_adaptation.experimental_feedback import (
        ExperimentalMeasurement,
        ExperimentRun,
    )

    return ExperimentRun(
        run_id=run_id,
        domain="oer-electrocatalysis",
        protocol_id="protocol-1",
        protocol_package=_package_ref("oer-electrocatalysis", "0.3.3"),
        performed_at=datetime(2026, 9, 3, 14, 0, tzinfo=timezone.utc),
        source_uri=f"s3://experimental-results/{run_id}.json",
        source_artifact_sha256="a" * 64,
        conditions={"electrolyte": "1 M KOH", "temperature": "25 degC"},
        instrument_ids=["potentiostat-1"],
        replicate_group_id="replicate-group-1",
        status="completed",
        measurements=[
            ExperimentalMeasurement(
                measurement_id="measurement-1",
                metric="overpotential_at_10_mA_cm2",
                raw_value="287 mV",
                normalized_value=0.287,
                normalized_unit="V",
                uncertainty=0.004,
            )
        ],
    )


def test_experiment_run_requires_content_addressed_provenance():
    run = _completed_run()
    payload = run.model_dump(mode="json")
    payload["source_artifact_sha256"] = "not-a-sha"

    with pytest.raises(ValidationError, match="source_artifact_sha256"):
        type(run).model_validate(payload)


def test_compiler_is_deterministic_and_preserves_failed_runs():
    from app.domain_adaptation.experimental_feedback import (
        ExperimentRun,
        compile_experimental_evidence,
    )

    completed = _completed_run("run-completed")
    failed = ExperimentRun(
        run_id="run-failed",
        domain="oer-electrocatalysis",
        protocol_id="protocol-1",
        protocol_package=_package_ref("oer-electrocatalysis", "0.3.3"),
        performed_at=datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc),
        source_uri="s3://experimental-results/run-failed.json",
        source_artifact_sha256="b" * 64,
        status="failed",
        failure_reason="Reference electrode drift exceeded the run limit.",
    )

    first = compile_experimental_evidence(
        [failed, completed],
        package_id="oer-experimental-feedback",
        package_version="2026.09.03",
    )
    second = compile_experimental_evidence(
        [completed, failed],
        package_id="oer-experimental-feedback",
        package_version="2026.09.03",
    )

    assert first == second
    assert first.package.package_kind == "evidence"
    assert len(first.records) == 2
    assert {record.evidence_kind for record in first.records} == {
        "measurement",
        "run_failure",
    }
    assert len(first.content_sha256) == 64


def test_claim_updates_must_resolve_to_compiled_evidence():
    from app.domain_adaptation.experimental_feedback import (
        ClaimUpdateCandidate,
        compile_experimental_evidence,
        validate_claim_updates,
    )

    bundle = compile_experimental_evidence(
        [_completed_run()],
        package_id="oer-experimental-feedback",
        package_version="2026.09.03",
    )
    candidate = ClaimUpdateCandidate(
        update_id="update-1",
        domain="oer-electrocatalysis",
        target_claim_id="claim-1",
        update_kind="refines",
        evidence_ids=[bundle.records[0].evidence_id],
        summary="The result is conditional on 1 M KOH at 25 degC.",
        proposer_id="teacher:gpt",
    )

    assert validate_claim_updates(bundle, [candidate]) == [candidate]
    bad = candidate.model_copy(update={"evidence_ids": ["missing-evidence"]})
    with pytest.raises(ValueError, match="unknown evidence"):
        validate_claim_updates(bundle, [bad])


def test_feedback_release_plan_links_previous_domain_and_evidence_packages():
    from app.domain_adaptation.experimental_feedback import (
        compile_experimental_evidence,
        plan_domain_feedback_release,
    )
    from app.domain_adaptation.package_graph import (
        PackageDependency,
        PackageDescriptor,
        PackageGraphError,
        PackageReference,
        resolve_package_graph,
    )

    core = PackageDescriptor(
        package_id="scientific-core",
        package_version="1.0.0",
        package_kind="scientific_core",
        domain="general scientific reasoning",
    )
    current = PackageDescriptor(
        package_id="oer-electrocatalysis",
        package_version="0.3.3",
        package_kind="domain",
        domain="oer-electrocatalysis",
        dependencies=[
            PackageDependency(
                package_id="scientific-core",
                package_version="1.0.0",
                dependency_kind="scientific_core",
            )
        ],
    )
    bundle = compile_experimental_evidence(
        [_completed_run()],
        package_id="oer-experimental-feedback",
        package_version="2026.09.03",
    )

    plan = plan_domain_feedback_release(
        current_package=current,
        next_package_version="0.4.0",
        evidence_bundle=bundle,
        dependency_catalog=[core],
    )

    assert plan.next_package.coordinate == "oer-electrocatalysis@0.4.0"
    assert plan.graph.resolution_order[-1] == "oer-electrocatalysis@0.4.0"
    assert set(plan.graph.edges[plan.next_package.coordinate]) == {
        "oer-electrocatalysis@0.3.3",
        "oer-experimental-feedback@2026.09.03",
    }
    evidence_dependency = next(
        dependency
        for dependency in plan.next_package.dependencies
        if dependency.dependency_kind == "evidence"
    )
    assert evidence_dependency.required_content_sha256 == bundle.content_sha256

    tampered_evidence = bundle.package.model_copy(
        update={"content_sha256": "f" * 64}
    )
    with pytest.raises(PackageGraphError, match="digest mismatch"):
        resolve_package_graph(
            [core, current, tampered_evidence, plan.next_package],
            root=PackageReference(
                package_id=plan.next_package.package_id,
                package_version=plan.next_package.package_version,
            ),
        )


def test_experimental_feedback_file_compiler_reports_unchanged_rebuild(tmp_path):
    import json

    from app.scripts.compile_experimental_feedback import (
        compile_experimental_feedback_file,
    )

    input_path = tmp_path / "runs.json"
    output_path = tmp_path / "evidence.json"
    input_path.write_text(
        json.dumps(
            {
                "package_id": "oer-experimental-feedback",
                "package_version": "2026.09.03",
                "runs": [_completed_run().model_dump(mode="json")],
            }
        ),
        encoding="utf-8",
    )

    first = compile_experimental_feedback_file(input_path, output_path)
    second = compile_experimental_feedback_file(input_path, output_path)

    assert first["changed"] is True
    assert second["changed"] is False
    assert first["content_sha256"] == second["content_sha256"]
