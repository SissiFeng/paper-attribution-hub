"""Compile experiment runs into immutable evidence and package release plans."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.domain_adaptation.models import DomainModel
from app.domain_adaptation.package_graph import (
    EvidencePackageDescriptor,
    PackageDependency,
    PackageDescriptor,
    PackageGraphReport,
    PackageReference,
    resolve_package_graph,
)


ExperimentStatus = Literal["completed", "failed", "invalid"]
EvidenceKind = Literal["measurement", "run_failure"]
ClaimUpdateKind = Literal["supports", "refutes", "refines", "invalidates"]


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _content_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class ExperimentalMeasurement(DomainModel):
    measurement_id: str = Field(min_length=1)
    metric: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    normalized_value: float | None = None
    normalized_unit: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_normalized_value(self) -> "ExperimentalMeasurement":
        if (self.normalized_value is None) != (self.normalized_unit is None):
            raise ValueError(
                "normalized_value and normalized_unit must be provided together"
            )
        if self.uncertainty is not None and self.normalized_value is None:
            raise ValueError("uncertainty requires a normalized value")
        return self


class ExperimentRun(DomainModel):
    schema_version: str = "domain-experiment-run-v0.1"
    run_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    protocol_package: PackageReference
    performed_at: datetime
    source_uri: str = Field(min_length=1)
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    conditions: dict[str, str] = Field(default_factory=dict)
    instrument_ids: list[str] = Field(default_factory=list)
    replicate_group_id: str | None = None
    status: ExperimentStatus
    measurements: list[ExperimentalMeasurement] = Field(default_factory=list)
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_run_state(self) -> "ExperimentRun":
        if self.performed_at.tzinfo is None or self.performed_at.utcoffset() is None:
            raise ValueError("performed_at must include a timezone")
        measurement_ids = [item.measurement_id for item in self.measurements]
        if len(measurement_ids) != len(set(measurement_ids)):
            raise ValueError("measurement IDs must be unique within a run")
        if self.status == "completed" and not self.measurements:
            raise ValueError("completed runs require at least one measurement")
        if self.status in {"failed", "invalid"} and not self.failure_reason:
            raise ValueError("failed or invalid runs require a failure reason")
        if self.status == "completed" and self.failure_reason is not None:
            raise ValueError("completed runs cannot include a failure reason")
        if any(not key.strip() or not value.strip() for key, value in self.conditions.items()):
            raise ValueError("condition names and values must be non-empty")
        return self


class ExperimentalEvidenceRecord(DomainModel):
    schema_version: str = "domain-experimental-evidence-v0.1"
    evidence_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    run_id: str
    domain: str
    protocol_id: str
    measurement_id: str | None = None
    metric: str | None = None
    raw_value: str | None = None
    normalized_value: float | None = None
    normalized_unit: str | None = None
    uncertainty: float | None = Field(default=None, ge=0)
    conditions: dict[str, str] = Field(default_factory=dict)
    status: ExperimentStatus
    failure_reason: str | None = None
    source_uri: str
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExperimentalEvidenceBundle(DomainModel):
    schema_version: str = "domain-experimental-evidence-bundle-v0.1"
    package: EvidencePackageDescriptor
    source_runs: list[ExperimentRun] = Field(min_length=1)
    records: list[ExperimentalEvidenceRecord] = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExperimentalEvidenceCompilationSpec(DomainModel):
    schema_version: str = "domain-experimental-evidence-input-v0.1"
    package_id: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    runs: list[ExperimentRun] = Field(min_length=1)


class ClaimUpdateCandidate(DomainModel):
    schema_version: str = "domain-claim-update-candidate-v0.1"
    update_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    target_claim_id: str = Field(min_length=1)
    update_kind: ClaimUpdateKind
    evidence_ids: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    proposer_id: str = Field(min_length=1)


class DomainFeedbackReleasePlan(DomainModel):
    schema_version: str = "domain-feedback-release-plan-v0.1"
    current_package: PackageDescriptor
    evidence_package: EvidencePackageDescriptor
    next_package: PackageDescriptor
    graph: PackageGraphReport


def _measurement_record(
    run: ExperimentRun,
    measurement: ExperimentalMeasurement,
) -> ExperimentalEvidenceRecord:
    payload = {
        "evidence_kind": "measurement",
        "run_id": run.run_id,
        "domain": run.domain,
        "protocol_id": run.protocol_id,
        "measurement": measurement.model_dump(mode="json"),
        "conditions": dict(sorted(run.conditions.items())),
        "status": run.status,
        "source_uri": run.source_uri,
        "source_artifact_sha256": run.source_artifact_sha256,
    }
    digest = _content_sha256(payload)
    return ExperimentalEvidenceRecord(
        evidence_id=f"exp-evidence-{digest[:24]}",
        evidence_kind="measurement",
        run_id=run.run_id,
        domain=run.domain,
        protocol_id=run.protocol_id,
        measurement_id=measurement.measurement_id,
        metric=measurement.metric,
        raw_value=measurement.raw_value,
        normalized_value=measurement.normalized_value,
        normalized_unit=measurement.normalized_unit,
        uncertainty=measurement.uncertainty,
        conditions=dict(sorted(run.conditions.items())),
        status=run.status,
        source_uri=run.source_uri,
        source_artifact_sha256=run.source_artifact_sha256,
        content_sha256=digest,
    )


def _failure_record(run: ExperimentRun) -> ExperimentalEvidenceRecord:
    payload = {
        "evidence_kind": "run_failure",
        "run_id": run.run_id,
        "domain": run.domain,
        "protocol_id": run.protocol_id,
        "conditions": dict(sorted(run.conditions.items())),
        "status": run.status,
        "failure_reason": run.failure_reason,
        "source_uri": run.source_uri,
        "source_artifact_sha256": run.source_artifact_sha256,
    }
    digest = _content_sha256(payload)
    return ExperimentalEvidenceRecord(
        evidence_id=f"exp-evidence-{digest[:24]}",
        evidence_kind="run_failure",
        run_id=run.run_id,
        domain=run.domain,
        protocol_id=run.protocol_id,
        conditions=dict(sorted(run.conditions.items())),
        status=run.status,
        failure_reason=run.failure_reason,
        source_uri=run.source_uri,
        source_artifact_sha256=run.source_artifact_sha256,
        content_sha256=digest,
    )


def compile_experimental_evidence(
    runs: list[ExperimentRun],
    *,
    package_id: str,
    package_version: str,
) -> ExperimentalEvidenceBundle:
    """Compile ordered, content-addressed evidence without interpreting results."""
    if not runs:
        raise ValueError("Experimental evidence compilation requires runs")
    run_ids = [run.run_id for run in runs]
    if len(run_ids) != len(set(run_ids)):
        raise ValueError("Experiment run IDs must be unique")
    domains = {run.domain for run in runs}
    if len(domains) != 1:
        raise ValueError("One evidence package cannot mix domains")

    ordered_runs = sorted(runs, key=lambda item: item.run_id)
    records: list[ExperimentalEvidenceRecord] = []
    for run in ordered_runs:
        records.extend(
            _measurement_record(run, measurement)
            for measurement in sorted(
                run.measurements, key=lambda item: item.measurement_id
            )
        )
        if run.status in {"failed", "invalid"}:
            records.append(_failure_record(run))
    records.sort(key=lambda item: item.evidence_id)

    domain = next(iter(domains))
    content_payload = {
        "package_id": package_id,
        "package_version": package_version,
        "domain": domain,
        "source_runs": [run.model_dump(mode="json") for run in ordered_runs],
        "records": [record.model_dump(mode="json") for record in records],
    }
    content_sha256 = _content_sha256(content_payload)
    package = EvidencePackageDescriptor(
        package_id=package_id,
        package_version=package_version,
        domain=domain,
        facets=["experimental-feedback"],
        content_sha256=content_sha256,
    )
    return ExperimentalEvidenceBundle(
        package=package,
        source_runs=ordered_runs,
        records=records,
        content_sha256=content_sha256,
    )


def validate_claim_updates(
    bundle: ExperimentalEvidenceBundle,
    candidates: list[ClaimUpdateCandidate],
) -> list[ClaimUpdateCandidate]:
    """Validate LLM-proposed updates without promoting or applying them."""
    update_ids = [item.update_id for item in candidates]
    if len(update_ids) != len(set(update_ids)):
        raise ValueError("Claim update IDs must be unique")
    known_evidence = {record.evidence_id for record in bundle.records}
    for candidate in candidates:
        if candidate.domain != bundle.package.domain:
            raise ValueError("Claim update domain does not match evidence package")
        missing = sorted(set(candidate.evidence_ids) - known_evidence)
        if missing:
            raise ValueError(
                f"Claim update references unknown evidence: {', '.join(missing)}"
            )
    return sorted(candidates, key=lambda item: item.update_id)


def plan_domain_feedback_release(
    *,
    current_package: PackageDescriptor,
    next_package_version: str,
    evidence_bundle: ExperimentalEvidenceBundle,
    dependency_catalog: list[PackageDescriptor],
) -> DomainFeedbackReleasePlan:
    """Plan a new domain version without mutating its current release."""
    if current_package.package_kind != "domain":
        raise ValueError("Experimental feedback can update only a domain package")
    if current_package.domain != evidence_bundle.package.domain:
        raise ValueError("Domain and experimental evidence package do not match")
    if next_package_version == current_package.package_version:
        raise ValueError("A feedback release requires a new package version")

    next_package = PackageDescriptor(
        package_id=current_package.package_id,
        package_version=next_package_version,
        package_kind="domain",
        domain=current_package.domain,
        facets=current_package.facets,
        dependencies=[
            PackageDependency(
                package_id=current_package.package_id,
                package_version=current_package.package_version,
                dependency_kind="parent_domain",
                required_layers=["corpus", "kb", "rag", "tasks"],
            ),
            PackageDependency(
                package_id=evidence_bundle.package.package_id,
                package_version=evidence_bundle.package.package_version,
                dependency_kind="evidence",
                required_layers=["experimental_evidence"],
                required_content_sha256=evidence_bundle.content_sha256,
            ),
        ],
    )
    descriptors = [
        *dependency_catalog,
        current_package,
        evidence_bundle.package,
        next_package,
    ]
    graph = resolve_package_graph(
        descriptors,
        root=PackageReference(
            package_id=next_package.package_id,
            package_version=next_package.package_version,
        ),
    )
    return DomainFeedbackReleasePlan(
        current_package=current_package,
        evidence_package=evidence_bundle.package,
        next_package=next_package,
        graph=graph,
    )
