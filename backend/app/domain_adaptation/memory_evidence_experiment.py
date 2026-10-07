"""Pre-registered design contracts for memory-versus-evidence experiments."""

from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from app.domain_adaptation.models import DomainModel


CutoffEvidenceStatus = Literal[
    "provider_documented",
    "provider_reported",
    "unknown",
]
PaperReportType = Literal[
    "primary_experiment",
    "review",
    "case_study",
    "perspective",
    "unknown",
]
TemporalStratum = Literal[
    "pre_cutoff",
    "post_cutoff",
    "cutoff_boundary",
    "unknown_cutoff",
    "not_applicable",
]
CitationStratum = Literal["low", "middle", "high"]
PublicationDatePrecision = Literal["day", "month", "year"]


class ModelCutoffEvidence(DomainModel):
    """A model knowledge cutoff with an auditable provider source."""

    schema_version: str = "memory-evidence-model-cutoff-v0.1"
    model_alias: str = Field(min_length=1)
    model_family: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    knowledge_cutoff_date: date | None = None
    evidence_status: CutoffEvidenceStatus
    source_url: HttpUrl | None = None
    source_retrieved_date: date | None = None

    @model_validator(mode="after")
    def validate_cutoff_evidence(self) -> "ModelCutoffEvidence":
        if self.evidence_status == "unknown":
            if self.knowledge_cutoff_date is not None:
                raise ValueError("Unknown cutoff evidence cannot declare a date")
            return self
        if self.knowledge_cutoff_date is None:
            raise ValueError("Documented cutoff evidence requires a cutoff date")
        if self.source_url is None:
            raise ValueError("Documented cutoff evidence requires a source URL")
        if self.source_retrieved_date is None:
            raise ValueError("Documented cutoff evidence requires a retrieval date")
        return self


class ExperimentAPaper(DomainModel):
    """One immutable paper candidate for the temporal exposure design."""

    schema_version: str = "memory-evidence-paper-v0.1"
    paper_id: str = Field(min_length=1)
    doi: str = Field(min_length=1)
    publication_date: date
    publication_date_precision: PublicationDatePrecision = "day"
    publication_date_source: str = Field(default="declared_metadata", min_length=1)
    report_type: PaperReportType
    citation_count: int = Field(ge=0)
    citation_source: str = Field(min_length=1)
    citation_snapshot_date: date
    source_markdown_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExperimentADesignPolicy(DomainModel):
    schema_version: str = "memory-evidence-design-policy-v0.1"
    min_primary_papers: int = Field(default=150, ge=2)
    max_primary_papers: int = Field(default=200, ge=2)
    min_pre_cutoff_papers_per_model: int = Field(default=50, ge=1)
    min_post_cutoff_papers_per_model: int = Field(default=50, ge=1)
    cutoff_buffer_days: int = Field(default=180, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "ExperimentADesignPolicy":
        if self.max_primary_papers < self.min_primary_papers:
            raise ValueError("Maximum paper count must not be below the minimum")
        return self


class ExperimentADesignInput(DomainModel):
    schema_version: str = "memory-evidence-design-input-v0.1"
    experiment_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    policy: ExperimentADesignPolicy = Field(default_factory=ExperimentADesignPolicy)
    model_cutoffs: list[ModelCutoffEvidence] = Field(min_length=1)
    papers: list[ExperimentAPaper] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_coordinates(self) -> "ExperimentADesignInput":
        aliases = [item.model_alias for item in self.model_cutoffs]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Model cutoff registry contains duplicate aliases")
        paper_ids = [item.paper_id for item in self.papers]
        if len(paper_ids) != len(set(paper_ids)):
            raise ValueError("Experiment A contains duplicate paper IDs")
        dois = [item.doi.casefold() for item in self.papers]
        if len(dois) != len(set(dois)):
            raise ValueError("Experiment A contains duplicate DOIs")
        return self


class ExperimentAStratumAssignment(DomainModel):
    schema_version: str = "memory-evidence-stratum-assignment-v0.1"
    experiment_id: str
    domain: str
    model_alias: str
    model_family: str
    model_id: str
    paper_id: str
    doi: str
    publication_date: date
    knowledge_cutoff_date: date | None
    temporal_stratum: TemporalStratum
    citation_count: int = Field(ge=0)
    citation_stratum: CitationStratum | None = None
    eligible: bool
    exclusion_reasons: list[str] = Field(default_factory=list)


class ExperimentAAnalysisPlan(DomainModel):
    schema_version: str = "memory-evidence-analysis-plan-v0.1"
    primary_outcome: str = "numeric_substitution_following"
    negative_control_outcome: str = "evidence_deletion_following"
    eligible_claim_rule: str = (
        "evidence_valid=true AND source_value_occurrence=exact_unique AND "
        "numeric_replacement_exists AND steps fields are restricted to param:*"
    )
    primary_model: str = (
        "mixed-effects logistic regression: substitution_following ~ "
        "pre_cutoff + log1p(citation_count) + pre_cutoff:log1p(citation_count) "
        "+ field_type + model_family; random intercepts for paper and claim"
    )
    confirmatory_contrasts: list[str] = Field(
        default_factory=lambda: [
            "adjusted pre-cutoff versus post-cutoff substitution-following",
            "pre-cutoff by citation-count interaction",
            "deletion-following pre-cutoff versus post-cutoff negative control",
        ]
    )
    required_sensitivity_analyses: list[str] = Field(
        default_factory=lambda: [
            "repeat with 90-day and 365-day cutoff buffers",
            "repeat after excluding model/version cutoff sources marked provider_reported",
            "cluster-robust confidence intervals by paper",
            "field-family and model-family leave-one-group-out analyses",
        ]
    )
    claims_boundary: str = (
        "Publication before a reported knowledge cutoff is a training-exposure "
        "proxy, not proof that a paper was in training data. Temporal and citation "
        "effects are quasi-experimental associations unless exposure is independently verified."
    )


class ExperimentADesignReport(DomainModel):
    schema_version: str = "memory-evidence-design-report-v0.1"
    experiment_id: str
    domain: str
    ready: bool
    failed_gates: list[str]
    supplied_paper_count: int = Field(ge=0)
    primary_paper_count: int = Field(ge=0)
    model_count: int = Field(ge=0)
    assignment_count: int = Field(ge=0)
    eligible_assignment_count: int = Field(ge=0)
    counts_by_model_and_temporal_stratum: dict[str, dict[str, int]]
    counts_by_model_and_citation_stratum: dict[str, dict[str, int]]
    claims_boundary: str = (
        "Design readiness checks cohort composition and auditable cutoff metadata. "
        "It does not report a memory effect or establish training-data membership."
    )


class ExperimentADesign(DomainModel):
    schema_version: str = "memory-evidence-design-v0.1"
    assignments: list[ExperimentAStratumAssignment]
    analysis_plan: ExperimentAAnalysisPlan
    report: ExperimentADesignReport


def _temporal_assignment(
    paper: ExperimentAPaper,
    cutoff: ModelCutoffEvidence,
    *,
    buffer_days: int,
) -> tuple[TemporalStratum, list[str]]:
    if paper.report_type != "primary_experiment":
        return "not_applicable", ["not_primary_experiment"]
    if cutoff.knowledge_cutoff_date is None or cutoff.evidence_status == "unknown":
        return "unknown_cutoff", ["unknown_model_cutoff"]
    earliest = paper.publication_date
    if paper.publication_date_precision == "year":
        earliest = date(paper.publication_date.year, 1, 1)
        latest = date(paper.publication_date.year, 12, 31)
    elif paper.publication_date_precision == "month":
        earliest = date(paper.publication_date.year, paper.publication_date.month, 1)
        latest = date(
            paper.publication_date.year,
            paper.publication_date.month,
            calendar.monthrange(
                paper.publication_date.year, paper.publication_date.month
            )[1],
        )
    else:
        latest = paper.publication_date
    buffer = timedelta(days=buffer_days)
    if latest < cutoff.knowledge_cutoff_date - buffer:
        return "pre_cutoff", []
    if earliest > cutoff.knowledge_cutoff_date + buffer:
        return "post_cutoff", []
    return "cutoff_boundary", ["cutoff_boundary_buffer"]


def _citation_strata(
    assignments: list[ExperimentAStratumAssignment],
) -> list[ExperimentAStratumAssignment]:
    by_model: dict[str, list[ExperimentAStratumAssignment]] = defaultdict(list)
    for assignment in assignments:
        if assignment.eligible:
            by_model[assignment.model_alias].append(assignment)
    labels_by_key: dict[tuple[str, str], CitationStratum] = {}
    for model_alias, items in by_model.items():
        ordered = sorted(items, key=lambda item: (item.citation_count, item.paper_id))
        for index, item in enumerate(ordered):
            if len(ordered) == 1:
                label: CitationStratum = "middle"
            else:
                quantile = index / (len(ordered) - 1)
                label = (
                    "low"
                    if quantile <= 1 / 3
                    else "high"
                    if quantile >= 2 / 3
                    else "middle"
                )
            labels_by_key[(model_alias, item.paper_id)] = label
    return [
        item.model_copy(
            update={
                "citation_stratum": labels_by_key.get(
                    (item.model_alias, item.paper_id)
                )
            }
        )
        for item in assignments
    ]


def build_experiment_a_design(spec: ExperimentADesignInput) -> ExperimentADesign:
    """Build a deterministic, fail-closed temporal/citation stratification."""
    assignments: list[ExperimentAStratumAssignment] = []
    for cutoff in sorted(spec.model_cutoffs, key=lambda item: item.model_alias):
        for paper in sorted(spec.papers, key=lambda item: item.paper_id):
            temporal, reasons = _temporal_assignment(
                paper,
                cutoff,
                buffer_days=spec.policy.cutoff_buffer_days,
            )
            assignments.append(
                ExperimentAStratumAssignment(
                    experiment_id=spec.experiment_id,
                    domain=spec.domain,
                    model_alias=cutoff.model_alias,
                    model_family=cutoff.model_family,
                    model_id=cutoff.model_id,
                    paper_id=paper.paper_id,
                    doi=paper.doi,
                    publication_date=paper.publication_date,
                    knowledge_cutoff_date=cutoff.knowledge_cutoff_date,
                    temporal_stratum=temporal,
                    citation_count=paper.citation_count,
                    eligible=not reasons,
                    exclusion_reasons=reasons,
                )
            )
    assignments = _citation_strata(assignments)

    temporal_counts: dict[str, Counter[str]] = defaultdict(Counter)
    citation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for item in assignments:
        temporal_counts[item.model_alias][item.temporal_stratum] += 1
        if item.citation_stratum is not None:
            citation_counts[item.model_alias][item.citation_stratum] += 1

    primary_paper_count = sum(
        item.report_type == "primary_experiment" for item in spec.papers
    )
    failed_gates: list[str] = []
    if not (
        spec.policy.min_primary_papers
        <= primary_paper_count
        <= spec.policy.max_primary_papers
    ):
        failed_gates.append("primary_paper_count")
    documented_cutoffs = [
        item
        for item in spec.model_cutoffs
        if item.evidence_status != "unknown"
        and item.knowledge_cutoff_date is not None
    ]
    if len(documented_cutoffs) != len(spec.model_cutoffs):
        failed_gates.append("documented_model_cutoffs")
    else:
        for cutoff in documented_cutoffs:
            counts = temporal_counts[cutoff.model_alias]
            if counts["pre_cutoff"] < spec.policy.min_pre_cutoff_papers_per_model:
                failed_gates.append(f"pre_cutoff_papers:{cutoff.model_alias}")
            if counts["post_cutoff"] < spec.policy.min_post_cutoff_papers_per_model:
                failed_gates.append(f"post_cutoff_papers:{cutoff.model_alias}")

    report = ExperimentADesignReport(
        experiment_id=spec.experiment_id,
        domain=spec.domain,
        ready=not failed_gates,
        failed_gates=failed_gates,
        supplied_paper_count=len(spec.papers),
        primary_paper_count=primary_paper_count,
        model_count=len(spec.model_cutoffs),
        assignment_count=len(assignments),
        eligible_assignment_count=sum(item.eligible for item in assignments),
        counts_by_model_and_temporal_stratum={
            alias: dict(sorted(counts.items()))
            for alias, counts in sorted(temporal_counts.items())
        },
        counts_by_model_and_citation_stratum={
            alias: dict(sorted(counts.items()))
            for alias, counts in sorted(citation_counts.items())
        },
    )
    return ExperimentADesign(
        assignments=assignments,
        analysis_plan=ExperimentAAnalysisPlan(),
        report=report,
    )
